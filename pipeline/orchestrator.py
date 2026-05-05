from __future__ import annotations

import time
from collections.abc import Sequence

from pipeline.base import DocumentStage, Preprocessor
from pipeline.models import (
    ExtractionResult,
    PipelineInput,
    extraction_result_from_document,
)


class NepotismPipeline:
    def __init__(
        self,
        *,
        preprocessor: Preprocessor,
        stages: Sequence[DocumentStage],
    ) -> None:
        self.preprocessor = preprocessor
        self.stages = list(stages)

    def run(self, data: PipelineInput) -> ExtractionResult:
        t0 = time.perf_counter()
        document = self.preprocessor.run(data)
        document.raw_html = ""  # free raw HTML memory
        document.execution_times["preprocessor"] = time.perf_counter() - t0

        for stage in self.stages:
            # Skip subsequent stages if document is determined irrelevant
            if document.relevance is not None and not document.relevance.is_relevant:
                break

            t0 = time.perf_counter()
            document = stage.run(document)
            document.execution_times[stage.name()] = time.perf_counter() - t0

        return extraction_result_from_document(document)
