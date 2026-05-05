from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from datetime import date

from pipeline.domain_types import (
    ClusterID,
    DocumentID,
    EntityID,
    FactID,
)

WHITESPACE_RE = re.compile(r"\s+")

DATE_RE = re.compile(r"\b(20\d{2}[-./]\d{2}[-./]\d{2}|\d{1,2}[.-]\d{1,2}[.-]20\d{2})\b")
LOCAL_DATE_RE = re.compile(
    r"\b(?:od|od dnia|od dniach|w|we)?\s*"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>"
    r"stycz(?:eń|nia)?|lut(?:y|ego)?|mar(?:ec|ca)?|kwiet(?:eń|nia)?|"
    r"maj(?:a)?|czerw(?:iec|ca)?|lip(?:iec|ca)?|sierp(?:ień|nia)?|"
    r"wrześ(?:eń|nia)?|paździer(?:nik|nika)?|listopad(?:a)?|grud(?:zień|nia)?)"
    r"(?:\s+(?P<year>\d{4}))?"
    r"(?:\s*r(?:ok|oku)?\.?)?\b",
    re.IGNORECASE,
)
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
POLISH_MONTH_NUMBERS = {
    "stycz": 1,
    "lut": 2,
    "mar": 3,
    "kwiet": 4,
    "maj": 5,
    "czerw": 6,
    "lip": 7,
    "sierp": 8,
    "wrześ": 9,
    "wrzes": 9,
    "paździer": 10,
    "pazdzier": 10,
    "listopad": 11,
    "grud": 12,
}


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


def extract_local_event_date(text: str, publication_date: str | None = None) -> str | None:
    numeric_match = next(iter(find_dates(text)), None)
    if numeric_match is not None:
        return _normalize_numeric_date(numeric_match)

    local_match = LOCAL_DATE_RE.search(text)
    if local_match is None:
        return None
    month = _month_number(local_match.group("month"))
    if month is None:
        return None
    day = int(local_match.group("day"))
    year = (
        int(local_match.group("year"))
        if local_match.group("year")
        else _publication_year(publication_date)
    )
    if year is None:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _publication_year(publication_date: str | None) -> int | None:
    if publication_date is None:
        return None
    match = re.match(r"(?P<year>\d{4})", publication_date)
    return int(match.group("year")) if match is not None else None


def _month_number(month_text: str) -> int | None:
    lowered = month_text.casefold()
    for prefix, month in POLISH_MONTH_NUMBERS.items():
        if lowered.startswith(prefix):
            return month
    return None


def _normalize_numeric_date(raw_date: str) -> str | None:
    for separator in ("-", ".", "/"):
        if separator not in raw_date:
            continue
        parts = raw_date.split(separator)
        if len(parts) != 3:
            return None
        if len(parts[0]) == 4:
            year, month, day = (int(part) for part in parts)
        else:
            day, month, year = (int(part) for part in parts)
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


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
