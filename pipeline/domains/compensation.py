from __future__ import annotations

import uuid

from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    ClusterID,
    EntityType,
    FactID,
    FactType,
    FrameID,
    TimeScope,
)
from pipeline.domains.public_money import FUNDING_SURFACE_FALLBACKS
from pipeline.entity_classifiers import is_employer_like_name
from pipeline.extraction_context import ExtractionContext
from pipeline.lemma_signals import lemma_set
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    CompensationFrame,
    EntityCluster,
    EvidenceSpan,
    Fact,
)
from pipeline.nlp_rules import COMPENSATION_PATTERN, FUNDING_HINTS
from pipeline.role_text import find_role_text
from pipeline.temporal import resolve_event_date
from pipeline.utils import normalize_entity_name, stable_id

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
PUBLIC_REMUNERATION_MARKERS = frozenset(
    {
        "uposaż",
        "dieta",
        "pieniądze publiczne",
        "kasy sejmu",
        "z sejmu",
        "poselsk",
        "mandatu posła",
        "parlamentarzyst",
        "pobrał",
        "pobiera",
        "otrzymuje",
    }
)


class PolishCompensationFrameExtractor:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_compensation_frame_extractor"

    def run(self, document: ArticleDocument, context: ExtractionContext) -> ArticleDocument:
        document.compensation_frames = []
        for clause in document.clause_units:
            if self._looks_like_funding_clause(document, clause):
                continue
            for match in COMPENSATION_PATTERN.finditer(clause.text):
                if not self._has_compensation_context(document, clause):
                    continue
                frame = self._extract_frame_from_clause(document, clause, match, context)
                if frame is not None:
                    document.compensation_frames.append(frame)
        return document

    def _extract_frame_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        match,
        context: ExtractionContext,
    ) -> CompensationFrame | None:
        amount_text = match.group("amount")
        if not amount_text:
            return None
        period = match.group("period")
        amount_start = clause.start_char + match.start("amount")
        amount_rank = sum(
            1
            for earlier_match in COMPENSATION_PATTERN.finditer(clause.text)
            if earlier_match.start("amount") < match.start("amount")
        )

        person_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        role_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        org_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )

        local_person_cluster = self._best_local_cluster(person_clusters, clause, amount_start)
        local_role_cluster = self._best_local_cluster(role_clusters, clause, amount_start)
        local_org_cluster = self._best_local_org_cluster(org_clusters, clause, amount_start)

        if (
            amount_rank > 0
            and local_person_cluster is None
            and local_role_cluster is None
            and local_org_cluster is None
        ):
            return None

        person_cluster = local_person_cluster or ExtractionContext.best_cluster_near_offset(
            person_clusters,
            amount_start,
        )
        role_cluster = local_role_cluster or ExtractionContext.best_cluster_near_offset(
            role_clusters, amount_start
        )
        if role_cluster is None:
            role_cluster = self._find_role_from_text(document, clause)
        org_cluster = local_org_cluster or self._best_valid_org_cluster(org_clusters, amount_start)
        local_org_selected = local_org_cluster is not None

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
        if person_cluster is None and self._has_public_remuneration_context(clause.text):
            person_cluster = self._extended_context_cluster(
                document,
                clause,
                {EntityType.PERSON},
                amount_start,
                max_sentence_distance=1,
            )
            if person_cluster is not None:
                context_reason = "cross_paragraph_person"
        if role_cluster is None and self._has_public_remuneration_context(clause.text):
            role_cluster = self._extended_context_cluster(
                document,
                clause,
                {EntityType.POSITION},
                amount_start,
            )
        if org_cluster is None and self._has_public_remuneration_context(clause.text):
            org_cluster = self._extended_context_cluster(
                document,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                amount_start,
            )
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "cross_paragraph_org"

        governance_context = self._governance_context(document, clause, person_cluster)
        if role_cluster is None and governance_context is not None:
            role_cluster = self._cluster_by_id(context, governance_context.role_cluster_id)
        if org_cluster is None and governance_context is not None:
            org_cluster = self._cluster_by_id(context, governance_context.target_org_cluster_id)
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "governance_context"
        if (
            org_cluster is not None
            and not local_org_selected
            and context_reason in {"paragraph_org", "cross_paragraph_org"}
            and not self._has_public_remuneration_context(clause.text)
        ):
            org_cluster = None

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

    @staticmethod
    def _find_cluster_for_mention(
        mention_ref,
        context: ExtractionContext,
    ) -> EntityCluster | None:
        return context.cluster_for_mention(mention_ref)

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
            and cls._cluster_is_valid_compensation_anchor(cluster)
            and any(
                mention.paragraph_index == clause.paragraph_index
                and mention.sentence_index <= clause.sentence_index
                for mention in cluster.mentions
            )
        ]
        return ExtractionContext.best_cluster_near_offset(candidates, offset)

    @classmethod
    def _extended_context_cluster(
        cls,
        document: ArticleDocument,
        clause: ClauseUnit,
        entity_types: set[EntityType],
        offset: int,
        *,
        max_sentence_distance: int = 3,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in entity_types
            and cls._cluster_is_valid_compensation_anchor(cluster)
            and any(
                mention.sentence_index < clause.sentence_index
                and clause.sentence_index - mention.sentence_index <= max_sentence_distance
                for mention in cluster.mentions
            )
        ]
        return ExtractionContext.best_cluster_near_offset(candidates, offset)

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
        context: ExtractionContext,
        cluster_id: ClusterID | None,
    ) -> EntityCluster | None:
        return context.cluster_by_id(cluster_id)

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

    @staticmethod
    def _has_public_remuneration_context(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in PUBLIC_REMUNERATION_MARKERS)

    @classmethod
    def _cluster_is_valid_compensation_anchor(cls, cluster: EntityCluster) -> bool:
        if cluster.entity_type != EntityType.ORGANIZATION:
            return True
        if is_employer_like_name(cluster.normalized_name):
            return True
        stripped = cluster.canonical_name.strip()
        return stripped.isupper() and 2 <= len(stripped) <= 8

    @classmethod
    def _best_valid_org_cluster(
        cls,
        clusters: list[EntityCluster],
        offset: int,
    ) -> EntityCluster | None:
        valid_clusters = [
            cluster for cluster in clusters if cls._cluster_is_valid_compensation_anchor(cluster)
        ]
        return ExtractionContext.best_cluster_near_offset(valid_clusters, offset)

    @staticmethod
    def _best_local_cluster(
        clusters: list[EntityCluster],
        clause: ClauseUnit,
        offset: int,
    ) -> EntityCluster | None:
        candidates: list[tuple[int, EntityCluster]] = []
        for cluster in clusters:
            mention_offsets = [
                max(0, offset - mention.end_char)
                for mention in cluster.mentions
                if mention.sentence_index == clause.sentence_index
                and mention.end_char <= offset
                and offset - mention.end_char <= 80
            ]
            if mention_offsets:
                candidates.append((min(mention_offsets), cluster))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    @classmethod
    def _best_local_org_cluster(
        cls,
        clusters: list[EntityCluster],
        clause: ClauseUnit,
        offset: int,
    ) -> EntityCluster | None:
        valid_clusters = [
            cluster for cluster in clusters if cls._cluster_is_valid_compensation_anchor(cluster)
        ]
        before_amount = cls._best_local_cluster(valid_clusters, clause, offset)
        if before_amount is not None:
            return before_amount
        candidates: list[tuple[int, EntityCluster]] = []
        for cluster in valid_clusters:
            mention_offsets = [
                max(0, mention.start_char - offset)
                for mention in cluster.mentions
                if mention.sentence_index == clause.sentence_index
                and mention.start_char >= offset
                and mention.start_char - offset <= 80
            ]
            if mention_offsets:
                candidates.append((min(mention_offsets), cluster))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]


class CompensationFactBuilder:
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]:
        facts = [
            fact
            for frame in document.compensation_frames
            if (fact := self._fact_for_frame(document, frame, context)) is not None
        ]
        return self._deduplicate_compensation_facts(facts)

    def _fact_for_frame(
        self,
        document: ArticleDocument,
        frame: CompensationFrame,
        context: ExtractionContext,
    ) -> Fact | None:
        subject_id = (
            context.entity_id_for_cluster_id(frame.person_cluster_id)
            or context.entity_id_for_cluster_id(frame.role_cluster_id)
            or context.entity_id_for_cluster_id(frame.organization_cluster_id)
        )
        if subject_id is None:
            return None
        org_id = context.entity_id_for_cluster_id(frame.organization_cluster_id)
        role_id = context.entity_id_for_cluster_id(frame.role_cluster_id)
        subject_cluster = context.cluster_by_entity_id(subject_id)
        object_id = (
            org_id
            if subject_cluster is None or subject_cluster.entity_type != EntityType.ORGANIZATION
            else None
        )
        role_text = context.cluster_name(frame.role_cluster_id)
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")

        organization = next(
            (
                cluster
                for cluster in document.clusters
                if cluster.cluster_id == frame.organization_cluster_id
            ),
            None,
        )

        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    str(document.document_id),
                    FactType.COMPENSATION.value,
                    str(subject_id),
                    str(object_id) if object_id else "",
                    frame.amount_normalized,
                    frame.period or "",
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.COMPENSATION,
            subject_entity_id=subject_id,
            object_entity_id=object_id,
            value_text=frame.amount_text,
            value_normalized=frame.amount_normalized,
            time_scope=TimeScope.CURRENT,
            event_date=resolve_event_date(
                document,
                sentence_index=evidence.sentence_index,
                text=evidence.text,
                start_char=evidence.start_char,
                end_char=evidence.end_char,
            ),
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            amount_text=frame.amount_normalized,
            period=frame.period,
            position_entity_id=role_id,
            role=role_text,
            organization_kind=organization.organization_kind if organization is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            overlaps_governance=False,
            source_extractor="compensation_frame",
            score_reason=frame.score_reason,
        )

    @staticmethod
    def _deduplicate_compensation_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str | None, str | None, str], Fact] = {}
        for fact in facts:
            key = (
                fact.subject_entity_id,
                fact.object_entity_id,
                fact.value_normalized,
                fact.evidence.text,
            )
            if key not in deduplicated or deduplicated[key].confidence < fact.confidence:
                deduplicated[key] = fact
        return list(deduplicated.values())
