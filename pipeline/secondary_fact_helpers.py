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
from pipeline.relation_signals import (
    between_candidates_text,
    candidate_head_word,
    candidate_words,
    is_quote_speaker_risk,
    party_context_window_supports,
    party_syntactic_signal,
)
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
    return party_syntactic_signal(
        parsed_words=context.parsed_words,
        sentence_text=context.sentence.text,
        lowered_text=context.lowered_text,
        person=person,
        party=party,
    )


def _party_context_window_supports(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
) -> bool:
    return party_context_window_supports(
        parsed_words=context.parsed_words,
        lowered_text=context.lowered_text,
        person=person,
        party=party,
    )


def _candidate_head_word(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> ParsedWord | None:
    return candidate_head_word(parsed_words, candidate)


def _candidate_words(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> list[ParsedWord]:
    return candidate_words(parsed_words, candidate)


def _between_candidates(
    context: SentenceContext,
    left: EntityCandidate,
    right: EntityCandidate,
) -> str:
    return between_candidates_text(context.lowered_text, left, right)


def _is_quote_speaker_risk(
    context: SentenceContext,
    candidate: EntityCandidate,
) -> bool:
    return is_quote_speaker_risk(context.parsed_words, candidate)
