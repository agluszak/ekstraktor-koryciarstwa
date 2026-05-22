from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol

from sentence_transformers import SentenceTransformer

from pipeline_v2.ids import EvidenceId

type EmbeddingVector = tuple[float, ...]


class EmbeddingProvider(Protocol):
    def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]: ...


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        encoded = self._model.encode(list(texts), convert_to_numpy=True)
        return tuple(tuple(float(value) for value in vector) for vector in encoded)


@dataclass(frozen=True, slots=True)
class SemanticEvidenceMatch:
    evidence_id: EvidenceId
    score: float


class EvidenceVectorIndex:
    def __init__(self) -> None:
        self._vectors_by_evidence_id: dict[EvidenceId, EmbeddingVector] = {}

    def add(self, evidence_id: EvidenceId, vector: EmbeddingVector) -> None:
        self._vectors_by_evidence_id[evidence_id] = self._normalize(vector)

    def vector_for(self, evidence_id: EvidenceId) -> EmbeddingVector | None:
        return self._vectors_by_evidence_id.get(evidence_id)

    def search(
        self,
        query: EmbeddingVector,
        *,
        limit: int,
        min_score: float = 0.0,
    ) -> tuple[SemanticEvidenceMatch, ...]:
        normalized_query = self._normalize(query)
        scored = [
            SemanticEvidenceMatch(
                evidence_id=evidence_id,
                score=round(self._dot_product(normalized_query, vector), 6),
            )
            for evidence_id, vector in self._vectors_by_evidence_id.items()
        ]
        filtered = [match for match in scored if match.score >= min_score]
        filtered.sort(key=lambda match: (-match.score, str(match.evidence_id)))
        return tuple(filtered[:limit])

    @staticmethod
    def _normalize(vector: EmbeddingVector) -> EmbeddingVector:
        magnitude = sqrt(sum(value * value for value in vector))
        if magnitude == 0.0:
            return vector
        return tuple(value / magnitude for value in vector)

    @staticmethod
    def _dot_product(left: EmbeddingVector, right: EmbeddingVector) -> float:
        if len(left) != len(right):
            raise ValueError(f"embedding dimensions must match, got {len(left)} and {len(right)}")
        return sum(left_value * right_value for left_value, right_value in zip(left, right))
