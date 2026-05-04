from __future__ import annotations

from collections.abc import Iterable

from pipeline.domain_types import TimeScope
from pipeline.models import ParsedWord
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
