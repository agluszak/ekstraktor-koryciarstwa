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
from pipeline.relation_signals import is_quote_speaker_risk
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
    SAME_SENTENCE = 0.55

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
    lemmas: AbstractSet[str],
) -> bool:
    return bool(lemma_set(parsed_words).intersection(lemmas))


def _is_quote_speaker_risk(
    context: SentenceContext,
    candidate: EntityCandidate,
) -> bool:
    return is_quote_speaker_risk(context.parsed_words, candidate)
