from __future__ import annotations

from pipeline.base import FactExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_registry import DomainRegistry, build_default_domain_registry
from pipeline.extraction_context import ExtractionContext, FactExtractionContext, SentenceContext
from pipeline.models import ArticleDocument, Fact
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.relations.candidate_graph import CandidateGraphBuilder


class PolishFactExtractor(FactExtractor):
    def __init__(
        self,
        config: PipelineConfig,
        registry: DomainRegistry | None = None,
    ) -> None:
        self.config = config
        self.graph_builder = CandidateGraphBuilder(config)
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self.registry = registry or build_default_domain_registry(config)

    def name(self) -> str:
        return "polish_fact_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        candidate_graph = self.graph_builder.build(
            document=document,
            parsed_sentences=document.parsed_sentences,
        )
        extraction_context = ExtractionContext.build(document)
        fact_context = FactExtractionContext.build(candidate_graph)
        facts: list[Fact] = list(document.facts)
        for sentence in document.sentences:
            sentence_candidates = fact_context.sentence_candidates(sentence.sentence_index)
            if not sentence_candidates:
                continue
            context = SentenceContext(
                document=document,
                sentence=sentence,
                parsed_words=document.parsed_sentences.get(sentence.sentence_index, []),
                graph=candidate_graph,
                candidates=sentence_candidates,
                paragraph_candidates=fact_context.paragraph_candidates(sentence.paragraph_index),
                previous_candidates=fact_context.previous_sentence_candidates(
                    paragraph_index=sentence.paragraph_index,
                    sentence_index=sentence.sentence_index,
                ),
            )
            for extractor in self.registry.sentence_fact_extractors:
                facts.extend(extractor.extract(context))

        for builder in self.registry.document_fact_builders:
            facts.extend(builder.build(document, extraction_context))
        for builder in self.registry.graph_fact_builders:
            facts.extend(builder.build(document, extraction_context, fact_context))

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
