"""SQLite-backed knowledge base for persistent entity linking."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from pipeline.base import EntityKnowledgeBase
from pipeline.config import PipelineConfig
from pipeline.domain_types import KBID, EntityType
from pipeline.models import EntityCluster, KBAliasRecord, KBEntityRecord
from pipeline.runtime import PipelineRuntime

if TYPE_CHECKING:
    from pipeline.linking_kb import InMemoryKnowledgeBase

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_entity (
    kb_id           TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    description     TEXT,
    locality        TEXT,
    parent_org_id   TEXT,
    party_id        TEXT,
    active_from     TEXT,
    active_to       TEXT,
    embedding_json  TEXT,
    lemmas_json     TEXT
);

CREATE TABLE IF NOT EXISTS kb_alias (
    alias            TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    kb_id            TEXT NOT NULL REFERENCES kb_entity(kb_id) ON DELETE CASCADE,
    prior            REAL NOT NULL DEFAULT 1.0,
    source           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (normalized_alias, kb_id)
);

CREATE TABLE IF NOT EXISTS kb_external_id (
    kb_id TEXT NOT NULL REFERENCES kb_entity(kb_id) ON DELETE CASCADE,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (kb_id, key)
);

CREATE INDEX IF NOT EXISTS idx_kb_alias_normalized ON kb_alias(normalized_alias);
CREATE INDEX IF NOT EXISTS idx_kb_entity_type_name ON kb_entity(entity_type, normalized_name);
"""


class SQLiteKnowledgeBase(EntityKnowledgeBase):
    """Entity knowledge base backed by a SQLite database.

    The database is created (with the required schema) on first access if it
    does not exist yet.  Thread-safety is *not* guaranteed; use one instance
    per process/thread.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # EntityKnowledgeBase ABC
    # ------------------------------------------------------------------

    def get_candidates(self, cluster: EntityCluster) -> list[KBEntityRecord]:
        """Return KB records reachable via the cluster's names and aliases."""
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
                rows = self._conn.execute(
                    "SELECT kb_id FROM kb_alias WHERE normalized_alias = ?",
                    (variant,),
                ).fetchall()
                for row in rows:
                    kb_id = row["kb_id"]
                    if kb_id in seen:
                        continue
                    record = self.get_entity(KBID(kb_id))
                    if record is None:
                        continue
                    from pipeline.linking_kb import registry_types_compatible

                    if registry_types_compatible(
                        cluster.entity_type.value, record.entity_type.value
                    ):
                        seen[kb_id] = record
        return list(seen.values())

    def upsert_entity(self, record: KBEntityRecord) -> KBID:
        embedding_json = json.dumps(record.embedding) if record.embedding else None
        lemmas_json = json.dumps(record.lemmas) if record.lemmas else None
        self._conn.execute(
            """
            INSERT INTO kb_entity
                (kb_id, entity_type, canonical_name, normalized_name,
                 description, locality, parent_org_id, party_id,
                 active_from, active_to, embedding_json, lemmas_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(kb_id) DO UPDATE SET
                canonical_name  = excluded.canonical_name,
                normalized_name = excluded.normalized_name,
                description     = excluded.description,
                locality        = excluded.locality,
                parent_org_id   = excluded.parent_org_id,
                party_id        = excluded.party_id,
                active_from     = excluded.active_from,
                active_to       = excluded.active_to,
                embedding_json  = excluded.embedding_json,
                lemmas_json     = excluded.lemmas_json
            """,
            (
                record.kb_id,
                record.entity_type.value,
                record.canonical_name,
                record.normalized_name,
                record.description,
                record.locality,
                record.parent_org_id,
                record.party_id,
                record.active_from,
                record.active_to,
                embedding_json,
                lemmas_json,
            ),
        )
        # External IDs
        for key, value in record.external_ids.items():
            self._conn.execute(
                """
                INSERT INTO kb_external_id (kb_id, key, value)
                VALUES (?,?,?)
                ON CONFLICT(kb_id, key) DO UPDATE SET value = excluded.value
                """,
                (record.kb_id, key, value),
            )
        # Aliases embedded in the record
        for alias in record.aliases:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO kb_alias (alias, normalized_alias, kb_id, source)
                VALUES (?, ?, ?, 'record')
                """,
                (alias, alias.lower(), record.kb_id),
            )
        self._conn.commit()
        return KBID(record.kb_id)

    def add_alias(self, record: KBAliasRecord) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO kb_alias
                (alias, normalized_alias, kb_id, prior, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (record.alias, record.normalized_alias, record.kb_id, record.prior, record.source),
        )
        self._conn.commit()

    def get_entity(self, kb_id: KBID) -> KBEntityRecord | None:
        row = self._conn.execute("SELECT * FROM kb_entity WHERE kb_id = ?", (kb_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    # ------------------------------------------------------------------
    # Interop with InMemoryKnowledgeBase
    # ------------------------------------------------------------------

    def to_in_memory_kb(
        self, config: PipelineConfig, runtime: PipelineRuntime
    ) -> "InMemoryKnowledgeBase":
        """Create and warm an ``InMemoryKnowledgeBase`` from this SQLite store."""
        from pipeline.linking_kb import InMemoryKnowledgeBase

        kb = InMemoryKnowledgeBase(config, runtime)
        # Load all entities
        for row in self._conn.execute("SELECT * FROM kb_entity").fetchall():
            record = self._row_to_record(row)
            kb.upsert_entity(record)
        # Load all aliases
        for row in self._conn.execute("SELECT * FROM kb_alias").fetchall():
            kb._add_alias(row["kb_id"], row["alias"])
        return kb

    def flush_from_in_memory(
        self,
        kb: "InMemoryKnowledgeBase",
    ) -> None:
        """Write any new in-memory entries back to SQLite."""
        existing_ids = {
            row[0] for row in self._conn.execute("SELECT kb_id FROM kb_entity").fetchall()
        }
        for kb_id, entry in kb._registry.items():
            if kb_id in existing_ids:
                continue
            fp = entry.fingerprint
            record = KBEntityRecord(
                kb_id=KBID(kb_id),
                entity_type=EntityType(entry.entity_type),
                canonical_name=entry.canonical_name,
                normalized_name=fp.get("normalized_name", entry.canonical_name),
                embedding=entry.embedding,
                lemmas=fp.get("lemmas", []),
            )
            self.upsert_entity(record)
        # Flush aliases not yet in SQLite
        existing_aliases: set[tuple[str, str]] = {
            (row[0], row[1])
            for row in self._conn.execute("SELECT normalized_alias, kb_id FROM kb_alias").fetchall()
        }
        for alias_str, kb_ids in kb._alias_to_registry.items():
            for kb_id in kb_ids:
                if (alias_str.lower(), kb_id) not in existing_aliases:
                    self._conn.execute(
                        """
                        INSERT OR IGNORE INTO kb_alias (alias, normalized_alias, kb_id, source)
                        VALUES (?, ?, ?, 'in_memory')
                        """,
                        (alias_str, alias_str.lower(), kb_id),
                    )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> KBEntityRecord:
        embedding: list[float] = json.loads(row["embedding_json"]) if row["embedding_json"] else []
        lemmas: list[str] = json.loads(row["lemmas_json"]) if row["lemmas_json"] else []

        ext_rows = self._conn.execute(
            "SELECT key, value FROM kb_external_id WHERE kb_id = ?", (row["kb_id"],)
        ).fetchall()
        from typing import cast

        from pipeline.models import KBExternalIDs

        external_ids = cast(KBExternalIDs, {r["key"]: r["value"] for r in ext_rows})

        alias_rows = self._conn.execute(
            "SELECT alias FROM kb_alias WHERE kb_id = ?", (row["kb_id"],)
        ).fetchall()
        aliases = [r["alias"] for r in alias_rows]

        return KBEntityRecord(
            kb_id=KBID(row["kb_id"]),
            entity_type=EntityType(row["entity_type"]),
            canonical_name=row["canonical_name"],
            normalized_name=row["normalized_name"],
            aliases=aliases,
            external_ids=external_ids,
            description=row["description"],
            locality=row["locality"],
            parent_org_id=row["parent_org_id"],
            party_id=row["party_id"],
            active_from=row["active_from"],
            active_to=row["active_to"],
            embedding=embedding,
            lemmas=lemmas,
        )

    def close(self) -> None:
        self._conn.close()
