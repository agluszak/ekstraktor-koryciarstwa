from __future__ import annotations

from pipeline.models import EntityCandidate, ParsedWord
from pipeline.nlp_rules import PARTY_CONTEXT_LEMMAS, PARTY_PROFILE_CONTEXT_LEMMAS

KINSHIP_CONTEXT_MARKERS = frozenset(
    {
        "mąż",
        "żona",
        "partner",
        "partnerka",
        "syn",
        "córka",
        "ojciec",
        "matka",
        "brat",
        "siostra",
        "szwagier",
        "synowa",
        "teść",
        "teściowa",
        "narzeczona",
        "narzeczony",
    }
)


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
        if not _supports_descriptive_tail_link(lowered_text, person, party):
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
        if _supports_descriptive_tail_link(lowered_text, person, party):
            return distance <= 180
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

    if _supports_descriptive_tail_link(lowered_text, person, party):
        return distance <= 180

    return False


def person_role_syntactic_signal(
    *,
    parsed_words: list[ParsedWord],
    lowered_text: str,
    person: EntityCandidate,
    role: EntityCandidate,
    sentence_persons: list[EntityCandidate],
) -> str | None:
    if person.is_proxy_person and _candidate_contains(person, role):
        return None

    between_text = between_candidates_text(lowered_text, person, role)
    if any(marker in between_text for marker in KINSHIP_CONTEXT_MARKERS):
        return None

    if _supports_descriptive_tail_link(lowered_text, person, role):
        return "appositive_context"

    if _other_person_between(person, role, sentence_persons):
        return None

    compact_between = between_text.strip(" \t,()[]\"'")
    if compact_between == "":
        return "appositive_context"

    person_head = candidate_head_word(parsed_words, person)
    role_head = candidate_head_word(parsed_words, role)
    if person_head is None or role_head is None:
        return None

    if person_head.head == role_head.index or role_head.head == person_head.index:
        return "syntactic_direct"

    person_children = {word.index for word in parsed_words if word.head == person_head.index}
    role_children = {word.index for word in parsed_words if word.head == role_head.index}
    if person_head.index in role_children or role_head.index in person_children:
        return "syntactic_direct"

    return None


def supports_person_role_link(
    *,
    parsed_words: list[ParsedWord],
    sentence_text: str,
    person: EntityCandidate,
    role: EntityCandidate,
    sentence_persons: list[EntityCandidate],
) -> bool:
    lowered_text = sentence_text.casefold()
    signal = person_role_syntactic_signal(
        parsed_words=parsed_words,
        lowered_text=lowered_text,
        person=person,
        role=role,
        sentence_persons=sentence_persons,
    )
    if signal is not None:
        return True

    distance = abs(person.start_char - role.start_char)
    if person.is_proxy_person:
        return False

    if _supports_descriptive_tail_link(lowered_text, person, role):
        return distance <= 180

    if distance > 32:
        return False

    between_text = between_candidates_text(lowered_text, person, role)
    if any(marker in between_text for marker in KINSHIP_CONTEXT_MARKERS):
        return False
    if _other_person_between(person, role, sentence_persons):
        return False
    return between_text.strip(" \t,:;()[]\"'") == ""


def _candidate_contains(container: EntityCandidate, inner: EntityCandidate) -> bool:
    return container.start_char <= inner.start_char and inner.end_char <= container.end_char


def _other_person_between(
    left: EntityCandidate,
    right: EntityCandidate,
    sentence_persons: list[EntityCandidate],
) -> bool:
    between_start = min(left.end_char, right.end_char)
    between_end = max(left.start_char, right.start_char)
    return any(
        candidate.candidate_id not in {left.candidate_id, right.candidate_id}
        and candidate.start_char >= between_start
        and candidate.end_char <= between_end
        for candidate in sentence_persons
    )


def _supports_descriptive_tail_link(
    lowered_text: str,
    person: EntityCandidate,
    target: EntityCandidate,
) -> bool:
    if target.start_char <= person.end_char:
        return False
    prefix = lowered_text[: person.start_char].strip(" \t\"'([")
    if prefix not in {"", "to"}:
        return False
    between_text = between_candidates_text(lowered_text, person, target)
    if any(marker in between_text for marker in KINSHIP_CONTEXT_MARKERS):
        return False
    if not any(marker in between_text for marker in (" - ", " – ", " — ", ",")):
        return False
    return not any(marker in between_text for marker in (".", ";", "?", "!"))
