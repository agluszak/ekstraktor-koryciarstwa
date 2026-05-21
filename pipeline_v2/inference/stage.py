from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.backends.pgmpy_backend import PgmpyInferenceBackend
from pipeline_v2.inference.factor_builders import FactInferenceGraphBuilder
from pipeline_v2.inference.materialize import FactAssessmentMaterializer
from pipeline_v2.inference.resolution import ProbabilisticResolutionInferencer


@dataclass(slots=True)
class ProbabilisticInferenceStage:
    backend: InferenceBackend | None = None
    graph_builder: FactInferenceGraphBuilder | None = None
    materializer: FactAssessmentMaterializer | None = None
    resolution_inferencer: ProbabilisticResolutionInferencer | None = None

    def name(self) -> str:
        return "probabilistic_inference_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        builder = self.graph_builder or FactInferenceGraphBuilder()
        built_graph = builder.build(document)
        backend = self.backend or PgmpyInferenceBackend()
        result = backend.run(built_graph.spec)
        materializer = self.materializer or FactAssessmentMaterializer()
        document = materializer.materialize(
            document=document,
            built_graph=built_graph,
            result=result,
        )
        resolution_inferencer = self.resolution_inferencer or ProbabilisticResolutionInferencer()
        entity_result, reference_result, fact_result = resolution_inferencer.run(
            document=document,
            backend=backend,
        )
        document.inference_marginals = [
            *result.marginals,
            *entity_result.marginals,
            *reference_result.marginals,
            *fact_result.marginals,
        ]
        document.inference_diagnostics = [
            *result.diagnostics,
            *entity_result.diagnostics,
            *reference_result.diagnostics,
            *fact_result.diagnostics,
        ]
        return document
