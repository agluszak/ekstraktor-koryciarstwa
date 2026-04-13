from __future__ import annotations

from pipeline.base import EventExtractor
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, Event, EvidenceSpan
from pipeline.utils import find_dates, stable_id


class PolishEventExtractor(EventExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_event_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        positions = {
            entity.entity_id: entity
            for entity in document.entities
            if entity.entity_type == "Position"
        }
        relations_by_sentence: dict[int, list] = {}
        for relation in document.relations:
            if relation.evidence.sentence_index is not None:
                relations_by_sentence.setdefault(
                    relation.evidence.sentence_index,
                    [],
                ).append(relation)

        for sentence in document.sentences:
            lowered = sentence.text.lower()
            event_type = None
            if any(verb in lowered for verb in self.config.patterns.appointment_verbs):
                event_type = "appointment"
            if any(verb in lowered for verb in self.config.patterns.dismissal_verbs):
                event_type = "dismissal"
            if event_type is None:
                continue

            relations = relations_by_sentence.get(sentence.sentence_index, [])
            appointed_rel = next(
                (rel for rel in relations if rel.relation_type == "APPOINTED_TO"),
                None,
            )
            position_rel = next(
                (rel for rel in relations if rel.relation_type == "HOLDS_POSITION"),
                None,
            )
            event_date = next(iter(find_dates(sentence.text)), document.publication_date)
            document.events.append(
                Event(
                    event_id=stable_id("event", document.document_id, event_type, sentence.text),
                    event_type=event_type,
                    person_entity_id=appointed_rel.source_entity_id if appointed_rel else None,
                    organization_entity_id=(
                        appointed_rel.target_entity_id if appointed_rel else None
                    ),
                    position_entity_id=(
                        position_rel.target_entity_id
                        if position_rel and position_rel.target_entity_id in positions
                        else None
                    ),
                    event_date=event_date,
                    confidence=0.8 if event_type == "appointment" else 0.7,
                    evidence=EvidenceSpan(
                        text=sentence.text,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=sentence.start_char,
                        end_char=sentence.end_char,
                    ),
                )
            )
        return document
