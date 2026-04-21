from __future__ import annotations

from pipeline.base import (
    ClauseParser,
    CoreferenceResolver,
    EntityClusterer,
    EntityLinker,
    FactExtractor,
    FrameExtractor,
    IdentityResolver,
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
        identity_resolver: IdentityResolver,
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
        self.identity_resolver = identity_resolver
        self.frame_extractor = frame_extractor
        self.scorer = scorer

    def run(self, data: PipelineInput) -> ExtractionResult:
        import time

        t0 = time.perf_counter()
        document = self.preprocessor.run(data)
        document.execution_times["preprocessor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document.relevance = self.relevance_filter.run(document)
        document.execution_times["relevance_filter"] = time.perf_counter() - t0

        if not document.relevance.is_relevant:
            return extraction_result_from_document(document)

        t0 = time.perf_counter()
        document = self.segmenter.run(document)
        document.execution_times["segmenter"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.ner_extractor.run(document)
        document.execution_times["ner_extractor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        coreference = self.coreference_resolver.run(document)
        document.execution_times["coreference_resolver"] = time.perf_counter() - t0

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

        t0 = time.perf_counter()
        document = self.entity_clusterer.run(document)
        document.execution_times["entity_clusterer"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.clause_parser.run(document)
        document.execution_times["clause_parser"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.identity_resolver.run(document)
        document.execution_times["identity_resolver"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.frame_extractor.run(document)
        document.execution_times["frame_extractor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.fact_extractor.run(document, coreference)
        document.execution_times["fact_extractor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.entity_linker.run(document)
        document.execution_times["entity_linker"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.scorer.run(document)
        document.execution_times["scorer"] = time.perf_counter() - t0

        return extraction_result_from_document(document)
