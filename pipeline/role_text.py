from __future__ import annotations

from pipeline.models import ArticleDocument, ClauseUnit
from pipeline.nlp_rules import ROLE_PATTERNS
from pipeline.role_matching import match_role_mentions
from pipeline.utils import normalize_entity_name


def find_role_text(document: ArticleDocument, clause: ClauseUnit) -> str | None:
    parsed = document.parsed_sentences.get(clause.sentence_index, [])
    role_matches = match_role_mentions(parsed)
    if role_matches:
        return role_matches[0].canonical_name
    return find_role_text_from_text(clause)


def find_role_text_from_text(clause: ClauseUnit) -> str | None:
    for role, modifier, pattern in sorted(
        ROLE_PATTERNS,
        key=lambda item: len(item[0].value) + (len(item[1].value) if item[1] else 0),
        reverse=True,
    ):
        if pattern.search(clause.text):
            base_name = normalize_entity_name(role.value)
            return f"{modifier.value} {base_name}" if modifier else base_name
    return None
