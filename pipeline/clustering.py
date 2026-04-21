from __future__ import annotations

import uuid

from pipeline.base import EntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import ClusterID, EntityID, EntityType
from pipeline.models import ArticleDocument, ClusterMention, Entity, EntityCluster, Mention
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.utils import unique_preserve_order


class PolishEntityClusterer(EntityClusterer):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.canonicalizer = DocumentEntityCanonicalizer(config)

    def name(self) -> str:
        return "polish_entity_clusterer"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not document.entities:
            return document

        for entity in document.entities:
            self.canonicalizer._normalize_entity(entity)

        clusters: list[EntityCluster] = []
        entity_to_cluster_id: dict[str, str] = {}

        for entity in document.entities:
            match = next(
                (cluster for cluster in clusters if self._entity_matches_cluster(entity, cluster)),
                None,
            )

            if match is None:
                cluster_id = ClusterID(f"cluster-{uuid.uuid4().hex[:8]}")
                cluster = self._create_cluster(cluster_id, entity)
                clusters.append(cluster)
                entity_to_cluster_id[entity.entity_id] = cluster_id
            else:
                self._add_to_cluster(match, entity)
                entity_to_cluster_id[entity.entity_id] = match.cluster_id

        for mention in document.mentions:
            if mention.entity_id and mention.entity_id in entity_to_cluster_id:
                cluster_id = entity_to_cluster_id[mention.entity_id]
                cluster = next(c for c in clusters if c.cluster_id == cluster_id)

                m_start, m_end, m_para = self._mention_location(document, mention)

                if not any(
                    (m.start_char == m_start and m.sentence_index == mention.sentence_index)
                    or (
                        m.text == mention.text
                        and m.sentence_index == mention.sentence_index
                        and not m.start_char
                        and not m_start
                    )
                    for m in cluster.mentions
                ):
                    cluster.mentions.append(
                        ClusterMention(
                            text=mention.text,
                            entity_type=cluster.entity_type,
                            sentence_index=mention.sentence_index,
                            paragraph_index=m_para,
                            start_char=m_start,
                            end_char=m_end,
                            entity_id=mention.entity_id,
                        )
                    )

        document.clusters = clusters
        return document

    def _entity_matches_cluster(self, entity: Entity, cluster: EntityCluster) -> bool:
        if (
            entity.is_proxy_person or cluster.is_proxy_person or entity.is_honorific_person_ref
            # Note: EntityCluster doesn't have is_honorific_person_ref,
            # it was only in Entity.attributes before.
        ):
            return entity.entity_id == cluster.proxy_entity_id

        temp_entity = Entity(
            entity_id=EntityID(str(cluster.cluster_id)),
            entity_type=cluster.entity_type,
            canonical_name=cluster.canonical_name,
            normalized_name=cluster.normalized_name,
            aliases=list(cluster.aliases),
            lemmas=cluster.lemmas,
            organization_kind=cluster.organization_kind,
        )
        return self.canonicalizer._entities_compatible(entity, temp_entity)

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
                )
            )

        return EntityCluster(
            cluster_id=cluster_id,
            entity_type=entity.entity_type,
            canonical_name=entity.canonical_name,
            normalized_name=entity.normalized_name,
            mentions=mentions,
            aliases=list(entity.aliases),
            lemmas=list(entity.lemmas),
            organization_kind=entity.organization_kind,
            is_proxy_person=entity.is_proxy_person,
            proxy_entity_id=entity.entity_id if entity.is_proxy_person else None,
            proxy_kind=entity.proxy_kind,
            kinship_detail=entity.kinship_detail,
            proxy_anchor_entity_id=entity.proxy_anchor_entity_id,
            role_kind=entity.role_kind,
            role_modifier=entity.role_modifier,
        )

    def _add_to_cluster(self, cluster: EntityCluster, entity: Entity) -> None:
        all_names = unique_preserve_order(
            [
                cluster.canonical_name,
                *cluster.aliases,
                entity.canonical_name,
                *entity.aliases,
            ]
        )

        if cluster.entity_type == EntityType.PERSON:
            cluster.canonical_name = self.canonicalizer._best_person_name(all_names)
        elif cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            cluster.canonical_name = self.canonicalizer._best_organization_name(entity, all_names)

        cluster.normalized_name = cluster.canonical_name
        cluster.aliases = all_names

        for evidence in entity.evidence:
            if not any(
                m.start_char == evidence.start_char and m.sentence_index == evidence.sentence_index
                for m in cluster.mentions
            ):
                cluster.mentions.append(
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
                    )
                )

    @staticmethod
    def _mention_location(document: ArticleDocument, mention: Mention) -> tuple[int, int, int]:
        if (
            isinstance(mention.start_char, int)
            and isinstance(mention.end_char, int)
            and isinstance(mention.paragraph_index, int)
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
