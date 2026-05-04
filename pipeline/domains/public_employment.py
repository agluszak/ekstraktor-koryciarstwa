from __future__ import annotations

import uuid

from pipeline.attribution import resolve_public_employment_attribution
from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import FrameID, PublicEmploymentSignal
from pipeline.frame_grounding import FrameSlotGrounder
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    EvidenceSpan,
    PublicEmploymentFrame,
)
from pipeline.runtime import PipelineRuntime
from pipeline.semantic_signals import EMPLOYMENT_CONTEXT_MARKERS


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
