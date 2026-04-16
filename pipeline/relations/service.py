from __future__ import annotations

from typing import cast

from pipeline.base import RelationExtractor
from pipeline.compensation import CompensationFactBuilder
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    FactType,
)
from pipeline.funding import FundingFactBuilder
from pipeline.governance import GovernanceFactBuilder
from pipeline.models import (
    ArticleDocument,
    CoreferenceResult,
    Fact,
)
from pipeline.normalization import DocumentEntityCanonicalizer

from .candidate_graph import CandidateGraphBuilder
from .fact_extractors import (
    PoliticalProfileFactExtractor,
    SentenceContext,
    TieFactExtractor,
)


class PolishRuleBasedRelationExtractor(RelationExtractor):
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
        return "polish_rule_based_relation_extractor"

    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        document.candidate_graph = self.graph_builder.build(
            document=document,
            coreference=coreference,
            parsed_sentences=document.parsed_sentences,
        )

        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_candidates = [
                candidate
                for candidate in document.candidate_graph.candidates
                if candidate.sentence_index == sentence.sentence_index
            ]
            if not sentence_candidates:
                continue
            paragraph_candidates = [
                candidate
                for candidate in document.candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
            ]
            previous_candidates = [
                candidate
                for candidate in document.candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
                and candidate.sentence_index == sentence.sentence_index - 1
            ]
            context = SentenceContext(
                document=document,
                sentence=sentence,
                parsed_words=document.parsed_sentences.get(sentence.sentence_index, []),
                graph=document.candidate_graph,
                candidates=sentence_candidates,
                paragraph_candidates=paragraph_candidates,
                previous_candidates=previous_candidates,
            )
            for extractor in self.fact_extractors:
                facts.extend(extractor.extract(context))

        facts.extend(self.governance_fact_builder.build(document))
        facts.extend(self.compensation_fact_builder.build(document))
        facts.extend(self.funding_fact_builder.build(document))

        document.facts = self._deduplicate_facts(facts)
        return self.canonicalizer.run(document)

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

