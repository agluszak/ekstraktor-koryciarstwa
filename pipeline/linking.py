"""Entity linking orchestration.

``InMemoryEntityLinker``
    In-process linker that resolves document entities to a shared in-memory
    knowledge base.  Linking is cluster-aware: when the document already has
    entity clusters (built by ``PolishEntityClusterer``), the linker works at
    the cluster level and writes the resolved ``registry_id`` back to every
    constituent entity.  When no clusters are present it falls back to the
    per-entity path.

``PersistentEntityLinker``
    Drop-in replacement for ``InMemoryEntityLinker`` that backs the knowledge
    base with a SQLite store (see ``linking_sqlite.py``).  The in-memory cache
    is still kept for the duration of a process; new records are flushed back
    to SQLite after each document.
"""

from __future__ import annotations

from pipeline.base import EntityLinker
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityID, EntityType
from pipeline.linking_candidates import AliasCandidateGenerator
from pipeline.linking_dedup import RegistryDeduplicator
from pipeline.linking_disambiguator import RuleBasedEntityDisambiguator
from pipeline.linking_kb import (
    InMemoryKnowledgeBase,
)
from pipeline.models import ArticleDocument, Entity, EntityCluster, EntityFingerprint
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime
from pipeline.utils import stable_id


class InMemoryEntityLinker(EntityLinker):
    """Thin orchestrator composed of KB, candidate generator, disambiguator, deduplicator."""

    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        _runtime = runtime or PipelineRuntime(config)
        self._kb = InMemoryKnowledgeBase(config, _runtime)
        self._candidates = AliasCandidateGenerator(self._kb)
        self._disambiguator = RuleBasedEntityDisambiguator(config, _runtime)
        self._dedup = RegistryDeduplicator()
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self.organization_naming = self.canonicalizer.organization_naming

    def name(self) -> str:
        return "in_memory_entity_linker"

    # ------------------------------------------------------------------
    # Backward-compat delegates (used by tests that inspect internals)
    # ------------------------------------------------------------------

    def _upsert_registry(
        self,
        registry_id: str,
        entity_type: str,
        canonical_name: str,
        fingerprint: EntityFingerprint,
        embedding: list[float],
    ) -> None:
        self._kb._upsert_registry(registry_id, entity_type, canonical_name, fingerprint, embedding)

    @property
    def _knowledge_seeded(self) -> bool:
        return self._kb._knowledge_seeded

    @_knowledge_seeded.setter
    def _knowledge_seeded(self, value: bool) -> None:
        self._kb._knowledge_seeded = value

    # ------------------------------------------------------------------
    # DocumentStage
    # ------------------------------------------------------------------

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not self._kb._knowledge_seeded and (document.entities or document.clusters):
            self._kb.seed()
            self._kb._knowledge_seeded = True

        if document.clusters:
            self._run_cluster_based(document)
        else:
            self._run_entity_based(document)

        # Deduplicate entities that resolved to the same registry_id
        document.entities, id_remap = self._dedup.deduplicate_by_registry(document.entities)
        document.entities, exact_name_remap = self._dedup.deduplicate_exact_names(document.entities)
        id_remap.update(exact_name_remap)

        # Remap entity references in extracted facts / mentions
        if id_remap:
            for fact in document.facts:
                fact.subject_entity_id = id_remap.get(
                    fact.subject_entity_id,
                    fact.subject_entity_id,
                )
                if fact.object_entity_id:
                    fact.object_entity_id = id_remap.get(
                        fact.object_entity_id,
                        fact.object_entity_id,
                    )
            for mention in document.mentions:
                if mention.entity_id:
                    mention.entity_id = id_remap.get(mention.entity_id, mention.entity_id)

        return self.canonicalizer.run(document)

    # ------------------------------------------------------------------
    # Cluster-based linking (Step 5)
    # ------------------------------------------------------------------

    def _run_cluster_based(self, document: ArticleDocument) -> None:
        """Link each cluster as a unit, writing registry_id to all its entities."""
        entity_by_id: dict[EntityID, Entity] = {e.entity_id: e for e in document.entities}

        for cluster in document.clusters:
            cluster_entity_ids: set[EntityID] = {
                m.entity_id for m in cluster.mentions if m.entity_id is not None
            }
            cluster_entities = [
                entity_by_id[eid] for eid in cluster_entity_ids if eid in entity_by_id
            ]

            proxy_entities = [
                e for e in cluster_entities if e.is_proxy_person or e.is_honorific_person_ref
            ]
            real_entities = [
                e
                for e in cluster_entities
                if not e.is_proxy_person and not e.is_honorific_person_ref
            ]

            for entity in proxy_entities:
                entity.registry_id = stable_id(
                    "document_local_ref", document.document_id, entity.entity_id
                )

            if not real_entities:
                continue

            registry_id = self._match_or_create_from_cluster(cluster)

            entry = self._kb.get_entry(registry_id)
            for entity in real_entities:
                entity.registry_id = registry_id
                if entry is not None:
                    preferred = self._preferred_registry_canonical(entity, entry.canonical_name)
                    entity.canonical_name = preferred
                    entity.normalized_name = preferred
                    if preferred != entry.canonical_name:
                        entry.canonical_name = preferred

        # Handle entities not referenced by any cluster (defensive)
        clustered_entity_ids: set[EntityID] = {
            m.entity_id
            for cluster in document.clusters
            for m in cluster.mentions
            if m.entity_id is not None
        }
        for entity in document.entities:
            if entity.entity_id not in clustered_entity_ids:
                if entity.is_proxy_person or entity.is_honorific_person_ref:
                    entity.registry_id = stable_id(
                        "document_local_ref", document.document_id, entity.entity_id
                    )
                else:
                    fingerprint = self._candidates.fingerprint_from_entity(entity)
                    entity.registry_id = self._match_or_create(entity, fingerprint)

    # ------------------------------------------------------------------
    # Per-entity fallback linking (used when no clusters present)
    # ------------------------------------------------------------------

    def _run_entity_based(self, document: ArticleDocument) -> None:
        for entity in document.entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                entity.registry_id = stable_id(
                    "document_local_ref", document.document_id, entity.entity_id
                )
                continue
            fingerprint = self._candidates.fingerprint_from_entity(entity)
            registry_id = self._match_or_create(entity, fingerprint)
            entity.registry_id = registry_id

            entry = self._kb.get_entry(registry_id)
            if entry is not None:
                preferred = self._preferred_registry_canonical(entity, entry.canonical_name)
                entity.canonical_name = preferred
                entity.normalized_name = preferred
                if preferred != entry.canonical_name:
                    entry.canonical_name = preferred

    # ------------------------------------------------------------------
    # Match-or-create: entity path
    # ------------------------------------------------------------------

    def _match_or_create(self, entity: Entity, fingerprint: EntityFingerprint) -> str:
        search_names = self._candidates.alias_search_names_from_entity(entity)
        matches = self._kb.alias_matches(search_names, entity.entity_type.value)
        if matches:
            match_id = matches[0]
            self._kb.upsert_aliases_from_entity(match_id, entity)
            return match_id

        entity_embedding = self._disambiguator.encode_embedding(
            self._disambiguator.embedding_text_from_entity(entity)
        )

        tokens = entity.normalized_name.split()
        search_term = (
            tokens[-1].lower() if entity.entity_type == EntityType.PERSON and tokens else None
        )

        candidates = self._kb.type_candidates(entity.entity_type.value, search_term)
        for registry_id, entry in candidates:
            stored_fp: EntityFingerprint = {
                "normalized_name": entry.fingerprint.get("normalized_name", ""),
                "name_tokens": entry.fingerprint.get("name_tokens", []),
                "lemmas": entry.fingerprint.get("lemmas", []),
            }
            score = self._disambiguator._match_score(
                entity.entity_type,
                fingerprint,
                stored_fp,
                entity_embedding,
                entry.embedding,
            )
            if score >= self.config.registry.similarity_threshold:
                self._kb.upsert_aliases_from_entity(registry_id, entity)
                return registry_id

        registry_id = stable_id(
            f"{entity.entity_type.value.lower()}_registry",
            entity.normalized_name,
            entity.entity_id,
        )
        self._kb._upsert_registry(
            registry_id,
            entity.entity_type.value,
            entity.normalized_name,
            fingerprint,
            entity_embedding.tolist(),
        )
        self._kb.upsert_aliases_from_entity(registry_id, entity)
        return registry_id

    # ------------------------------------------------------------------
    # Match-or-create: cluster path
    # ------------------------------------------------------------------

    def _match_or_create_from_cluster(self, cluster: EntityCluster) -> str:
        search_names = self._candidates.alias_search_names_from_cluster(cluster)
        matches = self._kb.alias_matches(search_names, cluster.entity_type.value)
        if matches:
            match_id = matches[0]
            self._kb.upsert_aliases_from_cluster(match_id, cluster)
            return match_id

        cluster_embedding = self._disambiguator.encode_embedding(
            self._disambiguator.embedding_text_from_cluster(cluster)
        )
        cluster_fp = self._candidates.fingerprint_from_cluster(cluster)

        tokens = cluster.normalized_name.split()
        search_term = (
            tokens[-1].lower() if cluster.entity_type == EntityType.PERSON and tokens else None
        )

        candidates = self._kb.type_candidates(cluster.entity_type.value, search_term)
        for kb_id, entry in candidates:
            stored_fp: EntityFingerprint = {
                "normalized_name": entry.fingerprint.get("normalized_name", ""),
                "name_tokens": entry.fingerprint.get("name_tokens", []),
                "lemmas": entry.fingerprint.get("lemmas", []),
            }
            score = self._disambiguator._match_score(
                cluster.entity_type,
                cluster_fp,
                stored_fp,
                cluster_embedding,
                entry.embedding,
            )
            if score >= self.config.registry.similarity_threshold:
                self._kb.upsert_aliases_from_cluster(kb_id, cluster)
                return kb_id

        kb_id = stable_id(
            f"{cluster.entity_type.value.lower()}_registry",
            cluster.normalized_name,
            cluster.cluster_id,
        )
        self._kb._upsert_registry(
            kb_id,
            cluster.entity_type.value,
            cluster.normalized_name,
            cluster_fp,
            cluster_embedding.tolist(),
        )
        self._kb.upsert_aliases_from_cluster(kb_id, cluster)
        return kb_id

    # ------------------------------------------------------------------
    # Canonical-name resolution
    # ------------------------------------------------------------------

    def _preferred_registry_canonical(self, entity: Entity, registry_canonical: str) -> str:
        if entity.entity_type not in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            return registry_canonical
        candidates = [
            registry_canonical,
            entity.canonical_name,
            entity.normalized_name,
            *entity.aliases,
        ]
        if institution_canonical := self.organization_naming.canonical_institution_name(
            entity,
            candidates,
        ):
            return institution_canonical
        return self.organization_naming.best_organization_name(entity, candidates)


# ---------------------------------------------------------------------------
# PersistentEntityLinker
# ---------------------------------------------------------------------------


class PersistentEntityLinker(InMemoryEntityLinker):
    """``InMemoryEntityLinker`` backed by a SQLite knowledge base.

    The in-memory cache stays warm for the duration of the process.  After
    each document, newly created KB records are flushed back to SQLite so
    they survive across runs.
    """

    def __init__(
        self,
        config: PipelineConfig,
        *,
        db_path: str,
        runtime: PipelineRuntime | None = None,
    ) -> None:
        from pipeline.linking_sqlite import SQLiteKnowledgeBase

        _runtime = runtime or PipelineRuntime(config)
        super().__init__(config, runtime=_runtime)
        self._sqlite_kb = SQLiteKnowledgeBase(db_path)
        # Replace the in-memory KB with one warmed from SQLite.
        self._kb = self._sqlite_kb.to_in_memory_kb(config, _runtime)
        self._candidates._kb = self._kb

    def name(self) -> str:
        return "persistent_entity_linker"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        result = super().run(document)
        self._sqlite_kb.flush_from_in_memory(self._kb)
        return result
