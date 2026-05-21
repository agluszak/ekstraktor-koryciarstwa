from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.ids import EntityCandidateId, TokenId
from pipeline_v2.nlp import DependencyArc, Sentence, Token
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import DependencyRelation, EntityKind, SyntaxRelationClass


@dataclass(frozen=True, slots=True)
class EntityTokenBinding:
    entity_id: EntityCandidateId
    entity_kind: EntityKind
    token_id: TokenId
    start_char: int
    end_char: int


@dataclass(frozen=True, slots=True)
class SyntaxBinding:
    entity_id: EntityCandidateId
    entity_kind: EntityKind
    entity_head_token_id: TokenId
    trigger_token_id: TokenId
    relation: DependencyRelation
    relation_class: SyntaxRelationClass
    path_length: int
    direction: str


class SyntaxView:
    """Small typed view over dependency arcs and Morfeusz tokens.

    Producers should ask this helper for linguistic relations instead of
    peeking at raw parser records or doing broad sentence-window joins.
    """

    _subject_relations = frozenset(
        {
            DependencyRelation.NSUBJ,
            DependencyRelation.NSUBJ_PASS,
            DependencyRelation.CSUBJ,
        }
    )
    _object_relations = frozenset({DependencyRelation.OBJ, DependencyRelation.IOBJ})
    _oblique_relations = frozenset({DependencyRelation.OBL})
    _modifier_relations = frozenset(
        {
            DependencyRelation.ACL,
            DependencyRelation.AMOD,
            DependencyRelation.NMOD,
            DependencyRelation.NUMMOD,
        }
    )

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
                if arc.relation == DependencyRelation.AUX_PASS:
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
                    entity_kind=self.store.entity_candidates[entity_id].kind,
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
                    entity_kind=self.store.entity_candidates[entity_id].kind,
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
    ) -> DependencyRelation | None:
        binding = self.syntax_binding(
            sentence=sentence,
            trigger_token_id=trigger_token_id,
            entity_id=entity_id,
        )
        return binding.relation if binding is not None else None

    def syntax_binding(
        self,
        *,
        sentence: Sentence,
        trigger_token_id: TokenId,
        entity_id: EntityCandidateId,
    ) -> SyntaxBinding | None:
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
        arcs = self.store.dependency_arcs_for_sentence(sentence.id)
        for arc in arcs:
            if arc.dependent_token_id not in entity_token_ids:
                continue
            if arc.head_token_id == trigger_token_id:
                return self._syntax_binding(
                    binding=binding,
                    trigger_token_id=trigger_token_id,
                    arc=arc,
                    path_length=1,
                    direction="entity_dependent",
                )
        for arc in arcs:
            if arc.head_token_id not in entity_token_ids:
                continue
            if arc.dependent_token_id == trigger_token_id:
                return self._syntax_binding(
                    binding=binding,
                    trigger_token_id=trigger_token_id,
                    arc=arc,
                    path_length=1,
                    direction="trigger_dependent",
                )
        for first_arc in arcs:
            if first_arc.dependent_token_id not in entity_token_ids:
                continue
            intermediate = first_arc.head_token_id
            if intermediate is None:
                continue
            for second_arc in arcs:
                if second_arc.dependent_token_id != intermediate:
                    continue
                if second_arc.head_token_id != trigger_token_id:
                    continue
                return self._syntax_binding(
                    binding=binding,
                    trigger_token_id=trigger_token_id,
                    arc=first_arc,
                    path_length=2,
                    direction="entity_via_head",
                )
        return None

    def is_subject_relation(self, relation: DependencyRelation | None) -> bool:
        return relation in self._subject_relations

    def is_object_relation(self, relation: DependencyRelation | None) -> bool:
        return relation in self._object_relations or relation in self._oblique_relations

    def relation_class(self, relation: DependencyRelation) -> SyntaxRelationClass:
        if relation in self._subject_relations:
            return SyntaxRelationClass.SUBJECT
        if relation in self._object_relations:
            return SyntaxRelationClass.OBJECT
        if relation in self._oblique_relations:
            return SyntaxRelationClass.OBLIQUE
        if relation == DependencyRelation.APPOS:
            return SyntaxRelationClass.APPOSITION
        if relation == DependencyRelation.COP:
            return SyntaxRelationClass.COPULAR
        if relation == DependencyRelation.AUX_PASS:
            return SyntaxRelationClass.AUX_PASSIVE
        if relation in self._modifier_relations:
            return SyntaxRelationClass.MODIFIER
        return SyntaxRelationClass.OTHER

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

    def token_children(
        self,
        sentence: Sentence,
        head_token_id: TokenId,
        *,
        relations: frozenset[DependencyRelation] | None = None,
    ) -> tuple[DependencyArc, ...]:
        return tuple(
            arc
            for arc in self.store.dependency_arcs_for_sentence(sentence.id)
            if arc.head_token_id == head_token_id
            and (relations is None or arc.relation in relations)
        )

    def token_case_lemma(self, sentence: Sentence, token_id: TokenId) -> str | None:
        for arc in self.token_children(
            sentence,
            token_id,
            relations=frozenset({DependencyRelation.CASE}),
        ):
            token = self.store.tokens[arc.dependent_token_id]
            lemma = token.preferred_lemma()
            if lemma is not None:
                return lemma
        return None

    def _syntax_binding(
        self,
        *,
        binding: EntityTokenBinding,
        trigger_token_id: TokenId,
        arc: DependencyArc,
        path_length: int,
        direction: str,
    ) -> SyntaxBinding:
        return SyntaxBinding(
            entity_id=binding.entity_id,
            entity_kind=binding.entity_kind,
            entity_head_token_id=binding.token_id,
            trigger_token_id=trigger_token_id,
            relation=arc.relation,
            relation_class=self.relation_class(arc.relation),
            path_length=path_length,
            direction=direction,
        )
