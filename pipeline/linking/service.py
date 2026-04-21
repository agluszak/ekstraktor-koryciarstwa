from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypedDict, cast

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


class SQLiteEntityLinker(EntityLinker):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)
        self.db_path = Path(config.registry.sqlite_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self._knowledge_seeded = False
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self._ensure_schema()

    def name(self) -> str:
        return "sqlite_entity_linker"

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
            rows = list(
                self.connection.execute(
                    "SELECT canonical_name FROM entity_registry WHERE registry_id = ?",
                    (registry_id,),
                )
            )
            if rows:
                entity.canonical_name = rows[0][0]
                entity.normalized_name = rows[0][0]

        # Deduplicate: merge entities that resolved to the same registry_id
        document.entities, id_remap = self._deduplicate_by_registry(document.entities)
        document.entities, exact_name_remap = self._deduplicate_exact_names(document.entities)
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
                    mention.entity_id = EntityID(id_remap.get(mention.entity_id, mention.entity_id))

        return self.canonicalizer.run(document)

    def _ensure_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_registry (
                registry_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_alias (
                registry_id TEXT NOT NULL,
                alias TEXT NOT NULL,
                UNIQUE(registry_id, alias)
            )
            """
        )
        self.connection.commit()

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
            rows = list(
                self.connection.execute(
                    "SELECT registry_id FROM entity_registry WHERE registry_id = ?",
                    (registry_id,),
                )
            )
            if rows:
                self.connection.execute(
                    (
                        "UPDATE entity_registry "
                        "SET entity_type = ?, canonical_name = ?, fingerprint = ?, embedding = ? "
                        "WHERE registry_id = ?"
                    ),
                    (
                        EntityType.POLITICAL_PARTY.value,
                        normalized,
                        json.dumps(fingerprint, ensure_ascii=False),
                        json.dumps(embedding.tolist()),
                        registry_id,
                    ),
                )
            else:
                self.connection.execute(
                    (
                        "INSERT INTO entity_registry "
                        "(registry_id, entity_type, canonical_name, fingerprint, embedding) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (
                        registry_id,
                        EntityType.POLITICAL_PARTY.value,
                        normalized,
                        json.dumps(fingerprint, ensure_ascii=False),
                        json.dumps(embedding.tolist()),
                    ),
                )
            # Seed all known surface forms: raw alias, canonical, and
            # title-cased variants so case-insensitive matching works.
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO entity_alias (registry_id, alias) VALUES (?, ?)",
                        (registry_id, variant),
                    )

        self.connection.commit()

        institution_groups: dict[str, set[str]] = {}
        for alias, canonical in self.config.institution_aliases.items():
            normalized_canonical = alias if alias == canonical else canonical
            normalized_canonical = normalized_canonical.strip(" ,.;:")
            institution_groups.setdefault(normalized_canonical, set()).add(alias)
            institution_groups[normalized_canonical].add(canonical)

        for normalized, aliases in institution_groups.items():
            registry_id = stable_id("publicinstitution_registry", normalized, normalized)
            fingerprint = self._fingerprint_from_name(normalized)
            fingerprint["lemmas"] = [t.lower() for t in normalized.split()]
            embedding = self._encode_embedding(normalized)
            rows = list(
                self.connection.execute(
                    "SELECT registry_id FROM entity_registry WHERE registry_id = ?",
                    (registry_id,),
                )
            )
            if rows:
                self.connection.execute(
                    (
                        "UPDATE entity_registry "
                        "SET entity_type = ?, canonical_name = ?, fingerprint = ?, embedding = ? "
                        "WHERE registry_id = ?"
                    ),
                    (
                        EntityType.PUBLIC_INSTITUTION.value,
                        normalized,
                        json.dumps(fingerprint, ensure_ascii=False),
                        json.dumps(embedding.tolist()),
                        registry_id,
                    ),
                )
            else:
                self.connection.execute(
                    (
                        "INSERT INTO entity_registry "
                        "(registry_id, entity_type, canonical_name, fingerprint, embedding) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (
                        registry_id,
                        EntityType.PUBLIC_INSTITUTION.value,
                        normalized,
                        json.dumps(fingerprint, ensure_ascii=False),
                        json.dumps(embedding.tolist()),
                    ),
                )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO entity_alias (registry_id, alias) VALUES (?, ?)",
                        (registry_id, variant),
                    )
        self.connection.commit()

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
            rows = list(
                self.connection.execute(
                    "SELECT registry_id FROM entity_registry WHERE registry_id = ?",
                    (registry_id,),
                )
            )
            if not rows:
                fingerprint: EntityFingerprint = {
                    "normalized_name": normalized,
                    "name_tokens": normalized.split(),
                    "lemmas": [t.lower() for t in normalized.split()],
                    "is_media": True,
                }
                embedding = self._encode_embedding(normalized)
                self.connection.execute(
                    (
                        "INSERT INTO entity_registry "
                        "(registry_id, entity_type, canonical_name, fingerprint, embedding) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (
                        registry_id,
                        EntityType.ORGANIZATION.value,
                        normalized,
                        json.dumps(fingerprint, ensure_ascii=False),
                        json.dumps(embedding.tolist()),
                    ),
                )
            for alias_text in aliases:
                for variant in {alias_text, alias_text.title(), alias_text.lower()}:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO entity_alias (registry_id, alias) VALUES (?, ?)",
                        (registry_id, variant),
                    )
        self.connection.commit()

    def _encode_embedding(self, text: str):
        model = self.runtime.get_sentence_transformer_model()
        try:
            return model.encode(text, normalize_embeddings=True)
        except TypeError:
            return model.encode(text)

    def _match_or_create(self, entity: Entity, fingerprint: EntityFingerprint) -> str:
        # Try alias-based match first (case-insensitive via multiple
        # candidate forms: canonical_name, normalized_name, raw aliases).
        search_names = self._alias_search_names(entity)
        related_types = {
            EntityType.ORGANIZATION.value,
            EntityType.POLITICAL_PARTY.value,
            EntityType.PUBLIC_INSTITUTION.value,
        }

        for name in search_names:
            for variant in {name, name.title(), name.lower()}:
                alias_matches = list(
                    self.connection.execute(
                        "SELECT registry_id FROM entity_alias WHERE alias = ?",
                        (variant,),
                    )
                )
                for (match_id,) in alias_matches:
                    type_row = list(
                        self.connection.execute(
                            "SELECT entity_type FROM entity_registry WHERE registry_id = ?",
                            (match_id,),
                        )
                    )
                    if type_row:
                        match_type = type_row[0][0]
                        type_match = match_type == entity.entity_type.value or (
                            match_type in related_types
                            and entity.entity_type.value in related_types
                        )
                        if type_match:
                            self._upsert_alias(match_id, entity)
                            return match_id

        # Candidate search
        if entity.entity_type == EntityType.PERSON:
            search_term = entity.normalized_name.split()[-1]
            rows = list(
                self.connection.execute(
                    (
                        "SELECT registry_id, canonical_name, fingerprint, embedding "
                        "FROM entity_registry WHERE canonical_name LIKE ? AND entity_type = ?"
                    ),
                    (f"%{search_term}%", entity.entity_type.value),
                )
            )
        else:
            # For non-persons, search all entities of the same type (or related types for Org/Party)
            # to allow matching via lemmas even if the canonical name is different (inflection).
            if entity.entity_type.value in related_types:
                rows = list(
                    self.connection.execute(
                        (
                            "SELECT registry_id, canonical_name, fingerprint, embedding "
                            "FROM entity_registry WHERE entity_type IN (?, ?)"
                        ),
                        (EntityType.ORGANIZATION.value, EntityType.POLITICAL_PARTY.value),
                    )
                )
            else:
                rows = list(
                    self.connection.execute(
                        (
                            "SELECT registry_id, canonical_name, fingerprint, embedding "
                            "FROM entity_registry WHERE entity_type = ?"
                        ),
                        (entity.entity_type.value,),
                    )
                )

        entity_embedding = self.runtime.get_sentence_transformer_model().encode(
            self._embedding_text(entity),
            normalize_embeddings=True,
        )

        for registry_id, _canonical_name, fingerprint_json, embedding_json in rows:
            stored = cast(EntityFingerprint, json.loads(fingerprint_json))
            score = self._match_score(
                entity.entity_type,
                fingerprint,
                stored,
                entity_embedding,
                cast(list[float], json.loads(embedding_json)),
            )
            if score >= self.config.registry.similarity_threshold:
                self._upsert_alias(registry_id, entity)
                return registry_id

        registry_id = stable_id(
            f"{entity.entity_type.value.lower()}_registry", entity.normalized_name, entity.entity_id
        )
        self.connection.execute(
            (
                "INSERT INTO entity_registry "
                "(registry_id, entity_type, canonical_name, fingerprint, embedding) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            (
                registry_id,
                entity.entity_type.value,
                entity.normalized_name,
                json.dumps(fingerprint, ensure_ascii=False),
                json.dumps(entity_embedding.tolist()),
            ),
        )
        self._upsert_alias(registry_id, entity)
        self.connection.commit()
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
    def _deduplicate_by_registry(entities: list[Entity]) -> tuple[list[Entity], dict[str, str]]:
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
                    dict.fromkeys([*primary.aliases, *entity.aliases, entity.canonical_name])
                )
                primary.evidence.extend(entity.evidence)
                id_remap[entity.entity_id] = primary.entity_id
        return result, id_remap

    @staticmethod
    def _deduplicate_exact_names(entities: list[Entity]) -> tuple[list[Entity], dict[str, str]]:
        exact_name_map: dict[tuple[str, str], Entity] = {}
        id_remap: dict[str, str] = {}
        result: list[Entity] = []
        related_types = {EntityType.ORGANIZATION.value, EntityType.POLITICAL_PARTY.value}
        for entity in entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                result.append(entity)
                continue
            key_type = entity.entity_type.value
            if key_type in related_types:
                key_type = "org-or-party"
            key = (key_type, entity.canonical_name.casefold())
            existing = exact_name_map.get(key)
            if existing is None:
                exact_name_map[key] = entity
                result.append(entity)
                continue
            existing.aliases = list(
                dict.fromkeys([*existing.aliases, existing.canonical_name, *entity.aliases])
            )
            existing.evidence.extend(entity.evidence)
            id_remap[entity.entity_id] = existing.entity_id
        return result, id_remap

    def _upsert_alias(self, registry_id: str, entity: Entity) -> None:
        aliases = {
            alias
            for alias in {entity.canonical_name, entity.normalized_name, *entity.aliases}
            if "\n" not in alias and "\r" not in alias
        }
        for alias in aliases:
            self.connection.execute(
                "INSERT OR IGNORE INTO entity_alias (registry_id, alias) VALUES (?, ?)",
                (registry_id, alias),
            )
        self.connection.commit()

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
        current_embedding,
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

        return float(sum(a * b for a, b in zip(current_embedding, stored_embedding, strict=False)))

    @staticmethod
    def _embedding_text(entity: Entity) -> str:
        # Since these were not inlined in models.py, we just use name.
        return entity.normalized_name.strip()
