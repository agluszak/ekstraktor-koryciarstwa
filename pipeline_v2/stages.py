from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from pipeline_v2.document import (
    ArticleDocument,
    ExtractionResult,
    PipelineInput,
    StageDiagnostic,
    StageDiagnosticStatus,
    extraction_result_from_document,
)


class Preprocessor(Protocol):
    def name(self) -> str: ...

    def run(self, data: PipelineInput) -> ArticleDocument: ...


class DocumentStage(Protocol):
    def name(self) -> str: ...

    def run(self, document: ArticleDocument) -> ArticleDocument: ...


class DiagnosticStage:
    def __init__(
        self,
        *,
        stage_name: str,
        status: StageDiagnosticStatus,
        reason: str,
    ) -> None:
        self._stage_name = stage_name
        self.status = status
        self.reason = reason

    def name(self) -> str:
        return self._stage_name

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.stage_diagnostics.append(
            StageDiagnostic(
                stage_name=self._stage_name,
                status=self.status,
                reason=self.reason,
            )
        )
        return document


class V2Pipeline:
    def __init__(
        self,
        *,
        preprocessor: Preprocessor,
        stages: tuple[DocumentStage, ...],
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.preprocessor = preprocessor
        self.stages = stages
        self.timer = timer

    def run(self, data: PipelineInput) -> ExtractionResult:
        return extraction_result_from_document(self.run_document(data))

    def run_document(self, data: PipelineInput) -> ArticleDocument:
        started_at = self.timer()
        document = self.preprocessor.run(data)
        document.execution_times[self.preprocessor.name()] = self.timer() - started_at

        for stage in self.stages:
            if document.relevance is not None and not document.relevance.is_relevant:
                break
            started_at = self.timer()
            document = stage.run(document)
            document.execution_times[stage.name()] = self.timer() - started_at

        return document
