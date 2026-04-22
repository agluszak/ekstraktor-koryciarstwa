from __future__ import annotations

from typing import AbstractSet

from pipeline.models import ParsedWord


def lemma_set(parsed_words: list[ParsedWord]) -> set[str]:
    return {_lemma(word) for word in parsed_words}


def has_lemma(parsed_words: list[ParsedWord], lemmas: AbstractSet[str]) -> bool:
    return bool(lemma_set(parsed_words).intersection(lemmas))


def words_with_lemmas(
    parsed_words: list[ParsedWord],
    lemmas: AbstractSet[str],
) -> list[ParsedWord]:
    return [word for word in parsed_words if _lemma(word) in lemmas]


def word_by_index(parsed_words: list[ParsedWord], index: int) -> ParsedWord | None:
    return next((word for word in parsed_words if word.index == index), None)


def child_words(
    parsed_words: list[ParsedWord],
    head: ParsedWord,
) -> list[ParsedWord]:
    return [word for word in parsed_words if word.head == head.index]


def has_child_lemma(
    parsed_words: list[ParsedWord],
    head: ParsedWord,
    lemmas: AbstractSet[str],
) -> bool:
    return any(_lemma(word) in lemmas for word in child_words(parsed_words, head))


def has_descendant_lemma(
    parsed_words: list[ParsedWord],
    head: ParsedWord,
    lemmas: AbstractSet[str],
    *,
    max_depth: int = 3,
) -> bool:
    pending = [(head.index, 0)]
    seen = {head.index}
    while pending:
        head_index, depth = pending.pop()
        if depth >= max_depth:
            continue
        for word in parsed_words:
            if word.head != head_index or word.index in seen:
                continue
            if _lemma(word) in lemmas:
                return True
            seen.add(word.index)
            pending.append((word.index, depth + 1))
    return False


def has_lemma_pair(
    parsed_words: list[ParsedWord],
    head_lemmas: AbstractSet[str],
    dependent_lemmas: AbstractSet[str],
) -> bool:
    return any(
        _lemma(head) in head_lemmas
        and (
            has_child_lemma(parsed_words, head, dependent_lemmas)
            or has_descendant_lemma(parsed_words, head, dependent_lemmas)
        )
        for head in parsed_words
    )


def _lemma(word: ParsedWord) -> str:
    return (word.lemma or word.text).casefold()
