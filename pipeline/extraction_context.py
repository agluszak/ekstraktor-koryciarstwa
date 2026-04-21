from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, ClauseUnit, EntityCluster, EvidenceSpan


@dataclass(slots=True)
class ExtractionContext:
    document: ArticleDocument

    @classmethod
    def build(cls, document: ArticleDocument) -> ExtractionContext:
        return cls(document=document)

    def clusters_for_clause(
        self,
        clause: ClauseUnit,
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        return self.clusters_in_sentence(clause.sentence_index, entity_types)

    def clusters_in_sentence(
        self,
        sentence_index: int,
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        return self._clusters_with_mentions(
            entity_types,
            lambda mention: mention.sentence_index == sentence_index,
        )

    def clusters_in_sentence_window(
        self,
        clause: ClauseUnit,
        entity_types: set[EntityType],
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
        entity_types: set[EntityType],
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

    def following_clusters(
        self,
        clause: ClauseUnit,
        entity_types: set[EntityType],
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

    def _clusters_with_mentions(
        self,
        entity_types: set[EntityType],
        predicate,
    ) -> list[EntityCluster]:
        seen: set[str] = set()
        clusters: list[EntityCluster] = []
        for cluster in self.document.clusters:
            if cluster.entity_type not in entity_types or cluster.cluster_id in seen:
                continue
            if not any(predicate(mention) for mention in cluster.mentions):
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters
