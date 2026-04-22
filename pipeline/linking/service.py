from __future__ import annotations

from typing import TypedDict, cast

import numpy as np

from pipeline.base import EntityLinker
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, Entity
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_party_name, stable_id


class EntityFingerprint(TypedDict, total=False):
    normalized_name: str
    name_tokens: list[str]
    lemmas: list[str]
    organizations: list[str]
    education: list[str]
    positions: list[str]
    parties: list[str]
    is_media: bool


class _RegistryEntry(TypedDict):
    entity_type: str
    canonical_name: str
    fingerprint: EntityFingerprint
    embedding: list[float]


class InMemoryEntityLinker(EntityLinker):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)
        # registry_id -> entry
        self._registry: dict[str, _RegistryEntry] = {}
        # alias string -> list of registry_ids ordered by insertion
        # (UNIQUE(registry_id, alias) semantics: a registry_id appears at most once per alias)
        self._alias_to_registry: dict[str, list[str]] = {}
        self._knowledge_seeded = False
        self.canonicalizer = DocumentEntityCanonicalizer(config)

    def name(self) -> str:
        return "in_memory_entity_linker"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not self._knowledge_seeded and document.entities:
            self._seed_knowledge_graph()
            self._knowledge_seeded = True
        for entity in document.entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                entity.registry_id = stable_id(
                    "document_local_ref", document.document_id, entity.entity_id
                )
                continue
            fingerprint = self._fingerprint(entity)
            registry_id = self._match_or_create(entity, fingerprint)
            entity.registry_id = registry_id

            # Update entity name to the canonical form from the registry
            entry = self._registry.get(registry_id)
            if entry is not None:
                entity.canonical_name = entry["canonical_name"]
                entity.normalized_name = entry["canonical_name"]

        # Deduplicate: merge entities that resolved to the same registry_id
        document.entities, id_remap = self._deduplicate_by_registry(document.entities)
        document.entities, exact_name_remap = self._deduplicate_exact_names(
            document.entities,
        )
        id_remap.update(exact_name_remap)

        # Remap entity references in extracted facts
        if id_remap:
            from pipeline.domain_types import EntityID

            for fact in document.facts:
                fact.subject_entity_id = EntityID(
                    id_remap.get(fact.subject_entity_id, fact.subject_entity_id)
                )
                if fact.object_entity_id:
                    fact.object_entity_id = EntityID(
                        id_remap.get(fact.object_entity_id, fact.object_entity_id)
                    )
            for mention in document.mentions:
                if mention.entity_id:
                    mention.entity_id = EntityID(
                        id_remap.get(mention.entity_id, mention.entity_id),
                    )

        return self.canonicalizer.run(document)

    def _upsert_registry(
        self,
        registry_id: str,
        entity_type: str,
        canonical_name: str,
        fingerprint: EntityFingerprint,
        embedding: list[float],
    ) -> None:
        """Insert or replace a registry entry (always overwrites, same semantics as seed upsert)."""
        self._registry[registry_id] = {
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "fingerprint": fingerprint,
            "embedding": embedding,
        }

    def _add_alias(self, registry_id: str, alias: str) -> None:
        """Add alias -> registry_id mapping.

        Matches UNIQUE(registry_id, alias) semantics: a registry_id is added
        at most once per alias, but the same alias may point to several registry
        entries (different entities / types).
        """
        bucket = self._alias_to_registry.setdefault(alias, [])
        if registry_id not in bucket:
            bucket.append(registry_id)

    def _seed_knowledge_graph(self) -> None:
        # Group aliases by canonical party name so all aliases of one party
        # share a single registry_id.
        canonical_groups: dict[str, set[str]] = {}
        for alias, canonical in self.config.party_aliases.items():
            normalized_canonical = normalize_party_name(canonical)
            canonical_groups.setdefault(normalized_canonical, set()).add(alias)
            canonical_groups[normalized_canonical].add(canonical)

        for normalized, aliases in canonical_groups.items():
            registry_id = stable_id("politicalparty_registry", normalized, normalized)
            fingerprint = self._fingerprint_from_name(normalized)
            fingerprint["lemmas"] = [t.lower() for t in normalized.split()]
            embedding = self._encode_embedding(normalized)
            self._upsert_registry(
                registry_id,
                EntityType.POLITICAL_PARTY.value,
                normalized,
                fingerprint,
                embedding.tolist(),
            )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self._add_alias(registry_id, variant)

        institution_groups: dict[str, set[str]] = {}
        for alias, canonical in self.config.institution_aliases.items():
            normalized_canonical = alias if alias == canonical else canonical
            normalized_canonical = normalized_canonical.strip(" ,.;:")
            institution_groups.setdefault(normalized_canonical, set()).add(alias)
            institution_groups[normalized_canonical].add(canonical)

        for normalized, aliases in institution_groups.items():
            registry_id = stable_id(
                "publicinstitution_registry",
                normalized,
                normalized,
            )
            fingerprint = self._fingerprint_from_name(normalized)
            fingerprint["lemmas"] = [t.lower() for t in normalized.split()]
            embedding = self._encode_embedding(normalized)
            self._upsert_registry(
                registry_id,
                EntityType.PUBLIC_INSTITUTION.value,
                normalized,
                fingerprint,
                embedding.tolist(),
            )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self._add_alias(registry_id, variant)

        # Seed common media organizations with aliases
        media_groups = {
            "Onet": ["Onet", "Onetowi", "Onetem"],
            "PAP": ["PAP", "Pap"],
            "Wirtualna Polska": ["Wirtualna Polska", "WP", "Wp", "Wirtualnej Polski"],
            "Rzeczypospolita": ["Rzeczypospolita", "Rzeczpospolitej"],
            "Fakt": ["Fakt", "Faktu"],
        }
        for normalized, aliases in media_groups.items():
            registry_id = stable_id("organization_registry", "media", normalized)
            if registry_id not in self._registry:
                fingerprint: EntityFingerprint = {
                    "normalized_name": normalized,
                    "name_tokens": normalized.split(),
                    "lemmas": [t.lower() for t in normalized.split()],
                    "is_media": True,
                }
                embedding = self._encode_embedding(normalized)
                self._upsert_registry(
                    registry_id,
                    EntityType.ORGANIZATION.value,
                    normalized,
                    fingerprint,
                    embedding.tolist(),
                )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self._add_alias(registry_id, variant)

    def _encode_embedding(self, text: str) -> np.ndarray:
        model = self.runtime.get_sentence_transformer_model()
        try:
            return model.encode(text, normalize_embeddings=True)  # type: ignore[no-any-return]
        except TypeError:
            return model.encode(text)  # type: ignore[no-any-return]

    def _match_or_create(self, entity: Entity, fingerprint: EntityFingerprint) -> str:
        # Try alias-based match first (case-insensitive via multiple
        # candidate forms: canonical_name, normalized_name, raw aliases).
        search_names = self._alias_search_names(entity)
        for name in search_names:
            for variant in {name, name.title(), name.lower()}:
                for match_id in self._alias_to_registry.get(variant, []):
                    entry = self._registry.get(match_id)
                    if entry is not None:
                        match_type = entry["entity_type"]
                        type_match = self._registry_types_compatible(
                            entity.entity_type.value,
                            match_type,
                        )
                        if type_match:
                            self._upsert_alias(match_id, entity)
                            return match_id

        # Candidate search
        entity_embedding = self._encode_embedding(self._embedding_text(entity))

        if entity.entity_type == EntityType.PERSON:
            search_term = entity.normalized_name.split()[-1].lower()
            candidate_ids = [
                rid
                for rid, entry in self._registry.items()
                if entry["entity_type"] == entity.entity_type.value
                and search_term in entry["canonical_name"].lower()
            ]
        else:
            if entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                compatible_types = {
                    EntityType.ORGANIZATION.value,
                    EntityType.PUBLIC_INSTITUTION.value,
                }
                candidate_ids = [
                    rid
                    for rid, entry in self._registry.items()
                    if entry["entity_type"] in compatible_types
                ]
            else:
                candidate_ids = [
                    rid
                    for rid, entry in self._registry.items()
                    if entry["entity_type"] == entity.entity_type.value
                ]

        for registry_id in candidate_ids:
            entry = self._registry[registry_id]
            stored = cast(EntityFingerprint, entry["fingerprint"])
            score = self._match_score(
                entity.entity_type,
                fingerprint,
                stored,
                entity_embedding,
                entry["embedding"],
            )
            if score >= self.config.registry.similarity_threshold:
                self._upsert_alias(registry_id, entity)
                return registry_id

        registry_id = stable_id(
            f"{entity.entity_type.value.lower()}_registry",
            entity.normalized_name,
            entity.entity_id,
        )
        self._upsert_registry(
            registry_id,
            entity.entity_type.value,
            entity.normalized_name,
            fingerprint,
            entity_embedding.tolist(),
        )
        self._upsert_alias(registry_id, entity)
        return registry_id

    @staticmethod
    def _alias_search_names(entity: Entity) -> set[str]:
        primary_names = {
            name
            for name in {entity.canonical_name, entity.normalized_name}
            if "\n" not in name and "\r" not in name
        }
        primary_tokens = {
            token.lower() for name in primary_names for token in name.split() if token
        }
        has_multi_token_primary = any(len(name.split()) > 1 for name in primary_names)
        names = set(primary_names)
        for alias in entity.aliases:
            if "\n" in alias or "\r" in alias:
                continue
            alias_tokens = alias.split()
            alias_is_component_acronym = (
                has_multi_token_primary
                and len(alias_tokens) == 1
                and alias_tokens[0].lower() in primary_tokens
                and alias_tokens[0].isupper()
            )
            if not alias_is_component_acronym:
                names.add(alias)
        return names

    @staticmethod
    def _deduplicate_by_registry(
        entities: list[Entity],
    ) -> tuple[list[Entity], dict[str, str]]:
        """Merge entities that resolved to the same registry_id.

        Returns the deduplicated list and a mapping from removed entity_ids
        to the primary entity_id they were merged into.
        """
        registry_map: dict[str, Entity] = {}
        id_remap: dict[str, str] = {}
        result: list[Entity] = []
        for entity in entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                result.append(entity)
                continue
            rid = entity.registry_id
            if rid is None or rid not in registry_map:
                if rid is not None:
                    registry_map[rid] = entity
                result.append(entity)
            else:
                # Merge aliases and evidence into the first entity
                primary = registry_map[rid]
                primary.aliases = list(
                    dict.fromkeys(
                        [*primary.aliases, *entity.aliases, entity.canonical_name],
                    )
                )
                primary.evidence.extend(entity.evidence)
                id_remap[entity.entity_id] = primary.entity_id
        return result, id_remap

    @staticmethod
    def _deduplicate_exact_names(
        entities: list[Entity],
    ) -> tuple[list[Entity], dict[str, str]]:
        exact_name_map: dict[tuple[str, str], Entity] = {}
        id_remap: dict[str, str] = {}
        result: list[Entity] = []
        for entity in entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                result.append(entity)
                continue
            key_type = entity.entity_type.value
            if entity.entity_type in {
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            }:
                key_type = "org-or-public-institution"
            key = (key_type, entity.canonical_name.casefold())
            existing = exact_name_map.get(key)
            if existing is None:
                exact_name_map[key] = entity
                result.append(entity)
                continue
            existing.aliases = list(
                dict.fromkeys(
                    [*existing.aliases, existing.canonical_name, *entity.aliases],
                )
            )
            existing.evidence.extend(entity.evidence)
            id_remap[entity.entity_id] = existing.entity_id
        return result, id_remap

    @staticmethod
    def _registry_types_compatible(entity_type: str, match_type: str) -> bool:
        if entity_type == match_type:
            return True
        return {entity_type, match_type} <= {
            EntityType.ORGANIZATION.value,
            EntityType.PUBLIC_INSTITUTION.value,
        }

    def _upsert_alias(self, registry_id: str, entity: Entity) -> None:
        aliases = {
            alias
            for alias in {
                entity.canonical_name,
                entity.normalized_name,
                *entity.aliases,
            }
            if "\n" not in alias and "\r" not in alias
        }
        for alias in aliases:
            self._add_alias(registry_id, alias)

    @staticmethod
    def _fingerprint_from_name(normalized_name: str) -> EntityFingerprint:
        tokens = normalized_name.split()
        return {"normalized_name": normalized_name, "name_tokens": tokens}

    @staticmethod
    def _fingerprint(entity: Entity) -> EntityFingerprint:
        tokens = entity.normalized_name.split()
        return {
            "normalized_name": entity.normalized_name,
            "name_tokens": tokens,
            "lemmas": entity.lemmas,
            "organizations": [],
            "education": [],
            "positions": [],
            "parties": [],
            "is_media": False,
        }

    def _match_score(
        self,
        entity_type: EntityType,
        current: EntityFingerprint,
        stored: EntityFingerprint,
        current_embedding: np.ndarray,
        stored_embedding: list[float],
    ) -> float:
        current_tokens = current["name_tokens"]
        stored_tokens = stored["name_tokens"]
        if current_tokens == stored_tokens:
            return 1.0

        if entity_type == EntityType.PERSON:
            if current_tokens[-1] != stored_tokens[-1]:
                return 0.0
            if len(current_tokens) != len(stored_tokens):
                return 0.0
            if current_tokens[:-1] != stored_tokens[:-1]:
                return 0.0
        else:
            # For non-persons, if lemmas match significantly, it's a match
            current_lemmas = set(current.get("lemmas", []))
            stored_lemmas = set(stored.get("lemmas", []))
            if current_lemmas and stored_lemmas and current_lemmas == stored_lemmas:
                return 1.0

        return float(
            sum(a * b for a, b in zip(current_embedding, stored_embedding, strict=False))
        )

    @staticmethod
    def _embedding_text(entity: Entity) -> str:
        return entity.normalized_name.strip()
