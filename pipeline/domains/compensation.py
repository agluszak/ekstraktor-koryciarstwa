from __future__ import annotations

import uuid
from collections.abc import Iterable

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import ClusterID, EntityType, FrameID
from pipeline.domains.public_money import FUNDING_SURFACE_FALLBACKS
from pipeline.extraction_context import ExtractionContext
from pipeline.lemma_signals import lemma_set
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    CompensationFrame,
    EntityCluster,
    EvidenceSpan,
)
from pipeline.nlp_rules import COMPENSATION_PATTERN, FUNDING_HINTS
from pipeline.role_text import find_role_text
from pipeline.utils import normalize_entity_name

COMPENSATION_CONTEXT_LEMMAS = frozenset(
    {
        "zarabiać",
        "zarobić",
        "wynagrodzenie",
        "pensja",
        "płaca",
        "uposażenie",
        "dieta",
        "brutto",
        "netto",
    }
)

COMPENSATION_CONTEXT_TEXTS = frozenset(
    {
        "miesięcznie",
        "rocznie",
        "za miesiąc",
        "wynagrodzenia",
        "wynagrodzenie",
        "pensję",
        "pensja",
        "zarabia",
        "zarabiał",
        "zarobić",
        "brutto",
    }
)


class PolishCompensationFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_compensation_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.compensation_frames = []
        for clause in document.clause_units:
            if self._looks_like_funding_clause(document, clause):
                continue
            for match in COMPENSATION_PATTERN.finditer(clause.text):
                if not self._has_compensation_context(document, clause):
                    continue
                frame = self._extract_frame_from_clause(document, clause, match)
                if frame is not None:
                    document.compensation_frames.append(frame)
        return document

    def _extract_frame_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        match,
    ) -> CompensationFrame | None:
        amount_text = match.group("amount")
        if not amount_text:
            return None
        period = match.group("period")
        amount_start = clause.start_char + match.start("amount")

        person_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        role_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        org_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )

        person_cluster = self._best_cluster_near_offset(person_clusters, amount_start)
        role_cluster = self._best_cluster_near_offset(role_clusters, amount_start)
        if role_cluster is None:
            role_cluster = self._find_role_from_text(document, clause)
        org_cluster = self._best_cluster_near_offset(org_clusters, amount_start)

        context_reason = "same_clause"
        if person_cluster is None:
            person_cluster = self._paragraph_context_cluster(
                document,
                clause,
                {EntityType.PERSON},
                amount_start,
            )
            if person_cluster is not None:
                context_reason = "paragraph_carryover"
        if org_cluster is None:
            org_cluster = self._paragraph_context_cluster(
                document,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                amount_start,
            )
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "paragraph_org"

        governance_context = self._governance_context(document, clause, person_cluster)
        if role_cluster is None and governance_context is not None:
            role_cluster = self._cluster_by_id(document, governance_context.role_cluster_id)
        if org_cluster is None and governance_context is not None:
            org_cluster = self._cluster_by_id(document, governance_context.target_org_cluster_id)
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "governance_context"

        if person_cluster is None and role_cluster is None and org_cluster is None:
            return None

        confidence, score_reason = self._score_frame(
            person_cluster=person_cluster,
            role_cluster=role_cluster,
            org_cluster=org_cluster,
            context_reason=context_reason,
        )
        return CompensationFrame(
            frame_id=FrameID(f"comp-frame-{uuid.uuid4().hex[:8]}"),
            amount_text=amount_text,
            amount_normalized=normalize_entity_name(amount_text.lower()),
            period=normalize_entity_name(period.lower()) if period else None,
            person_cluster_id=person_cluster.cluster_id if person_cluster else None,
            role_cluster_id=role_cluster.cluster_id if role_cluster else None,
            organization_cluster_id=org_cluster.cluster_id if org_cluster else None,
            confidence=confidence,
            evidence=[
                EvidenceSpan(
                    text=clause.text,
                    sentence_index=clause.sentence_index,
                    paragraph_index=clause.paragraph_index,
                    start_char=clause.start_char,
                    end_char=clause.end_char,
                )
            ],
            extraction_signal=self._extraction_signal(score_reason),
            evidence_scope="same_clause" if context_reason == "same_clause" else "same_paragraph",
            score_reason=score_reason,
            context_reason=context_reason,
        )

    def _has_compensation_context(self, document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        if any(trigger in lowered for trigger in COMPENSATION_CONTEXT_TEXTS):
            return True
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        return bool(
            {word.lemma.lower() for word in parsed_words}.intersection(COMPENSATION_CONTEXT_LEMMAS)
        )

    @staticmethod
    def _looks_like_funding_clause(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        return bool(
            lemmas.intersection(FUNDING_HINTS)
            or clause.trigger_head_lemma.lower() in FUNDING_HINTS
            or (not parsed_words and any(hint in lowered for hint in FUNDING_SURFACE_FALLBACKS))
        )

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

    @staticmethod
    def _find_cluster_for_mention(
        mention_ref: ClusterMention,
        document: ArticleDocument,
    ) -> EntityCluster | None:
        return ExtractionContext.build(document).cluster_for_mention(mention_ref)

    @staticmethod
    def _best_cluster_near_offset(
        clusters: list[EntityCluster],
        offset: int,
    ) -> EntityCluster | None:
        return ExtractionContext.best_cluster_near_offset(clusters, offset)

    @classmethod
    def _paragraph_context_cluster(
        cls,
        document: ArticleDocument,
        clause: ClauseUnit,
        entity_types: set[EntityType],
        offset: int,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in entity_types
            and any(
                mention.paragraph_index == clause.paragraph_index
                and mention.sentence_index <= clause.sentence_index
                for mention in cluster.mentions
            )
        ]
        return cls._best_cluster_near_offset(candidates, offset)

    def _find_role_from_text(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        role_text = find_role_text(document, clause)
        if role_text is None:
            return None
        for cluster in document.clusters:
            if cluster.entity_type != EntityType.POSITION:
                continue
            if cluster.canonical_name.lower() == role_text.lower():
                return cluster
        return None

    @staticmethod
    def _governance_context(
        document: ArticleDocument,
        clause: ClauseUnit,
        person: EntityCluster | None,
    ):
        for frame in document.governance_frames:
            if not frame.evidence:
                continue
            evidence = frame.evidence[0]
            same_paragraph = evidence.paragraph_index == clause.paragraph_index
            same_person = person is not None and frame.person_cluster_id == person.cluster_id
            if same_paragraph and (same_person or person is None):
                return frame
        return None

    @staticmethod
    def _cluster_by_id(
        document: ArticleDocument,
        cluster_id: ClusterID | None,
    ) -> EntityCluster | None:
        return ExtractionContext.build(document).cluster_by_id(cluster_id)

    @staticmethod
    def _score_frame(
        *,
        person_cluster: EntityCluster | None,
        role_cluster: EntityCluster | None,
        org_cluster: EntityCluster | None,
        context_reason: str,
    ) -> tuple[float, str]:
        if person_cluster is not None and org_cluster is not None and role_cluster is not None:
            return 0.85, "person_amount_role_org_same_clause"
        if person_cluster is not None and org_cluster is not None:
            if context_reason == "same_clause":
                return 0.74, "person_amount_org_same_clause"
            return 0.66, "person_amount_paragraph_org"
        if role_cluster is not None and org_cluster is not None:
            return 0.66, "role_amount_org"
        if org_cluster is not None:
            return 0.55, "public_org_amount_salary_context"
        if person_cluster is not None:
            return 0.55, "amount_person"
        return 0.42, "paragraph_carryover"

    @staticmethod
    def _extraction_signal(score_reason: str) -> str:
        if score_reason == "person_amount_role_org_same_clause":
            return "syntactic_direct"
        if "same_clause" in score_reason:
            return "dependency_edge"
        if "paragraph" in score_reason:
            return "same_paragraph"
        return "same_clause"
