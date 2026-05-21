from __future__ import annotations

from typing import Protocol

from pipeline_v2.inference.graph_spec import InferenceGraphSpec, InferenceResult


class InferenceBackend(Protocol):
    def run(self, spec: InferenceGraphSpec) -> InferenceResult: ...
