from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from pipeline.domain_types import NERLabel, TimeScope
from pipeline.models import ParsedWord, TemporalExpression
from pipeline.nlp_rules import FORMER_MARKERS

_FUTURE_MARKERS = ("ma zostać", "ma objąć", "ma pełnić")
_STATUS_LEMMAS = frozenset({"być", "pracować", "pełnić", "zasiadać"})


def word_feat(word: ParsedWord, feature: str) -> str | None:
    return word.feats.get(feature)


def has_tense(words: Iterable[ParsedWord], tense: str) -> bool:
    return any(word_feat(word, "Tense") == tense for word in words)


def infer_sentence_time_scope(text: str, parsed_words: list[ParsedWord]) -> TimeScope:
    lowered = text.lower()
    if any(marker in lowered for marker in FORMER_MARKERS):
        return TimeScope.FORMER
    if any(marker in lowered for marker in _FUTURE_MARKERS) or has_tense(parsed_words, "Fut"):
        return TimeScope.FUTURE
    return TimeScope.CURRENT


def infer_time_scope_with_temporal_context(
    text: str,
    parsed_words: list[ParsedWord],
    *,
    temporal_expressions: list[TemporalExpression],
    sentence_index: int,
    publication_date: str | None,
) -> TimeScope:
    """Like `infer_sentence_time_scope` but also anchors against dated temporal expressions.

    If the basic lexical/tense inference returns CURRENT, we look for DATE temporal
    expressions in the same sentence.  An expression whose normalized ISO value falls
    before the article's publication date implies the described event already happened
    (FORMER); one after the publication date implies it is yet to happen (FUTURE).
    """
    scope = infer_sentence_time_scope(text, parsed_words)
    if scope != TimeScope.CURRENT:
        return scope
    anchored = _scope_from_temporal_expressions(
        temporal_expressions, sentence_index, publication_date
    )
    return anchored if anchored is not None else scope


def infer_status_time_scope(text: str, parsed_words: list[ParsedWord]) -> TimeScope:
    scope = infer_sentence_time_scope(text, parsed_words)
    if scope != TimeScope.CURRENT:
        return scope
    if any(
        word.lemma in _STATUS_LEMMAS
        and word.upos in {"VERB", "AUX"}
        and word_feat(word, "Tense") == "Past"
        for word in parsed_words
    ):
        return TimeScope.FORMER
    return TimeScope.CURRENT


def _scope_from_temporal_expressions(
    temporal_expressions: list[TemporalExpression],
    sentence_index: int,
    publication_date: str | None,
) -> TimeScope | None:
    pub = _parse_iso_date(publication_date)
    for expr in temporal_expressions:
        if expr.sentence_index != sentence_index:
            continue
        if expr.label != NERLabel.DATE:
            continue
        expr_date = _parse_iso_date(expr.normalized_value)
        if expr_date is None:
            continue
        if pub is not None:
            if expr_date < pub:
                return TimeScope.FORMER
            if expr_date > pub:
                return TimeScope.FUTURE
    return None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    # Try year-month-day, year-month, year — accept any ISO-like prefix
    for length in (10, 7, 4):
        fragment = value[:length]
        try:
            if length == 10:
                return date.fromisoformat(fragment)
            if length == 7 and "-" in fragment:
                y, m = fragment.split("-", 1)
                return date(int(y), int(m), 1)
            if length == 4 and fragment.isdigit():
                return date(int(fragment), 1, 1)
        except (ValueError, AttributeError):
            pass
    return None
