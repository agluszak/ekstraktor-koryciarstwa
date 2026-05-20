from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pipeline_v2.candidates import Assessment, FactCandidate, ReferenceResolutionProposal
from pipeline_v2.embeddings import EvidenceVectorIndex
from pipeline_v2.ids import DocumentId, FactCandidateId
from pipeline_v2.store import ExtractionStore


@dataclass(frozen=True, slots=True)
class PipelineInput:
    raw_html: str
    source_url: str | None = None
    publication_date: str | None = None
    document_id: DocumentId | None = None


from pipeline_v2.types import RelevanceSignal, Signal


@dataclass(frozen=True, slots=True)
class RelevanceDecision:
    is_relevant: bool
    score: float
    reasons: tuple[RelevanceSignal, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"relevance score must be in [0.0, 1.0], got {self.score}")


class StageDiagnosticStatus(StrEnum):
    RAN = "ran"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class StageDiagnostic:
    stage_name: str
    status: StageDiagnosticStatus
    reason: str


@dataclass(frozen=True, slots=True)
class FactAssessment:
    fact_candidate_id: FactCandidateId
    assessment: Assessment


@dataclass(slots=True)
class ArticleDocument:
    document_id: DocumentId
    source_url: str | None
    title: str
    publication_date: str | None
    cleaned_text: str
    paragraphs: tuple[str, ...]
    store: ExtractionStore = field(default_factory=ExtractionStore)
    evidence_index: EvidenceVectorIndex = field(default_factory=EvidenceVectorIndex)
    reference_resolution_proposals: list[ReferenceResolutionProposal] = field(default_factory=list)
    fact_assessments: list[FactAssessment] = field(default_factory=list)
    relevance: RelevanceDecision | None = None
    execution_times: dict[str, float] = field(default_factory=dict)
    stage_diagnostics: list[StageDiagnostic] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    document_id: DocumentId
    source_url: str | None
    title: str
    publication_date: str | None
    relevance: RelevanceDecision
    fact_candidates: tuple[FactCandidate, ...]
    execution_times: dict[str, float]


def extraction_result_from_document(document: ArticleDocument) -> ExtractionResult:
    return ExtractionResult(
        document_id=document.document_id,
        source_url=document.source_url,
        title=document.title,
        publication_date=document.publication_date,
        relevance=document.relevance or RelevanceDecision(is_relevant=False, score=0.0),
        fact_candidates=tuple(document.store.fact_candidates.values()),
        execution_times=dict(document.execution_times),
    )
