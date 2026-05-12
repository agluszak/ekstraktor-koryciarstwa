from __future__ import annotations

import numpy as np

from pipeline.base import EntityClusterer
from pipeline.config import PipelineConfig
from pipeline.document_graph import merge_entities
from pipeline.domain_types import EntityID, EntityType
from pipeline.entity_graph_remapper import EntityGraphRemapper
from pipeline.models import ArticleDocument, Entity, Mention
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime


class PolishEntityClusterer(EntityClusterer):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self._org_similarity_threshold = 0.85

    def name(self) -> str:
        return "polish_entity_clusterer"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not document.entities:
            return document

        for mention in document.mentions:
            start_char, end_char, paragraph_index = self._mention_location(document, mention)
            mention.start_char = start_char
            mention.end_char = end_char
            mention.paragraph_index = paragraph_index

        for entity in document.entities:
            self.canonicalizer.normalize_entity(entity)

        self.canonicalizer.ambiguous_person_singletons = self.canonicalizer.ambiguous_person_names(
            document.entities
        )

        remap: dict[EntityID, EntityID] = {}
        canonical_entities: list[Entity] = []
        for entity in document.entities:
            match = next(
                (
                    candidate
                    for candidate in canonical_entities
                    if self._entity_matches_entity(entity, candidate)
                ),
                None,
            )

            if match is None:
                canonical_entities.append(entity)
                continue
            remap[entity.entity_id] = match.entity_id

        if remap:
            merge_entities(document, remap, merge_fn=EntityGraphRemapper.merge_entity)

        for entity in document.entities:
            self.canonicalizer.normalize_entity(entity)
        return document

    def _entity_matches_entity(
        self,
        entity: Entity,
        candidate: Entity,
    ) -> bool:
        if (
            entity.is_proxy_person
            or candidate.is_proxy_person
            or entity.is_honorific_person_ref
            or candidate.is_honorific_person_ref
        ):
            return entity.entity_id == candidate.entity_id

        if self.canonicalizer.entities_compatible(entity, candidate):
            return True

        # Embedding-based fallback for organizations/institutions
        if (
            self.runtime is not None
            and entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and candidate.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        ):
            left_emb = self._encode_text(entity.canonical_name)
            right_emb = self._encode_text(candidate.canonical_name)
            if self._cosine_similarity(left_emb, right_emb) >= self._org_similarity_threshold:
                return True

        return False

    def _encode_text(self, text: str) -> np.ndarray:
        if self.runtime is None:
            return np.array([], dtype=float)
        return self.runtime.encode_text(text)

    @staticmethod
    def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
        if left.size == 0 or right.size == 0:
            return 0.0
        return float(np.dot(left, right))

    @staticmethod
    def _mention_location(document: ArticleDocument, mention: Mention) -> tuple[int, int, int]:
        if (
            isinstance(mention.start_char, int)
            and isinstance(mention.end_char, int)
            and isinstance(mention.paragraph_index, int)
            and mention.end_char > mention.start_char
        ):
            return mention.start_char, mention.end_char, mention.paragraph_index

        sentence = next(
            (
                sentence
                for sentence in document.sentences
                if sentence.sentence_index == mention.sentence_index
            ),
            None,
        )
        if sentence is None:
            return 0, 0, 0

        local_start = sentence.text.lower().find(mention.text.lower())
        if local_start < 0:
            tokens = [token for token in mention.text.split() if token]
            if tokens:
                local_start = sentence.text.lower().find(tokens[-1].lower())
        if local_start < 0:
            return 0, 0, sentence.paragraph_index
        abs_start = sentence.start_char + local_start
        return abs_start, abs_start + len(mention.text), sentence.paragraph_index
