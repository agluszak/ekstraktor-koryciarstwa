from __future__ import annotations

from typing import cast

from pipeline.base import FactExtractor
from pipeline.compensation import CompensationFactBuilder
from pipeline.config import PipelineConfig
from pipeline.domain_types import CandidateType, FactAttributes, FactType, TimeScope
from pipeline.funding import FundingFactBuilder
from pipeline.governance import GovernanceFactBuilder
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    CoreferenceResult,
    EntityCandidate,
    EvidenceSpan,
    Fact,
)
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.utils import stable_id

from .candidate_graph import CandidateGraphBuilder
from .fact_extractors import (
    PoliticalProfileFactExtractor,
    SentenceContext,
    TieFactExtractor,
)


class PolishFactExtractor(FactExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.graph_builder = CandidateGraphBuilder(config)
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self.governance_fact_builder = GovernanceFactBuilder()
        self.compensation_fact_builder = CompensationFactBuilder()
        self.funding_fact_builder = FundingFactBuilder()
        self.fact_extractors = [
            PoliticalProfileFactExtractor(),
            TieFactExtractor(),
        ]

    def name(self) -> str:
        return "polish_fact_extractor"

    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        candidate_graph = self.graph_builder.build(
            document=document,
            coreference=coreference,
            parsed_sentences=document.parsed_sentences,
        )
        facts: list[Fact] = list(document.facts)
        for sentence in document.sentences:
            sentence_candidates = [
                candidate
                for candidate in candidate_graph.candidates
                if candidate.sentence_index == sentence.sentence_index
            ]
            if not sentence_candidates:
                continue
            paragraph_candidates = [
                candidate
                for candidate in candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
            ]
            previous_candidates = [
                candidate
                for candidate in candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
                and candidate.sentence_index == sentence.sentence_index - 1
            ]
            context = SentenceContext(
                document=document,
                sentence=sentence,
                parsed_words=document.parsed_sentences.get(sentence.sentence_index, []),
                graph=candidate_graph,
                candidates=sentence_candidates,
                paragraph_candidates=paragraph_candidates,
                previous_candidates=previous_candidates,
            )
            for extractor in self.fact_extractors:
                facts.extend(extractor.extract(context))

        facts.extend(self.governance_fact_builder.build(document))
        facts.extend(self.compensation_fact_builder.build(document))
        facts.extend(self.funding_fact_builder.build(document))
        facts.extend(self._cross_sentence_party_facts(document, candidate_graph))

        document.facts = self._deduplicate_facts(facts)
        return self.canonicalizer.run(document)

    @staticmethod
    def _cross_sentence_party_facts(
        document: ArticleDocument,
        candidate_graph: CandidateGraph,
    ) -> list[Fact]:
        candidates_by_sentence: dict[int, list[EntityCandidate]] = {}
        for candidate in candidate_graph.candidates:
            candidates_by_sentence.setdefault(candidate.sentence_index, []).append(candidate)

        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_candidates = candidates_by_sentence.get(sentence.sentence_index, [])
            parties = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == CandidateType.POLITICAL_PARTY
                and candidate.entity_id is not None
            ]
            if not parties:
                continue
            lowered = sentence.text.lower()
            if not any(
                marker in lowered for marker in ("działacz", "polityk", "radn", "lider", "członk")
            ):
                continue
            if any(
                candidate.candidate_type == CandidateType.PERSON
                for candidate in sentence_candidates
            ):
                continue
            next_sentence = next(
                (
                    candidate_sentence
                    for candidate_sentence in document.sentences
                    if candidate_sentence.sentence_index == sentence.sentence_index + 1
                ),
                None,
            )
            if (
                next_sentence is None
                or next_sentence.paragraph_index - sentence.paragraph_index > 1
            ):
                continue
            persons = [
                candidate
                for candidate in candidates_by_sentence.get(next_sentence.sentence_index, [])
                if candidate.candidate_type == CandidateType.PERSON
                and candidate.entity_id is not None
                and candidate.start_char <= 20
            ]
            if not persons:
                continue
            person = min(persons, key=lambda candidate: candidate.start_char)
            for party in parties:
                facts.append(
                    Fact(
                        fact_id=stable_id(
                            "fact",
                            document.document_id,
                            FactType.PARTY_MEMBERSHIP,
                            person.entity_id or "",
                            party.entity_id or "",
                            str(sentence.sentence_index),
                        ),
                        fact_type=FactType.PARTY_MEMBERSHIP,
                        subject_entity_id=person.entity_id or "",
                        object_entity_id=party.entity_id,
                        value_text=party.canonical_name,
                        value_normalized=party.normalized_name,
                        time_scope=TimeScope.CURRENT,
                        event_date=document.publication_date,
                        confidence=0.68,
                        evidence=EvidenceSpan(
                            text=f"{sentence.text} {next_sentence.text}",
                            sentence_index=next_sentence.sentence_index,
                            paragraph_index=next_sentence.paragraph_index,
                            start_char=sentence.start_char,
                            end_char=next_sentence.end_char,
                        ),
                        attributes=cast(
                            FactAttributes,
                            {
                                "source_extractor": "political_profile",
                                "extraction_signal": "discourse_window",
                                "evidence_scope": "adjacent_sentence",
                                "party": party.canonical_name,
                            },
                        ),
                    )
                )
        return facts

    @staticmethod
    def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str, str | None, str | None, str], Fact] = {}
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
