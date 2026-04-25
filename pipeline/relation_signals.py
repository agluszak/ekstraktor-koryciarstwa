from __future__ import annotations

from pipeline.models import EntityCandidate, ParsedWord
from pipeline.nlp_rules import PARTY_CONTEXT_LEMMAS, PARTY_PROFILE_CONTEXT_LEMMAS


def candidate_words(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> list[ParsedWord]:
    return [
        word
        for word in parsed_words
        if candidate.start_char <= word.start < candidate.end_char
        or word.start <= candidate.start_char < word.end
    ]


def candidate_head_word(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> ParsedWord | None:
    words = candidate_words(parsed_words, candidate)
    if not words:
        return None
    word_indices = {word.index for word in words}
    return next((word for word in words if word.head not in word_indices), words[-1])


def between_candidates_text(
    lowered_text: str,
    left: EntityCandidate,
    right: EntityCandidate,
) -> str:
    between_start = min(left.end_char, right.end_char)
    between_end = max(left.start_char, right.start_char)
    return lowered_text[between_start:between_end]


def is_quote_speaker_risk(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> bool:
    overlapping_words = candidate_words(parsed_words, candidate)
    if not overlapping_words:
        return False
    speech_roots = {
        word.index
        for word in parsed_words
        if word.deprel == "root"
        and any(
            child.deprel.startswith("parataxis")
            for child in parsed_words
            if child.head == word.index
        )
    }
    return any(
        word.head in speech_roots and word.deprel.startswith("nsubj") for word in overlapping_words
    )


def party_syntactic_signal(
    *,
    parsed_words: list[ParsedWord],
    sentence_text: str,
    lowered_text: str,
    person: EntityCandidate,
    party: EntityCandidate,
) -> str | None:
    party_word = candidate_head_word(parsed_words, party)
    person_words = candidate_words(parsed_words, person)
    if party_word is None or not person_words:
        return None

    head = next((word for word in parsed_words if word.index == party_word.head), None)
    if head is not None and head.lemma.casefold() in PARTY_CONTEXT_LEMMAS:
        if any(person_word.index == head.head for person_word in person_words):
            return "syntactic_direct"
        if any(person_word.head == head.index for person_word in person_words):
            return "appositive_context"
        between_text = between_candidates_text(lowered_text, person, party)
        if any(marker in between_text for marker in (" z ", ",", "(", ")")):
            return "appositive_context"

    preceding_text = sentence_text[max(0, party.start_char - 3) : party.start_char].lower()
    if preceding_text.endswith(" z "):
        return "syntactic_direct"
    return None


def party_context_window_supports(
    *,
    parsed_words: list[ParsedWord],
    lowered_text: str,
    person: EntityCandidate,
    party: EntityCandidate,
    window_before: int = 8,
    window_after: int = 16,
) -> bool:
    window_start = max(0, min(person.start_char, party.start_char) - window_before)
    window_end = max(person.end_char, party.end_char) + window_after
    between_text = between_candidates_text(lowered_text, person, party)
    party_context_words = [
        word
        for word in parsed_words
        if word.lemma.casefold() in PARTY_PROFILE_CONTEXT_LEMMAS
        and window_start <= word.start <= window_end
    ]
    if party_context_words:
        return True
    if any(marker in between_text for marker in (" z ", " z ")):
        return True
    if parsed_words:
        return False
    party_window = lowered_text[window_start:window_end]
    return any(marker in party_window for marker in PARTY_PROFILE_CONTEXT_LEMMAS)


def supports_party_link(
    *,
    sentence_text: str,
    parsed_words: list[ParsedWord],
    person: EntityCandidate,
    party: EntityCandidate,
) -> bool:
    lowered_text = sentence_text.lower()
    distance = abs(person.start_char - party.start_char)
    if distance > 56:
        return False

    preceding_text = lowered_text[max(0, party.start_char - 3) : party.start_char]
    if preceding_text.endswith(" z ") and distance <= 28:
        return True

    if party_context_window_supports(
        parsed_words=parsed_words,
        lowered_text=lowered_text,
        person=person,
        party=party,
        window_before=24,
        window_after=24,
    ):
        return distance <= 36

    if (
        party_syntactic_signal(
            parsed_words=parsed_words,
            sentence_text=sentence_text,
            lowered_text=lowered_text,
            person=person,
            party=party,
        )
        is not None
    ):
        return distance <= 40

    return False
