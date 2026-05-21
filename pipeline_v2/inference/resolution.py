from __future__ import annotations

from collections import defaultdict

from pipeline_v2.candidates import (
    Assessment,
    EntityResolutionClaim,
    EntityResolutionProposal,
    FactResolutionClaim,
    FactResolutionProposal,
    ReferenceResolutionClaim,
    ReferenceResolutionProposal,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_resolution import FactResolutionProposalBuilder
from pipeline_v2.ids import (
    EntityCandidateId,
    InferenceFactorId,
    InferenceStateId,
    InferenceVariableId,
    ProducerId,
    ScorerId,
)
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.factor_builders import FALSE_STATE, TRUE_STATE, UNKNOWN_STATE
from pipeline_v2.inference.graph_spec import (
    InferenceFactor,
    InferenceFactorKind,
    InferenceGraphSpec,
    InferenceResult,
    InferenceState,
    InferenceVariable,
    InferenceVariableKind,
)
from pipeline_v2.producers import EvidenceSignalProducer
from pipeline_v2.retrieval import EntityCandidateRetriever
from pipeline_v2.scoring import (
    EntityResolutionScorer,
    FactResolutionScorer,
    ReferenceResolutionScorer,
)
from pipeline_v2.types import ResolutionRelation, Signal, SignalPolarity


class ProbabilisticResolutionInferencer:
    producer_id = ProducerId("probabilistic_inference_stage_v2")

    def run(
        self,
        *,
        document: ArticleDocument,
        backend: InferenceBackend,
    ) -> tuple[InferenceResult, InferenceResult, InferenceResult]:
        document.store.clear_resolution_claims()
        document.store.clear_reference_resolution_claims()
        document.store.clear_fact_resolution_claims()
        entity_result = self._infer_entities(document=document, backend=backend)
        reference_result = self._infer_references(document=document, backend=backend)
        fact_result = self._infer_same_fact(document=document, backend=backend)
        return entity_result, reference_result, fact_result

    def _infer_entities(
        self,
        *,
        document: ArticleDocument,
        backend: InferenceBackend,
    ) -> InferenceResult:
        retriever = EntityCandidateRetriever(document.store)
        signal_producer = EvidenceSignalProducer()
        scorer = EntityResolutionScorer(document.store)
        proposals: list[EntityResolutionProposal] = []
        seen_pairs: set[tuple[str, str]] = set()
        for entity in document.store.entity_candidates.values():
            for proposal in retriever.proposals_for_entity(entity):
                enriched = signal_producer.enrich_resolution_proposal(document.store, proposal)
                left = str(enriched.left_entity_id)
                right = str(enriched.right_entity_id)
                pair = (left, right) if left <= right else (right, left)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                proposals.append(enriched)
        if not proposals:
            return InferenceResult(marginals=())

        variables: list[InferenceVariable] = []
        factors: list[InferenceFactor] = []
        proposals_by_variable_id: dict[InferenceVariableId, EntityResolutionProposal] = {}
        for proposal in proposals:
            variable_id = InferenceVariableId(
                f"same-entity:{proposal.left_entity_id}:{proposal.right_entity_id}"
            )
            score = scorer.score(proposal).score
            variables.append(
                InferenceVariable(
                    id=variable_id,
                    kind=InferenceVariableKind.SAME_ENTITY,
                    states=(FALSE_STATE, TRUE_STATE),
                )
            )
            factors.append(
                InferenceFactor(
                    id=InferenceFactorId(
                        f"factor:entity-resolution:{proposal.left_entity_id}:{proposal.right_entity_id}"
                    ),
                    kind=InferenceFactorKind.EVIDENCE_PRIOR,
                    variable_ids=(variable_id,),
                    potentials=(1.0 - score, score),
                    evidence_ids=proposal.evidence_ids,
                    signals=tuple(
                        dict.fromkeys([*proposal.retrieval_signals, *proposal.context_signals])
                    ),
                )
            )
            proposals_by_variable_id[variable_id] = proposal

        result = backend.run(InferenceGraphSpec(variables=tuple(variables), factors=tuple(factors)))
        for variable_id, proposal in proposals_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None:
                continue
            document.store.add_resolution_claim(
                EntityResolutionClaim(
                    id=document.store.next_resolution_claim_id(),
                    left_entity_id=proposal.left_entity_id,
                    right_entity_id=proposal.right_entity_id,
                    relation=ResolutionRelation.SAME_AS,
                    evidence_ids=proposal.evidence_ids,
                    assessment=self._assessment(
                        score=marginal.probability_for(TRUE_STATE.id),
                        positive=proposal.retrieval_signals,
                        negative=proposal.context_signals,
                        scorer_id=ScorerId("probabilistic_entity_resolution_inference_v2"),
                        explanation="entity resolution posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        return result

    def _infer_references(
        self,
        *,
        document: ArticleDocument,
        backend: InferenceBackend,
    ) -> InferenceResult:
        signal_producer = EvidenceSignalProducer()
        scorer = ReferenceResolutionScorer(document.store)
        grouped: dict[str, dict[EntityCandidateId, ReferenceResolutionProposal]] = defaultdict(dict)
        for proposal in document.reference_resolution_proposals:
            enriched = signal_producer.enrich_reference_resolution_proposal(
                document.store,
                proposal,
            )
            grouped[str(enriched.reference_id)][enriched.candidate_entity_id] = enriched
        if not grouped:
            return InferenceResult(marginals=())

        variables: list[InferenceVariable] = []
        factors: list[InferenceFactor] = []
        proposals_by_variable_id: dict[
            InferenceVariableId, dict[InferenceStateId, ReferenceResolutionProposal]
        ] = {}
        for reference_id, candidate_map in grouped.items():
            ordered_proposals = [
                candidate_map[entity_id]
                for entity_id in sorted(candidate_map.keys(), key=lambda item: str(item))
            ]
            variable_id = InferenceVariableId(f"reference-target:{reference_id}")
            states = [UNKNOWN_STATE]
            weights = [
                self._unknown_weight(
                    tuple(scorer.score(proposal).score for proposal in ordered_proposals)
                )
            ]
            state_proposals: dict[InferenceStateId, ReferenceResolutionProposal] = {}
            evidence_ids: list = []
            signals: list[Signal] = []
            for proposal in ordered_proposals:
                state_id = InferenceStateId(str(proposal.candidate_entity_id))
                states.append(InferenceState(state_id, str(proposal.candidate_entity_id)))
                weights.append(scorer.score(proposal).score)
                state_proposals[state_id] = proposal
                evidence_ids.extend(proposal.evidence_ids)
                signals.extend(proposal.retrieval_signals)
                signals.extend(proposal.context_signals)
            normalized = self._normalize(tuple(weights))
            variables.append(
                InferenceVariable(
                    id=variable_id,
                    kind=InferenceVariableKind.REFERENCE_TARGET,
                    states=tuple(states),
                )
            )
            factors.append(
                InferenceFactor(
                    id=InferenceFactorId(f"factor:reference-target:{reference_id}"),
                    kind=InferenceFactorKind.EVIDENCE_PRIOR,
                    variable_ids=(variable_id,),
                    potentials=normalized,
                    evidence_ids=tuple(dict.fromkeys(evidence_ids)),
                    signals=tuple(dict.fromkeys(signals)),
                )
            )
            proposals_by_variable_id[variable_id] = state_proposals

        result = backend.run(InferenceGraphSpec(variables=tuple(variables), factors=tuple(factors)))
        for variable_id, state_proposals in proposals_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None or not state_proposals:
                continue
            unknown_probability = marginal.probability_for(UNKNOWN_STATE.id)
            best_state_id, best_proposal, best_probability = max(
                (
                    (
                        state_id,
                        proposal,
                        marginal.probability_for(state_id),
                    )
                    for state_id, proposal in state_proposals.items()
                ),
                key=lambda item: item[2],
            )
            _ = best_state_id
            if best_probability <= unknown_probability:
                continue
            document.store.add_reference_resolution_claim(
                ReferenceResolutionClaim(
                    id=document.store.next_reference_resolution_claim_id(),
                    reference_id=best_proposal.reference_id,
                    candidate_entity_id=best_proposal.candidate_entity_id,
                    relation=ResolutionRelation.REFERENT_OF,
                    evidence_ids=best_proposal.evidence_ids,
                    assessment=self._assessment(
                        score=best_probability,
                        positive=best_proposal.retrieval_signals,
                        negative=best_proposal.context_signals,
                        scorer_id=ScorerId("probabilistic_reference_resolution_inference_v2"),
                        explanation="reference target posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        return result

    def _infer_same_fact(
        self,
        *,
        document: ArticleDocument,
        backend: InferenceBackend,
    ) -> InferenceResult:
        scorer = FactResolutionScorer()
        fact_scores = {
            assessment.fact_candidate_id: assessment.assessment.score
            for assessment in document.fact_assessments
        }
        proposals = FactResolutionProposalBuilder().build(document)
        if not proposals:
            return InferenceResult(marginals=())

        variables: list[InferenceVariable] = []
        factors: list[InferenceFactor] = []
        proposals_by_variable_id: dict[InferenceVariableId, FactResolutionProposal] = {}
        for proposal in proposals:
            variable_id = InferenceVariableId(
                f"same-event:{proposal.left_fact_id}:{proposal.right_fact_id}"
            )
            base_score = scorer.score(proposal).score
            connected_score = base_score * min(
                fact_scores.get(proposal.left_fact_id, 1.0),
                fact_scores.get(proposal.right_fact_id, 1.0),
            )
            variables.append(
                InferenceVariable(
                    id=variable_id,
                    kind=InferenceVariableKind.SAME_EVENT,
                    states=(FALSE_STATE, TRUE_STATE),
                )
            )
            factors.append(
                InferenceFactor(
                    id=InferenceFactorId(
                        f"factor:same-event:{proposal.left_fact_id}:{proposal.right_fact_id}"
                    ),
                    kind=InferenceFactorKind.EVIDENCE_PRIOR,
                    variable_ids=(variable_id,),
                    potentials=(1.0 - connected_score, connected_score),
                    evidence_ids=proposal.evidence_ids,
                    signals=tuple(
                        dict.fromkeys([*proposal.retrieval_signals, *proposal.context_signals])
                    ),
                )
            )
            proposals_by_variable_id[variable_id] = proposal

        result = backend.run(InferenceGraphSpec(variables=tuple(variables), factors=tuple(factors)))
        for variable_id, proposal in proposals_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None:
                continue
            probability = marginal.probability_for(TRUE_STATE.id)
            if probability < 0.5:
                continue
            document.store.add_fact_resolution_claim(
                FactResolutionClaim(
                    id=document.store.next_fact_resolution_claim_id(),
                    left_fact_id=proposal.left_fact_id,
                    right_fact_id=proposal.right_fact_id,
                    relation=ResolutionRelation.SAME_FACT,
                    evidence_ids=proposal.evidence_ids,
                    assessment=self._assessment(
                        score=probability,
                        positive=proposal.retrieval_signals,
                        negative=proposal.context_signals,
                        scorer_id=ScorerId("probabilistic_fact_resolution_inference_v2"),
                        explanation="same-fact posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        return result

    def _unknown_weight(self, scores: tuple[float, ...]) -> float:
        if not scores:
            return 1.0
        return max(0.05, 1.0 - max(scores))

    def _normalize(self, weights: tuple[float, ...]) -> tuple[float, ...]:
        total = sum(weights)
        if total <= 0.0:
            return tuple(1.0 / len(weights) for _ in weights)
        return tuple(weight / total for weight in weights)

    def _assessment(
        self,
        *,
        score: float,
        positive: tuple[Signal, ...],
        negative: tuple[Signal, ...],
        scorer_id: ScorerId,
        explanation: str,
    ) -> Assessment:
        return Assessment(
            score=round(score, 3),
            positive_signals=tuple(
                signal for signal in positive if signal.polarity is SignalPolarity.POSITIVE
            ),
            negative_signals=tuple(
                signal for signal in negative if signal.polarity is SignalPolarity.NEGATIVE
            ),
            scorer_id=scorer_id,
            explanation=explanation,
        )
