from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet

from pipeline.domain_types import (
    EntityID,
    FactID,
    FactType,
    RelationshipType,
    RoleKind,
)
from pipeline.extraction_context import SentenceContext
from pipeline.lemma_signals import lemma_set
from pipeline.models import ArticleDocument, EntityCandidate, Fact, ParsedWord
from pipeline.nlp_rules import PARTY_CONTEXT_LEMMAS, PARTY_PROFILE_CONTEXT_LEMMAS
from pipeline.utils import stable_id

POLITICAL_ROLE_NAMES = frozenset(
    {
        RoleKind.RADNY.value,
        RoleKind.POSEL.value,
        RoleKind.SENATOR.value,
        RoleKind.MINISTER.value,
        RoleKind.PREZYDENT_MIASTA.value,
        RoleKind.WOJEWODA.value,
        RoleKind.WOJT.value,
        RoleKind.STAROSTA.value,
        RoleKind.SEKRETARZ_POWIATU.value,
        RoleKind.MARSZALEK_WOJEWODZTWA.value,
    }
)


@dataclass(frozen=True, slots=True)
class SecondaryFactScore:
    confidence: float
    extraction_signal: str
    evidence_scope: str
    reason: str


class SecondaryFactScorer:
    SYNTACTIC_DIRECT = 0.85
    APPOSITIVE_CONTEXT = 0.78
    DEPENDENCY_EDGE = 0.72
    SAME_CLAUSE = 0.64
    SAME_SENTENCE = 0.55
    SAME_PARAGRAPH = 0.42
    BROAD_CONTEXT = 0.30

    @classmethod
    def party_membership(
        cls,
        context: SentenceContext,
        person: EntityCandidate,
        party: EntityCandidate,
        *,
        governance_signal: bool,
    ) -> SecondaryFactScore | None:
        edge_confidence = context.edge_confidence(
            "person-affiliated-party",
            person.candidate_id,
            party.candidate_id,
        )
        syntactic_signal = _party_syntactic_signal(context, person, party)
        distance = abs(person.start_char - party.start_char)

        if syntactic_signal == "syntactic_direct":
            confidence = max(cls.SYNTACTIC_DIRECT, edge_confidence or 0.0)
            return cls._score(confidence, syntactic_signal, "same_sentence", "direct_party_edge")
        if syntactic_signal == "appositive_context":
            confidence = max(cls.APPOSITIVE_CONTEXT, edge_confidence or 0.0)
            return cls._score(confidence, syntactic_signal, "same_sentence", "party_apposition")
        if edge_confidence is not None:
            confidence = max(cls.DEPENDENCY_EDGE, edge_confidence)
            if governance_signal:
                confidence -= 0.12
            return cls._score(
                confidence,
                "dependency_edge",
                "same_sentence",
                "candidate_graph_party_edge",
            )
        if distance <= 40 and _party_context_window_supports(context, person, party):
            confidence = cls.SAME_SENTENCE - (0.1 if governance_signal else 0.0)
            return cls._score(confidence, "same_sentence", "same_sentence", "near_party_context")
        return None

    @classmethod
    def political_office(
        cls,
        context: SentenceContext,
        person: EntityCandidate,
        role: EntityCandidate,
        *,
        governance_signal: bool,
    ) -> SecondaryFactScore | None:
        edge_confidence = context.edge_confidence(
            "person-has-role",
            person.candidate_id,
            role.candidate_id,
        )
        distance = abs(person.start_char - role.start_char)
        if edge_confidence is not None and edge_confidence >= 0.72:
            confidence = max(cls.DEPENDENCY_EDGE, edge_confidence)
            if governance_signal:
                confidence -= 0.1
            return cls._score(
                confidence,
                "dependency_edge",
                "same_sentence",
                "person_role_edge",
            )
        if distance <= 28:
            confidence = cls.SAME_SENTENCE - (0.08 if governance_signal else 0.0)
            return cls._score(confidence, "same_sentence", "same_sentence", "near_office_role")
        if distance <= 48 and not governance_signal:
            return cls._score(cls.SAME_PARAGRAPH, "same_paragraph", "same_sentence", "loose_role")
        return None

    @classmethod
    def candidacy(
        cls,
        context: SentenceContext,
        person: EntityCandidate,
    ) -> SecondaryFactScore | None:
        lemmas = {word.lemma for word in context.parsed_words}
        if not (
            {"kandydować", "startować"}.intersection(lemmas)
            or "kandydat" in context.lowered_text
            or "wybory" in context.lowered_text
        ):
            return None
        governing_words = [
            word
            for word in context.parsed_words
            if word.lemma in {"kandydować", "startować"} or word.lemma == "kandydat"
        ]
        if "wybory" not in context.lowered_text and "kandydat" not in context.lowered_text:
            return None
        if any(abs(person.start_char - word.start) <= 28 for word in governing_words):
            return cls._score(cls.DEPENDENCY_EDGE, "dependency_edge", "same_sentence", "candidacy")
        return cls._score(cls.SAME_SENTENCE, "same_sentence", "same_sentence", "election_context")

    @classmethod
    def tie(
        cls,
        context: SentenceContext,
        source: EntityCandidate,
        target: EntityCandidate,
        trigger: str,
        edge_confidence: float,
    ) -> SecondaryFactScore:
        strong_triggers = {"przyjaciel", "doradca", "rekomendować", "rekomendacja"}
        distance = abs(source.start_char - target.start_char)
        confidence = max(cls.SAME_SENTENCE, edge_confidence)
        signal = "dependency_edge"
        reason = f"tie_trigger:{trigger}"
        if trigger in strong_triggers:
            confidence += 0.08
            signal = "syntactic_direct"
        if distance > 120:
            confidence -= 0.12
            reason += ":long_distance"
        if _is_quote_speaker_risk(context, source) or _is_quote_speaker_risk(context, target):
            confidence -= 0.12
            reason += ":quote_speaker_risk"
        return cls._score(confidence, signal, "same_sentence", reason)

    @staticmethod
    def _score(
        confidence: float,
        extraction_signal: str,
        evidence_scope: str,
        reason: str,
    ) -> SecondaryFactScore:
        return SecondaryFactScore(
            confidence=max(0.05, min(confidence, 0.95)),
            extraction_signal=extraction_signal,
            evidence_scope=evidence_scope,
            reason=reason,
        )


def build_secondary_fact(
    *,
    document: ArticleDocument,
    sentence_context: SentenceContext,
    fact_type: FactType,
    subject: EntityCandidate,
    object_candidate: EntityCandidate | None,
    value_text: str | None,
    value_normalized: str | None,
    confidence: float,
    score: SecondaryFactScore,
    source_extractor: str,
    party: str | None = None,
    office_type: str | None = None,
    candidacy_scope: str | None = None,
    relationship_type: RelationshipType | None = None,
) -> Fact:
    f = Fact(
        fact_id=FactID(
            stable_id(
                "fact",
                document.document_id,
                fact_type,
                subject.entity_id or subject.candidate_id,
                object_candidate.entity_id or object_candidate.candidate_id
                if object_candidate
                else "",
                value_normalized or value_text or "",
                sentence_context.evidence.text,
            )
        ),
        fact_type=fact_type,
        subject_entity_id=EntityID(subject.entity_id or subject.candidate_id),
        object_entity_id=EntityID(object_candidate.entity_id or object_candidate.candidate_id)
        if object_candidate
        else None,
        value_text=value_text,
        value_normalized=value_normalized,
        time_scope=sentence_context.time_scope,
        event_date=sentence_context.event_date,
        confidence=round(confidence, 3),
        evidence=sentence_context.evidence,
        extraction_signal=score.extraction_signal,
        evidence_scope=score.evidence_scope,
        overlaps_governance=sentence_context.overlaps_governance,
        source_extractor=source_extractor,
        score_reason=score.reason,
    )
    f.party = party
    f.office_type = office_type
    f.candidacy_scope = candidacy_scope
    f.relationship_type = relationship_type
    return f


def _has_signal(
    parsed_words: list[ParsedWord],
    lowered_text: str,
    lemmas: AbstractSet[str],
    surface_triggers: AbstractSet[str],
) -> bool:
    parsed_lemmas = lemma_set(parsed_words)
    return bool(
        parsed_lemmas.intersection(lemmas)
        or any(trigger in lowered_text for trigger in surface_triggers)
    )


def _party_syntactic_signal(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
) -> str | None:
    party_word = _candidate_head_word(context.parsed_words, party)
    person_words = _candidate_words(context.parsed_words, person)
    if party_word is None or not person_words:
        return None

    head = next((word for word in context.parsed_words if word.index == party_word.head), None)
    if head is not None and head.lemma.casefold() in PARTY_CONTEXT_LEMMAS:
        if any(person_word.index == head.head for person_word in person_words):
            return "syntactic_direct"
        if any(person_word.head == head.index for person_word in person_words):
            return "appositive_context"
        between_text = _between_candidates(context, person, party)
        if any(marker in between_text for marker in (" z ", ",", "(", ")")):
            return "appositive_context"

    preceding_text = context.sentence.text[max(0, party.start_char - 3) : party.start_char].lower()
    if preceding_text.endswith(" z "):
        return "syntactic_direct"
    return None


def _party_context_window_supports(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
) -> bool:
    window_start = max(0, min(person.start_char, party.start_char) - 8)
    window_end = max(person.end_char, party.end_char) + 16
    between_text = _between_candidates(context, person, party)
    party_context_words = [
        word
        for word in context.parsed_words
        if word.lemma.casefold() in PARTY_PROFILE_CONTEXT_LEMMAS
        and window_start <= word.start <= window_end
    ]
    if party_context_words:
        return True
    if any(marker in between_text for marker in (" z ", " z ")):
        return True
    if context.parsed_words:
        return False
    party_window = context.lowered_text[window_start:window_end]
    return any(marker in party_window for marker in PARTY_PROFILE_CONTEXT_LEMMAS)


def _candidate_head_word(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> ParsedWord | None:
    words = _candidate_words(parsed_words, candidate)
    if not words:
        return None
    word_indices = {word.index for word in words}
    return next((word for word in words if word.head not in word_indices), words[-1])


def _candidate_words(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> list[ParsedWord]:
    return [
        word
        for word in parsed_words
        if candidate.start_char <= word.start < candidate.end_char
        or word.start <= candidate.start_char < word.end
    ]


def _between_candidates(
    context: SentenceContext,
    left: EntityCandidate,
    right: EntityCandidate,
) -> str:
    between_start = min(left.end_char, right.end_char)
    between_end = max(left.start_char, right.start_char)
    return context.lowered_text[between_start:between_end]


def _is_quote_speaker_risk(
    context: SentenceContext,
    candidate: EntityCandidate,
) -> bool:
    candidate_words = _candidate_words(context.parsed_words, candidate)
    if not candidate_words:
        return False
    speech_roots = {
        word.index
        for word in context.parsed_words
        if word.deprel == "root"
        and any(
            child.deprel.startswith("parataxis")
            for child in context.parsed_words
            if child.head == word.index
        )
    }
    return any(
        word.head in speech_roots and word.deprel.startswith("nsubj") for word in candidate_words
    )
