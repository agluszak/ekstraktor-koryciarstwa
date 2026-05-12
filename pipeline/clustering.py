from __future__ import annotations

import uuid

import numpy as np

from pipeline.base import EntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import ClusterID, EntityID, EntityType
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    Mention,
)
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime
from pipeline.utils import unique_preserve_order


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

        for entity in document.entities:
            self.canonicalizer.normalize_entity(entity)

        self.canonicalizer.ambiguous_person_singletons = self.canonicalizer.ambiguous_person_names(
            document.entities
        )

        clusters: list[EntityCluster] = []
        entity_to_cluster_id: dict[EntityID, ClusterID] = {}
        entities_by_id = {entity.entity_id: entity for entity in document.entities}

        for entity in document.entities:
            match = next(
                (
                    cluster
                    for cluster in clusters
                    if self._entity_matches_cluster(entity, cluster, entities_by_id)
                ),
                None,
            )

            if match is None:
                cluster_id = ClusterID(f"cluster-{uuid.uuid4().hex[:8]}")
                cluster = self._create_cluster(cluster_id, entity)
                clusters.append(cluster)
                entity_to_cluster_id[entity.entity_id] = cluster_id
            else:
                self._add_to_cluster(match, entity, entities_by_id)
                entity_to_cluster_id[entity.entity_id] = match.cluster_id

        for mention in document.mentions:
            if mention.entity_id and mention.entity_id in entity_to_cluster_id:
                cluster_id = entity_to_cluster_id[mention.entity_id]
                cluster = next(c for c in clusters if c.cluster_id == cluster_id)

                m_start, m_end, m_para = self._mention_location(document, mention)

                existing_mention = next(
                    (
                        m
                        for m in cluster.mentions
                        if (
                            (m.start_char == m_start and m.sentence_index == mention.sentence_index)
                            or (
                                m.text == mention.text
                                and m.sentence_index == mention.sentence_index
                                and not m.start_char
                                and not m_start
                            )
                        )
                    ),
                    None,
                )
                if existing_mention is None:
                    cluster.mentions.append(
                        ClusterMention(
                            text=mention.text,
                            entity_type=mention.entity_type,
                            sentence_index=mention.sentence_index,
                            paragraph_index=m_para,
                            start_char=m_start,
                            end_char=m_end,
                            mention_kind=mention.mention_kind,
                            entity_id=mention.entity_id,
                            ner_label=mention.ner_label,
                        )
                    )
                elif existing_mention.ner_label is None and mention.ner_label is not None:
                    existing_mention.ner_label = mention.ner_label

        document.clusters = clusters
        return document

    def _entity_matches_cluster(
        self,
        entity: Entity,
        cluster: EntityCluster,
        entities_by_id: dict[EntityID, Entity],
    ) -> bool:
        cluster_entity = self._representative_entity(cluster, entities_by_id)
        if cluster_entity is None:
            return False
        if (
            entity.is_proxy_person
            or cluster_entity.is_proxy_person
            or entity.is_honorific_person_ref
            or cluster_entity.is_honorific_person_ref
        ):
            return entity.entity_id == cluster_entity.entity_id

        if self.canonicalizer.entities_compatible(entity, cluster_entity):
            return True

        # Embedding-based fallback for organizations/institutions
        if (
            self.runtime is not None
            and entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and cluster_entity.entity_type
            in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        ):
            left_emb = self._encode_text(entity.canonical_name)
            right_emb = self._encode_text(cluster_entity.canonical_name)
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

    def _create_cluster(self, cluster_id: ClusterID, entity: Entity) -> EntityCluster:
        mentions = []
        # Add mentions from entity evidence
        for evidence in entity.evidence:
            mentions.append(
                ClusterMention(
                    text=evidence.text,
                    entity_type=entity.entity_type,
                    sentence_index=evidence.sentence_index or 0,
                    paragraph_index=0
                    if evidence.paragraph_index is None
                    else evidence.paragraph_index,
                    start_char=0 if evidence.start_char is None else evidence.start_char,
                    end_char=0 if evidence.end_char is None else evidence.end_char,
                    entity_id=entity.entity_id,
                    ner_label=None,
                )
            )

        return EntityCluster(
            cluster_id=cluster_id,
            mentions=mentions,
            primary_entity_id=entity.entity_id,
            member_entity_ids=[entity.entity_id],
        )

    def _add_to_cluster(
        self,
        cluster: EntityCluster,
        entity: Entity,
        entities_by_id: dict[EntityID, Entity],
    ) -> None:
        representative = self._representative_entity(cluster, entities_by_id)
        if representative is None:
            cluster.primary_entity_id = entity.entity_id
            representative = entity
        all_names = unique_preserve_order(
            [
                representative.canonical_name,
                *representative.aliases,
                entity.canonical_name,
                *entity.aliases,
            ]
        )

        # Merge evidence/mentions first so naming considers everything
        new_mentions = []
        for evidence in entity.evidence:
            if not any(
                m.start_char == evidence.start_char and m.sentence_index == evidence.sentence_index
                for m in cluster.mentions
            ):
                new_mentions.append(
                    ClusterMention(
                        text=evidence.text,
                        entity_type=entity.entity_type,
                        sentence_index=evidence.sentence_index or 0,
                        paragraph_index=0
                        if evidence.paragraph_index is None
                        else evidence.paragraph_index,
                        start_char=0 if evidence.start_char is None else evidence.start_char,
                        end_char=0 if evidence.end_char is None else evidence.end_char,
                        entity_id=entity.entity_id,
                        ner_label=None,
                    )
                )
        cluster.mentions.extend(new_mentions)
        if entity.entity_id not in cluster.member_entity_ids:
            cluster.member_entity_ids.append(entity.entity_id)
        representative.aliases = all_names

        # Create a representative entity for naming policy
        representative_entity = Entity(
            entity_id=EntityID(str(cluster.cluster_id)),
            entity_type=representative.entity_type,
            canonical_name=representative.canonical_name,
            normalized_name=representative.normalized_name,
            aliases=all_names,
            lemmas=unique_preserve_order([*representative.lemmas, *entity.lemmas]),
            evidence=[
                EvidenceSpan(
                    text=m.text,
                    sentence_index=m.sentence_index,
                    paragraph_index=m.paragraph_index,
                    start_char=m.start_char,
                    end_char=m.end_char,
                )
                for m in cluster.mentions
            ],
        )

        if representative.entity_type == EntityType.PERSON:
            representative.canonical_name = self.canonicalizer.best_person_name(all_names)
        elif representative.entity_type == EntityType.LOCATION:
            representative.canonical_name = self.canonicalizer.location_naming.best_location_name(
                all_names
            )
        elif representative.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            representative.canonical_name = self.canonicalizer.best_organization_name(
                representative_entity, all_names
            )

        representative.normalized_name = representative.canonical_name
        representative.lemmas = representative_entity.lemmas

        if representative.role_kind is None:
            representative.role_kind = entity.role_kind
        if representative.role_modifier is None:
            representative.role_modifier = entity.role_modifier

    @staticmethod
    def _representative_entity(
        cluster: EntityCluster,
        entities_by_id: dict[EntityID, Entity],
    ) -> Entity | None:
        if cluster.primary_entity_id is not None:
            entity = entities_by_id.get(cluster.primary_entity_id)
            if entity is not None:
                return entity
        for entity_id in cluster.member_entity_ids:
            entity = entities_by_id.get(entity_id)
            if entity is not None:
                return entity
        return next(
            (
                entities_by_id[mention.entity_id]
                for mention in cluster.mentions
                if mention.entity_id in entities_by_id
            ),
            None,
        )

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
