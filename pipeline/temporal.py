from __future__ import annotations

import re

from pipeline.domain_types import NERLabel
from pipeline.models import ArticleDocument, TemporalExpression
from pipeline.utils import compact_whitespace, extract_local_event_date

_PERIOD_PATTERNS = (
    re.compile(r"\bod\s+\d+\s+lat\b", re.IGNORECASE),
    re.compile(r"\bprzez\s+\d+\s+lat\b", re.IGNORECASE),
    re.compile(r"\bod\s+\d{4}\s*r?\.?\b", re.IGNORECASE),
    re.compile(
        r"\bod\s+\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia|sty\.?|lut\.?|mar\.?|kwi\.?|maj\.?|cze\.?|lip\.?|sie\.?|wrz\.?|paź\.?|lis\.?|gru\.?)\b",
        re.IGNORECASE,
    ),
)


def resolve_event_date(
    document: ArticleDocument,
    *,
    sentence_index: int | None,
    text: str,
    start_char: int | None = None,
    end_char: int | None = None,
) -> str | None:
    for expression in _matching_temporal_expressions(
        document,
        sentence_index=sentence_index,
        start_char=start_char,
        end_char=end_char,
    ):
        if expression.label != NERLabel.DATE:
            continue
        if expression.normalized_value is not None:
            return expression.normalized_value
        normalized = extract_local_event_date(expression.text, document.publication_date)
        if normalized is not None:
            return normalized
    return extract_local_event_date(text, document.publication_date) or document.publication_date


def extract_temporal_period(
    document: ArticleDocument,
    *,
    sentence_index: int | None,
    text: str,
    start_char: int | None = None,
    end_char: int | None = None,
) -> str | None:
    for expression in _matching_temporal_expressions(
        document,
        sentence_index=sentence_index,
        start_char=start_char,
        end_char=end_char,
    ):
        if expression.label == NERLabel.DATE and expression.text:
            lowered = text.lower()
            if f"od {expression.text.lower()}" in lowered:
                return compact_whitespace(f"od {expression.text}")
    for pattern in _PERIOD_PATTERNS:
        if match := pattern.search(text):
            return compact_whitespace(match.group(0))
    return None


def _matching_temporal_expressions(
    document: ArticleDocument,
    *,
    sentence_index: int | None,
    start_char: int | None,
    end_char: int | None,
) -> list[TemporalExpression]:
    matches: list[TemporalExpression] = []
    for expression in document.temporal_expressions:
        if start_char is not None and end_char is not None:
            if expression.start_char is None or expression.end_char is None:
                continue
            if expression.end_char <= start_char or expression.start_char >= end_char:
                continue
            matches.append(expression)
            continue
        if sentence_index is not None and expression.sentence_index == sentence_index:
            matches.append(expression)
    return sorted(
        matches,
        key=lambda expression: (
            expression.start_char if expression.start_char is not None else 10**9
        ),
    )
