from __future__ import annotations

from pipeline.models import ArticleDocument, ClauseUnit
from pipeline.role_matching import match_role_mentions


def find_role_text(document: ArticleDocument, clause: ClauseUnit) -> str | None:
    parsed = document.parsed_sentences.get(clause.sentence_index, [])
    role_matches = match_role_mentions(parsed)
    if role_matches:
        return role_matches[0].canonical_name
    return None
