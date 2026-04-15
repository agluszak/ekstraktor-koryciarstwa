from __future__ import annotations

from collections import Counter
from typing import cast

from pipeline.domain_types import FactAttributes, FactType, TimeScope
from pipeline.models import ArticleDocument, EntityCluster, EvidenceSpan, Fact, FundingFrame
from pipeline.utils import stable_id


class FundingFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = {
            cluster.cluster_id: self._get_best_entity_id(cluster) for cluster in document.clusters
        }
        facts = [
            fact
            for frame in document.funding_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return self._deduplicate_funding_facts(facts)

    def _fact_for_frame(
        self,
        document: ArticleDocument,
        frame: FundingFrame,
        cluster_to_entity_id: dict[str, str],
    ) -> Fact | None:
        recipient_id = cluster_to_entity_id.get(frame.recipient_cluster_id or "")
        funder_id = cluster_to_entity_id.get(frame.funder_cluster_id or "")
        project_id = cluster_to_entity_id.get(frame.project_cluster_id or "")
        subject_id = recipient_id or project_id
        if subject_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        return Fact(
            fact_id=stable_id(
                "fact",
                document.document_id,
                FactType.FUNDING,
                subject_id,
                funder_id or "",
                frame.amount_normalized or "",
                str(evidence.start_char or ""),
            ),
            fact_type=FactType.FUNDING,
            subject_entity_id=subject_id,
            object_entity_id=funder_id,
            value_text=frame.amount_text,
            value_normalized=frame.amount_normalized,
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            attributes=self._attributes_for_frame(document, frame, project_id),
        )

    @staticmethod
    def _attributes_for_frame(
        document: ArticleDocument,
        frame: FundingFrame,
        project_id: str | None,
    ) -> FactAttributes:
        funder = next(
            (
                cluster
                for cluster in document.clusters
                if cluster.cluster_id == frame.funder_cluster_id
            ),
            None,
        )
        return cast(
            FactAttributes,
            {
                "amount_text": frame.amount_normalized,
                "organization_kind": funder.attributes.get("organization_kind")
                if funder is not None
                else None,
                "extraction_signal": frame.attributes.get("extraction_signal"),
                "evidence_scope": frame.attributes.get("evidence_scope"),
                "overlaps_governance": False,
                "source_extractor": "funding_frame",
                "score_reason": frame.attributes.get("score_reason"),
                "owner_context_entity_id": project_id,
            },
        )

    @staticmethod
    def _get_best_entity_id(cluster: EntityCluster) -> str:
        entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
        if entity_ids:
            return Counter(entity_ids).most_common(1)[0][0]
        return cluster.cluster_id

    @staticmethod
    def _deduplicate_funding_facts(facts: list[Fact]) -> list[Fact]:
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
