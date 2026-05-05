from __future__ import annotations

import uuid
from collections import Counter

from pipeline.attribution import resolve_public_employment_attribution
from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    ClusterID,
    EntityID,
    FactID,
    FactType,
    FrameID,
    PublicEmploymentSignal,
    TimeScope,
)
from pipeline.frame_grounding import FrameSlotGrounder
from pipeline.grammar_signals import infer_status_time_scope
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    EntityCluster,
    EvidenceSpan,
    Fact,
    PublicEmploymentFrame,
)
from pipeline.runtime import PipelineRuntime
from pipeline.semantic_signals import EMPLOYMENT_CONTEXT_MARKERS
from pipeline.temporal import extract_temporal_period, resolve_event_date
from pipeline.utils import stable_id


class PolishPublicEmploymentFrameExtractor(FrameExtractor):
    ENTRY_LEMMAS = frozenset({"zatrudnić", "dostać", "objąć", "zostać", "trafić"})
    STATUS_LEMMAS = frozenset({"pracować", "być"})
    ENTRY_TEXT_MARKERS = (
        "dostał pracę",
        "dostała pracę",
        "został zatrudniony",
        "została zatrudniona",
        "zatrudniono",
        "został koordynatorem",
        "została koordynatorką",
        "objął funkcję",
        "objęła funkcję",
    )
    STATUS_TEXT_MARKERS = (
        "pracuje",
        "pracowała",
        "pracował",
        "jest zatrudniona",
        "jest zatrudniony",
        "była zatrudniona",
        "był zatrudniony",
        "jest dyrektorem",
        "jest dyrektorką",
    )

    def __init__(
        self,
        config: PipelineConfig,
        runtime: PipelineRuntime | None = None,
    ) -> None:
        self.config = config
        self.slot_grounder = FrameSlotGrounder(config, runtime=runtime)

    def name(self) -> str:
        return "polish_public_employment_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.public_employment_frames = []
        for clause in document.clause_units:
            signal = self._signal(document, clause)
            if signal is None:
                continue
            attribution = resolve_public_employment_attribution(
                document,
                clause,
                config=self.config,
            )
            if attribution is None:
                continue
            employee = attribution.employee
            employer = attribution.employer
            role_cluster = attribution.role_cluster
            grounded_role = self.slot_grounder.ground_public_employment_role(
                document,
                clause,
                employee=employee,
                role_cluster=role_cluster,
            )
            role_label = grounded_role.label if grounded_role is not None else None
            role_cluster_id = grounded_role.role_cluster_id if grounded_role is not None else None
            if (
                signal == PublicEmploymentSignal.ENTRY
                and role_label is None
                and not self._has_explicit_employment_context(clause.text)
            ):
                continue
            document.public_employment_frames.append(
                PublicEmploymentFrame(
                    frame_id=FrameID(f"public-employment-frame-{uuid.uuid4().hex[:8]}"),
                    signal=signal,
                    employee_cluster_id=employee.cluster_id,
                    employer_cluster_id=employer.cluster_id,
                    role_label=role_label,
                    role_cluster_id=role_cluster_id,
                    confidence=0.78 if role_label is not None else 0.64,
                    evidence=[self._evidence(clause)],
                    extraction_signal=(
                        "dependency_edge" if role_label is not None else "same_clause"
                    ),
                    evidence_scope="same_clause",
                    score_reason="public_employment",
                )
            )
        return document

    def _signal(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> PublicEmploymentSignal | None:
        lowered = clause.text.casefold()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = {word.lemma.casefold() for word in parsed_words}
        if any(marker in lowered for marker in self.ENTRY_TEXT_MARKERS):
            return PublicEmploymentSignal.ENTRY
        if "zostać" in lemmas and any(
            marker in lowered for marker in ("koordynator", "specjalist", "stanowisk")
        ):
            return PublicEmploymentSignal.ENTRY
        if lemmas.intersection(self.ENTRY_LEMMAS - {"zostać"}):
            return PublicEmploymentSignal.ENTRY
        if any(marker in lowered for marker in self.STATUS_TEXT_MARKERS):
            return PublicEmploymentSignal.STATUS
        if lemmas.intersection(self.STATUS_LEMMAS) and "zatrudn" in lowered:
            return PublicEmploymentSignal.STATUS
        if "pracuje" in lowered or "pracował" in lowered:
            return PublicEmploymentSignal.STATUS
        return None

    @classmethod
    def _has_explicit_employment_context(cls, text: str) -> bool:
        lowered = text.casefold()
        return any(marker in lowered for marker in EMPLOYMENT_CONTEXT_MARKERS)

    @staticmethod
    def _evidence(clause: ClauseUnit) -> EvidenceSpan:
        return EvidenceSpan(
            text=clause.text,
            sentence_index=clause.sentence_index,
            paragraph_index=clause.paragraph_index,
            start_char=clause.start_char,
            end_char=clause.end_char,
        )


def _pe_cluster_to_entity_id(document: ArticleDocument) -> dict[ClusterID, EntityID]:
    return {cluster.cluster_id: _pe_get_best_entity_id(cluster) for cluster in document.clusters}


def _pe_get_best_entity_id(cluster: EntityCluster) -> EntityID:
    entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
    if entity_ids:
        return EntityID(Counter(entity_ids).most_common(1)[0][0])
    return EntityID(cluster.cluster_id)


def _pe_cluster_by_id(document: ArticleDocument, cluster_id: ClusterID) -> EntityCluster | None:
    return next(
        (cluster for cluster in document.clusters if cluster.cluster_id == cluster_id), None
    )


def _pe_deduplicate_facts(facts: list[Fact]) -> list[Fact]:
    deduplicated: dict[tuple[FactType, EntityID, EntityID | None, str | None, str], Fact] = {}
    for fact in facts:
        key = (
            fact.fact_type,
            fact.subject_entity_id,
            fact.object_entity_id,
            fact.value_normalized,
            fact.evidence.text,
        )
        if key not in deduplicated or deduplicated[key].confidence < fact.confidence:
            deduplicated[key] = fact
    return list(deduplicated.values())


class PublicEmploymentFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _pe_cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.public_employment_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _pe_deduplicate_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: PublicEmploymentFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        employee_id = cluster_to_entity_id.get(frame.employee_cluster_id)
        employer_id = cluster_to_entity_id.get(frame.employer_cluster_id)
        if employee_id is None or employer_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        employer = _pe_cluster_by_id(document, frame.employer_cluster_id)
        role_cluster = (
            _pe_cluster_by_id(document, frame.role_cluster_id)
            if frame.role_cluster_id is not None
            else None
        )
        fact_type = (
            FactType.APPOINTMENT
            if frame.signal == PublicEmploymentSignal.ENTRY
            else FactType.ROLE_HELD
        )
        time_scope = (
            TimeScope.CURRENT
            if fact_type == FactType.APPOINTMENT
            else infer_status_time_scope(
                evidence.text,
                document.parsed_sentences.get(
                    evidence.sentence_index if evidence.sentence_index is not None else -1,
                    [],
                ),
            )
        )
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    fact_type,
                    employee_id,
                    employer_id,
                    frame.role_label or "",
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=fact_type,
            subject_entity_id=EntityID(employee_id),
            object_entity_id=EntityID(employer_id),
            value_text=frame.role_label,
            value_normalized=frame.role_label,
            time_scope=time_scope,
            event_date=resolve_event_date(
                document,
                sentence_index=evidence.sentence_index,
                text=evidence.text,
                start_char=evidence.start_char,
                end_char=evidence.end_char,
            ),
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            period=(
                extract_temporal_period(
                    document,
                    sentence_index=evidence.sentence_index,
                    text=evidence.text,
                    start_char=evidence.start_char,
                    end_char=evidence.end_char,
                )
                if fact_type == FactType.ROLE_HELD
                else None
            ),
            position_entity_id=_pe_get_best_entity_id(role_cluster) if role_cluster else None,
            role=frame.role_label,
            role_kind=role_cluster.role_kind if role_cluster is not None else None,
            role_modifier=role_cluster.role_modifier if role_cluster is not None else None,
            organization_kind=employer.organization_kind if employer is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="public_employment_frame",
            score_reason=frame.score_reason,
        )
