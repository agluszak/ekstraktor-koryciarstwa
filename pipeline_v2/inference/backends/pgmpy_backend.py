from __future__ import annotations

import math
from dataclasses import dataclass

from pipeline_v2.ids import InferenceFactorId, InferenceVariableId
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.graph_spec import (
    InferenceDiagnostic,
    InferenceFactor,
    InferenceGraphSpec,
    InferenceResult,
    InferenceVariable,
    StateProbability,
    VariableMarginal,
)


@dataclass(frozen=True, slots=True)
class PgmpyInferenceBackend(InferenceBackend):
    """pgmpy adapter kept behind V2's typed inference facade."""

    show_progress: bool = False
    minimum_potential: float = 1e-6

    def run(self, spec: InferenceGraphSpec) -> InferenceResult:
        if not spec.variables:
            return InferenceResult(marginals=())

        marginals: list[VariableMarginal] = []
        for component in self._components(spec):
            component_result = self._run_component(
                variables=component.variables,
                factors=component.factors,
            )
            marginals.extend(component_result.marginals)
        return InferenceResult(
            marginals=tuple(marginals),
            diagnostics=(InferenceDiagnostic(message="pgmpy belief propagation completed"),),
        )

    def _run_component(
        self,
        *,
        variables: tuple[InferenceVariable, ...],
        factors: tuple[InferenceFactor, ...],
    ) -> InferenceResult:
        if not factors:
            return InferenceResult(
                marginals=tuple(self._uniform_marginal(variable) for variable in variables)
            )

        from pgmpy.factors.discrete import DiscreteFactor
        from pgmpy.inference import BeliefPropagation
        from pgmpy.models import FactorGraph

        variables_by_id = {variable.id: variable for variable in variables}
        variable_names = {variable.id: str(variable.id) for variable in variables}
        model = FactorGraph()
        model.add_nodes_from(variable_names.values())
        for factor in factors:
            variable_name_list = [
                variable_names[variable_id] for variable_id in factor.variable_ids
            ]
            cardinalities = [
                len(variables_by_id[variable_id].states) for variable_id in factor.variable_ids
            ]
            discrete_factor = DiscreteFactor(
                variables=variable_name_list,
                cardinality=cardinalities,
                values=list(self._sanitize_potentials(factor.potentials)),
            )
            model.add_factors(discrete_factor)
            for variable_name in variable_name_list:
                model.add_edge(variable_name, discrete_factor)
        model.check_model()

        inference = BeliefPropagation(model)
        marginals: list[VariableMarginal] = []
        for variable in variables:
            pgmpy_factor = inference.query(
                variables=[variable_names[variable.id]],
                show_progress=self.show_progress,
            )
            flat_values = pgmpy_factor.values.reshape(-1)
            normalized = self._normalize_probabilities(flat_values, len(variable.states))
            probabilities = tuple(
                StateProbability(state_id=state.id, probability=normalized[index])
                for index, state in enumerate(variable.states)
            )
            marginals.append(VariableMarginal(variable_id=variable.id, probabilities=probabilities))
        return InferenceResult(marginals=tuple(marginals))

    def _sanitize_potentials(self, potentials: tuple[float, ...]) -> tuple[float, ...]:
        if not potentials:
            return ()
        sanitized = [
            self.minimum_potential
            if not math.isfinite(value) or value <= 0.0
            else float(value)
            for value in potentials
        ]
        return tuple(sanitized)

    def _normalize_probabilities(
        self,
        values,
        state_count: int,
    ) -> tuple[float, ...]:
        flattened = [float(value) for value in values]
        if not flattened:
            return tuple()
        if not all(math.isfinite(value) for value in flattened):
            return tuple(1.0 / state_count for _ in range(state_count))
        total = sum(flattened)
        if total <= 0.0:
            return tuple(1.0 / state_count for _ in range(state_count))
        return tuple(value / total for value in flattened)

    def _uniform_marginal(self, variable: InferenceVariable) -> VariableMarginal:
        probability = 1.0 / len(variable.states)
        return VariableMarginal(
            variable_id=variable.id,
            probabilities=tuple(
                StateProbability(state_id=state.id, probability=probability)
                for state in variable.states
            ),
        )

    def _components(self, spec: InferenceGraphSpec) -> tuple["_InferenceComponent", ...]:
        variables_by_id = {variable.id: variable for variable in spec.variables}
        factors_by_id = {factor.id: factor for factor in spec.factors}
        variable_to_factor_ids: dict[InferenceVariableId, set[InferenceFactorId]] = {
            variable.id: set() for variable in spec.variables
        }
        factor_to_variable_ids: dict[InferenceFactorId, set[InferenceVariableId]] = {}
        for factor in spec.factors:
            factor_to_variable_ids[factor.id] = set(factor.variable_ids)
            for variable_id in factor.variable_ids:
                variable_to_factor_ids.setdefault(variable_id, set()).add(factor.id)

        remaining = set(variables_by_id)
        components: list[_InferenceComponent] = []
        while remaining:
            start = remaining.pop()
            component_variable_ids = {start}
            component_factor_ids: set[InferenceFactorId] = set()
            queue = [start]
            while queue:
                variable_id = queue.pop()
                for factor_id in variable_to_factor_ids.get(variable_id, set()):
                    component_factor_ids.add(factor_id)
                    for neighbor_id in factor_to_variable_ids.get(factor_id, set()):
                        if neighbor_id in component_variable_ids:
                            continue
                        component_variable_ids.add(neighbor_id)
                        remaining.discard(neighbor_id)
                        queue.append(neighbor_id)
            components.append(
                _InferenceComponent(
                    variables=tuple(
                        variables_by_id[variable_id] for variable_id in component_variable_ids
                    ),
                    factors=tuple(factors_by_id[factor_id] for factor_id in component_factor_ids),
                )
            )
        return tuple(components)


@dataclass(frozen=True, slots=True)
class _InferenceComponent:
    variables: tuple[InferenceVariable, ...]
    factors: tuple[InferenceFactor, ...]
