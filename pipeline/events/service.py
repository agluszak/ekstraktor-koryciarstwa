from __future__ import annotations

from collections import Counter

from pipeline.base import EventExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import EventType, FactType
from pipeline.models import ArticleDocument, EntityCluster, Event
from pipeline.utils import stable_id


class PolishEventExtractor(EventExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_event_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if document.governance_frames:
            document.events = self._events_from_frames(document)
            return document

        document.events = []
        for fact in document.facts:
            if fact.fact_type not in {FactType.APPOINTMENT, FactType.DISMISSAL}:
                continue
            document.events.append(
                Event(
                    event_id=stable_id(
                        "event",
                        document.document_id,
                        fact.fact_type,
                        fact.subject_entity_id,
                        fact.object_entity_id or "",
                        fact.value_normalized or "",
                    ),
                    event_type=(
                        EventType.APPOINTMENT
                        if fact.fact_type == FactType.APPOINTMENT
                        else EventType.DISMISSAL
                    ),
                    person_entity_id=fact.subject_entity_id,
                    organization_entity_id=fact.object_entity_id,
                    position_entity_id=fact.attributes.get("position_entity_id"),
                    event_date=fact.event_date,
                    confidence=fact.confidence,
                    evidence=fact.evidence,
                    attributes={
                        "time_scope": fact.time_scope,
                        **fact.attributes,
                    },
                )
            )
        return document

    def _events_from_frames(self, document: ArticleDocument) -> list[Event]:
        cluster_to_entity_id = {
            cluster.cluster_id: self._get_best_entity_id(cluster) for cluster in document.clusters
        }
        events: list[Event] = []
        for frame in document.governance_frames:
            person_id = cluster_to_entity_id.get(frame.person_cluster_id or "")
            if person_id is None or not frame.evidence:
                continue
            org_id = cluster_to_entity_id.get(frame.target_org_cluster_id or "")
            events.append(
                Event(
                    event_id=stable_id(
                        "event",
                        document.document_id,
                        frame.event_type,
                        person_id,
                        org_id or "",
                        frame.frame_id,
                    ),
                    event_type=frame.event_type,
                    person_entity_id=person_id,
                    organization_entity_id=org_id,
                    position_entity_id=cluster_to_entity_id.get(frame.role_cluster_id or ""),
                    event_date=document.publication_date,
                    confidence=frame.confidence,
                    evidence=frame.evidence[0],
                    attributes={
                        **frame.attributes,
                        "owner_context_entity_id": cluster_to_entity_id.get(
                            frame.owner_context_cluster_id or ""
                        ),
                        "governing_body_entity_id": cluster_to_entity_id.get(
                            frame.governing_body_cluster_id or ""
                        ),
                        "appointing_authority_entity_id": cluster_to_entity_id.get(
                            frame.appointing_authority_cluster_id or ""
                        ),
                    },
                )
            )
        return events

    def _get_best_entity_id(self, cluster: EntityCluster) -> str:
        entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
        if entity_ids:
            return Counter(entity_ids).most_common(1)[0][0]
        return cluster.cluster_id
