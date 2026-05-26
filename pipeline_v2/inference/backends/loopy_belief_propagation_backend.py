from __future__ import annotations

import math
from dataclasses import dataclass
from functools import reduce
from operator import mul

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
class LoopyBeliefPropagationBackend(InferenceBackend):
    """Bounded sum-product inference over V2 factor graphs.

    This backend is intentionally small and deterministic. It is not exact for loopy
    graphs, but it preserves pairwise and higher-order constraint structure unlike
    independent axis-marginal fallbacks.
    """

    max_iterations: int = 100
    tolerance: float = 1e-6
    damping: float = 0.5
    minimum_potential: float = 1e-6

    def run(self, spec: InferenceGraphSpec) -> InferenceResult:
        if not spec.variables:
            return InferenceResult(marginals=())

        variables_by_id = {variable.id: variable for variable in spec.variables}
        factors_by_variable_id: dict[InferenceVariableId, list[InferenceFactorId]] = {
            variable.id: [] for variable in spec.variables
        }
        for factor in spec.factors:
            for variable_id in factor.variable_ids:
                factors_by_variable_id[variable_id].append(factor.id)

        variable_to_factor: dict[
            tuple[InferenceVariableId, InferenceFactorId], tuple[float, ...]
        ] = {}
        factor_to_variable: dict[
            tuple[InferenceFactorId, InferenceVariableId], tuple[float, ...]
        ] = {}
        for factor in spec.factors:
            cardinalities = self._factor_cardinalities(factor, variables_by_id)
            self._validate_factor_shape(factor=factor, cardinalities=cardinalities)
            for variable_id in factor.variable_ids:
                state_count = len(variables_by_id[variable_id].states)
                uniform = tuple(1.0 / state_count for _ in range(state_count))
                variable_to_factor[(variable_id, factor.id)] = uniform
                factor_to_variable[(factor.id, variable_id)] = uniform

        converged = False
        max_delta = 0.0
        iterations = 0
        for iteration in range(1, self.max_iterations + 1):
            iterations = iteration
            max_delta = 0.0
            new_factor_to_variable: dict[
                tuple[InferenceFactorId, InferenceVariableId], tuple[float, ...]
            ] = {}
            for factor in spec.factors:
                cardinalities = self._factor_cardinalities(factor, variables_by_id)
                sanitized = self._sanitize_potentials(factor.potentials)
                for axis, variable_id in enumerate(factor.variable_ids):
                    message = self._factor_message(
                        factor=factor,
                        potentials=sanitized,
                        cardinalities=cardinalities,
                        axis=axis,
                        incoming=variable_to_factor,
                    )
                    key = (factor.id, variable_id)
                    damped = self._damped_message(factor_to_variable[key], message)
                    new_factor_to_variable[key] = damped
                    max_delta = max(max_delta, self._max_abs_delta(factor_to_variable[key], damped))
            factor_to_variable = new_factor_to_variable

            new_variable_to_factor: dict[
                tuple[InferenceVariableId, InferenceFactorId], tuple[float, ...]
            ] = {}
            for variable in spec.variables:
                neighboring_factor_ids = factors_by_variable_id[variable.id]
                for target_factor_id in neighboring_factor_ids:
                    incoming_messages = [
                        factor_to_variable[(factor_id, variable.id)]
                        for factor_id in neighboring_factor_ids
                        if factor_id != target_factor_id
                    ]
                    message = self._variable_message(len(variable.states), incoming_messages)
                    key = (variable.id, target_factor_id)
                    damped = self._damped_message(variable_to_factor[key], message)
                    new_variable_to_factor[key] = damped
                    max_delta = max(max_delta, self._max_abs_delta(variable_to_factor[key], damped))
            variable_to_factor = new_variable_to_factor

            if max_delta <= self.tolerance:
                converged = True
                break

        marginals: list[VariableMarginal] = []
        for variable in spec.variables:
            incoming_messages = [
                factor_to_variable[(factor_id, variable.id)]
                for factor_id in factors_by_variable_id[variable.id]
            ]
            probabilities = self._variable_message(len(variable.states), incoming_messages)
            marginals.append(
                VariableMarginal(
                    variable_id=variable.id,
                    probabilities=tuple(
                        StateProbability(state_id=state.id, probability=probabilities[index])
                        for index, state in enumerate(variable.states)
                    ),
                )
            )

        return InferenceResult(
            marginals=tuple(marginals),
            diagnostics=(
                InferenceDiagnostic(message="backend mode: loopy_belief_propagation"),
                InferenceDiagnostic(message=f"loopy bp converged: {converged}"),
                InferenceDiagnostic(message=f"loopy bp iterations: {iterations}"),
                InferenceDiagnostic(message=f"loopy bp max delta: {max_delta:.6g}"),
            ),
        )

    def _factor_message(
        self,
        *,
        factor: InferenceFactor,
        potentials: tuple[float, ...],
        cardinalities: tuple[int, ...],
        axis: int,
        incoming: dict[tuple[InferenceVariableId, InferenceFactorId], tuple[float, ...]],
    ) -> tuple[float, ...]:
        output = [0.0 for _ in range(cardinalities[axis])]
        for flat_index, potential in enumerate(potentials):
            assignment = self._assignment_for_flat_index(flat_index, cardinalities)
            value = potential
            for other_axis, variable_id in enumerate(factor.variable_ids):
                if other_axis == axis:
                    continue
                value *= incoming[(variable_id, factor.id)][assignment[other_axis]]
            output[assignment[axis]] += value
        return self._normalize(output, cardinalities[axis])

    def _variable_message(
        self,
        state_count: int,
        incoming_messages: list[tuple[float, ...]],
    ) -> tuple[float, ...]:
        values = [1.0 for _ in range(state_count)]
        for message in incoming_messages:
            for index, probability in enumerate(message):
                values[index] *= probability
        return self._normalize(values, state_count)

    def _factor_cardinalities(
        self,
        factor: InferenceFactor,
        variables_by_id: dict[InferenceVariableId, InferenceVariable],
    ) -> tuple[int, ...]:
        return tuple(
            len(variables_by_id[variable_id].states) for variable_id in factor.variable_ids
        )

    def _assignment_for_flat_index(
        self,
        flat_index: int,
        cardinalities: tuple[int, ...],
    ) -> tuple[int, ...]:
        assignment = []
        remainder = flat_index
        for axis, cardinality in enumerate(cardinalities):
            stride = reduce(mul, cardinalities[axis + 1 :], 1)
            assignment.append((remainder // stride) % cardinality)
        return tuple(assignment)

    def _sanitize_potentials(self, potentials: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(
            self.minimum_potential if not math.isfinite(value) or value <= 0.0 else float(value)
            for value in potentials
        )

    def _validate_factor_shape(
        self,
        *,
        factor: InferenceFactor,
        cardinalities: tuple[int, ...],
    ) -> None:
        expected_count = reduce(mul, cardinalities, 1)
        if len(factor.potentials) == expected_count:
            return
        raise ValueError(
            f"Inference factor {factor.id} has {len(factor.potentials)} potentials "
            f"for cardinalities {cardinalities}; expected {expected_count}"
        )

    def _normalize(
        self,
        values: list[float] | tuple[float, ...],
        state_count: int,
    ) -> tuple[float, ...]:
        if not values or not all(math.isfinite(value) for value in values):
            return tuple(1.0 / state_count for _ in range(state_count))
        total = sum(values)
        if total <= 0.0:
            return tuple(1.0 / state_count for _ in range(state_count))
        return tuple(value / total for value in values)

    def _damped_message(
        self,
        previous: tuple[float, ...],
        current: tuple[float, ...],
    ) -> tuple[float, ...]:
        return tuple(
            self.damping * old + (1.0 - self.damping) * new
            for old, new in zip(previous, current, strict=True)
        )

    def _max_abs_delta(self, left: tuple[float, ...], right: tuple[float, ...]) -> float:
        return max(abs(a - b) for a, b in zip(left, right, strict=True))
