from __future__ import annotations

import uuid

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_context_helpers import (
    cluster_clause_distance,
    clusters_for_mentions,
    paragraph_context_clusters,
)
from pipeline.domain_types import EntityType, FrameID
from pipeline.domains.public_money import (
    FUNDING_SURFACE_FALLBACKS,
    PublicMoneyFlowKind,
    _public_money_flow_signal,
    is_reporting_przekazac_context,
    is_reporting_przekazac_without_amount,
)
from pipeline.extraction_context import ExtractionContext
from pipeline.frame_grounding import FrameSlotGrounder
from pipeline.lemma_signals import lemma_set
from pipeline.models import ArticleDocument, ClauseUnit, EntityCluster, FundingFrame
from pipeline.nlp_rules import COMPENSATION_PATTERN, FUNDING_HINTS
from pipeline.utils import normalize_entity_name


class PolishFundingFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.slot_grounder = FrameSlotGrounder(config)

    def name(self) -> str:
        return "polish_funding_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.funding_frames = []
        for clause in document.clause_units:
            grounded_orgs = self.slot_grounder.ground_organization_mentions(document, clause)
            signal = _public_money_flow_signal(document, clause, grounded_orgs)
            if signal is not None:
                if signal.kind != PublicMoneyFlowKind.FUNDING:
                    continue
                document.funding_frames.append(
                    FundingFrame(
                        frame_id=FrameID(f"funding-frame-{uuid.uuid4().hex[:8]}"),
                        amount_text=signal.amount_text,
                        amount_normalized=signal.amount_normalized,
                        funder_cluster_id=signal.payer_cluster.cluster_id
                        if signal.payer_cluster is not None
                        else None,
                        recipient_cluster_id=signal.recipient_cluster.cluster_id
                        if signal.recipient_cluster is not None
                        else None,
                        confidence=signal.confidence,
                        evidence=[ExtractionContext.evidence_for_clause(clause)],
                        extraction_signal="public_money_flow",
                        evidence_scope=signal.evidence_scope,
                        score_reason=signal.score_reason,
                    )
                )
                continue
            if not self._has_funding_context(document, clause):
                continue
            amount_match = COMPENSATION_PATTERN.search(clause.text)
            if is_reporting_przekazac_context(document, clause):
                continue
            if is_reporting_przekazac_without_amount(document, clause, amount_match):
                continue
            frame = self._extract_frame_from_clause(document, clause, amount_match)
            if frame is not None:
                document.funding_frames.append(frame)
        return document

    def _extract_frame_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        amount_match,
    ) -> FundingFrame | None:
        org_clusters = clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )
        if not org_clusters:
            org_clusters = paragraph_context_clusters(
                document,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
            )
        if not org_clusters:
            return None

        funder = self._best_funder(document, clause, org_clusters)
        recipient = self._best_recipient(document, clause, org_clusters, funder)
        project = self._best_project(document, clause, org_clusters, funder, recipient)
        if recipient is None and project is not None:
            recipient = project
            project = None
        if funder is None and recipient is None:
            return None

        amount_text = amount_match.group("amount") if amount_match else None
        confidence, score_reason = self._score_frame(
            funder=funder,
            recipient=recipient,
            amount_text=amount_text,
            same_clause_org_count=len(org_clusters),
        )
        return FundingFrame(
            frame_id=FrameID(f"funding-frame-{uuid.uuid4().hex[:8]}"),
            amount_text=amount_text,
            amount_normalized=normalize_entity_name(amount_text.lower()) if amount_text else None,
            funder_cluster_id=funder.cluster_id if funder else None,
            recipient_cluster_id=recipient.cluster_id if recipient else None,
            project_cluster_id=project.cluster_id if project else None,
            confidence=confidence,
            evidence=[ExtractionContext.evidence_for_clause(clause)],
            extraction_signal=self._extraction_signal(score_reason),
            evidence_scope="same_clause" if len(org_clusters) >= 2 else "same_paragraph",
            score_reason=score_reason,
        )

    @staticmethod
    def _has_funding_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        return bool(
            lemmas.intersection(FUNDING_HINTS)
            or clause.trigger_head_lemma.lower() in FUNDING_HINTS
            or (not parsed_words and any(hint in lowered for hint in FUNDING_SURFACE_FALLBACKS))
        )

    def _best_funder(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
    ) -> EntityCluster | None:
        if not org_clusters:
            return None
        trigger_index = self._funding_trigger_index(document, clause)
        if self._trigger_prefers_postposed_funder(document, clause):
            after_trigger = [
                cluster
                for cluster in org_clusters
                if self._cluster_after_offset_in_clause(cluster, trigger_index, clause)
            ]
            if after_trigger:
                return max(after_trigger, key=lambda cluster: self._funder_score(cluster))
        before_trigger = [
            cluster
            for cluster in org_clusters
            if self._cluster_before_offset(cluster, trigger_index)
        ]
        candidates = before_trigger or org_clusters
        return max(candidates, key=lambda cluster: self._funder_score(cluster))

    def _best_recipient(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
        funder: EntityCluster | None,
    ) -> EntityCluster | None:
        candidates = [cluster for cluster in org_clusters if cluster != funder]
        if not candidates:
            return None
        trigger_index = self._funding_trigger_index(document, clause)
        after_trigger = [
            cluster
            for cluster in candidates
            if not self._cluster_before_offset(cluster, trigger_index)
        ]
        candidates = after_trigger or candidates
        return max(candidates, key=lambda cluster: self._recipient_score(cluster))

    @staticmethod
    def _best_project(
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
        funder: EntityCluster | None,
        recipient: EntityCluster | None,
    ) -> EntityCluster | None:
        _ = document
        project_markers = ("projekt", "park", "program", "inwestyc", "budow")
        excluded_ids = {
            cluster.cluster_id for cluster in (funder, recipient) if cluster is not None
        }
        candidates = [
            cluster
            for cluster in org_clusters
            if cluster.cluster_id not in excluded_ids
            and any(marker in cluster.normalized_name.lower() for marker in project_markers)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda cluster: cluster_clause_distance(cluster, clause),
        )

    @staticmethod
    def _funder_score(cluster: EntityCluster) -> tuple[int, int, int]:
        normalized = cluster.normalized_name.lower()
        public_bonus = 2 if cluster.entity_type == EntityType.PUBLIC_INSTITUTION else 0
        if any(term in normalized for term in ("minister", "fundusz", "urząd", "nfoś", "wfoś")):
            public_bonus += 2
        if any(term in normalized for term in ("spółka", "agencja", "krajowy")):
            public_bonus += 1
        return (public_bonus, len(cluster.canonical_name.split()), len(cluster.canonical_name))

    @staticmethod
    def _recipient_score(cluster: EntityCluster) -> tuple[int, int, int]:
        normalized = cluster.normalized_name.lower()
        recipient_bonus = 0
        if any(term in normalized for term in ("fundacja", "stowarzyszenie", "instytut")):
            recipient_bonus += 3
        if any(term in normalized for term in ("projekt", "park", "program")):
            recipient_bonus += 2
        if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
            recipient_bonus -= 1
        return (recipient_bonus, len(cluster.canonical_name.split()), len(cluster.canonical_name))

    @staticmethod
    def _funding_trigger_index(document: ArticleDocument, clause: ClauseUnit) -> int:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        trigger_words = [
            clause.start_char + word.start
            for word in parsed_words
            if word.lemma.lower() in FUNDING_HINTS
        ]
        if trigger_words:
            return min(trigger_words)
        lowered = clause.text.lower()
        positions = [
            lowered.find(hint) for hint in FUNDING_SURFACE_FALLBACKS if lowered.find(hint) >= 0
        ]
        if positions:
            return clause.start_char + min(positions)
        return clause.start_char

    @staticmethod
    def _trigger_prefers_postposed_funder(
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> bool:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        if any(word.lemma.lower() == "wyłożyć" for word in parsed_words):
            return True
        return "wyłożył" in clause.text.lower() or "wyłożyły" in clause.text.lower()

    @staticmethod
    def _cluster_before_offset(cluster: EntityCluster, offset: int) -> bool:
        return any(mention.end_char <= offset for mention in cluster.mentions)

    @staticmethod
    def _cluster_after_offset_in_clause(
        cluster: EntityCluster,
        offset: int,
        clause: ClauseUnit,
    ) -> bool:
        return any(
            mention.sentence_index == clause.sentence_index
            and mention.start_char >= offset
            and mention.start_char <= clause.end_char
            for mention in cluster.mentions
        )

    @staticmethod
    def _score_frame(
        *,
        funder: EntityCluster | None,
        recipient: EntityCluster | None,
        amount_text: str | None,
        same_clause_org_count: int,
    ) -> tuple[float, str]:
        if funder is not None and recipient is not None and amount_text is not None:
            return 0.82, "funder_recipient_amount_same_clause"
        if funder is not None and recipient is not None:
            return 0.74, "funder_recipient_no_amount"
        if amount_text is not None and same_clause_org_count >= 1:
            return 0.68, "amount_paragraph_context"
        if funder is not None and amount_text is not None:
            return 0.58, "public_funder_amount"
        return 0.45, "weak_public_money_context"

    @staticmethod
    def _extraction_signal(score_reason: str) -> str:
        if score_reason == "funder_recipient_amount_same_clause":
            return "syntactic_direct"
        if "same_clause" in score_reason:
            return "dependency_edge"
        if "paragraph" in score_reason:
            return "same_paragraph"
        return "same_clause"
