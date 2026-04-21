from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

from pipeline.domain_types import (
    ClusterID,
    DocumentID,
    EntityID,
    FactID,
    RoleKind,
    RoleModifier,
)
from pipeline.nlp_rules import ROLE_PATTERNS

WHITESPACE_RE = re.compile(r"\s+")

DATE_RE = re.compile(r"\b(20\d{2}[-./]\d{2}[-./]\d{2}|\d{1,2}[.-]\d{1,2}[.-]20\d{2})\b")
LOWERCASE_CONNECTORS = frozenset(
    {
        "a",
        "do",
        "i",
        "im",
        "na",
        "o",
        "od",
        "oraz",
        "po",
        "u",
        "w",
        "we",
        "z",
        "ze",
    }
)


def compact_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_entity_name(text: str) -> str:
    text = compact_whitespace(text).strip(" ,;:")
    if not text:
        return ""
    parts = text.split(" ")
    normalized_parts = [
        _normalize_entity_token(part, index=index) for index, part in enumerate(parts) if part
    ]
    return " ".join(normalized_parts)


def join_hyphenated_parts(parts: list[str]) -> str:
    output: list[str] = []
    for part in parts:
        if part == "-" and output:
            output[-1] = f"{output[-1]}-"
            continue
        if output and output[-1].endswith("-"):
            output[-1] = f"{output[-1]}{part}"
        else:
            output.append(part)
    return " ".join(output)


def normalize_party_name(text: str) -> str:
    return normalize_entity_name(text)


def find_dates(text: str) -> list[str]:
    return [match.group(1) for match in DATE_RE.finditer(text)]


def stable_id(prefix: str, *parts: str) -> str:
    base = "::".join(part for part in parts if part)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, base or prefix).hex[:16]}"


def generate_entity_id(prefix: str, *parts: str) -> EntityID:
    return EntityID(stable_id(prefix, *parts))


def generate_fact_id(prefix: str, *parts: str) -> FactID:
    return FactID(stable_id(prefix, *parts))


def generate_cluster_id(prefix: str, *parts: str) -> ClusterID:
    return ClusterID(stable_id(prefix, *parts))


def generate_document_id(source_url: str | None, publication_date: str | None) -> DocumentID:
    from datetime import date

    slug = (source_url or "local-document").rstrip("/").split("/")[-1] or "document"
    date_prefix = publication_date or date.today().isoformat()
    return DocumentID(f"{date_prefix}:{slug}")


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def acronym_from_lemmas(lemmas: Iterable[str]) -> str:
    cleaned = [lemma for lemma in lemmas if lemma]
    return "".join(part[0] for part in cleaned if part)


def lowercase_signature_tokens(text: str) -> list[str]:
    cleaned = normalize_entity_name(text)
    return [token.lower() for token in cleaned.split() if token]


def _normalize_entity_token(token: str, *, index: int) -> str:
    had_trailing_dot = token.endswith(".")
    stripped = token.strip(" ,;:()[]{}\"'")
    if not stripped:
        return ""
    trailing_dot_needs_restore = had_trailing_dot and not stripped.endswith(".")
    lowered = stripped.lower()
    if index > 0 and lowered in LOWERCASE_CONNECTORS:
        return lowered
    if _looks_like_acronym(stripped):
        return stripped
    if "-" in stripped:
        normalized = "-".join(
            _normalize_entity_token(part, index=index if i == 0 else 1)
            for i, part in enumerate(stripped.split("-"))
            if part
        )
        return f"{normalized}." if trailing_dot_needs_restore else normalized
    normalized = stripped[:1].upper() + stripped[1:].lower()
    if trailing_dot_needs_restore and (
        len(stripped) <= 4 or any(char.isdigit() for char in stripped)
    ):
        return f"{normalized}."
    return normalized


def _looks_like_acronym(token: str) -> bool:
    letters = [char for char in token if char.isalpha()]
    if len(letters) >= 2 and all(char.isupper() for char in letters):
        return True
    return any(char.isupper() for char in token[1:])


def extract_role_from_text(text: str) -> tuple[RoleKind | None, RoleModifier | None]:
    for role_kind, role_modifier, pattern in ROLE_PATTERNS:
        if pattern.search(text):
            return role_kind, role_modifier
    return None, None
