from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

WHITESPACE_RE = re.compile(r"\s+")
DATE_RE = re.compile(r"\b(20\d{2}[-./]\d{2}[-./]\d{2}|\d{1,2}[.-]\d{1,2}[.-]20\d{2})\b")


def compact_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_entity_name(text: str) -> str:
    text = compact_whitespace(text)
    return text.strip(" ,.;:").title()


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


def normalize_party_name(text: str, aliases: dict[str, str]) -> str:
    cleaned = compact_whitespace(text)
    return aliases.get(cleaned, aliases.get(cleaned.upper(), cleaned))


def find_dates(text: str) -> list[str]:
    return [match.group(1) for match in DATE_RE.finditer(text)]


def stable_id(prefix: str, *parts: str) -> str:
    base = "::".join(part for part in parts if part)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, base or prefix).hex[:16]}"


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
