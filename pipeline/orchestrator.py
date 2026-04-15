from __future__ import annotations

from pipeline.base import (
    ClauseParser,
    CoreferenceResolver,
    EntityClusterer,
    EntityLinker,
    EventExtractor,
    FrameExtractor,
    NERExtractor,
    OutputBuilder,
    Preprocessor,
    RelationExtractor,
    RelevanceFilter,
    Scorer,
    Segmenter,
)
from pipeline.models import ExtractionResult, PipelineInput


class NepotismPipeline:
    def __init__(
        self,
        *,
        preprocessor: Preprocessor,
        relevance_filter: RelevanceFilter,
        segmenter: Segmenter,
        ner_extractor: NERExtractor,
        coreference_resolver: CoreferenceResolver,
        relation_extractor: RelationExtractor,
        event_extractor: EventExtractor,
        entity_linker: EntityLinker,
        entity_clusterer: EntityClusterer,
        clause_parser: ClauseParser,
        frame_extractor: FrameExtractor,
        scorer: Scorer,
        output_builder: OutputBuilder,
    ) -> None:
        self.preprocessor = preprocessor
        self.relevance_filter = relevance_filter
        self.segmenter = segmenter
        self.ner_extractor = ner_extractor
        self.coreference_resolver = coreference_resolver
        self.relation_extractor = relation_extractor
        self.event_extractor = event_extractor
        self.entity_linker = entity_linker
        self.entity_clusterer = entity_clusterer
        self.clause_parser = clause_parser
        self.frame_extractor = frame_extractor
        self.scorer = scorer
        self.output_builder = output_builder

    def run(self, data: PipelineInput) -> ExtractionResult:
        document = self.preprocessor.run(data)
        document.relevance = self.relevance_filter.run(document)
        if not document.relevance.is_relevant:
            return self.output_builder.run(document)
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
        document = self.relation_extractor.run(document, coreference)
        document = self.event_extractor.run(document)
        document = self.entity_linker.run(document)
        document = self.scorer.run(document)
        return self.output_builder.run(document)
