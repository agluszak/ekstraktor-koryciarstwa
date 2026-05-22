from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.ids import InferenceComponentId, InferenceFactorId, InferenceVariableId
from pipeline_v2.inference.graph_spec import (
    InferenceGraphSpec,
)


@dataclass(frozen=True, slots=True)
class InferenceComponent:
    id: InferenceComponentId
    variable_ids: tuple[InferenceVariableId, ...]
    factor_ids: tuple[InferenceFactorId, ...]
    spec: InferenceGraphSpec


@dataclass(frozen=True, slots=True)
class BuiltInferenceComponents:
    components: tuple[InferenceComponent, ...]

    @property
    def spec(self) -> InferenceGraphSpec:
        return InferenceGraphSpec(
            variables=tuple(
                variable for component in self.components for variable in component.spec.variables
            ),
            factors=tuple(
                factor for component in self.components for factor in component.spec.factors
            ),
        )


class InferenceComponentBuilder:
    """Build inspectable V2 inference components before backend execution."""

    def build(self, spec: InferenceGraphSpec) -> BuiltInferenceComponents:
        if not spec.variables:
            return BuiltInferenceComponents(components=())

        variables_by_id = {variable.id: variable for variable in spec.variables}
        factors_by_id = {factor.id: factor for factor in spec.factors}
        variable_to_factor_ids: dict[InferenceVariableId, set[InferenceFactorId]] = {
            variable.id: set() for variable in spec.variables
        }
        factor_to_variable_ids: dict[InferenceFactorId, set[InferenceVariableId]] = {}

        for factor in spec.factors:
            variable_ids = set(factor.variable_ids)
            unknown_variable_ids = variable_ids - set(variables_by_id)
            if unknown_variable_ids:
                raise ValueError(
                    f"Inference factor {factor.id} references unknown variables "
                    f"{tuple(sorted(unknown_variable_ids))}"
                )
            factor_to_variable_ids[factor.id] = variable_ids
            for variable_id in variable_ids:
                variable_to_factor_ids[variable_id].add(factor.id)

        remaining = set(variables_by_id)
        components: list[InferenceComponent] = []
        while remaining:
            start = min(remaining)
            remaining.remove(start)
            component_variable_ids = {start}
            component_factor_ids: set[InferenceFactorId] = set()
            queue = [start]
            while queue:
                variable_id = queue.pop(0)
                for factor_id in variable_to_factor_ids[variable_id]:
                    component_factor_ids.add(factor_id)
                    for neighbor_id in factor_to_variable_ids[factor_id]:
                        if neighbor_id in component_variable_ids:
                            continue
                        component_variable_ids.add(neighbor_id)
                        remaining.discard(neighbor_id)
                        queue.append(neighbor_id)

            ordered_variable_ids = tuple(sorted(component_variable_ids))
            ordered_factor_ids = tuple(sorted(component_factor_ids))
            components.append(
                InferenceComponent(
                    id=InferenceComponentId(f"inference-component:{len(components) + 1}"),
                    variable_ids=ordered_variable_ids,
                    factor_ids=ordered_factor_ids,
                    spec=InferenceGraphSpec(
                        variables=tuple(
                            variables_by_id[variable_id] for variable_id in ordered_variable_ids
                        ),
                        factors=tuple(factors_by_id[factor_id] for factor_id in ordered_factor_ids),
                    ),
                )
            )

        return BuiltInferenceComponents(components=tuple(components))
