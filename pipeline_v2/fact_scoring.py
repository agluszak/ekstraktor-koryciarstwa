from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.stage import ProbabilisticInferenceStage


class FactScoringStage:
    def __init__(self, backend: InferenceBackend | None = None) -> None:
        self.stage = ProbabilisticInferenceStage(backend=backend)

    def name(self) -> str:
        return "fact_scoring_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        return self.stage.run(document)
