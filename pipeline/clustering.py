from __future__ import annotations

import uuid
from typing import cast

from pipeline.base import EntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityAttributes, EntityType
from pipeline.models import ArticleDocument, ClusterMention, Entity, EntityCluster
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
                cluster_id = f"cluster-{uuid.uuid4().hex[:8]}"
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

                m_start = mention.attributes.get("start_char", 0)
                m_end = mention.attributes.get("end_char", 0)
                m_para = mention.attributes.get("paragraph_index", 0)

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
        temp_entity = Entity(
            entity_id=cluster.cluster_id,
            entity_type=cluster.entity_type,
            canonical_name=cluster.canonical_name,
            normalized_name=cluster.normalized_name,
            aliases=list(cluster.attributes.get("aliases", [])),
            attributes=cast(EntityAttributes, cluster.attributes),
        )
        return self.canonicalizer._entities_compatible(entity, temp_entity)

    def _create_cluster(self, cluster_id: str, entity: Entity) -> EntityCluster:
        mentions = []
        # Add mentions from entity evidence
        for evidence in entity.evidence:
            mentions.append(
                ClusterMention(
                    text=evidence.text,
                    entity_type=entity.entity_type,
                    sentence_index=evidence.sentence_index or 0,
                    paragraph_index=evidence.paragraph_index or 0,
                    start_char=evidence.start_char or 0,
                    end_char=evidence.end_char or 0,
                    entity_id=entity.entity_id,
                )
            )

        return EntityCluster(
            cluster_id=cluster_id,
            entity_type=entity.entity_type,
            canonical_name=entity.canonical_name,
            normalized_name=entity.normalized_name,
            mentions=mentions,
            attributes={
                "aliases": entity.aliases,
                "lemmas": entity.attributes.get("lemmas", []),
                "organization_kind": entity.attributes.get("organization_kind"),
            },
        )

    def _add_to_cluster(self, cluster: EntityCluster, entity: Entity) -> None:
        all_names = unique_preserve_order(
            [
                cluster.canonical_name,
                *cluster.attributes.get("aliases", []),
                entity.canonical_name,
                *entity.aliases,
            ]
        )

        if cluster.entity_type == EntityType.PERSON:
            cluster.canonical_name = self.canonicalizer._best_person_name(all_names)
        elif cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            cluster.canonical_name = self.canonicalizer._best_organization_name(entity, all_names)

        cluster.normalized_name = cluster.canonical_name
        cluster.attributes["aliases"] = all_names

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
                        paragraph_index=evidence.paragraph_index or 0,
                        start_char=evidence.start_char or 0,
                        end_char=evidence.end_char or 0,
                        entity_id=entity.entity_id,
                    )
                )
