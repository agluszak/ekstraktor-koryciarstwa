from __future__ import annotations

from pipeline.base import (
    ClauseParser,
    CoreferenceResolver,
    EntityClusterer,
    EntityLinker,
    FactExtractor,
    FrameExtractor,
    NERExtractor,
    Preprocessor,
    RelevanceFilter,
    Scorer,
    Segmenter,
)
from pipeline.models import ExtractionResult, PipelineInput, extraction_result_from_document


class NepotismPipeline:
    def __init__(
        self,
        *,
        preprocessor: Preprocessor,
        relevance_filter: RelevanceFilter,
        segmenter: Segmenter,
        ner_extractor: NERExtractor,
        coreference_resolver: CoreferenceResolver,
        fact_extractor: FactExtractor,
        entity_linker: EntityLinker,
        entity_clusterer: EntityClusterer,
        clause_parser: ClauseParser,
        frame_extractor: FrameExtractor,
        scorer: Scorer,
    ) -> None:
        self.preprocessor = preprocessor
        self.relevance_filter = relevance_filter
        self.segmenter = segmenter
        self.ner_extractor = ner_extractor
        self.coreference_resolver = coreference_resolver
        self.fact_extractor = fact_extractor
        self.entity_linker = entity_linker
        self.entity_clusterer = entity_clusterer
        self.clause_parser = clause_parser
        self.frame_extractor = frame_extractor
        self.scorer = scorer

    def run(self, data: PipelineInput) -> ExtractionResult:
        document = self.preprocessor.run(data)
        document.relevance = self.relevance_filter.run(document)
        if not document.relevance.is_relevant:
            return extraction_result_from_document(document)
        document = self.segmenter.run(document)
        document = self.ner_extractor.run(document)
        coreference = self.coreference_resolver.run(document)
        if coreference.resolved_mentions:
            existing_keys = {
                (mention.text, mention.sentence_index, mention.entity_id)
                for mention in document.mentions
            }
            for mention in coreference.resolved_mentions:
                key = (mention.text, mention.sentence_index, mention.entity_id)
                if key not in existing_keys:
                    document.mentions.append(mention)
                    existing_keys.add(key)
        document = self.entity_clusterer.run(document)
        document = self.clause_parser.run(document)
        document = self.frame_extractor.run(document)
        document = self.fact_extractor.run(document, coreference)
        document = self.entity_linker.run(document)
        document = self.scorer.run(document)
        return extraction_result_from_document(document)
