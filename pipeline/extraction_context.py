from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from pipeline.dependency_frames import DependencyFrameBuilder, TriggerArgumentFrame
from pipeline.domain_types import (
    CandidateType,
    ClauseID,
    ClusterID,
    EntityID,
    EntityType,
    TimeScope,
)
from pipeline.grammar_signals import (
    infer_time_scope_with_temporal_context,
)
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    ClauseUnit,
    ClusterMention,
    Entity,
    EntityCandidate,
    EvidenceSpan,
    ParsedWord,
    ResolvedEntity,
    SentenceFragment,
)
from pipeline.temporal import resolve_event_date


@dataclass(slots=True)
class ExtractionContext:
    document: ArticleDocument
    clusters_by_id: dict[ClusterID, ResolvedEntity] = field(init=False)
    entities_by_id: dict[EntityID, Entity] = field(init=False)
    cluster_by_entity_id_index: dict[EntityID, ResolvedEntity] = field(init=False)
    exact_mention_index: dict[tuple[int, int, int, EntityType], ResolvedEntity] = field(init=False)
    text_mention_index: dict[tuple[str, int, int, EntityType], list[ResolvedEntity]] = field(
        init=False
    )
    clusters_by_sentence_type: dict[tuple[int, EntityType], list[ResolvedEntity]] = field(
        init=False
    )
    clusters_by_paragraph_type: dict[tuple[int, EntityType], list[ResolvedEntity]] = field(
        init=False
    )
    dependency_frames_by_clause_id: dict[ClauseID, TriggerArgumentFrame] = field(init=False)

    @classmethod
    def build(cls, document: ArticleDocument) -> ExtractionContext:
        return cls(document=document)

    def __post_init__(self) -> None:
        self.clusters_by_id = {
            cluster.entity_id: cluster for cluster in self.document.resolved_entities
        }
        self.entities_by_id = {entity.entity_id: entity for entity in self.document.entities}
        self.cluster_by_entity_id_index = {}
        self.exact_mention_index = {}
        self.text_mention_index = {}
        self.clusters_by_sentence_type = {}
        self.clusters_by_paragraph_type = {}
        self.dependency_frames_by_clause_id = {}

        for cluster in self.document.resolved_entities:
            for mention in cluster.mentions:
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
                self._append_unique_cluster(
                    self.clusters_by_sentence_type,
                    (mention.sentence_index, mention.entity_type),
                    cluster,
                )
                self._append_unique_cluster(
                    self.clusters_by_paragraph_type,
                    (mention.paragraph_index, mention.entity_type),
                    cluster,
                )
        self.dependency_frames_by_clause_id = DependencyFrameBuilder().build(self.document, self)

    def dependency_frame_for_clause(self, clause: ClauseUnit) -> TriggerArgumentFrame | None:
        return self.dependency_frames_by_clause_id.get(clause.clause_id)

    def clusters_for_clause(
        self,
        clause: ClauseUnit,
        entity_types: set[EntityType],
    ) -> list[ResolvedEntity]:
        return self.clusters_in_sentence(clause.sentence_index, entity_types)

    def clusters_for_mentions(
        self,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[ResolvedEntity]:
        seen: set[ClusterID] = set()
        clusters: list[ResolvedEntity] = []
        for mention in mentions:
            if mention.entity_type not in entity_types:
                continue
            cluster = self.cluster_for_mention(mention)
            if cluster is None or cluster.entity_id in seen:
                continue
            seen.add(cluster.entity_id)
            clusters.append(cluster)
        return clusters

    def cluster_for_mention(self, mention_ref: ClusterMention) -> ResolvedEntity | None:
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

        fallback_matches: list[ResolvedEntity] = []
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

    def cluster_by_id(self, cluster_id: ClusterID | None) -> ResolvedEntity | None:
        if cluster_id is None:
            return None
        return self.clusters_by_id.get(cluster_id)

    def entity_by_id(self, entity_id: EntityID | None) -> Entity | None:
        if entity_id is None:
            return None
        return self.entities_by_id.get(entity_id)

    def entity_id_for_cluster_id(self, cluster_id: ClusterID | None) -> EntityID | None:
        cluster = self.cluster_by_id(cluster_id)
        return self.entity_id_for_cluster(cluster) if cluster is not None else None

    @staticmethod
    def entity_id_for_cluster(cluster: ResolvedEntity) -> EntityID:
        return cluster.entity_id

    def cluster_entity_id_map(self) -> dict[EntityID, EntityID]:
        return {re.entity_id: re.entity_id for re in self.document.resolved_entities}

    def cluster_name(self, cluster_id: ClusterID | None) -> str | None:
        cluster = self.cluster_by_id(cluster_id)
        return cluster.canonical_name if cluster is not None else None

    def cluster_by_entity_id(self, entity_id: EntityID | None) -> ResolvedEntity | None:
        if entity_id is None:
            return None
        return self.cluster_by_entity_id_index.get(entity_id)

    def clusters_in_sentence(
        self,
        sentence_index: int,
        entity_types: set[EntityType],
    ) -> list[ResolvedEntity]:
        return self._clusters_from_index(
            self.clusters_by_sentence_type,
            sentence_index,
            entity_types,
        )

    def clusters_in_sentence_window(
        self,
        clause: ClauseUnit,
        entity_types: set[EntityType],
        *,
        before: int = 2,
        after: int = 2,
    ) -> list[ResolvedEntity]:
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
        entity_types: set[EntityType],
        *,
        max_distance: int = 2,
    ) -> list[ResolvedEntity]:
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
        entity_types: set[EntityType],
    ) -> list[ResolvedEntity]:
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
        entity_types: set[EntityType],
        *,
        max_distance: int = 2,
        same_paragraph: bool = True,
    ) -> list[ResolvedEntity]:
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
        clusters: Iterable[ResolvedEntity],
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
    def cluster_clause_distance(cluster: ResolvedEntity, clause: ClauseUnit) -> tuple[int, int]:
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
        clusters: Iterable[ResolvedEntity],
        offset: int,
    ) -> ResolvedEntity | None:
        return min(
            clusters,
            key=lambda cluster: min(
                abs(mention.start_char - offset) for mention in cluster.mentions
            ),
            default=None,
        )

    @staticmethod
    def merge_clusters(
        primary: Iterable[ResolvedEntity],
        secondary: Iterable[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        merged: list[ResolvedEntity] = []
        seen: set[ClusterID] = set()
        for cluster in [*primary, *secondary]:
            if cluster.entity_id in seen:
                continue
            seen.add(cluster.entity_id)
            merged.append(cluster)
        return merged

    @staticmethod
    def sort_clusters_by_clause_distance(
        clusters: list[ResolvedEntity],
        clause: ClauseUnit,
    ) -> list[ResolvedEntity]:
        return sorted(
            clusters, key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause)
        )

    def _clusters_with_mentions(
        self,
        entity_types: set[EntityType],
        predicate: Callable[[ClusterMention], bool],
    ) -> list[ResolvedEntity]:
        seen: set[ClusterID] = set()
        clusters: list[ResolvedEntity] = []
        for cluster in self.document.resolved_entities:
            if cluster.entity_type not in entity_types or cluster.entity_id in seen:
                continue
            if not any(predicate(mention) for mention in cluster.mentions):
                continue
            seen.add(cluster.entity_id)
            clusters.append(cluster)
        return clusters

    @staticmethod
    def _clusters_from_index(
        index: dict[tuple[int, EntityType], list[ResolvedEntity]],
        index_value: int,
        entity_types: set[EntityType],
    ) -> list[ResolvedEntity]:
        seen: set[ClusterID] = set()
        clusters: list[ResolvedEntity] = []
        for entity_type in entity_types:
            for cluster in index.get((index_value, entity_type), []):
                if cluster.entity_id in seen:
                    continue
                seen.add(cluster.entity_id)
                clusters.append(cluster)
        return clusters

    @staticmethod
    def _append_unique_cluster(
        index: dict[tuple[int, EntityType], list[ResolvedEntity]],
        key: tuple[int, EntityType],
        cluster: ResolvedEntity,
    ) -> None:
        bucket = index.setdefault(key, [])
        if all(existing.entity_id != cluster.entity_id for existing in bucket):
            bucket.append(cluster)


@dataclass(slots=True)
class FactExtractionContext:
    graph: CandidateGraph
    candidates_by_sentence: dict[int, list[EntityCandidate]] = field(init=False)
    candidates_by_paragraph: dict[int, list[EntityCandidate]] = field(init=False)

    @classmethod
    def build(cls, graph: CandidateGraph) -> FactExtractionContext:
        return cls(graph=graph)

    def __post_init__(self) -> None:
        self.candidates_by_sentence = {}
        self.candidates_by_paragraph = {}
        for candidate in self.graph.candidates:
            self.candidates_by_sentence.setdefault(candidate.sentence_index, []).append(candidate)
            self.candidates_by_paragraph.setdefault(candidate.paragraph_index, []).append(candidate)

    def sentence_candidates(self, sentence_index: int) -> list[EntityCandidate]:
        return self.candidates_by_sentence.get(sentence_index, [])

    def paragraph_candidates(self, paragraph_index: int) -> list[EntityCandidate]:
        return self.candidates_by_paragraph.get(paragraph_index, [])

    def previous_sentence_candidates(
        self,
        *,
        paragraph_index: int,
        sentence_index: int,
    ) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.sentence_candidates(sentence_index - 1)
            if candidate.paragraph_index == paragraph_index
        ]


@dataclass(slots=True)
class SentenceContext:
    document: ArticleDocument
    sentence: SentenceFragment
    parsed_words: list[ParsedWord]
    graph: CandidateGraph
    candidates: list[EntityCandidate]
    paragraph_candidates: list[EntityCandidate]
    previous_candidates: list[EntityCandidate]

    @property
    def persons(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.PERSON
        ]

    @property
    def positions(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.POSITION
        ]

    @property
    def organizations(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type
            in {CandidateType.ORGANIZATION, CandidateType.PUBLIC_INSTITUTION}
        ]

    @property
    def locations(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.LOCATION
        ]

    @property
    def parties(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.POLITICAL_PARTY
        ]

    @property
    def paragraph_persons(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.paragraph_candidates
            if candidate.candidate_type == CandidateType.PERSON
        ]

    @property
    def paragraph_organizations(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.paragraph_candidates
            if candidate.candidate_type
            in {CandidateType.ORGANIZATION, CandidateType.PUBLIC_INSTITUTION}
        ]

    @property
    def paragraph_locations(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.paragraph_candidates
            if candidate.candidate_type == CandidateType.LOCATION
        ]

    @property
    def lowered_text(self) -> str:
        return self.sentence.text.lower()

    @property
    def event_date(self) -> str | None:
        return resolve_event_date(
            self.document,
            sentence_index=self.sentence.sentence_index,
            text=self.sentence.text,
        )

    @property
    def time_scope(self) -> TimeScope:
        return infer_time_scope_with_temporal_context(
            self.sentence.text,
            self.parsed_words,
            temporal_expressions=self.document.temporal_expressions,
            sentence_index=self.sentence.sentence_index,
            publication_date=self.document.publication_date,
        )

    @property
    def evidence(self) -> EvidenceSpan:
        return EvidenceSpan(
            text=self.sentence.text,
            sentence_index=self.sentence.sentence_index,
            paragraph_index=self.sentence.paragraph_index,
            start_char=self.sentence.start_char,
            end_char=self.sentence.end_char,
        )

    def edge_confidence(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
    ) -> float | None:
        candidates = [
            edge.confidence
            for edge in self.graph.edges
            if edge.edge_type == edge_type
            and edge.sentence_index == self.sentence.sentence_index
            and edge.source_candidate_id == source_id
            and edge.target_candidate_id == target_id
        ]
        return max(candidates) if candidates else None

    def outgoing(self, edge_type: str, source_id: str) -> list[EntityCandidate]:
        target_ids = [
            edge.target_candidate_id
            for edge in self.graph.edges
            if edge.edge_type == edge_type
            and edge.sentence_index == self.sentence.sentence_index
            and edge.source_candidate_id == source_id
        ]
        return [candidate for candidate in self.candidates if candidate.candidate_id in target_ids]

    @property
    def overlaps_governance(self) -> bool:
        return any(
            evidence.sentence_index == self.sentence.sentence_index
            for frame in self.document.governance_frames
            for evidence in frame.evidence
        )
