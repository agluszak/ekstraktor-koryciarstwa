from __future__ import annotations

from collections import Counter

from pipeline.domain_types import ClusterID, EntityID, FactID, FactType, TimeScope
from pipeline.models import (
    AntiCorruptionInvestigationFrame,
    AntiCorruptionReferralFrame,
    ArticleDocument,
    EntityCluster,
    EvidenceSpan,
    Fact,
    PublicContractFrame,
    PublicProcurementAbuseFrame,
)
from pipeline.utils import stable_id


class PublicContractFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.public_contract_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _deduplicate_public_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: PublicContractFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        contractor_id = cluster_to_entity_id.get(frame.contractor_cluster_id)
        counterparty_id = cluster_to_entity_id.get(frame.counterparty_cluster_id)
        if contractor_id is None or counterparty_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        counterparty = _cluster_by_id(document, frame.counterparty_cluster_id)
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.PUBLIC_CONTRACT,
                    contractor_id,
                    counterparty_id,
                    frame.amount_normalized or "",
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.PUBLIC_CONTRACT,
            subject_entity_id=EntityID(contractor_id),
            object_entity_id=EntityID(counterparty_id),
            value_text=frame.amount_text,
            value_normalized=frame.amount_normalized,
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            amount_text=frame.amount_normalized,
            organization_kind=counterparty.organization_kind if counterparty is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="public_contract_frame",
            score_reason=frame.score_reason,
        )


class AntiCorruptionReferralFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.anti_corruption_referral_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _deduplicate_public_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: AntiCorruptionReferralFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        complainant_id = cluster_to_entity_id.get(frame.complainant_cluster_id)
        target_id = cluster_to_entity_id.get(frame.target_cluster_id)
        if complainant_id is None or target_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        target = _cluster_by_id(document, frame.target_cluster_id)
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.ANTI_CORRUPTION_REFERRAL,
                    complainant_id,
                    target_id,
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.ANTI_CORRUPTION_REFERRAL,
            subject_entity_id=EntityID(complainant_id),
            object_entity_id=EntityID(target_id),
            value_text=target.canonical_name if target is not None else None,
            value_normalized=target.normalized_name if target is not None else None,
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            organization_kind=target.organization_kind if target is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="anti_corruption_referral_frame",
            score_reason=frame.score_reason,
        )


class AntiCorruptionInvestigationFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.anti_corruption_investigation_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _deduplicate_public_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: AntiCorruptionInvestigationFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        institution_id = cluster_to_entity_id.get(frame.institution_cluster_id)
        target_id = cluster_to_entity_id.get(frame.target_cluster_id)
        if institution_id is None or target_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        target = _cluster_by_id(document, frame.target_cluster_id)
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.ANTI_CORRUPTION_INVESTIGATION,
                    institution_id,
                    target_id,
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.ANTI_CORRUPTION_INVESTIGATION,
            subject_entity_id=EntityID(institution_id),
            object_entity_id=EntityID(target_id),
            value_text=target.canonical_name if target is not None else None,
            value_normalized=target.normalized_name if target is not None else None,
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            organization_kind=target.organization_kind if target is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="anti_corruption_investigation_frame",
            score_reason=frame.score_reason,
        )


class PublicProcurementAbuseFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.public_procurement_abuse_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _deduplicate_public_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: PublicProcurementAbuseFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        actor_id = cluster_to_entity_id.get(frame.actor_cluster_id)
        context_id = (
            cluster_to_entity_id.get(frame.public_context_cluster_id)
            if frame.public_context_cluster_id is not None
            else None
        )
        if actor_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        context = (
            _cluster_by_id(document, frame.public_context_cluster_id)
            if frame.public_context_cluster_id is not None
            else None
        )
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.PUBLIC_PROCUREMENT_ABUSE,
                    actor_id,
                    context_id or "",
                    frame.amount_normalized or "",
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.PUBLIC_PROCUREMENT_ABUSE,
            subject_entity_id=EntityID(actor_id),
            object_entity_id=EntityID(context_id) if context_id is not None else None,
            value_text=frame.amount_text,
            value_normalized=frame.amount_normalized,
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            amount_text=frame.amount_normalized,
            organization_kind=context.organization_kind if context is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="public_procurement_abuse_frame",
            score_reason=frame.score_reason,
        )


def _cluster_to_entity_id(document: ArticleDocument) -> dict[ClusterID, EntityID]:
    return {cluster.cluster_id: _get_best_entity_id(cluster) for cluster in document.clusters}


def _get_best_entity_id(cluster: EntityCluster) -> EntityID:
    entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
    if entity_ids:
        return EntityID(Counter(entity_ids).most_common(1)[0][0])
    return EntityID(cluster.cluster_id)


def _cluster_by_id(document: ArticleDocument, cluster_id: ClusterID) -> EntityCluster | None:
    return next(
        (cluster for cluster in document.clusters if cluster.cluster_id == cluster_id), None
    )


def _deduplicate_public_facts(facts: list[Fact]) -> list[Fact]:
    deduplicated: dict[tuple[FactType, EntityID, EntityID | None, str | None, str], Fact] = {}
    for fact in facts:
        key = (
            fact.fact_type,
            fact.subject_entity_id,
            fact.object_entity_id,
            fact.value_normalized,
            fact.evidence.text,
        )
        if key not in deduplicated or deduplicated[key].confidence < fact.confidence:
            deduplicated[key] = fact
    return list(deduplicated.values())
