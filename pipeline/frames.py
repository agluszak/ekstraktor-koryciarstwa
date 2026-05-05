from __future__ import annotations

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_registry import DomainRegistry, build_default_domain_registry
from pipeline.extraction_context import ExtractionContext
from pipeline.models import ArticleDocument
from pipeline.runtime import PipelineRuntime


class PolishFrameExtractor(FrameExtractor):
    def __init__(
        self,
        config: PipelineConfig,
        runtime: PipelineRuntime | None = None,
        registry: DomainRegistry | None = None,
    ) -> None:
        self.registry = registry or build_default_domain_registry(config, runtime=runtime)

    def name(self) -> str:
        return "polish_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        context = ExtractionContext.build(document)
        for extractor in self.registry.frame_extractors:
            document = extractor.run(document, context)
        return document
