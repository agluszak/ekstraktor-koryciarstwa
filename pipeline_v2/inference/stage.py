from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.backends.hybrid_backend import HybridInferenceBackend
from pipeline_v2.inference.components import BuiltInferenceComponents, InferenceComponentBuilder
from pipeline_v2.inference.external_factors import ExternalInferenceFactorBuilder
from pipeline_v2.inference.factor_builders import FactInferenceGraphBuilder
from pipeline_v2.inference.graph_spec import (
    InferenceDiagnostic,
    InferenceGraphSpec,
    InferenceResult,
)
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
    component_builder: InferenceComponentBuilder | None = None
    external_factor_builders: tuple[ExternalInferenceFactorBuilder, ...] = ()

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
        external_factors = tuple(
            factor
            for factor_builder in self.external_factor_builders
            for factor in factor_builder.build(document=document, spec=combined_spec)
        )
        if external_factors:
            combined_spec = InferenceGraphSpec(
                variables=combined_spec.variables,
                factors=(*combined_spec.factors, *external_factors),
            )
        component_builder = self.component_builder or InferenceComponentBuilder()
        built_components = component_builder.build(combined_spec)
        backend = self.backend or HybridInferenceBackend()
        result = self._run_components(backend=backend, built_components=built_components)
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

    def _run_components(
        self,
        *,
        backend: InferenceBackend,
        built_components: BuiltInferenceComponents,
    ) -> InferenceResult:
        marginals = []
        diagnostics = []
        approximate_components = 0
        exact_components = 0
        largest_variable_count = 0
        for component in built_components.components:
            largest_variable_count = max(largest_variable_count, len(component.spec.variables))
            component_result = backend.run(component.spec)
            marginals.extend(component_result.marginals)
            diagnostics.extend(component_result.diagnostics)
            used_approximate = any(
                diagnostic.message == "hybrid backend mode: approximate"
                for diagnostic in component_result.diagnostics
            )
            used_exact = any(
                diagnostic.message == "hybrid backend mode: exact"
                for diagnostic in component_result.diagnostics
            )
            if used_approximate:
                approximate_components += 1
            if used_exact:
                exact_components += 1
        diagnostics.extend(
            (
                InferenceDiagnostic(
                    message=f"inference total component count: {len(built_components.components)}"
                ),
                InferenceDiagnostic(message=f"inference exact component count: {exact_components}"),
                InferenceDiagnostic(
                    message=f"inference fallback component count: {approximate_components}"
                ),
                InferenceDiagnostic(
                    message=f"inference largest variable count: {largest_variable_count}"
                ),
            )
        )
        return InferenceResult(marginals=tuple(marginals), diagnostics=tuple(diagnostics))
