from __future__ import annotations

import uuid
from dataclasses import replace

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

        person_clusters = context.clusters_for_clause(clause, {EntityType.PERSON})
        role_clusters = context.clusters_for_clause(clause, {EntityType.POSITION})
        org_clusters = context.clusters_for_clause(
            clause,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )

        local_person_cluster = self._best_local_cluster(person_clusters, clause, amount_start)
        local_role_cluster = self._best_local_cluster(role_clusters, clause, amount_start)
        local_org_cluster = self._best_local_org_cluster(
            org_clusters, context, clause, amount_start
        )

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
        pronoun_beneficiary = self._pronoun_beneficiary_cluster(
            context,
            clause,
            amount_start,
            excluded_cluster=person_cluster,
        )
        if pronoun_beneficiary is not None:
            person_cluster = pronoun_beneficiary
        role_cluster = local_role_cluster or ExtractionContext.best_cluster_near_offset(
            role_clusters, amount_start
        )
        if role_cluster is None:
            role_cluster = self._find_role_from_text(document, clause, context)
        org_cluster = local_org_cluster or self._best_valid_org_cluster(
            org_clusters, context, amount_start
        )
        local_org_selected = local_org_cluster is not None

        context_reason = "same_clause"
        if person_cluster is None:
            person_cluster = self._paragraph_context_cluster(
                context,
                clause,
                {EntityType.PERSON},
                amount_start,
            )
            if person_cluster is not None:
                context_reason = "paragraph_carryover"
        if org_cluster is None:
            org_cluster = self._paragraph_context_cluster(
                context,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                amount_start,
            )
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "paragraph_org"
        if person_cluster is None and self._has_public_remuneration_context(clause.text):
            person_cluster = self._extended_context_cluster(
                context,
                clause,
                {EntityType.PERSON},
                amount_start,
                max_sentence_distance=1,
            )
            if person_cluster is not None:
                context_reason = "cross_paragraph_person"
        if role_cluster is None and self._has_public_remuneration_context(clause.text):
            role_cluster = self._extended_context_cluster(
                context,
                clause,
                {EntityType.POSITION},
                amount_start,
            )
        if org_cluster is None and self._has_public_remuneration_context(clause.text):
            org_cluster = self._extended_context_cluster(
                context,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                amount_start,
            )
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "cross_paragraph_org"

        governance_context = self._governance_context(document, clause, person_cluster)
        if role_cluster is None and governance_context is not None:
            role_cluster = context.cluster_by_entity_id(governance_context.role_entity_id)
        if org_cluster is None and governance_context is not None:
            org_cluster = context.cluster_by_entity_id(governance_context.target_org_entity_id)
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
            person_entity_id=context.entity_id_for_cluster(person_cluster)
            if person_cluster
            else None,
            role_entity_id=context.entity_id_for_cluster(role_cluster) if role_cluster else None,
            organization_entity_id=context.entity_id_for_cluster(org_cluster)
            if org_cluster
            else None,
            role_label=context.canonical_name_for_cluster(role_cluster) if role_cluster else None,
            organization_kind=(
                entity.organization_kind
                if org_cluster is not None
                and (entity := context.entity_for_cluster(org_cluster)) is not None
                else None
            ),
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
    def _pronoun_beneficiary_cluster(
        context: ExtractionContext,
        clause: ClauseUnit,
        amount_start: int,
        *,
        excluded_cluster: EntityCluster | None,
    ) -> EntityCluster | None:
        lowered = clause.text.casefold()
        if "kobieta" not in lowered and "żona" not in lowered:
            return None
        if not any(marker in lowered for marker in ("dostaje", "otrzymuje", "pobiera")):
            return None

        family_context = PolishCompensationFrameExtractor._family_context_beneficiary(
            context,
            clause,
            amount_start,
        )
        if family_context is not None:
            return family_context

        candidates: list[tuple[int, EntityCluster]] = []
        for cluster in context.document.clusters:
            if cluster.cluster_id == (excluded_cluster.cluster_id if excluded_cluster else None):
                continue
            if context.entity_type_for_cluster(cluster) != EntityType.PERSON:
                continue
            entity = context.entity_for_cluster(cluster)
            if entity is not None and (entity.is_proxy_person or entity.is_honorific_person_ref):
                continue
            distances = [
                amount_start - mention.end_char
                for mention in cluster.mentions
                if mention.end_char <= amount_start
                and 0 <= clause.sentence_index - mention.sentence_index <= 2
            ]
            if distances:
                candidates.append((min(distances), cluster))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    @staticmethod
    def _family_context_beneficiary(
        context: ExtractionContext,
        clause: ClauseUnit,
        amount_start: int,
    ) -> EntityCluster | None:
        candidates: list[tuple[int, EntityCluster]] = []
        for fact in context.document.facts:
            if fact.kinship_detail is None or fact.relationship_type is None:
                continue
            if fact.object_entity_id is None:
                continue
            sentence_index = fact.evidence.sentence_index
            end_char = fact.evidence.end_char
            if sentence_index is None or end_char is None:
                continue
            if not (0 <= clause.sentence_index - sentence_index <= 4 and end_char <= amount_start):
                continue
            cluster = context.cluster_by_entity_id(fact.object_entity_id)
            if cluster is None:
                continue
            candidates.append((amount_start - end_char, cluster))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

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
        context: ExtractionContext,
        clause: ClauseUnit,
        entity_types: set[EntityType],
        offset: int,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in context.document.clusters
            if context.entity_type_for_cluster(cluster) in entity_types
            and cls._cluster_is_valid_compensation_anchor(context, cluster)
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
        context: ExtractionContext,
        clause: ClauseUnit,
        entity_types: set[EntityType],
        offset: int,
        *,
        max_sentence_distance: int = 3,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in context.document.clusters
            if context.entity_type_for_cluster(cluster) in entity_types
            and cls._cluster_is_valid_compensation_anchor(context, cluster)
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
        context: ExtractionContext,
    ) -> EntityCluster | None:
        role_text = find_role_text(document, clause)
        if role_text is None:
            return None
        for cluster in document.clusters:
            if context.entity_type_for_cluster(cluster) != EntityType.POSITION:
                continue
            if context.canonical_name_for_cluster(cluster).lower() == role_text.lower():
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
            same_person = (
                person is not None
                and frame.person_entity_id is not None
                and frame.person_entity_id == ExtractionContext.entity_id_for_cluster(person)
            )
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
    def _cluster_is_valid_compensation_anchor(
        cls,
        context: ExtractionContext,
        cluster: EntityCluster,
    ) -> bool:
        if context.entity_type_for_cluster(cluster) != EntityType.ORGANIZATION:
            return True
        if is_employer_like_name(context.normalized_name_for_cluster(cluster)):
            return True
        stripped = context.canonical_name_for_cluster(cluster).strip()
        return stripped.isupper() and 2 <= len(stripped) <= 8

    @classmethod
    def _best_valid_org_cluster(
        cls,
        clusters: list[EntityCluster],
        context: ExtractionContext,
        offset: int,
    ) -> EntityCluster | None:
        valid_clusters = [
            cluster
            for cluster in clusters
            if cls._cluster_is_valid_compensation_anchor(context, cluster)
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
        context: ExtractionContext,
        clause: ClauseUnit,
        offset: int,
    ) -> EntityCluster | None:
        valid_clusters = [
            cluster
            for cluster in clusters
            if cls._cluster_is_valid_compensation_anchor(context, cluster)
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
        subject_id = frame.person_entity_id
        if subject_id is None and frame.role_entity_id is None:
            subject_id = frame.organization_entity_id
        if subject_id is None:
            return None
        org_id = frame.organization_entity_id
        role_id = frame.role_entity_id
        subject_entity = context.entity_by_id(subject_id)
        object_id = (
            org_id
            if subject_entity is None or subject_entity.entity_type != EntityType.ORGANIZATION
            else None
        )
        role_text = frame.role_label
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")

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
            organization_kind=frame.organization_kind,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            overlaps_governance=False,
            source_extractor="compensation_frame",
            score_reason=frame.score_reason,
        )

    @staticmethod
    def _deduplicate_compensation_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str | None, str | None, str | None, str | None], Fact] = {}
        for fact in facts:
            key = (
                fact.subject_entity_id,
                fact.object_entity_id,
                fact.value_normalized,
                fact.period,
                fact.role,
            )
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = fact
                continue
            preferred = max(
                (existing, fact),
                key=lambda candidate: (
                    candidate.confidence,
                    candidate.object_entity_id is not None,
                    candidate.position_entity_id is not None,
                    len(candidate.evidence.text),
                ),
            )
            fallback = fact if preferred is existing else existing
            deduplicated[key] = replace(
                preferred,
                object_entity_id=preferred.object_entity_id or fallback.object_entity_id,
                position_entity_id=preferred.position_entity_id or fallback.position_entity_id,
                role=preferred.role or fallback.role,
            )
        return list(deduplicated.values())
