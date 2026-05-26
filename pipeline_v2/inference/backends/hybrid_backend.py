from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.backends.loopy_belief_propagation_backend import (
    LoopyBeliefPropagationBackend,
)
from pipeline_v2.inference.backends.pgmpy_backend import PgmpyInferenceBackend
from pipeline_v2.inference.graph_spec import (
    InferenceDiagnostic,
    InferenceGraphSpec,
    InferenceResult,
)


@dataclass(frozen=True, slots=True)
class HybridInferenceBackend(InferenceBackend):
    exact_backend: InferenceBackend = PgmpyInferenceBackend()
    approximate_backend: InferenceBackend = LoopyBeliefPropagationBackend()
    max_exact_state_space: int = 100_000
    max_exact_variables: int = 16

    def run(self, spec: InferenceGraphSpec) -> InferenceResult:
        state_space = self._state_space_size(spec)
        use_approximate = (
            state_space > self.max_exact_state_space
            or len(spec.variables) > self.max_exact_variables
        )
        backend = self.approximate_backend if use_approximate else self.exact_backend
        result = backend.run(spec)
        mode = "approximate" if use_approximate else "exact"
        return InferenceResult(
            marginals=result.marginals,
            diagnostics=(
                InferenceDiagnostic(message=f"hybrid backend mode: {mode}"),
                InferenceDiagnostic(message=f"component variable count: {len(spec.variables)}"),
                InferenceDiagnostic(message=f"component estimated state space: {state_space}"),
                *result.diagnostics,
            ),
        )

    def _state_space_size(self, spec: InferenceGraphSpec) -> int:
        size = 1
        for variable in spec.variables:
            size *= len(variable.states)
            if size > self.max_exact_state_space:
                return size
        return size
