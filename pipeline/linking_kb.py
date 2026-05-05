"""In-memory knowledge-base implementation used by InMemoryEntityLinker."""

from __future__ import annotations

import numpy as np

from pipeline.base import EntityKnowledgeBase
from pipeline.config import PipelineConfig
from pipeline.domain_types import KBID, EntityType
from pipeline.entity_naming import org_token_bases
from pipeline.models import (
    Entity,
    EntityCluster,
    EntityFingerprint,
    KBAliasRecord,
    KBEntityRecord,
)
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_party_name, stable_id


class _RegistryEntry:
    """Mutable in-memory entry for a single KB entity."""

    __slots__ = ("entity_type", "canonical_name", "fingerprint", "embedding")

    def __init__(
        self,
        entity_type: str,
        canonical_name: str,
        fingerprint: EntityFingerprint,
        embedding: list[float],
    ) -> None:
        self.entity_type = entity_type
        self.canonical_name = canonical_name
        self.fingerprint = fingerprint
        self.embedding = embedding


class InMemoryKnowledgeBase(EntityKnowledgeBase):
    """Alias-indexed in-memory knowledge base with embedding support."""

    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime) -> None:
        self.config = config
        self.runtime = runtime
        # kb_id -> entry
        self._registry: dict[str, _RegistryEntry] = {}
        # alias string -> list of kb_ids (UNIQUE(kb_id, alias) semantics)
        self._alias_to_registry: dict[str, list[str]] = {}
        self._knowledge_seeded = False

    @property
    def is_seeded(self) -> bool:
        """True once the KB has been populated with configured seed data."""
        return self._knowledge_seeded

    def mark_unseeded(self) -> None:
        """Force re-seeding on the next :meth:`seed` call (useful in tests)."""
        self._knowledge_seeded = False

    # ------------------------------------------------------------------
    # EntityKnowledgeBase ABC
    # ------------------------------------------------------------------

    def get_candidates(self, cluster: EntityCluster) -> list[KBEntityRecord]:
        """Return all KB records reachable via the cluster's known names/aliases."""
        search_names: set[str] = {cluster.canonical_name, cluster.normalized_name}
        for alias in cluster.aliases:
            if "\n" not in alias and "\r" not in alias:
                search_names.add(alias)
        for mention in cluster.mentions:
            if "\n" not in mention.text and "\r" not in mention.text:
                search_names.add(mention.text)

        seen: dict[str, KBEntityRecord] = {}
        for name in search_names:
            for variant in {name, name.title(), name.lower()}:
                for kb_id in self._alias_to_registry.get(variant, []):
                    if kb_id in seen:
                        continue
                    entry = self._registry.get(kb_id)
                    if entry and registry_types_compatible(
                        cluster.entity_type.value, entry.entity_type
                    ):
                        seen[kb_id] = self._entry_to_record(kb_id, entry)
        return list(seen.values())

    def upsert_entity(self, record: KBEntityRecord) -> KBID:
        tokens = record.normalized_name.split()
        fp: EntityFingerprint = {
            "normalized_name": record.normalized_name,
            "name_tokens": tokens,
            "lemmas": record.lemmas,
        }
        self._upsert_registry(
            record.kb_id,
            record.entity_type.value,
            record.canonical_name,
            fp,
            record.embedding,
        )
        for alias in record.aliases:
            self._add_alias(record.kb_id, alias)
        return KBID(record.kb_id)

    def add_alias(self, record: KBAliasRecord) -> None:
        self._add_alias(record.kb_id, record.alias)

    def get_entity(self, kb_id: KBID) -> KBEntityRecord | None:
        entry = self._registry.get(kb_id)
        if entry is None:
            return None
        return self._entry_to_record(kb_id, entry)

    # ------------------------------------------------------------------
    # Internal storage helpers
    # ------------------------------------------------------------------

    def _upsert_registry(
        self,
        kb_id: str,
        entity_type: str,
        canonical_name: str,
        fingerprint: EntityFingerprint,
        embedding: list[float],
    ) -> None:
        """Insert or replace a registry entry."""
        self._registry[kb_id] = _RegistryEntry(
            entity_type=entity_type,
            canonical_name=canonical_name,
            fingerprint=fingerprint,
            embedding=embedding,
        )

    def _add_alias(self, kb_id: str, alias: str) -> None:
        """Add alias -> kb_id mapping (UNIQUE(kb_id, alias) semantics)."""
        bucket = self._alias_to_registry.setdefault(alias, [])
        if kb_id not in bucket:
            bucket.append(kb_id)

    def upsert_aliases_from_entity(self, kb_id: str, entity: Entity) -> None:
        """Register all clean aliases from *entity* under *kb_id*."""
        aliases = {
            alias
            for alias in {entity.canonical_name, entity.normalized_name, *entity.aliases}
            if "\n" not in alias and "\r" not in alias
        }
        for alias in aliases:
            self._add_alias(kb_id, alias)

    def upsert_aliases_from_cluster(self, kb_id: str, cluster: EntityCluster) -> None:
        """Register all clean aliases from *cluster* under *kb_id*."""
        aliases = {
            alias
            for alias in {cluster.canonical_name, cluster.normalized_name, *cluster.aliases}
            if "\n" not in alias and "\r" not in alias
        }
        for alias in aliases:
            self._add_alias(kb_id, alias)

    def get_entry(self, kb_id: str) -> _RegistryEntry | None:
        return self._registry.get(kb_id)

    def iter_entities(self) -> list[tuple[str, _RegistryEntry]]:
        """Return all (kb_id, entry) pairs for persistence/export."""
        return list(self._registry.items())

    def iter_aliases(self) -> list[tuple[str, str]]:
        """Return all (alias, kb_id) pairs for persistence/export."""
        return [
            (alias, kb_id) for alias, kb_ids in self._alias_to_registry.items() for kb_id in kb_ids
        ]

    # ------------------------------------------------------------------
    # Lookup helpers used by the orchestrator
    # ------------------------------------------------------------------

    def alias_matches(self, names: set[str], entity_type: str) -> list[str]:
        """Return kb_ids reachable by alias lookup (type-compatible only)."""
        matches: list[str] = []
        seen: set[str] = set()
        for name in names:
            for variant in {name, name.title(), name.lower()}:
                for kb_id in self._alias_to_registry.get(variant, []):
                    if kb_id in seen:
                        continue
                    entry = self._registry.get(kb_id)
                    if entry and registry_types_compatible(entity_type, entry.entity_type):
                        matches.append(kb_id)
                        seen.add(kb_id)
        return matches

    def type_candidates(
        self, entity_type: str, search_term: str | None = None
    ) -> list[tuple[str, _RegistryEntry]]:
        """Return all (kb_id, entry) pairs compatible with *entity_type*.

        When *search_term* is given, only entries whose canonical name contains
        it are returned (used for fast person-surname pre-filtering).
        """
        if entity_type in {EntityType.ORGANIZATION.value, EntityType.PUBLIC_INSTITUTION.value}:
            compatible = {EntityType.ORGANIZATION.value, EntityType.PUBLIC_INSTITUTION.value}
        else:
            compatible = {entity_type}

        result: list[tuple[str, _RegistryEntry]] = []
        for kb_id, entry in self._registry.items():
            if entry.entity_type not in compatible:
                continue
            if search_term is not None and search_term not in entry.canonical_name.lower():
                continue
            result.append((kb_id, entry))
        return result

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    def seed(self) -> None:
        """Populate the KB with configured parties, institutions, and media."""
        if self._knowledge_seeded:
            return
        self._knowledge_seeded = True
        # --- political parties ---
        canonical_groups: dict[str, set[str]] = {}
        for alias, canonical in self.config.party_aliases.items():
            normalized_canonical = normalize_party_name(canonical)
            canonical_groups.setdefault(normalized_canonical, set()).add(alias)
            canonical_groups[normalized_canonical].add(canonical)

        for normalized, aliases in canonical_groups.items():
            kb_id = stable_id("politicalparty_registry", normalized, normalized)
            tokens = normalized.split()
            fp: EntityFingerprint = {
                "normalized_name": normalized,
                "name_tokens": tokens,
                "lemmas": [t.lower() for t in tokens],
            }
            embedding = self._encode_embedding(normalized)
            self._upsert_registry(
                kb_id, EntityType.POLITICAL_PARTY.value, normalized, fp, embedding.tolist()
            )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self._add_alias(kb_id, variant)

        # --- public institutions ---
        institution_groups: dict[str, set[str]] = {}
        for alias, canonical in self.config.institution_aliases.items():
            normalized_canonical = alias if alias == canonical else canonical
            normalized_canonical = normalized_canonical.strip(" ,.;:")
            institution_groups.setdefault(normalized_canonical, set()).add(alias)
            institution_groups[normalized_canonical].add(canonical)

        for normalized, aliases in institution_groups.items():
            kb_id = stable_id("publicinstitution_registry", normalized, normalized)
            tokens = normalized.split()
            fp = {
                "normalized_name": normalized,
                "name_tokens": tokens,
                "lemmas": [t.lower() for t in tokens],
            }
            embedding = self._encode_embedding(normalized)
            self._upsert_registry(
                kb_id, EntityType.PUBLIC_INSTITUTION.value, normalized, fp, embedding.tolist()
            )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self._add_alias(kb_id, variant)

        # --- common media ---
        media_groups: dict[str, list[str]] = {
            "Onet": ["Onet", "Onetowi", "Onetem"],
            "PAP": ["PAP", "Pap"],
            "Wirtualna Polska": ["Wirtualna Polska", "WP", "Wp", "Wirtualnej Polski"],
            "Rzeczypospolita": ["Rzeczypospolita", "Rzeczpospolitej"],
            "Fakt": ["Fakt", "Faktu"],
        }
        for normalized, aliases in media_groups.items():
            kb_id = stable_id("organization_registry", "media", normalized)
            if kb_id not in self._registry:
                tokens = normalized.split()
                fp = {
                    "normalized_name": normalized,
                    "name_tokens": tokens,
                    "lemmas": [t.lower() for t in tokens],
                }
                embedding = self._encode_embedding(normalized)
                self._upsert_registry(
                    kb_id, EntityType.ORGANIZATION.value, normalized, fp, embedding.tolist()
                )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self._add_alias(kb_id, variant)

    def _encode_embedding(self, text: str) -> np.ndarray:
        model = self.runtime.get_sentence_transformer_model()
        return model.encode(text, normalize_embeddings=True)

    # ------------------------------------------------------------------
    # Private conversion
    # ------------------------------------------------------------------

    def _entry_to_record(self, kb_id: str, entry: _RegistryEntry) -> KBEntityRecord:
        fp = entry.fingerprint
        return KBEntityRecord(
            kb_id=KBID(kb_id),
            entity_type=EntityType(entry.entity_type),
            canonical_name=entry.canonical_name,
            normalized_name=fp.get("normalized_name", entry.canonical_name),
            aliases=[],
            embedding=entry.embedding,
            lemmas=fp.get("lemmas", []),
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def registry_types_compatible(entity_type: str, match_type: str) -> bool:
    """Return True when two entity-type strings are compatible for linking."""
    if entity_type == match_type:
        return True
    return {entity_type, match_type} <= {
        EntityType.ORGANIZATION.value,
        EntityType.PUBLIC_INSTITUTION.value,
    }


def fingerprint_from_name(normalized_name: str) -> EntityFingerprint:
    tokens = normalized_name.split()
    return {"normalized_name": normalized_name, "name_tokens": tokens}


def token_bases_for(tokens: list[str]) -> set[str]:
    """Return inflection-normalised bases via :func:`org_token_bases`."""
    return org_token_bases(tokens)
