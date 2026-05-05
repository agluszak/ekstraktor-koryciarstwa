"""Rule-based entity disambiguator backed by embeddings and token overlap."""

from __future__ import annotations

import numpy as np

from pipeline.base import EntityDisambiguator
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.linking_kb import token_bases_for
from pipeline.models import (
    ArticleDocument,
    Entity,
    EntityCluster,
    EntityFingerprint,
    KBEntityRecord,
)
from pipeline.runtime import PipelineRuntime


class RuleBasedEntityDisambiguator(EntityDisambiguator):
    """Scores KB candidates using token overlap, lemmas, and cosine similarity."""

    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime) -> None:
        self.config = config
        self.runtime = runtime

    # ------------------------------------------------------------------
    # EntityDisambiguator ABC
    # ------------------------------------------------------------------

    def score(
        self,
        cluster: EntityCluster,
        candidate: KBEntityRecord,
        document: ArticleDocument,
    ) -> float:
        """Score a KB candidate record against a document cluster."""
        current_fp: EntityFingerprint = {
            "normalized_name": cluster.normalized_name,
            "name_tokens": cluster.normalized_name.split(),
            "lemmas": cluster.lemmas,
        }
        current_embedding = self.encode_embedding(cluster.normalized_name.strip())
        stored_embedding = candidate.embedding
        return self.match_score(
            cluster.entity_type,
            current_fp,
            candidate.normalized_name.split(),
            candidate.lemmas,
            current_embedding,
            stored_embedding,
        )

    # ------------------------------------------------------------------
    # Scoring helpers (also called directly by the orchestrator)
    # ------------------------------------------------------------------

    def score_entity_against_entry(
        self,
        entity: Entity,
        current_fp: EntityFingerprint,
        stored_fp: EntityFingerprint,
        current_embedding: np.ndarray,
        stored_embedding: list[float],
    ) -> float:
        """Score a raw registry entry against an entity fingerprint."""
        return self._match_score(
            entity.entity_type,
            current_fp,
            stored_fp,
            current_embedding,
            stored_embedding,
        )

    def match_score(
        self,
        entity_type: EntityType,
        current_fp: EntityFingerprint,
        stored_tokens: list[str],
        stored_lemmas: list[str],
        current_embedding: np.ndarray,
        stored_embedding: list[float],
    ) -> float:
        """Public interface for scoring: takes pre-split stored tokens/lemmas."""
        stored_fp: EntityFingerprint = {
            "name_tokens": stored_tokens,
            "lemmas": stored_lemmas,
        }
        return self._match_score(
            entity_type, current_fp, stored_fp, current_embedding, stored_embedding
        )

    def _match_score(
        self,
        entity_type: EntityType,
        current: EntityFingerprint,
        stored: EntityFingerprint,
        current_embedding: np.ndarray,
        stored_embedding: list[float],
    ) -> float:
        current_tokens = current.get("name_tokens", [])
        stored_tokens = stored.get("name_tokens", [])
        if current_tokens == stored_tokens:
            return 1.0

        if entity_type == EntityType.PERSON:
            if not current_tokens or not stored_tokens:
                return 0.0
            if current_tokens[-1] != stored_tokens[-1]:
                return 0.0
            if len(current_tokens) != len(stored_tokens):
                return 0.0
            if current_tokens[:-1] != stored_tokens[:-1]:
                return 0.0
        else:
            current_lemmas = set(current.get("lemmas", []))
            stored_lemmas = set(stored.get("lemmas", []))
            if current_lemmas and stored_lemmas and current_lemmas == stored_lemmas:
                return 1.0
            if entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                current_bases = token_bases_for(current_tokens)
                stored_bases = token_bases_for(stored_tokens)
                overlap = current_bases & stored_bases
                shorter_length = min(len(current_bases), len(stored_bases))
                if shorter_length <= 2 and current_bases != stored_bases:
                    return 0.0
                if shorter_length >= 3 and len(overlap) < 3:
                    return 0.0

        if not stored_embedding:
            return 0.0
        return float(sum(a * b for a, b in zip(current_embedding, stored_embedding, strict=False)))

    def encode_embedding(self, text: str) -> np.ndarray:
        model = self.runtime.get_sentence_transformer_model()
        return model.encode(text, normalize_embeddings=True)

    @staticmethod
    def embedding_text_from_entity(entity: Entity) -> str:
        return entity.normalized_name.strip()

    @staticmethod
    def embedding_text_from_cluster(cluster: EntityCluster) -> str:
        return cluster.normalized_name.strip()

    @staticmethod
    def registry_types_compatible(entity_type: str, match_type: str) -> bool:
        if entity_type == match_type:
            return True
        return {entity_type, match_type} <= {
            EntityType.ORGANIZATION.value,
            EntityType.PUBLIC_INSTITUTION.value,
        }
