from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pipeline_v2.ids import TokenId
from pipeline_v2.nlp import Sentence, Token
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.store import ExtractionStore
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import EntityKind, SyntaxRelationClass


class FrameArgumentRole(StrEnum):
    SUBJECT = "subject"
    OBJECT = "object"
    OBLIQUE = "oblique"
    APPOSITION = "apposition"
    MODIFIER = "modifier"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class FrameArgument:
    entity: SentenceEntity
    role: FrameArgumentRole
    preposition_lemma: str | None
    before_trigger: bool
    distance: int


@dataclass(frozen=True, slots=True)
class EventFrame:
    sentence: Sentence
    trigger: Token
    arguments: tuple[FrameArgument, ...]

    def entities(
        self,
        kind: EntityKind | frozenset[EntityKind],
        *,
        before_trigger: bool | None = None,
        prepositions: frozenset[str] | None = None,
        roles: frozenset[FrameArgumentRole] | None = None,
    ) -> tuple[FrameArgument, ...]:
        kinds = frozenset({kind}) if type(kind) is EntityKind else kind
        return tuple(
            argument
            for argument in self.arguments
            if argument.entity.kind in kinds
            and (before_trigger is None or argument.before_trigger is before_trigger)
            and (prepositions is None or argument.preposition_lemma in prepositions)
            and (roles is None or argument.role in roles)
        )

    def nearest(
        self,
        kind: EntityKind | frozenset[EntityKind],
        *,
        before_trigger: bool | None = None,
        prepositions: frozenset[str] | None = None,
        roles: frozenset[FrameArgumentRole] | None = None,
    ) -> FrameArgument | None:
        candidates = self.entities(
            kind,
            before_trigger=before_trigger,
            prepositions=prepositions,
            roles=roles,
        )
        if not candidates:
            return None
        return min(candidates, key=lambda argument: argument.distance)


class EventFrameBuilder:
    def __init__(self, store: ExtractionStore) -> None:
        self.store = store
        self.syntax = SyntaxView(store)
        self.retriever = SentenceEntityRetriever(store)

    def first_frame_for_lemmas(
        self,
        sentence: Sentence,
        lemmas: frozenset[str],
    ) -> EventFrame | None:
        trigger = self.syntax.first_token_with_lemmas(sentence, lemmas)
        if trigger is None:
            return None
        return self.frame_for_trigger(sentence, trigger)

    def frame_for_trigger(self, sentence: Sentence, trigger: Token) -> EventFrame:
        return EventFrame(
            sentence=sentence,
            trigger=trigger,
            arguments=tuple(
                self._argument(sentence, trigger, entity)
                for entity in self.retriever.entities_for_sentence(sentence)
            ),
        )

    def _argument(
        self,
        sentence: Sentence,
        trigger: Token,
        entity: SentenceEntity,
    ) -> FrameArgument:
        binding = self.syntax.syntax_binding(
            sentence=sentence,
            trigger_token_id=trigger.id,
            entity_id=entity.id,
        )
        relation_class = (
            binding.relation_class if binding is not None else SyntaxRelationClass.OTHER
        )
        return FrameArgument(
            entity=entity,
            role=_frame_role(relation_class),
            preposition_lemma=self._preposition_for_entity(sentence, entity),
            before_trigger=entity.start_char < trigger.span.start_char,
            distance=self._distance_to_trigger(sentence, trigger.id, entity),
        )

    def _preposition_for_entity(
        self,
        sentence: Sentence,
        entity: SentenceEntity,
    ) -> str | None:
        binding = self.syntax.entity_binding(sentence, entity.id)
        if binding is None:
            return self._lexical_preposition_before_entity(sentence, entity)
        return self.syntax.token_case_lemma(sentence, binding.token_id) or (
            self._lexical_preposition_before_entity(sentence, entity)
        )

    def _lexical_preposition_before_entity(
        self,
        sentence: Sentence,
        entity: SentenceEntity,
    ) -> str | None:
        token_ids = sentence.token_ids
        entity_token_index = next(
            (
                index
                for index, token_id in enumerate(token_ids)
                if self.store.tokens[token_id].span.start_char >= entity.start_char
            ),
            None,
        )
        if entity_token_index is None:
            return None
        for token_id in reversed(token_ids[max(0, entity_token_index - 3) : entity_token_index]):
            token = self.store.tokens[token_id]
            lemma = token.preferred_lemma()
            if lemma is not None:
                return lemma
        return None

    def _distance_to_trigger(
        self,
        sentence: Sentence,
        trigger_token_id: TokenId,
        entity: SentenceEntity,
    ) -> int:
        trigger_index = sentence.token_ids.index(trigger_token_id)
        entity_indexes = [
            index
            for index, token_id in enumerate(sentence.token_ids)
            if entity.start_char <= self.store.tokens[token_id].span.start_char < entity.end_char
        ]
        if not entity_indexes:
            return len(sentence.token_ids)
        return min(abs(index - trigger_index) for index in entity_indexes)


def _frame_role(relation_class: SyntaxRelationClass) -> FrameArgumentRole:
    if relation_class is SyntaxRelationClass.SUBJECT:
        return FrameArgumentRole.SUBJECT
    if relation_class in {SyntaxRelationClass.OBJECT, SyntaxRelationClass.OBLIQUE}:
        return FrameArgumentRole.OBJECT
    if relation_class is SyntaxRelationClass.APPOSITION:
        return FrameArgumentRole.APPOSITION
    if relation_class is SyntaxRelationClass.MODIFIER:
        return FrameArgumentRole.MODIFIER
    return FrameArgumentRole.OTHER
