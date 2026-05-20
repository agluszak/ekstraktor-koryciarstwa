from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.ids import EntityCandidateId, TokenId
from pipeline_v2.nlp import Sentence, Token
from pipeline_v2.store import ExtractionStore


@dataclass(frozen=True, slots=True)
class EntityTokenBinding:
    entity_id: EntityCandidateId
    token_id: TokenId
    start_char: int
    end_char: int


class SyntaxView:
    """Small typed view over dependency arcs and Morfeusz tokens.

    Producers should ask this helper for linguistic relations instead of
    peeking at raw parser records or doing broad sentence-window joins.
    """

    _subject_relations = frozenset({"nsubj", "nsubj:pass", "csubj"})
    _object_relations = frozenset({"obj", "iobj", "obl"})

    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def token_lemmas(self, token: Token) -> frozenset[str]:
        return frozenset(analysis.lemma for analysis in token.morph)

    def has_case(self, token: Token, case: str) -> bool:
        return any(analysis.case == case for analysis in token.morph)

    def is_passive_sentence(self, sentence: Sentence, trigger_token_id: TokenId | None) -> bool:
        if trigger_token_id is not None:
            for arc in self.store.dependency_arcs_for_sentence(sentence.id):
                if arc.head_token_id != trigger_token_id:
                    continue
                if arc.relation == "aux:pass":
                    return True
        for token_id in sentence.token_ids:
            token = self.store.tokens[token_id]
            if self.token_lemmas(token) & {"zostać", "być"}:
                return True
        return False

    def entity_binding(
        self,
        sentence: Sentence,
        entity_id: EntityCandidateId,
    ) -> EntityTokenBinding | None:
        spans: list[EntityTokenBinding] = []
        for mention in self.store.candidate_mentions(entity_id):
            if mention.sentence_id != sentence.id or not mention.token_ids:
                continue
            token_ids = mention.token_ids
            token = self.store.tokens[token_ids[-1]]
            spans.append(
                EntityTokenBinding(
                    entity_id=entity_id,
                    token_id=token.id,
                    start_char=self.store.tokens[token_ids[0]].span.start_char,
                    end_char=token.span.end_char,
                )
            )
        for reference in self.store.candidate_references(entity_id):
            if reference.sentence_id != sentence.id or not reference.token_ids:
                continue
            token_ids = reference.token_ids
            token = self.store.tokens[token_ids[-1]]
            spans.append(
                EntityTokenBinding(
                    entity_id=entity_id,
                    token_id=token.id,
                    start_char=self.store.tokens[token_ids[0]].span.start_char,
                    end_char=token.span.end_char,
                )
            )
        if not spans:
            return None
        return min(spans, key=lambda binding: binding.start_char)

    def dependency_relation(
        self,
        *,
        sentence: Sentence,
        trigger_token_id: TokenId,
        entity_id: EntityCandidateId,
    ) -> str | None:
        binding = self.entity_binding(sentence, entity_id)
        if binding is None:
            return None
        entity_token_ids = {
            token_id
            for mention in self.store.candidate_mentions(entity_id)
            if mention.sentence_id == sentence.id
            for token_id in mention.token_ids
        } | {
            token_id
            for reference in self.store.candidate_references(entity_id)
            if reference.sentence_id == sentence.id
            for token_id in reference.token_ids
        }
        for arc in self.store.dependency_arcs_for_sentence(sentence.id):
            if arc.dependent_token_id not in entity_token_ids:
                continue
            if arc.head_token_id == trigger_token_id:
                return arc.relation
            if arc.dependent_token_id == trigger_token_id:
                return arc.relation
        return None

    def is_subject_relation(self, relation: str | None) -> bool:
        return relation in self._subject_relations

    def is_object_relation(self, relation: str | None) -> bool:
        return relation in self._object_relations

    def first_token_with_lemmas(
        self,
        sentence: Sentence,
        lemmas: frozenset[str],
    ) -> Token | None:
        for token_id in sentence.token_ids:
            token = self.store.tokens[token_id]
            if self.token_lemmas(token) & lemmas:
                return token
        return None
