from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pipeline_v2.candidates import (
    ArgumentFiller,
    Assessment,
    EntityCandidate,
    EntityFiller,
    FactCandidateRecord,
    TextFiller,
    UnknownFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.graph_spec import InferenceDiagnostic, VariableMarginal
from pipeline_v2.nlp import EvidenceSpan, Mention, MorphAnalysis, ReferenceMention, Sentence, Token
from pipeline_v2.types import Signal

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


class JsonOutputWriter:
    def write(self, document: ArticleDocument, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document_to_json(document), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def document_to_json(document: ArticleDocument) -> JsonObject:
    return cast(
        JsonObject,
        {
            "document_id": str(document.document_id),
            "source_url": document.source_url,
            "title": document.title,
            "publication_date": document.publication_date,
            "relevance": relevance_to_json(document),
            "sentences": [
                sentence_to_json(sentence) for sentence in document.store.sentences.values()
            ],
            "tokens": {
                str(token_id): token_to_json(token)
                for token_id, token in document.store.tokens.items()
            },
            "mentions": [mention_to_json(mention) for mention in document.store.mentions.values()],
            "evidence": [
                evidence_to_json(evidence) for evidence in document.store.evidence.values()
            ],
            "entities": [
                entity_to_json(entity) for entity in document.store.entity_candidates.values()
            ],
            "event_candidates": [
                {
                    "id": str(event.id),
                    "kind": event.kind.value,
                    "trigger_evidence_id": (
                        str(event.trigger_evidence_id)
                        if event.trigger_evidence_id is not None
                        else None
                    ),
                    "evidence_ids": [str(evidence_id) for evidence_id in event.evidence_ids],
                    "source": str(event.source),
                    "signals": [signal_to_json(signal) for signal in event.signals],
                }
                for event in document.store.event_candidates.values()
            ],
            "argument_bindings": [
                {
                    "id": str(binding.id),
                    "event_id": str(binding.event_id),
                    "role": binding.role.value,
                    "filler": argument_filler_to_json(binding.filler),
                    "evidence_ids": [str(evidence_id) for evidence_id in binding.evidence_ids],
                    "signals": [signal_to_json(signal) for signal in binding.signals],
                }
                for bindings in document.store.argument_bindings_by_event_id.values()
                for binding in bindings
            ],
            "inference_marginals": [
                variable_marginal_to_json(marginal) for marginal in document.inference_marginals
            ],
            "inference_diagnostics": [
                inference_diagnostic_to_json(diagnostic)
                for diagnostic in document.inference_diagnostics
            ],
            "references": [
                reference_to_json(reference) for reference in document.store.references.values()
            ],
            "entity_resolution_claims": [
                {
                    "id": str(claim.id),
                    "left_entity_id": str(claim.left_entity_id),
                    "right_entity_id": str(claim.right_entity_id),
                    "relation": claim.relation.value,
                    "evidence_ids": [str(evidence_id) for evidence_id in claim.evidence_ids],
                    "assessment": assessment_to_json(claim.assessment),
                    "source": str(claim.source),
                }
                for claim in document.store.resolution_claims.values()
            ],
            "reference_resolution_proposals": [
                {
                    "reference_id": str(proposal.reference_id),
                    "candidate_entity_id": str(proposal.candidate_entity_id),
                    "evidence_ids": [str(evidence_id) for evidence_id in proposal.evidence_ids],
                    "retrieval_signals": [
                        signal.to_json() for signal in proposal.retrieval_signals
                    ],
                    "context_signals": [signal.to_json() for signal in proposal.context_signals],
                }
                for proposal in document.reference_resolution_proposals
            ],
            "reference_resolution_claims": [
                {
                    "id": str(claim.id),
                    "reference_id": str(claim.reference_id),
                    "candidate_entity_id": str(claim.candidate_entity_id),
                    "relation": claim.relation.value,
                    "evidence_ids": [str(evidence_id) for evidence_id in claim.evidence_ids],
                    "assessment": assessment_to_json(claim.assessment),
                    "source": str(claim.source),
                }
                for claim in document.store.reference_resolution_claims.values()
            ],
            "fact_resolution_claims": [
                {
                    "id": str(claim.id),
                    "left_fact_id": str(claim.left_fact_id),
                    "right_fact_id": str(claim.right_fact_id),
                    "relation": claim.relation.value,
                    "evidence_ids": [str(evidence_id) for evidence_id in claim.evidence_ids],
                    "assessment": assessment_to_json(claim.assessment),
                    "source": str(claim.source),
                }
                for claim in document.store.fact_resolution_claims.values()
            ],
            "materialized_facts": [
                fact_record_to_json(record) for record in document.materialized_fact_records
            ],
            "materialized_fact_assessments": [
                {
                    "materialized_fact_id": str(fact_assessment.materialized_fact_id),
                    "assessment": assessment_to_json(fact_assessment.assessment),
                }
                for fact_assessment in document.fact_assessments
            ],
            "stage_diagnostics": [
                {
                    "stage_name": diagnostic.stage_name,
                    "status": diagnostic.status.value,
                    "reason": diagnostic.reason,
                }
                for diagnostic in document.stage_diagnostics
            ],
            "execution_times": dict(document.execution_times),
        },
    )


def relevance_to_json(document: ArticleDocument) -> JsonObject:
    if document.relevance is None:
        return {"is_relevant": False, "score": 0.0, "reasons": []}
    return {
        "is_relevant": document.relevance.is_relevant,
        "score": document.relevance.score,
        "reasons": [signal_to_json(reason) for reason in document.relevance.reasons],
    }


def sentence_to_json(sentence: Sentence) -> JsonObject:
    return {
        "id": str(sentence.id),
        "sentence_index": sentence.sentence_index,
        "paragraph_index": sentence.paragraph_index,
        "text": sentence.text,
        "span": span_to_json(sentence.span.start_char, sentence.span.end_char),
        "token_ids": [str(token_id) for token_id in sentence.token_ids],
    }


def token_to_json(token: Token) -> JsonObject:
    return {
        "id": str(token.id),
        "text": token.text,
        "span": span_to_json(token.span.start_char, token.span.end_char),
        "morph": [morph_analysis_to_json(analysis) for analysis in token.morph],
    }


def morph_analysis_to_json(analysis: MorphAnalysis) -> JsonObject:
    return {
        "lemma": analysis.lemma,
        "pos": analysis.pos,
        "case": analysis.case,
        "gender": analysis.gender,
        "number": analysis.number,
        "person": analysis.person,
        "tag": analysis.tag,
        "labels": list(analysis.labels),
    }


def evidence_to_json(evidence: EvidenceSpan) -> JsonObject:
    return {
        "id": str(evidence.id),
        "text": evidence.text,
        "span": span_to_json(evidence.span.start_char, evidence.span.end_char),
        "sentence_id": str(evidence.sentence_id) if evidence.sentence_id is not None else None,
        "paragraph_index": evidence.paragraph_index,
        "source": evidence.source,
    }


def entity_to_json(entity: EntityCandidate) -> JsonObject:
    return {
        "id": str(entity.id),
        "kind": entity.kind.value,
        "mention_ids": [str(mention_id) for mention_id in entity.mention_ids],
        "reference_ids": [str(reference_id) for reference_id in entity.reference_ids],
        "canonical_hint": entity.canonical_hint,
        "grounding": entity.grounding.value,
        "source": str(entity.source),
    }


def argument_filler_to_json(filler: ArgumentFiller) -> JsonObject:
    match filler:
        case EntityFiller(entity_id=entity_id):
            return {"kind": "entity", "entity_id": str(entity_id)}
        case TextFiller(value=value):
            return {"kind": "text", "value": value}
        case UnknownFiller(reason=reason):
            return {"kind": "unknown", "reason": reason}


def variable_marginal_to_json(marginal: VariableMarginal) -> JsonObject:
    return {
        "variable_id": str(marginal.variable_id),
        "probabilities": [
            {
                "state_id": str(probability.state_id),
                "probability": probability.probability,
            }
            for probability in marginal.probabilities
        ],
    }


def inference_diagnostic_to_json(diagnostic: InferenceDiagnostic) -> JsonObject:
    return {"message": diagnostic.message}


def reference_to_json(reference: ReferenceMention) -> JsonObject:
    return {
        "id": str(reference.id),
        "text": reference.text,
        "kind": reference.kind.value,
        "evidence_id": str(reference.evidence_id),
        "sentence_id": str(reference.sentence_id),
        "head_lemma": reference.head_lemma,
        "modifier_lemmas": list(reference.modifier_lemmas),
        "relationship_detail": (
            reference.relationship_detail.value
            if reference.relationship_detail is not None
            else None
        ),
    }


def mention_to_json(mention: Mention) -> JsonObject:
    return {
        "id": str(mention.id),
        "text": mention.text,
        "kind": mention.kind.value,
        "evidence_id": str(mention.evidence_id),
        "sentence_id": str(mention.sentence_id),
        "head_lemma": mention.head_lemma,
        "token_ids": [str(token_id) for token_id in mention.token_ids],
    }


def assessment_to_json(assessment: Assessment) -> JsonObject:
    return {
        "score": assessment.score,
        "positive_signals": [signal_to_json(signal) for signal in assessment.positive_signals],
        "negative_signals": [signal_to_json(signal) for signal in assessment.negative_signals],
        "scorer_id": str(assessment.scorer_id),
        "explanation": assessment.explanation,
    }


def fact_record_to_json(record: FactCandidateRecord) -> JsonObject:
    return cast(
        JsonObject,
        {
            "id": str(record.id),
            "kind": record.kind.value,
            "arguments": [argument.to_json() for argument in record.arguments],
            "evidence_ids": [str(evidence_id) for evidence_id in record.evidence_ids],
            "source": str(record.source),
            "signals": [signal_to_json(signal) for signal in record.signals],
        },
    )


def signal_to_json(signal: Signal) -> JsonObject:
    return cast(JsonObject, signal.to_json())


def span_to_json(start_char: int, end_char: int) -> JsonObject:
    return {"start_char": start_char, "end_char": end_char}
