from __future__ import annotations

from pipeline.models import ClusterMentionView, ParsedWord

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
    candidate: ClusterMentionView,
    *,
    sentence_start: int,
) -> list[ParsedWord]:
    local_start = candidate.start_char - sentence_start
    local_end = candidate.end_char - sentence_start
    return [
        word
        for word in parsed_words
        if local_start <= word.start < local_end or word.start <= local_start < word.end
    ]


def candidate_head_word(
    parsed_words: list[ParsedWord],
    candidate: ClusterMentionView,
    *,
    sentence_start: int,
) -> ParsedWord | None:
    words = candidate_words(parsed_words, candidate, sentence_start=sentence_start)
    if not words:
        return None
    word_indices = {word.index for word in words}
    return next((word for word in words if word.head not in word_indices), words[-1])


def between_candidates_text(
    lowered_text: str,
    left: ClusterMentionView,
    right: ClusterMentionView,
    *,
    sentence_start: int,
) -> str:
    between_start = min(left.end_char, right.end_char) - sentence_start
    between_end = max(left.start_char, right.start_char) - sentence_start
    return lowered_text[between_start:between_end]


def is_quote_speaker_risk(
    parsed_words: list[ParsedWord],
    candidate: ClusterMentionView,
    *,
    sentence_start: int,
) -> bool:
    overlapping_words = candidate_words(parsed_words, candidate, sentence_start=sentence_start)
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
    person: ClusterMentionView,
    party: ClusterMentionView,
    sentence_start: int,
) -> str | None:
    party_word = candidate_head_word(parsed_words, party, sentence_start=sentence_start)
    person_words = candidate_words(parsed_words, person, sentence_start=sentence_start)
    if party_word is None or not person_words:
        return None

    person_word_indices = {word.index for word in person_words}

    # Direct link
    if party_word.head in person_word_indices:
        return "syntactic_direct"
    if any(word.head == party_word.index for word in person_words):
        return "syntactic_direct"

    # Indirect link via context head (e.g. "z", "członek")
    context_head = next((word for word in parsed_words if word.index == party_word.head), None)
    if context_head is not None:
        is_valid_join = context_head.upos in {
            "ADP",
            "PUNCT",
            "NOUN",
        } or context_head.lemma.casefold() in {"z", "w", "za", "od"}
        if is_valid_join:
            if context_head.head in person_word_indices or any(
                word.head == context_head.index for word in person_words
            ):
                return "appositive_context"

            # Grandhead check for deeper paths
            grand_head = next(
                (word for word in parsed_words if word.index == context_head.head), None
            )
            if grand_head is not None:
                if (
                    grand_head.index in person_word_indices
                    or grand_head.head in person_word_indices
                ):
                    return "appositive_context"

    party_start = party.start_char - sentence_start
    preceding_text = sentence_text[max(0, party_start - 3) : party_start].lower()
    if preceding_text.endswith(" z "):
        return "syntactic_direct"
    return None


def party_context_window_supports(
    *,
    parsed_words: list[ParsedWord],
    lowered_text: str,
    person: ClusterMentionView,
    party: ClusterMentionView,
    window_before: int = 8,
    window_after: int = 16,
    sentence_start: int,
) -> bool:
    between_text = between_candidates_text(
        lowered_text,
        person,
        party,
        sentence_start=sentence_start,
    )

    # If no specific context lemmas, we rely on proximity and "z" marker
    if any(marker in between_text for marker in (" z ", " z ", " (", " [")):
        return True

    # Generic window check: if they are very close and separated only by punctuation/spaces
    if abs(person.start_char - party.start_char) <= 8 and between_text.strip(" \t,()[]\"'") == "":
        return True

    return False


def supports_party_link(
    *,
    sentence_text: str,
    parsed_words: list[ParsedWord],
    person: ClusterMentionView,
    party: ClusterMentionView,
    sentence_start: int,
) -> bool:
    lowered_text = sentence_text.lower()
    distance = abs(person.start_char - party.start_char)
    if distance > 56:
        if not _supports_descriptive_tail_link(
            parsed_words,
            person,
            party,
            sentence_start=sentence_start,
        ):
            return False

    party_start = party.start_char - sentence_start
    preceding_text = lowered_text[max(0, party_start - 3) : party_start]
    if preceding_text.endswith(" z ") and distance <= 28:
        return True

    if party_context_window_supports(
        parsed_words=parsed_words,
        lowered_text=lowered_text,
        person=person,
        party=party,
        window_before=24,
        window_after=24,
        sentence_start=sentence_start,
    ):
        if _supports_descriptive_tail_link(
            parsed_words,
            person,
            party,
            sentence_start=sentence_start,
        ):
            return distance <= 180
        return distance <= 36

    if (
        party_syntactic_signal(
            parsed_words=parsed_words,
            sentence_text=sentence_text,
            lowered_text=lowered_text,
            person=person,
            party=party,
            sentence_start=sentence_start,
        )
        is not None
    ):
        return distance <= 40

    if _supports_descriptive_tail_link(
        parsed_words,
        person,
        party,
        sentence_start=sentence_start,
    ):
        return distance <= 180

    return False


def person_role_syntactic_signal(
    *,
    parsed_words: list[ParsedWord],
    lowered_text: str,
    person: ClusterMentionView,
    role: ClusterMentionView,
    sentence_persons: list[ClusterMentionView],
    sentence_start: int,
) -> str | None:
    if person.is_proxy_person and _candidate_contains(person, role):
        return None

    between_text = between_candidates_text(
        lowered_text,
        person,
        role,
        sentence_start=sentence_start,
    )
    if any(marker in between_text for marker in KINSHIP_CONTEXT_MARKERS):
        return None

    if _supports_descriptive_tail_link(
        parsed_words,
        person,
        role,
        sentence_start=sentence_start,
    ):
        return "appositive_context"

    if _other_person_between(person, role, sentence_persons):
        return None

    compact_between = between_text.strip(" \t,()[]\"'")
    if compact_between == "":
        return "appositive_context"

    person_head = candidate_head_word(parsed_words, person, sentence_start=sentence_start)
    role_head = candidate_head_word(parsed_words, role, sentence_start=sentence_start)
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
    person: ClusterMentionView,
    role: ClusterMentionView,
    sentence_persons: list[ClusterMentionView],
    sentence_start: int,
) -> bool:
    lowered_text = sentence_text.casefold()
    signal = person_role_syntactic_signal(
        parsed_words=parsed_words,
        lowered_text=lowered_text,
        person=person,
        role=role,
        sentence_persons=sentence_persons,
        sentence_start=sentence_start,
    )
    if signal is not None:
        return True

    distance = abs(person.start_char - role.start_char)
    if person.is_proxy_person:
        return False

    if _supports_descriptive_tail_link(
        parsed_words,
        person,
        role,
        sentence_start=sentence_start,
    ):
        return distance <= 180

    if distance > 32:
        return False

    between_text = between_candidates_text(
        lowered_text,
        person,
        role,
        sentence_start=sentence_start,
    )
    if any(marker in between_text for marker in KINSHIP_CONTEXT_MARKERS):
        return False
    if _other_person_between(person, role, sentence_persons):
        return False
    return between_text.strip(" \t,:;()[]\"'") == ""


def _candidate_contains(container: ClusterMentionView, inner: ClusterMentionView) -> bool:
    return container.start_char <= inner.start_char and inner.end_char <= container.end_char


def _other_person_between(
    left: ClusterMentionView,
    right: ClusterMentionView,
    sentence_persons: list[ClusterMentionView],
) -> bool:
    between_start = min(left.end_char, right.end_char)
    between_end = max(left.start_char, right.start_char)
    return any(
        candidate.cluster_id not in {left.cluster_id, right.cluster_id}
        and candidate.start_char >= between_start
        and candidate.end_char <= between_end
        for candidate in sentence_persons
    )


def _supports_descriptive_tail_link(
    parsed_words: list[ParsedWord],
    person: ClusterMentionView,
    target: ClusterMentionView,
    *,
    sentence_start: int,
) -> bool:
    """Check if the target is a descriptive appositive of the person.

    Replaces brittle string heuristics with dependency paths.
    """
    person_head = candidate_head_word(parsed_words, person, sentence_start=sentence_start)
    target_head = candidate_head_word(parsed_words, target, sentence_start=sentence_start)

    if person_head is None or target_head is None:
        return False

    # Apposition link
    if target_head.head == person_head.index and target_head.deprel == "appos":
        return True

    # Nmod link (e.g. "Jan Kowalski, dyrektor...")
    if target_head.head == person_head.index and target_head.deprel.startswith("nmod"):
        return True

    # Subject complement / Copula (e.g. "Jan Kowalski to dyrektor...")
    if person_head.head == target_head.index and person_head.deprel.startswith("nsubj"):
        return True

    return False
