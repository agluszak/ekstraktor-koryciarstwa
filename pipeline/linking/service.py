from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypedDict, cast

from pipeline.base import EntityLinker
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, Entity
from pipeline.runtime import PipelineRuntime
from pipeline.utils import stable_id


class PersonFingerprint(TypedDict):
    normalized_name: str
    name_tokens: list[str]
    organizations: list[str]
    education: list[str]
    positions: list[str]
    parties: list[str]


class SQLiteEntityLinker(EntityLinker):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)
        self.db_path = Path(config.registry.sqlite_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self._ensure_schema()

    def name(self) -> str:
        return "sqlite_entity_linker"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for entity in [entity for entity in document.entities if entity.entity_type == "Person"]:
            fingerprint = self._fingerprint(entity)
            registry_id = self._match_or_create(entity, fingerprint)
            entity.attributes["registry_id"] = registry_id
        return document

    def _ensure_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS person_registry (
                registry_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS person_alias (
                registry_id TEXT NOT NULL,
                alias TEXT NOT NULL,
                UNIQUE(registry_id, alias)
            )
            """
        )
        self.connection.commit()

    def _match_or_create(self, entity: Entity, fingerprint: PersonFingerprint) -> str:
        rows = list(
            self.connection.execute(
                (
                    "SELECT registry_id, canonical_name, fingerprint, embedding "
                    "FROM person_registry WHERE canonical_name LIKE ?"
                ),
                (f"%{entity.normalized_name.split()[-1]}",),
            )
        )
        entity_embedding = self.runtime.get_sentence_transformer_model().encode(
            self._embedding_text(entity),
            normalize_embeddings=True,
        )

        for registry_id, _canonical_name, fingerprint_json, embedding_json in rows:
            stored = cast(PersonFingerprint, json.loads(fingerprint_json))
            score = self._match_score(
                fingerprint,
                stored,
                entity_embedding,
                cast(list[float], json.loads(embedding_json)),
            )
            if score >= self.config.registry.similarity_threshold:
                self._upsert_alias(registry_id, entity)
                return registry_id

        registry_id = stable_id("person_registry", entity.normalized_name, entity.entity_id)
        self.connection.execute(
            (
                "INSERT INTO person_registry "
                "(registry_id, canonical_name, fingerprint, embedding) "
                "VALUES (?, ?, ?, ?)"
            ),
            (
                registry_id,
                entity.normalized_name,
                json.dumps(fingerprint, ensure_ascii=False),
                json.dumps(entity_embedding.tolist()),
            ),
        )
        self._upsert_alias(registry_id, entity)
        self.connection.commit()
        return registry_id

    def _upsert_alias(self, registry_id: str, entity: Entity) -> None:
        aliases = {entity.canonical_name, *entity.aliases}
        for alias in aliases:
            self.connection.execute(
                "INSERT OR IGNORE INTO person_alias (registry_id, alias) VALUES (?, ?)",
                (registry_id, alias),
            )
        self.connection.commit()

    @staticmethod
    def _fingerprint(entity: Entity) -> PersonFingerprint:
        tokens = entity.normalized_name.split()
        return {
            "normalized_name": entity.normalized_name,
            "name_tokens": tokens,
            "organizations": cast(list[str], entity.attributes.get("organizations", [])),
            "education": cast(list[str], entity.attributes.get("education", [])),
            "positions": cast(list[str], entity.attributes.get("positions", [])),
            "parties": cast(list[str], entity.attributes.get("parties", [])),
        }

    def _match_score(
        self,
        current: PersonFingerprint,
        stored: PersonFingerprint,
        current_embedding,
        stored_embedding: list[float],
    ) -> float:
        current_tokens = current["name_tokens"]
        stored_tokens = stored["name_tokens"]
        if current_tokens == stored_tokens:
            return 1.0
        if current_tokens[-1] != stored_tokens[-1]:
            return 0.0
        if len(current_tokens) != len(stored_tokens):
            return 0.0
        if current_tokens[:-1] != stored_tokens[:-1]:
            return 0.0
        return float(sum(a * b for a, b in zip(current_embedding, stored_embedding, strict=False)))

    @staticmethod
    def _embedding_text(entity: Entity) -> str:
        organizations = " ".join(entity.attributes.get("organizations", []))
        positions = " ".join(entity.attributes.get("positions", []))
        education = " ".join(entity.attributes.get("education", []))
        return f"{entity.normalized_name} {organizations} {positions} {education}".strip()
