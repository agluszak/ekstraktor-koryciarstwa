from __future__ import annotations

from pipeline.base import EventExtractor
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, Event
from pipeline.utils import stable_id


class PolishEventExtractor(EventExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_event_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.events = []
        for fact in document.facts:
            if fact.fact_type not in {"APPOINTMENT", "DISMISSAL"}:
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
                    event_type="appointment" if fact.fact_type == "APPOINTMENT" else "dismissal",
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
