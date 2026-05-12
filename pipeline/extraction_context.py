from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import AbstractSet

from pipeline.cluster_reads import (
    aliases_for_cluster as read_aliases_for_cluster,
)
from pipeline.cluster_reads import (
    canonical_name_for_cluster as read_canonical_name_for_cluster,
)
from pipeline.cluster_reads import (
    entity_for_cluster as read_entity_for_cluster,
)
from pipeline.cluster_reads import (
    entity_type_for_cluster as read_entity_type_for_cluster,
)
from pipeline.cluster_reads import (
    is_proxy_person_cluster as read_is_proxy_person_cluster,
)
from pipeline.cluster_reads import (
    kinship_detail_for_cluster as read_kinship_detail_for_cluster,
)
from pipeline.cluster_reads import (
    lemmas_for_cluster as read_lemmas_for_cluster,
)
from pipeline.cluster_reads import (
    normalized_name_for_cluster as read_normalized_name_for_cluster,
)
from pipeline.cluster_reads import (
    organization_kind_for_cluster as read_organization_kind_for_cluster,
)
from pipeline.cluster_reads import (
    proxy_anchor_entity_id_for_cluster as read_proxy_anchor_entity_id_for_cluster,
)
from pipeline.cluster_reads import (
    proxy_kind_for_cluster as read_proxy_kind_for_cluster,
)
from pipeline.cluster_reads import (
    role_kind_for_cluster as read_role_kind_for_cluster,
)
from pipeline.cluster_reads import (
    role_modifier_for_cluster as read_role_modifier_for_cluster,
)
from pipeline.dependency_frames import DependencyFrameBuilder, TriggerArgumentFrame
from pipeline.document_graph import clause_mentions as live_clause_mentions
from pipeline.document_graph import mention_dependency_role
from pipeline.domain_types import (
    ClauseID,
    ClusterID,
    EntityID,
    EntityType,
    KinshipDetail,
    OrganizationKind,
    ProxyKind,
    RoleKind,
    RoleModifier,
    TimeScope,
)
from pipeline.grammar_signals import (
    infer_time_scope_with_temporal_context,
)
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    ClusterMentionView,
    Entity,
    EntityCluster,
    EvidenceSpan,
    SentenceFragment,
)

ALL_ENTITY_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.PERSON,
        EntityType.POLITICAL_PARTY,
        EntityType.POSITION,
        EntityType.ORGANIZATION,
        EntityType.PUBLIC_INSTITUTION,
        EntityType.LOCATION,
    }
)


@dataclass(slots=True)
class ExtractionContext:
    document: ArticleDocument
    clusters_by_id: dict[ClusterID, EntityCluster] = field(init=False)
    entities_by_id: dict[EntityID, Entity] = field(init=False)
    cluster_by_entity_id_index: dict[EntityID, EntityCluster] = field(init=False)
    exact_mention_index: dict[tuple[int, int, int, EntityType], EntityCluster] = field(init=False)
    text_mention_index: dict[tuple[str, int, int, EntityType], list[EntityCluster]] = field(
        init=False
    )
    clusters_by_sentence_type: dict[tuple[int, EntityType], list[EntityCluster]] = field(init=False)
    clusters_by_paragraph_type: dict[tuple[int, EntityType], list[EntityCluster]] = field(
        init=False
    )
    dependency_frames_by_clause_id: dict[ClauseID, TriggerArgumentFrame] = field(init=False)

    @classmethod
    def build(cls, document: ArticleDocument) -> ExtractionContext:
        return cls(document=document)

    def __post_init__(self) -> None:
        self.clusters_by_id = {cluster.cluster_id: cluster for cluster in self.document.clusters}
        self.entities_by_id = {entity.entity_id: entity for entity in self.document.entities}
        self.cluster_by_entity_id_index = {}
        self.exact_mention_index = {}
        self.text_mention_index = {}
        self.clusters_by_sentence_type = {}
        self.clusters_by_paragraph_type = {}
        self.dependency_frames_by_clause_id = {}

        for cluster in self.document.clusters:
            for entity_id in self.entity_ids_for_cluster(cluster):
                if entity_id is not None and entity_id not in self.cluster_by_entity_id_index:
                    self.cluster_by_entity_id_index[entity_id] = cluster
            for mention in cluster.mentions:
                mention_entity = self.entity_by_id(mention.entity_id)
                indexed_entity_types = {mention.entity_type}
                if mention_entity is not None:
                    indexed_entity_types.add(mention_entity.entity_type)
                if (
                    mention.entity_id is not None
                    and mention.entity_id not in self.cluster_by_entity_id_index
                ):
                    self.cluster_by_entity_id_index[mention.entity_id] = cluster
                if self._has_exact_span(mention):
                    self.exact_mention_index[
                        (
                            mention.sentence_index,
                            mention.start_char,
                            mention.end_char,
                            mention.entity_type,
                        )
                    ] = cluster
                self.text_mention_index.setdefault(
                    (
                        mention.text,
                        mention.sentence_index,
                        mention.paragraph_index,
                        mention.entity_type,
                    ),
                    [],
                ).append(cluster)
                for entity_type in indexed_entity_types:
                    self._append_unique_cluster(
                        self.clusters_by_sentence_type,
                        (mention.sentence_index, entity_type),
                        cluster,
                    )
                    self._append_unique_cluster(
                        self.clusters_by_paragraph_type,
                        (mention.paragraph_index, entity_type),
                        cluster,
                    )
        self.dependency_frames_by_clause_id = DependencyFrameBuilder().build(self.document, self)

    def dependency_frame_for_clause(self, clause: ClauseUnit) -> TriggerArgumentFrame | None:
        return self.dependency_frames_by_clause_id.get(clause.clause_id)

    def clusters_for_clause(
        self,
        clause: ClauseUnit,
        entity_types: AbstractSet[EntityType],
    ) -> list[EntityCluster]:
        return self.clusters_for_mentions(self.mentions_for_clause(clause), entity_types)

    def clusters_for_mentions(
        self,
        mentions: Iterable[ClusterMention],
        entity_types: AbstractSet[EntityType],
    ) -> list[EntityCluster]:
        seen: set[ClusterID] = set()
        clusters: list[EntityCluster] = []
        for mention in mentions:
            mention_entity = self.entity_by_id(mention.entity_id)
            indexed_entity_types = {mention.entity_type}
            if mention_entity is not None:
                indexed_entity_types.add(mention_entity.entity_type)
            if indexed_entity_types.isdisjoint(entity_types):
                continue
            cluster = self.cluster_for_mention(mention)
            if cluster is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

    def mentions_for_clause(
        self,
        clause: ClauseUnit,
        entity_types: AbstractSet[EntityType] | None = None,
    ) -> list[ClusterMention]:
        mentions = live_clause_mentions(self.document, clause)
        if entity_types is None:
            return mentions
        return [
            mention
            for mention in mentions
            if not {
                mention.entity_type,
                *(
                    [entity.entity_type]
                    if (entity := self.entity_by_id(mention.entity_id)) is not None
                    else []
                ),
            }.isdisjoint(entity_types)
        ]

    def role_for_mention_in_clause(
        self,
        clause: ClauseUnit,
        mention: ClusterMention,
    ) -> str | None:
        sentence = next(
            (
                item
                for item in self.document.sentences
                if item.sentence_index == clause.sentence_index
            ),
            None,
        )
        return mention_dependency_role(self.document, sentence, mention)

    def cluster_for_mention(self, mention_ref: ClusterMention) -> EntityCluster | None:
        exact_match = self.exact_mention_index.get(
            (
                mention_ref.sentence_index,
                mention_ref.start_char,
                mention_ref.end_char,
                mention_ref.entity_type,
            )
        )
        if exact_match is not None:
            return exact_match
        if self._has_exact_span(mention_ref):
            return None

        fallback_matches: list[EntityCluster] = []
        candidate_clusters = self.text_mention_index.get(
            (
                mention_ref.text,
                mention_ref.sentence_index,
                mention_ref.paragraph_index,
                mention_ref.entity_type,
            ),
            [],
        )
        for cluster in candidate_clusters:
            for mention in cluster.mentions:
                if (
                    mention.text != mention_ref.text
                    or mention.sentence_index != mention_ref.sentence_index
                    or mention.paragraph_index != mention_ref.paragraph_index
                    or mention.entity_type != mention_ref.entity_type
                ):
                    continue
                if (
                    mention_ref.entity_id is not None
                    and mention.entity_id is not None
                    and mention.entity_id != mention_ref.entity_id
                ):
                    continue
                fallback_matches.append(cluster)
                break
        if len(fallback_matches) == 1:
            return fallback_matches[0]
        return None

    @staticmethod
    def _has_exact_span(mention: ClusterMention) -> bool:
        return mention.end_char > mention.start_char

    def cluster_by_id(self, cluster_id: ClusterID | None) -> EntityCluster | None:
        if cluster_id is None:
            return None
        return self.clusters_by_id.get(cluster_id)

    def entity_by_id(self, entity_id: EntityID | None) -> Entity | None:
        if entity_id is None:
            return None
        return self.entities_by_id.get(entity_id)

    def entity_for_cluster(self, cluster: EntityCluster) -> Entity | None:
        return read_entity_for_cluster(cluster, self.entities_by_id)

    def entity_for_mention_view(
        self,
        cluster: EntityCluster,
        mention: ClusterMention,
    ) -> Entity | None:
        if mention.entity_id is not None:
            entity = self.entities_by_id.get(mention.entity_id)
            if entity is not None:
                return entity
        return self.entity_for_cluster(cluster)

    def mention_view(
        self,
        cluster: EntityCluster,
        mention: ClusterMention | None = None,
    ) -> ClusterMentionView:
        if mention is None:
            mention = self._sentinel_mention_for_cluster(cluster)
        return ClusterMentionView(
            cluster=cluster,
            mention=mention,
            entity=self.entity_for_mention_view(cluster, mention),
        )

    def mention_views_for_clusters(
        self,
        clusters: Iterable[EntityCluster],
        sentence_index: int,
    ) -> list[ClusterMentionView]:
        views: list[ClusterMentionView] = []
        seen_cluster_ids: set[ClusterID] = set()
        for cluster in clusters:
            if cluster.cluster_id in seen_cluster_ids:
                continue
            sentence_mentions = [
                mention for mention in cluster.mentions if mention.sentence_index == sentence_index
            ]
            if not sentence_mentions:
                continue
            seen_cluster_ids.add(cluster.cluster_id)
            mention = min(sentence_mentions, key=lambda item: item.start_char)
            views.append(self.mention_view(cluster, mention))
        return views

    def mention_view_closest_to_sentence(
        self,
        cluster: EntityCluster,
        sentence: SentenceFragment,
    ) -> ClusterMentionView | None:
        if not cluster.mentions:
            return None
        mention = min(
            cluster.mentions,
            key=lambda candidate: (
                candidate.sentence_index != sentence.sentence_index,
                candidate.paragraph_index != sentence.paragraph_index,
                abs(candidate.start_char - sentence.start_char),
            ),
        )
        return self.mention_view(cluster, mention)

    @staticmethod
    def _sentinel_mention_for_cluster(cluster: EntityCluster) -> ClusterMention:
        mention = cluster.mentions[0] if cluster.mentions else None
        text = mention.text if mention is not None else str(cluster.cluster_id)
        entity_type = mention.entity_type if mention is not None else EntityType.ORGANIZATION
        return ClusterMention(
            text=text,
            entity_type=entity_type,
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=0,
        )

    def entity_type_for_cluster(self, cluster: EntityCluster) -> EntityType:
        return read_entity_type_for_cluster(cluster, self.entities_by_id)

    def canonical_name_for_cluster(self, cluster: EntityCluster) -> str:
        return read_canonical_name_for_cluster(cluster, self.entities_by_id)

    def normalized_name_for_cluster(self, cluster: EntityCluster) -> str:
        return read_normalized_name_for_cluster(cluster, self.entities_by_id)

    def aliases_for_cluster(self, cluster: EntityCluster) -> list[str]:
        return read_aliases_for_cluster(cluster, self.entities_by_id)

    def lemmas_for_cluster(self, cluster: EntityCluster) -> list[str]:
        return read_lemmas_for_cluster(cluster, self.entities_by_id)

    def organization_kind_for_cluster(self, cluster: EntityCluster) -> OrganizationKind | None:
        return read_organization_kind_for_cluster(cluster, self.entities_by_id)

    def is_proxy_person_cluster(self, cluster: EntityCluster) -> bool:
        return read_is_proxy_person_cluster(cluster, self.entities_by_id)

    def proxy_kind_for_cluster(self, cluster: EntityCluster) -> ProxyKind | None:
        return read_proxy_kind_for_cluster(cluster, self.entities_by_id)

    def kinship_detail_for_cluster(self, cluster: EntityCluster) -> KinshipDetail | None:
        return read_kinship_detail_for_cluster(cluster, self.entities_by_id)

    def proxy_anchor_entity_id_for_cluster(self, cluster: EntityCluster) -> EntityID | None:
        return read_proxy_anchor_entity_id_for_cluster(cluster, self.entities_by_id)

    def role_kind_for_cluster(self, cluster: EntityCluster) -> RoleKind | None:
        return read_role_kind_for_cluster(cluster, self.entities_by_id)

    def role_modifier_for_cluster(self, cluster: EntityCluster) -> RoleModifier | None:
        return read_role_modifier_for_cluster(cluster, self.entities_by_id)

    def entity_id_for_cluster_id(self, cluster_id: ClusterID | None) -> EntityID | None:
        cluster = self.cluster_by_id(cluster_id)
        return self.entity_id_for_cluster(cluster) if cluster is not None else None

    def primary_entity_id_for_cluster(self, cluster: EntityCluster) -> EntityID | None:
        if cluster.primary_entity_id is not None:
            return cluster.primary_entity_id
        mention_entity_ids = self.mention_entity_ids_for_cluster(cluster)
        return mention_entity_ids[0] if mention_entity_ids else None

    def member_entity_ids_for_cluster(self, cluster: EntityCluster) -> list[EntityID]:
        if cluster.member_entity_ids:
            return list(dict.fromkeys(cluster.member_entity_ids))
        return self.mention_entity_ids_for_cluster(cluster)

    @staticmethod
    def mention_entity_ids_for_cluster(cluster: EntityCluster) -> list[EntityID]:
        return [
            entity_id
            for entity_id in dict.fromkeys(mention.entity_id for mention in cluster.mentions)
            if entity_id is not None
        ]

    def entity_ids_for_cluster(self, cluster: EntityCluster) -> list[EntityID]:
        entity_ids: list[EntityID] = []
        primary_entity_id = self.primary_entity_id_for_cluster(cluster)
        if primary_entity_id is not None:
            entity_ids.append(primary_entity_id)
        for entity_id in self.member_entity_ids_for_cluster(cluster):
            if entity_id not in entity_ids:
                entity_ids.append(entity_id)
        for entity_id in self.mention_entity_ids_for_cluster(cluster):
            if entity_id not in entity_ids:
                entity_ids.append(entity_id)
        return entity_ids

    @staticmethod
    def entity_id_for_cluster(cluster: EntityCluster) -> EntityID:
        if cluster.primary_entity_id is not None:
            return cluster.primary_entity_id
        entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
        if entity_ids:
            return Counter(entity_ids).most_common(1)[0][0]
        return EntityID(str(cluster.cluster_id))

    def cluster_entity_id_map(self) -> dict[ClusterID, EntityID]:
        return {
            cluster.cluster_id: self.entity_id_for_cluster(cluster)
            for cluster in self.document.clusters
        }

    def cluster_name(self, cluster_id: ClusterID | None) -> str | None:
        cluster = self.cluster_by_id(cluster_id)
        return self.canonical_name_for_cluster(cluster) if cluster is not None else None

    def cluster_by_entity_id(self, entity_id: EntityID | None) -> EntityCluster | None:
        if entity_id is None:
            return None
        return self.cluster_by_entity_id_index.get(entity_id)

    def clusters_in_sentence(
        self,
        sentence_index: int,
        entity_types: AbstractSet[EntityType],
    ) -> list[EntityCluster]:
        return self._clusters_from_index(
            self.clusters_by_sentence_type,
            sentence_index,
            entity_types,
        )

    def clusters_in_sentence_window(
        self,
        clause: ClauseUnit,
        entity_types: AbstractSet[EntityType],
        *,
        before: int = 2,
        after: int = 2,
    ) -> list[EntityCluster]:
        start_sentence = max(0, clause.sentence_index - before)
        end_sentence = clause.sentence_index + after
        return self._clusters_with_mentions(
            entity_types,
            lambda mention: (
                mention.paragraph_index == clause.paragraph_index
                and start_sentence <= mention.sentence_index <= end_sentence
            ),
        )

    def previous_clusters(
        self,
        clause: ClauseUnit,
        entity_types: AbstractSet[EntityType],
        *,
        max_distance: int = 2,
    ) -> list[EntityCluster]:
        start_sentence = max(0, clause.sentence_index - max_distance)
        return self._clusters_with_mentions(
            entity_types,
            lambda mention: (
                mention.paragraph_index == clause.paragraph_index
                and start_sentence <= mention.sentence_index <= clause.sentence_index
            ),
        )

    def paragraph_context_clusters(
        self,
        clause: ClauseUnit,
        entity_types: AbstractSet[EntityType],
    ) -> list[EntityCluster]:
        return sorted(
            self._clusters_from_index(
                self.clusters_by_paragraph_type,
                clause.paragraph_index,
                entity_types,
            ),
            key=lambda cluster: self.cluster_clause_distance(cluster, clause),
        )

    def following_clusters(
        self,
        clause: ClauseUnit,
        entity_types: AbstractSet[EntityType],
        *,
        max_distance: int = 2,
        same_paragraph: bool = True,
    ) -> list[EntityCluster]:
        end_sentence = clause.sentence_index + max_distance
        return self._clusters_with_mentions(
            entity_types,
            lambda mention: (
                (not same_paragraph or mention.paragraph_index == clause.paragraph_index)
                and clause.sentence_index <= mention.sentence_index <= end_sentence
            ),
        )

    def evidence_window(
        self,
        clause: ClauseUnit,
        clusters: Iterable[EntityCluster],
    ) -> list[EvidenceSpan]:
        sentence_indexes = {clause.sentence_index}
        for cluster in clusters:
            for mention in cluster.mentions:
                if abs(mention.sentence_index - clause.sentence_index) <= 2:
                    sentence_indexes.add(mention.sentence_index)

        evidence: list[EvidenceSpan] = []
        for sentence in self.document.sentences:
            if sentence.sentence_index not in sentence_indexes:
                continue
            evidence.append(
                EvidenceSpan(
                    text=sentence.text,
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    start_char=sentence.start_char,
                    end_char=sentence.end_char,
                )
            )
        if evidence:
            return evidence
        return [
            EvidenceSpan(
                text=clause.text,
                sentence_index=clause.sentence_index,
                paragraph_index=clause.paragraph_index,
                start_char=clause.start_char,
                end_char=clause.end_char,
            )
        ]

    @staticmethod
    def evidence_for_clause(clause: ClauseUnit) -> EvidenceSpan:
        return EvidenceSpan(
            text=clause.text,
            sentence_index=clause.sentence_index,
            paragraph_index=clause.paragraph_index,
            start_char=clause.start_char,
            end_char=clause.end_char,
        )

    def fact_time_scope(self, evidence: EvidenceSpan) -> TimeScope:
        if evidence.sentence_index is None:
            return TimeScope.UNKNOWN
        parsed_words = self.document.parsed_sentences.get(evidence.sentence_index, [])
        return infer_time_scope_with_temporal_context(
            evidence.text,
            parsed_words,
            temporal_expressions=self.document.temporal_expressions,
            sentence_index=evidence.sentence_index,
            publication_date=self.document.publication_date,
        )

    @staticmethod
    def cluster_clause_distance(cluster: EntityCluster, clause: ClauseUnit) -> tuple[int, int]:
        distances = [
            (
                abs(mention.sentence_index - clause.sentence_index),
                abs(mention.start_char - clause.start_char),
            )
            for mention in cluster.mentions
        ]
        return min(distances, default=(9999, 9999))

    @staticmethod
    def best_cluster_near_offset(
        clusters: Iterable[EntityCluster],
        offset: int,
    ) -> EntityCluster | None:
        return min(
            clusters,
            key=lambda cluster: min(
                abs(mention.start_char - offset) for mention in cluster.mentions
            ),
            default=None,
        )

    @staticmethod
    def merge_clusters(
        primary: Iterable[EntityCluster],
        secondary: Iterable[EntityCluster],
    ) -> list[EntityCluster]:
        merged: list[EntityCluster] = []
        seen: set[ClusterID] = set()
        for cluster in [*primary, *secondary]:
            if cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            merged.append(cluster)
        return merged

    @staticmethod
    def sort_clusters_by_clause_distance(
        clusters: list[EntityCluster],
        clause: ClauseUnit,
    ) -> list[EntityCluster]:
        return sorted(
            clusters, key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause)
        )

    def _clusters_with_mentions(
        self,
        entity_types: AbstractSet[EntityType],
        predicate: Callable[[ClusterMention], bool],
    ) -> list[EntityCluster]:
        seen: set[ClusterID] = set()
        clusters: list[EntityCluster] = []
        for cluster in self.document.clusters:
            if (
                self.entity_type_for_cluster(cluster) not in entity_types
                or cluster.cluster_id in seen
            ):
                continue
            if not any(predicate(mention) for mention in cluster.mentions):
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

    @staticmethod
    def _clusters_from_index(
        index: dict[tuple[int, EntityType], list[EntityCluster]],
        index_value: int,
        entity_types: AbstractSet[EntityType],
    ) -> list[EntityCluster]:
        seen: set[ClusterID] = set()
        clusters: list[EntityCluster] = []
        for entity_type in entity_types:
            for cluster in index.get((index_value, entity_type), []):
                if cluster.cluster_id in seen:
                    continue
                seen.add(cluster.cluster_id)
                clusters.append(cluster)
        return clusters

    @staticmethod
    def _append_unique_cluster(
        index: dict[tuple[int, EntityType], list[EntityCluster]],
        key: tuple[int, EntityType],
        cluster: EntityCluster,
    ) -> None:
        bucket = index.setdefault(key, [])
        if all(existing.cluster_id != cluster.cluster_id for existing in bucket):
            bucket.append(cluster)

    def mention_views_in_sentence(
        self,
        sentence_index: int,
        entity_types: AbstractSet[EntityType],
    ) -> list[ClusterMentionView]:
        """Return one ClusterMentionView per cluster that has a mention in this sentence."""
        clusters = self.clusters_in_sentence(sentence_index, entity_types)
        return self.mention_views_for_clusters(clusters, sentence_index)

    def mention_views_in_paragraph(
        self,
        paragraph_index: int,
        entity_types: AbstractSet[EntityType],
    ) -> list[ClusterMentionView]:
        """Return one ClusterMentionView per cluster that has a mention in this paragraph."""
        clusters = self._clusters_from_index(
            self.clusters_by_paragraph_type,
            paragraph_index,
            entity_types,
        )
        views: list[ClusterMentionView] = []
        seen: set[ClusterID] = set()
        for cluster in clusters:
            if cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            para_mentions = sorted(
                [m for m in cluster.mentions if m.paragraph_index == paragraph_index],
                key=lambda m: m.start_char,
            )
            if not para_mentions:
                continue
            views.append(self.mention_view(cluster, para_mentions[0]))
        return views
