from __future__ import annotations

from collections import Counter
from typing import cast

from pipeline.domain_types import EntityType, FactAttributes, FactType, TimeScope
from pipeline.models import ArticleDocument, CompensationFrame, EntityCluster, EvidenceSpan, Fact
from pipeline.utils import stable_id


class CompensationFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = {
            cluster.cluster_id: self._get_best_entity_id(cluster) for cluster in document.clusters
        }
        facts = [
            fact
            for frame in document.compensation_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return self._deduplicate_compensation_facts(facts)

    def _fact_for_frame(
        self,
        document: ArticleDocument,
        frame: CompensationFrame,
        cluster_to_entity_id: dict[str, str],
    ) -> Fact | None:
        subject_id = (
            cluster_to_entity_id.get(frame.person_cluster_id or "")
            or cluster_to_entity_id.get(frame.role_cluster_id or "")
            or cluster_to_entity_id.get(frame.organization_cluster_id or "")
        )
        if subject_id is None:
            return None
        org_id = cluster_to_entity_id.get(frame.organization_cluster_id or "")
        role_id = cluster_to_entity_id.get(frame.role_cluster_id or "")
        subject_cluster = self._cluster_by_entity_id(document, subject_id)
        object_id = (
            org_id
            if subject_cluster is None or subject_cluster.entity_type != EntityType.ORGANIZATION
            else None
        )
        role_text = self._cluster_name(document, frame.role_cluster_id)
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        attributes = self._attributes_for_frame(document, frame, role_id, role_text)
        return Fact(
            fact_id=stable_id(
                "fact",
                document.document_id,
                FactType.COMPENSATION,
                subject_id,
                object_id or "",
                frame.amount_normalized,
                frame.period or "",
                str(evidence.start_char or ""),
            ),
            fact_type=FactType.COMPENSATION,
            subject_entity_id=subject_id,
            object_entity_id=object_id,
            value_text=frame.amount_text,
            value_normalized=frame.amount_normalized,
            time_scope=TimeScope.CURRENT,
            event_date=document.publication_date,
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            attributes=attributes,
        )

    @staticmethod
    def _attributes_for_frame(
        document: ArticleDocument,
        frame: CompensationFrame,
        role_id: str | None,
        role_text: str | None,
    ) -> FactAttributes:
        organization = next(
            (
                cluster
                for cluster in document.clusters
                if cluster.cluster_id == frame.organization_cluster_id
            ),
            None,
        )
        attributes = cast(
            FactAttributes,
            {
                "amount_text": frame.amount_normalized,
                "period": frame.period,
                "position_entity_id": role_id,
                "role": role_text,
                "organization_kind": organization.attributes.get("organization_kind")
                if organization is not None
                else None,
                "extraction_signal": frame.attributes.get("extraction_signal"),
                "evidence_scope": frame.attributes.get("evidence_scope"),
                "overlaps_governance": bool(frame.attributes.get("overlaps_governance", False)),
                "source_extractor": "compensation_frame",
                "score_reason": frame.attributes.get("score_reason"),
            },
        )
        return attributes

    @staticmethod
    def _get_best_entity_id(cluster: EntityCluster) -> str:
        entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
        if entity_ids:
            return Counter(entity_ids).most_common(1)[0][0]
        return cluster.cluster_id

    @staticmethod
    def _cluster_name(document: ArticleDocument, cluster_id: str | None) -> str | None:
        if cluster_id is None:
            return None
        cluster = next((item for item in document.clusters if item.cluster_id == cluster_id), None)
        return cluster.canonical_name if cluster is not None else None

    @staticmethod
    def _cluster_by_entity_id(
        document: ArticleDocument,
        entity_id: str,
    ) -> EntityCluster | None:
        return next(
            (
                cluster
                for cluster in document.clusters
                if any(mention.entity_id == entity_id for mention in cluster.mentions)
            ),
            None,
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
