from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pipeline_v2.candidates import (
    Assessment,
    EntityCandidate,
    EntityResolutionProposal,
    ReferenceResolutionProposal,
)
from pipeline_v2.producers import EvidenceSignalProducer
from pipeline_v2.retrieval import EntityCandidateRetriever
from pipeline_v2.scoring import EntityResolutionScorer, ReferenceResolutionScorer
from pipeline_v2.store import ExtractionStore


class EntityResolutionProposalScorer(Protocol):
    def score(self, proposal: EntityResolutionProposal) -> Assessment: ...


class ReferenceProposalScorer(Protocol):
    def score(self, proposal: ReferenceResolutionProposal) -> Assessment: ...


@dataclass(frozen=True, slots=True)
class EntityResolutionAssessment:
    proposal: EntityResolutionProposal
    assessment: Assessment


@dataclass(frozen=True, slots=True)
class ReferenceResolutionAssessment:
    proposal: ReferenceResolutionProposal
    assessment: Assessment


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    entity_resolution_assessments: tuple[EntityResolutionAssessment, ...]
    reference_resolution_assessments: tuple[ReferenceResolutionAssessment, ...]


class V2Orchestrator:
    def __init__(
        self,
        store: ExtractionStore,
        *,
        retriever: EntityCandidateRetriever | None = None,
        evidence_signal_producer: EvidenceSignalProducer | None = None,
        entity_resolution_scorer: EntityResolutionProposalScorer | None = None,
        reference_resolution_scorer: ReferenceProposalScorer | None = None,
    ) -> None:
        self.store = store
        self.retriever = retriever or EntityCandidateRetriever(store)
        self.evidence_signal_producer = evidence_signal_producer or EvidenceSignalProducer()
        self.entity_resolution_scorer = entity_resolution_scorer or EntityResolutionScorer(store)
        self.reference_resolution_scorer = reference_resolution_scorer or ReferenceResolutionScorer(
            store
        )

    def assess_entities(
        self,
        entities: tuple[EntityCandidate, ...],
    ) -> tuple[EntityResolutionAssessment, ...]:
        assessments: list[EntityResolutionAssessment] = []
        for entity in entities:
            for proposal in self.retriever.proposals_for_entity(entity):
                enriched = self.evidence_signal_producer.enrich_resolution_proposal(
                    self.store,
                    proposal,
                )
                assessments.append(
                    EntityResolutionAssessment(
                        proposal=enriched,
                        assessment=self.entity_resolution_scorer.score(enriched),
                    )
                )
        return tuple(assessments)

    def assess_references(
        self,
        proposals: tuple[ReferenceResolutionProposal, ...],
    ) -> tuple[ReferenceResolutionAssessment, ...]:
        assessments: list[ReferenceResolutionAssessment] = []
        for proposal in proposals:
            enriched = self.evidence_signal_producer.enrich_reference_resolution_proposal(
                self.store,
                proposal,
            )
            assessments.append(
                ReferenceResolutionAssessment(
                    proposal=enriched,
                    assessment=self.reference_resolution_scorer.score(enriched),
                )
            )
        return tuple(assessments)

    def assess(
        self,
        *,
        entities: tuple[EntityCandidate, ...] = (),
        reference_resolutions: tuple[ReferenceResolutionProposal, ...] = (),
    ) -> OrchestrationResult:
        return OrchestrationResult(
            entity_resolution_assessments=self.assess_entities(entities),
            reference_resolution_assessments=self.assess_references(reference_resolutions),
        )
