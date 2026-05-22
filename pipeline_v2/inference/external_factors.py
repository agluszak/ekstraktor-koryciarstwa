from __future__ import annotations

from typing import Protocol

from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.graph_spec import InferenceFactor, InferenceGraphSpec


class ExternalInferenceFactorBuilder(Protocol):
    """Typed extension seam for optional RAG/LLM/semantic factor producers.

    Implementations may support or oppose existing V2 inference variables, but they
    must return normal `InferenceFactor` records. They must not emit materialized
    facts or provider-specific payloads.
    """

    def build(
        self,
        *,
        document: ArticleDocument,
        spec: InferenceGraphSpec,
    ) -> tuple[InferenceFactor, ...]: ...
