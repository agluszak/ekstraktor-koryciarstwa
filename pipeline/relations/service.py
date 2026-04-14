from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pipeline.base import RelationExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, FactType, RelationAttributes, RelationType
from pipeline.models import ArticleDocument, CoreferenceResult, Entity, Fact, Relation
from pipeline.runtime import PipelineRuntime

from .candidate_graph import CandidateGraphBuilder
from .fact_extractors import (
    CompensationFactExtractor,
    FundingFactExtractor,
    GovernanceFactExtractor,
    PoliticalProfileFactExtractor,
    SentenceContext,
    TieFactExtractor,
)
from .types import ParsedWord


@dataclass(slots=True)
class ParsedSentence:
    start_char: int
    end_char: int
    words: list[ParsedWord]


class PolishRuleBasedRelationExtractor(RelationExtractor):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)
        self.graph_builder = CandidateGraphBuilder(config)
        self.fact_extractors = [
            GovernanceFactExtractor(),
            PoliticalProfileFactExtractor(),
            CompensationFactExtractor(),
            FundingFactExtractor(),
            TieFactExtractor(),
        ]

    def name(self) -> str:
        return "polish_rule_based_relation_extractor"

    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        parsed_sentences = self._parse_document(document)
        document.candidate_graph = self.graph_builder.build(
            document=document,
            coreference=coreference,
            parsed_sentences=parsed_sentences,
        )

        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_candidates = [
                candidate
                for candidate in document.candidate_graph.candidates
                if candidate.sentence_index == sentence.sentence_index
            ]
            if not sentence_candidates:
                continue
            paragraph_candidates = [
                candidate
                for candidate in document.candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
            ]
            previous_candidates = [
                candidate
                for candidate in document.candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
                and candidate.sentence_index == sentence.sentence_index - 1
            ]
            context = SentenceContext(
                document=document,
                sentence=sentence,
                parsed_words=parsed_sentences.get(sentence.sentence_index, []),
                graph=document.candidate_graph,
                candidates=sentence_candidates,
                paragraph_candidates=paragraph_candidates,
                previous_candidates=previous_candidates,
            )
            for extractor in self.fact_extractors:
                facts.extend(extractor.extract(context))

        document.facts = self._deduplicate_facts(facts)
        document.relations = self._derive_relations(document)
        self._append_person_attributes(document)
        return document

    def _parse_document(self, document: ArticleDocument) -> dict[int, list[ParsedWord]]:
        syntax_doc = self.runtime.get_stanza_syntax_pipeline()(document.cleaned_text)
        parsed_sentences = [self._to_parsed_sentence(sentence) for sentence in syntax_doc.sentences]
        return {
            sentence.sentence_index: self._align_sentence(sentence, parsed_sentences)
            for sentence in document.sentences
        }

    @staticmethod
    def _to_parsed_sentence(sentence) -> ParsedSentence:
        parsed_words = [
            ParsedWord(
                index=int(word.id if isinstance(word.id, int) else word.id[0]),
                text=word.text,
                lemma=(word.lemma or word.text).lower(),
                upos=word.upos or "",
                head=int(word.head or 0),
                deprel=word.deprel or "",
                start=int(word.start_char),
                end=int(word.end_char),
            )
            for word in sentence.words
        ]
        if not parsed_words:
            return ParsedSentence(start_char=0, end_char=0, words=[])
        return ParsedSentence(
            start_char=min(word.start for word in parsed_words),
            end_char=max(word.end for word in parsed_words),
            words=parsed_words,
        )

    @classmethod
    def _align_sentence(
        cls,
        sentence,
        parsed_sentences: list[ParsedSentence],
    ) -> list[ParsedWord]:
        if not parsed_sentences:
            return []

        best_sentence = max(
            parsed_sentences,
            key=lambda parsed_sentence: cls._sentence_overlap(sentence, parsed_sentence),
        )
        overlap = cls._sentence_overlap(sentence, best_sentence)
        if overlap <= 0:
            return []

        return [
            ParsedWord(
                index=word.index,
                text=word.text,
                lemma=word.lemma,
                upos=word.upos,
                head=word.head,
                deprel=word.deprel,
                start=max(0, word.start - sentence.start_char),
                end=max(0, word.end - sentence.start_char),
            )
            for word in best_sentence.words
        ]

    @staticmethod
    def _sentence_overlap(sentence, parsed_sentence: ParsedSentence) -> int:
        return max(
            0,
            min(sentence.end_char, parsed_sentence.end_char)
            - max(sentence.start_char, parsed_sentence.start_char),
        )

    def _derive_relations(self, document: ArticleDocument) -> list[Relation]:
        derived: list[Relation] = []
        for fact in document.facts:
            if fact.fact_type == FactType.APPOINTMENT and fact.object_entity_id:
                derived.append(
                    self._relation(
                        RelationType.APPOINTED_TO,
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                    )
                )
                position_entity_id = self._string_attribute(fact, "position_entity_id")
                if position_entity_id:
                    derived.append(
                        self._relation(
                            RelationType.HOLDS_POSITION,
                            fact.subject_entity_id,
                            position_entity_id,
                            fact,
                        )
                    )
                if bool(fact.attributes.get("board_role")):
                    derived.append(
                        self._relation(
                            RelationType.MEMBER_OF_BOARD,
                            fact.subject_entity_id,
                            fact.object_entity_id,
                            fact,
                            {"status": "current"},
                        )
                    )
            elif fact.fact_type == FactType.DISMISSAL and fact.object_entity_id:
                derived.append(
                    self._relation(
                        RelationType.DISMISSED_FROM,
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                    )
                )
                position_entity_id = self._string_attribute(fact, "position_entity_id")
                if position_entity_id:
                    derived.append(
                        self._relation(
                            RelationType.LEFT_POSITION,
                            fact.subject_entity_id,
                            position_entity_id,
                            fact,
                        )
                    )
                if bool(fact.attributes.get("board_role")):
                    derived.append(
                        self._relation(
                            RelationType.MEMBER_OF_BOARD,
                            fact.subject_entity_id,
                            fact.object_entity_id,
                            fact,
                            {"status": "former"},
                        )
                    )
            elif fact.fact_type == FactType.COMPENSATION and fact.object_entity_id:
                derived.append(
                    self._relation(
                        RelationType.RECEIVES_COMPENSATION,
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {
                            "amount_text": self._string_attribute(fact, "amount_text"),
                            "period": self._string_attribute(fact, "period"),
                        },
                    )
                )
            elif fact.fact_type == FactType.FUNDING and fact.object_entity_id:
                derived.append(
                    self._relation(
                        RelationType.FUNDED_BY,
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {"amount_text": self._string_attribute(fact, "amount_text")},
                    )
                )
            elif (
                fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
                and fact.object_entity_id
            ):
                derived.append(
                    self._relation(
                        RelationType.AFFILIATED_WITH_PARTY,
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {"time_scope": fact.time_scope},
                    )
                )
            elif fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE and fact.object_entity_id:
                derived.append(
                    self._relation(
                        RelationType.RELATED_TO,
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {"relationship": self._string_attribute(fact, "relationship_type")},
                    )
                )
        return self._deduplicate_relations(derived)

    def _append_person_attributes(self, document: ArticleDocument) -> None:
        entities = {entity.entity_id: entity for entity in document.entities}
        for fact in document.facts:
            person = entities.get(fact.subject_entity_id)
            if person is None or person.entity_type != EntityType.PERSON:
                continue
            if (
                fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
                and fact.object_entity_id
            ):
                party = entities.get(fact.object_entity_id)
                if party is not None:
                    self._append_list_value(person, "parties", party.canonical_name)
            if (
                fact.fact_type in {FactType.APPOINTMENT, FactType.DISMISSAL}
                and fact.object_entity_id
            ):
                organization = entities.get(fact.object_entity_id)
                if organization is not None:
                    self._append_list_value(person, "organizations", organization.canonical_name)
                role = self._string_attribute(fact, "role")
                if role:
                    self._append_list_value(person, "positions", role)
            if fact.fact_type == FactType.POLITICAL_OFFICE and fact.object_entity_id:
                office = entities.get(fact.object_entity_id)
                if office is not None:
                    self._append_list_value(person, "positions", office.canonical_name)

    @staticmethod
    def _relation(
        relation_type: RelationType,
        source_entity_id: str,
        target_entity_id: str,
        fact: Fact,
        extra_attributes: RelationAttributes | None = None,
    ) -> Relation:
        attributes = {
            key: value for key, value in (extra_attributes or {}).items() if value is not None
        }
        return Relation(
            relation_type=relation_type,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            confidence=fact.confidence,
            evidence=fact.evidence,
            attributes=cast(RelationAttributes, attributes),
        )

    @staticmethod
    def _string_attribute(fact: Fact, key: str) -> str | None:
        value = fact.attributes.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _append_list_value(entity: Entity, key: str, value: str) -> None:
        if key == "parties":
            values = entity.attributes.get("parties")
            if values is None:
                values = []
                entity.attributes["parties"] = values
        elif key == "organizations":
            values = entity.attributes.get("organizations")
            if values is None:
                values = []
                entity.attributes["organizations"] = values
        elif key == "positions":
            values = entity.attributes.get("positions")
            if values is None:
                values = []
                entity.attributes["positions"] = values
        elif key == "education":
            values = entity.attributes.get("education")
            if values is None:
                values = []
                entity.attributes["education"] = values
        else:
            return
        if isinstance(values, list) and value not in values:
            values.append(value)

    @staticmethod
    def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str, str | None, str | None, str], Fact] = {}
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

    @staticmethod
    def _deduplicate_relations(relations: list[Relation]) -> list[Relation]:
        deduplicated: dict[tuple[str, str, str, str], Relation] = {}
        for relation in relations:
            key = (
                relation.relation_type,
                relation.source_entity_id,
                relation.target_entity_id,
                relation.evidence.text,
            )
            if key not in deduplicated or deduplicated[key].confidence < relation.confidence:
                deduplicated[key] = relation
        return list(deduplicated.values())
