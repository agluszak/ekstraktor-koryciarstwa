from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.backends.pgmpy_backend import PgmpyInferenceBackend
from pipeline_v2.inference.factor_builders import FactInferenceGraphBuilder
from pipeline_v2.inference.graph_spec import InferenceGraphSpec
from pipeline_v2.inference.materialize import FactAssessmentMaterializer
from pipeline_v2.inference.resolution import (
    ResolutionAssessmentMaterializer,
    ResolutionInferenceGraphBuilder,
)


@dataclass(slots=True)
class ProbabilisticInferenceStage:
    backend: InferenceBackend | None = None
    graph_builder: FactInferenceGraphBuilder | None = None
    materializer: FactAssessmentMaterializer | None = None
    resolution_graph_builder: ResolutionInferenceGraphBuilder | None = None
    resolution_materializer: ResolutionAssessmentMaterializer | None = None

    def name(self) -> str:
        return "probabilistic_inference_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        builder = self.graph_builder or FactInferenceGraphBuilder()
        built_graph = builder.build(document)
        resolution_graph_builder = (
            self.resolution_graph_builder or ResolutionInferenceGraphBuilder()
        )
        built_resolution_graph = resolution_graph_builder.build(
            document=document,
            fact_graph=built_graph,
        )
        combined_spec = InferenceGraphSpec(
            variables=(*built_graph.spec.variables, *built_resolution_graph.spec.variables),
            factors=(*built_graph.spec.factors, *built_resolution_graph.spec.factors),
        )
        backend = self.backend or PgmpyInferenceBackend()
        result = backend.run(combined_spec)
        resolution_materializer = self.resolution_materializer or ResolutionAssessmentMaterializer()
        document = resolution_materializer.materialize(
            document=document,
            built_graph=built_resolution_graph,
            result=result,
        )
        materializer = self.materializer or FactAssessmentMaterializer()
        document = materializer.materialize(
            document=document,
            built_graph=built_graph,
            result=result,
        )
        document.inference_marginals = list(result.marginals)
        document.inference_diagnostics = list(result.diagnostics)
        return document
