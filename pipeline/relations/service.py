from __future__ import annotations

import re

from pipeline.base import RelationExtractor
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, CoreferenceResult, Entity, EvidenceSpan, Relation
from pipeline.utils import normalize_entity_name, normalize_party_name, stable_id


class PolishRuleBasedRelationExtractor(RelationExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.position_re = re.compile(
            r"(?:na|do)\s+(?:stanowisko\s+)?([A-ZŁŚŻŹĆŃÓa-ząćęłńóśźż\s-]{4,80})", re.IGNORECASE
        )
        self.party_alias_patterns = {
            alias: re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            for alias in config.party_aliases
        }

    def name(self) -> str:
        return "polish_rule_based_relation_extractor"

    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        person_by_sentence = self._people_by_sentence(document, coreference)
        org_by_sentence = self._entities_by_sentence(document, "Organization")

        for sentence in document.sentences:
            lowered = sentence.text.lower()
            people = person_by_sentence.get(sentence.sentence_index, [])
            organizations = org_by_sentence.get(sentence.sentence_index, [])
            if not people and not organizations:
                continue

            document.relations.extend(self._party_relations(document, sentence))
            subject_people = people
            if any(term in lowered for term in self.config.patterns.kinship_terms) and people:
                relative = self._get_or_create_relative(document, sentence.text, people[0])
                document.relations.extend(
                    self._kinship_relations(document, sentence, people[0], relative)
                )
                subject_people = [relative]

            if any(verb in lowered for verb in self.config.patterns.appointment_verbs):
                for person in subject_people:
                    for organization in organizations:
                        document.relations.append(
                            Relation(
                                relation_type="APPOINTED_TO",
                                source_entity_id=person.entity_id,
                                target_entity_id=organization.entity_id,
                                confidence=0.82,
                                evidence=EvidenceSpan(
                                    text=sentence.text,
                                    sentence_index=sentence.sentence_index,
                                    paragraph_index=sentence.paragraph_index,
                                    start_char=sentence.start_char,
                                    end_char=sentence.end_char,
                                ),
                            )
                        )
                        self._append_person_attribute(
                            person, "organizations", organization.canonical_name
                        )
                        if any(term in lowered for term in self.config.patterns.board_terms):
                            document.relations.append(
                                Relation(
                                    relation_type="MEMBER_OF_BOARD",
                                    source_entity_id=person.entity_id,
                                    target_entity_id=organization.entity_id,
                                    confidence=0.78,
                                    evidence=EvidenceSpan(
                                        text=sentence.text,
                                        sentence_index=sentence.sentence_index,
                                        paragraph_index=sentence.paragraph_index,
                                        start_char=sentence.start_char,
                                        end_char=sentence.end_char,
                                    ),
                                )
                            )
                            self._append_person_attribute(
                                person, "organizations", organization.canonical_name
                            )
                        position = self._extract_position(sentence.text, document)
                        if position is not None:
                            document.relations.append(
                                Relation(
                                    relation_type="HOLDS_POSITION",
                                    source_entity_id=person.entity_id,
                                    target_entity_id=position.entity_id,
                                    confidence=0.7,
                                    evidence=EvidenceSpan(
                                        text=sentence.text,
                                        sentence_index=sentence.sentence_index,
                                        paragraph_index=sentence.paragraph_index,
                                    ),
                                )
                            )
                            self._append_person_attribute(
                                person, "positions", position.canonical_name
                            )

        document.relations = self._deduplicate(document.relations)
        return document

    def _extract_position(self, sentence: str, document: ArticleDocument) -> Entity | None:
        match = self.position_re.search(sentence)
        if not match:
            return None
        title = normalize_entity_name(match.group(1))
        if len(title) < 4:
            return None
        existing = next(
            (
                entity
                for entity in document.entities
                if entity.entity_type == "Position" and entity.normalized_name == title
            ),
            None,
        )
        if existing is not None:
            return existing
        position = Entity(
            entity_id=stable_id("position", document.document_id, title),
            entity_type="Position",
            canonical_name=title,
            normalized_name=title,
            aliases=[match.group(1)],
        )
        document.entities.append(position)
        return position

    def _party_relations(self, document: ArticleDocument, sentence) -> list[Relation]:
        relations: list[Relation] = []
        persons = self._entities_by_sentence(document, "Person").get(sentence.sentence_index, [])
        for marker in self.config.patterns.party_markers:
            if marker not in sentence.text.lower():
                continue
            for alias, canonical in self.config.party_aliases.items():
                if self.party_alias_patterns[alias].search(sentence.text):
                    party_entity = self._get_or_create_entity(
                        document,
                        "PoliticalParty",
                        normalize_party_name(canonical, self.config.party_aliases),
                        alias,
                    )
                    for person in persons:
                        relations.append(
                            Relation(
                                relation_type="AFFILIATED_WITH_PARTY",
                                source_entity_id=person.entity_id,
                                target_entity_id=party_entity.entity_id,
                                confidence=0.74,
                                evidence=EvidenceSpan(
                                    text=sentence.text,
                                    sentence_index=sentence.sentence_index,
                                    paragraph_index=sentence.paragraph_index,
                                ),
                            )
                        )
                        self._append_person_attribute(
                            person, "parties", party_entity.canonical_name
                        )
        return relations

    def _kinship_relations(
        self, document: ArticleDocument, sentence, anchor_person: Entity, relative: Entity
    ) -> list[Relation]:
        relations: list[Relation] = []
        lowered = sentence.text.lower()
        for term in self.config.patterns.kinship_terms:
            if term not in lowered:
                continue
            relations.append(
                Relation(
                    relation_type="RELATED_TO",
                    source_entity_id=relative.entity_id,
                    target_entity_id=anchor_person.entity_id,
                    confidence=0.66,
                    evidence=EvidenceSpan(
                        text=sentence.text,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                    ),
                    attributes={"relationship": term},
                )
            )
        return relations

    def _get_or_create_relative(
        self, document: ArticleDocument, sentence_text: str, anchor_person: Entity
    ) -> Entity:
        lowered = sentence_text.lower()
        term = next(
            (candidate for candidate in self.config.patterns.kinship_terms if candidate in lowered),
            "krewny",
        )
        canonical_name = f"Nieustalony {term} {anchor_person.canonical_name}"
        relative = self._get_or_create_entity(document, "Person", canonical_name, term)
        self._append_person_attribute(relative, "related_to", anchor_person.canonical_name)
        return relative

    @staticmethod
    def _entities_by_sentence(
        document: ArticleDocument, entity_type: str
    ) -> dict[int, list[Entity]]:
        result: dict[int, list[Entity]] = {}
        entity_map = {
            entity.entity_id: entity
            for entity in document.entities
            if entity.entity_type == entity_type
        }
        for mention in document.mentions:
            if mention.entity_id in entity_map:
                result.setdefault(mention.sentence_index, []).append(entity_map[mention.entity_id])
        return result

    def _people_by_sentence(
        self, document: ArticleDocument, coreference: CoreferenceResult
    ) -> dict[int, list[Entity]]:
        result = self._entities_by_sentence(document, "Person")
        entity_map = {
            entity.entity_id: entity
            for entity in document.entities
            if entity.entity_type == "Person"
        }
        for mention in coreference.resolved_mentions:
            if mention.entity_id and mention.entity_id in entity_map:
                result.setdefault(mention.sentence_index, []).append(entity_map[mention.entity_id])
        return {
            key: list({entity.entity_id: entity for entity in value}.values())
            for key, value in result.items()
        }

    @staticmethod
    def _get_or_create_entity(
        document: ArticleDocument, entity_type: str, canonical_name: str, alias: str
    ) -> Entity:
        existing = next(
            (
                entity
                for entity in document.entities
                if entity.entity_type == entity_type and entity.normalized_name == canonical_name
            ),
            None,
        )
        if existing is not None:
            if alias not in existing.aliases:
                existing.aliases.append(alias)
            return existing
        entity = Entity(
            entity_id=stable_id(entity_type.lower(), document.document_id, canonical_name),
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name,
            aliases=[alias],
        )
        document.entities.append(entity)
        return entity

    @staticmethod
    def _append_person_attribute(entity: Entity, key: str, value: str) -> None:
        values = entity.attributes.setdefault(key, [])
        if value not in values:
            values.append(value)

    @staticmethod
    def _deduplicate(relations: list[Relation]) -> list[Relation]:
        deduplicated: dict[tuple[str, str, str, str], Relation] = {}
        for relation in relations:
            key = (
                relation.relation_type,
                relation.source_entity_id,
                relation.target_entity_id,
                relation.evidence.text,
            )
            deduplicated[key] = relation
        return list(deduplicated.values())
