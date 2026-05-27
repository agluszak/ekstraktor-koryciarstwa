from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.event_frames import EventFrame, FrameArgumentRole
from pipeline_v2.governance.base import GovernanceBase
from pipeline_v2.ids import EntityCandidateId, SentenceId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Token
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    AppointmentLemmaSignal,
    DependencyRelation,
    EntityKind,
    GroundingKind,
    LocalPersonSignal,
    LocalRoleSignal,
    MentionKind,
    Signal,
)


class GovernanceHeuristics(GovernanceBase):
    def _office_person_for_role(
        self,
        document: ArticleDocument,
        role_frame: EventFrame,
        role: SentenceEntity,
        people: tuple[SentenceEntity, ...],
    ) -> SentenceEntity | None:
        attached = tuple(
            argument.entity
            for argument in role_frame.entities(
                EntityKind.PERSON,
                roles=frozenset({FrameArgumentRole.APPOSITION, FrameArgumentRole.MODIFIER}),
            )
        )
        if attached:
            return min(attached, key=lambda person: abs(person.start_char - role.start_char))
        adjacent = tuple(
            person
            for person in people
            if abs(person.start_char - role.end_char) <= 2
            or abs(role.start_char - person.end_char) <= 3
        )
        if adjacent:
            return min(adjacent, key=lambda person: abs(person.start_char - role.start_char))
        copular_lemmas = self._sentence_lemmas(document, role_frame.sentence)
        if not (copular_lemmas & {"być", "zostać"}):
            return None
        copular = tuple(
            argument.entity
            for argument in role_frame.entities(
                EntityKind.PERSON,
                roles=frozenset({FrameArgumentRole.SUBJECT, FrameArgumentRole.OTHER}),
            )
            if argument.distance <= 4
        )
        if copular:
            return min(copular, key=lambda person: abs(person.start_char - role.start_char))
        return None

    def _first_holding_trigger(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> HoldingTrigger | None:
        role_vocab = self._governance_role_lemmas | self._political_role_lemmas
        for token_index, token_id in enumerate(sentence.token_ids):
            token = document.store.tokens[token_id]
            if self._is_former_role_descriptor_trigger(
                document=document,
                sentence=sentence,
                token_index=token_index,
                role_vocab=role_vocab,
            ):
                continue
            for analysis in token.morph:
                if analysis.lemma not in self._holding_lemmas:
                    continue
                if analysis.lemma == "być" and analysis.pos not in self._verb_like_pos:
                    continue
                return HoldingTrigger(
                    lemma=analysis.lemma,
                    start_char=token.span.start_char,
                )
        return None

    def _is_former_role_descriptor_trigger(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        token_index: int,
        role_vocab: frozenset[str],
    ) -> bool:
        token = document.store.tokens[sentence.token_ids[token_index]]
        if not self._token_has_former_descriptor(token):
            return False
        window_end = min(len(sentence.token_ids), token_index + 4)
        role_token_index = next(
            (
                next_index
                for next_index in range(token_index + 1, window_end)
                if {
                    analysis.lemma
                    for analysis in document.store.tokens[sentence.token_ids[next_index]].morph
                }
                & role_vocab
            ),
            None,
        )
        if role_token_index is None:
            return False
        role_token = document.store.tokens[sentence.token_ids[role_token_index]]
        if not self._token_has_instrumental_role_analysis(role_token, role_vocab):
            return True
        return self._sentence_has_following_finite_noncopular_verb(
            document=document,
            sentence=sentence,
            token_index=role_token_index + 1,
        )

    def _token_has_former_descriptor(self, token: Token) -> bool:
        token_lower = token.text.casefold()
        if token_lower in {"był", "była", "było", "byli", "byłe", "były"}:
            return True
        for analysis in token.morph:
            if analysis.lemma in self._former_descriptor_lemmas:
                return True
            if analysis.lemma == "być" and analysis.tag and "praet" in analysis.tag:
                return True
        return False

    def _sentence_has_following_finite_noncopular_verb(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        token_index: int,
    ) -> bool:
        for later_token_id in sentence.token_ids[token_index:]:
            token = document.store.tokens[later_token_id]
            for analysis in token.morph:
                if analysis.pos not in self._verb_like_pos:
                    continue
                if analysis.lemma == "być":
                    continue
                return True
        return False

    def _token_has_instrumental_role_analysis(
        self,
        token: Token,
        role_vocab: frozenset[str],
    ) -> bool:
        for analysis in token.morph:
            if analysis.lemma not in role_vocab:
                continue
            if analysis.tag and ":inst" in analysis.tag:
                return True
        return False

    def _role_has_former_descriptor(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        role: SentenceEntity,
    ) -> bool:
        role_token_indexes = [
            index
            for index, token_id in enumerate(sentence.token_ids)
            if role.start_char <= document.store.tokens[token_id].span.start_char < role.end_char
        ]
        if not role_token_indexes:
            return False
        first_role_index = min(role_token_indexes)
        for token_id in sentence.token_ids[max(0, first_role_index - 3) : first_role_index]:
            if self._token_has_former_descriptor(document.store.tokens[token_id]):
                return True
        return False

    def _role_is_embedded_under_other_role(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        role: SentenceEntity,
    ) -> bool:
        role_token_indexes = [
            index
            for index, token_id in enumerate(sentence.token_ids)
            if role.start_char <= document.store.tokens[token_id].span.start_char < role.end_char
        ]
        if not role_token_indexes:
            return False
        first_role_index = min(role_token_indexes)
        role_vocab = self._governance_role_lemmas | self._political_role_lemmas
        for token_id in sentence.token_ids[max(0, first_role_index - 2) : first_role_index]:
            if {analysis.lemma for analysis in document.store.tokens[token_id].morph} & role_vocab:
                return True
        return False

    def _first_token_for_entity(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity: SentenceEntity,
    ) -> Token:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if entity.start_char <= token.span.start_char < entity.end_char:
                return token
        return document.store.tokens[sentence.token_ids[0]]

    def _has_tight_generic_dismissal_cluster(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        dismissal_lemmas: frozenset[str],
    ) -> bool:
        generic_indexes: list[int] = []
        dismissal_indexes: list[int] = []
        for index, token_id in enumerate(sentence.token_ids):
            token = document.store.tokens[token_id]
            lemmas = {analysis.lemma for analysis in token.morph}
            if lemmas & self._generic_appointment_lemmas:
                generic_indexes.append(index)
            if lemmas & dismissal_lemmas:
                dismissal_indexes.append(index)
        if not generic_indexes or not dismissal_indexes:
            return False
        return all(
            any(abs(generic_index - dismissal_index) <= 2 for dismissal_index in dismissal_indexes)
            for generic_index in generic_indexes
        )

    def _person_starts_after_dismissal_cue(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
    ) -> bool:
        dismissal_starts = [
            document.store.tokens[token_id].span.start_char
            for token_id in sentence.token_ids
            if {analysis.lemma for analysis in document.store.tokens[token_id].morph}
            & (self._dismissal_lemmas - {"zasiadać"})
        ]
        if not dismissal_starts:
            return False
        person_starts = [
            evidence.span.start_char
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        ]
        return bool(person_starts) and min(person_starts) > min(dismissal_starts)

    def _objac_tokens_are_temporal(self, document: ArticleDocument, sentence: Sentence) -> bool:
        syntax = SyntaxView(document.store)
        objac_token_ids = [
            token_id
            for token_id in sentence.token_ids
            if {analysis.lemma for analysis in document.store.tokens[token_id].morph}
            & self._objac_appointment_lemmas
        ]
        if not objac_token_ids:
            return False

        def has_temporal_case(token_id) -> bool:
            for arc in syntax.token_children(
                sentence, token_id, relations=frozenset({DependencyRelation.CASE})
            ):
                case_lemmas = {
                    analysis.lemma
                    for analysis in document.store.tokens[arc.dependent_token_id].morph
                }
                if case_lemmas & self._temporal_prepositions:
                    return True
            return False

        return all(has_temporal_case(tid) for tid in objac_token_ids)

    def _sentence_has_successor_pattern(
        self, document: ArticleDocument, sentence: Sentence
    ) -> bool:
        lemmas = self._sentence_lemmas(document, sentence)
        return bool(lemmas & self._successor_noun_lemmas) and "zostać" in lemmas

    def _person_appears_after_trigger_in_sentence(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        trigger_start_char: int,
    ) -> bool:
        return any(
            evidence.span.start_char > trigger_start_char
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        )

    def _sentence_has_dash_apposition_with_current_role(
        self, document: ArticleDocument, sentence: Sentence
    ) -> bool:
        tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
        for i, token in enumerate(tokens):
            if token.text not in self._dash_chars:
                continue
            subsequent_lemmas: set[str] = set()
            for subsequent_token in tokens[i + 1 :]:
                for analysis in subsequent_token.morph:
                    subsequent_lemmas.add(analysis.lemma)
            if (
                subsequent_lemmas & self._current_descriptor_lemmas
                and subsequent_lemmas & self._governance_role_lemmas
            ):
                return True
        return False

    def _person_is_in_exception_clause(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
    ) -> bool:
        exception_ranges = self._exception_clause_ranges(document, sentence)
        if not exception_ranges:
            return False
        person_starts = [
            evidence.span.start_char
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        ]
        return any(
            start <= person_start < end
            for person_start in person_starts
            for start, end in exception_ranges
        )

    def _exception_clause_ranges(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[int, int], ...]:
        tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
        ranges: list[tuple[int, int]] = []
        for index, token in enumerate(tokens):
            if not ({analysis.lemma for analysis in token.morph} & self._exception_clause_lemmas):
                continue
            end = sentence.span.end_char
            for subsequent in tokens[index + 1 :]:
                if subsequent.text in {",", ";", ":", "—", "–"}:
                    end = subsequent.span.start_char
                    break
            ranges.append((token.span.start_char, end))
        return tuple(ranges)

    def _person_is_adjacent_before_trigger(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        trigger_start_char: int,
    ) -> bool:
        spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        ]
        return any(0 <= trigger_start_char - span.end_char <= 2 for span in spans)

    def _sentence_is_first_person_departure_report(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> bool:
        if not (self._sentence_lemmas(document, sentence) & self._dismissal_lemmas):
            return False
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if any(analysis.person == "pri" for analysis in token.morph):
                return True
        return False

    def _filter_exit_role_combinations(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        combinations: list[
            tuple[EntityCandidateId | None, EntityCandidateId | None, tuple[Signal, ...]]
        ],
    ) -> list[tuple[EntityCandidateId | None, EntityCandidateId | None, tuple[Signal, ...]]]:
        attached_role_ids = {
            role_id
            for _, role_id, _ in combinations
            if role_id is not None
            and self._role_is_locally_attached_to_person(
                document=document,
                sentence=sentence,
                person_id=person_id,
                role_id=role_id,
            )
        }
        if attached_role_ids:
            return [
                combination
                for combination in combinations
                if combination[1] is None or combination[1] in attached_role_ids
            ]

        non_alternative_role_ids = {
            role_id
            for _, role_id, _ in combinations
            if role_id is not None
            and not self._role_is_alternative_departure_target(
                document=document,
                sentence=sentence,
                role_id=role_id,
            )
        }
        if non_alternative_role_ids:
            return [
                combination
                for combination in combinations
                if combination[1] is None or combination[1] in non_alternative_role_ids
            ]
        return combinations

    def _role_is_locally_attached_to_person(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        role_id: EntityCandidateId,
    ) -> bool:
        person_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        ]
        role_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(role_id)
            if evidence.sentence_id == sentence.id
        ]
        if not person_spans or not role_spans:
            return False

        person_start = min(span.start_char for span in person_spans)
        person_end = max(span.end_char for span in person_spans)
        role_start = min(span.start_char for span in role_spans)
        role_end = max(span.end_char for span in role_spans)

        if role_end <= person_start:
            return person_start - role_end <= 2
        if person_end <= role_start:
            between_text = document.cleaned_text[person_end:role_start].strip()
            if len(between_text) > 2:
                return False
            return between_text in {"", ",", "—", "–", "-"}
        return False

    def _role_is_alternative_departure_target(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        role_id: EntityCandidateId,
    ) -> bool:
        role_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(role_id)
            if evidence.sentence_id == sentence.id
        ]
        if not role_spans:
            return False
        role_start_char = min(span.start_char for span in role_spans)
        prefix = document.cleaned_text[
            max(sentence.span.start_char, role_start_char - 24) : role_start_char
        ]
        prefix_folded = prefix.casefold()
        if "mandat" in prefix_folded:
            return True
        return "na rzecz" in prefix_folded

    def _augment_local_roles_with_person_titles(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        local_entities: tuple[SentenceEntity, ...],
        roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        existing_role_ids = {role.id for role, _signals in roles}
        sentence_token_ids = list(sentence.token_ids)
        augmented_roles = list(roles)
        role_vocab = self._governance_role_lemmas | self._political_role_lemmas

        for entity in local_entities:
            if entity.kind is not EntityKind.PERSON:
                continue
            person_start_index = next(
                (
                    index
                    for index, token_id in enumerate(sentence_token_ids)
                    if document.store.tokens[token_id].span.start_char >= entity.start_char
                ),
                None,
            )
            if person_start_index is None:
                continue
            title_index = person_start_index - 1
            if title_index < 0:
                continue
            title_token = document.store.tokens[sentence_token_ids[title_index]]
            title_lemmas = {analysis.lemma for analysis in title_token.morph}
            if not (title_lemmas & role_vocab):
                continue
            role_entity = self._materialize_local_role_entity(
                document=document,
                sentence=sentence,
                token_index=title_index,
            )
            if role_entity is None or role_entity.id in existing_role_ids:
                continue
            existing_role_ids.add(role_entity.id)
            augmented_roles.append((role_entity, (LocalRoleSignal(),)))
        holding_title = self._holding_predicate_role_entity(document, sentence)
        if holding_title is not None and holding_title.id not in existing_role_ids:
            augmented_roles.append((holding_title, (LocalRoleSignal(),)))
        return tuple(augmented_roles)

    def _materialize_local_role_entity(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        token_index: int,
    ) -> SentenceEntity | None:
        token_id = sentence.token_ids[token_index]
        token = document.store.tokens[token_id]
        start_char = token.span.start_char
        end_char = token.span.end_char

        for candidate in document.store.candidates_by_kind(EntityKind.ROLE):
            for evidence in document.store.evidence_for_entity(candidate.id):
                if (
                    evidence.sentence_id == sentence.id
                    and evidence.span.start_char == start_char
                    and evidence.span.end_char == end_char
                ):
                    return SentenceEntity(
                        id=candidate.id,
                        kind=EntityKind.ROLE,
                        start_char=start_char,
                        end_char=end_char,
                    )

        evidence_id = document.store.next_evidence_id()
        evidence = EvidenceSpan(
            id=evidence_id,
            text=token.text,
            span=token.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        mention = Mention(
            id=mention_id,
            text=token.text,
            kind=MentionKind.ROLE,
            evidence_id=evidence_id,
            sentence_id=sentence.id,
            token_ids=(token_id,),
            head_lemma=next((analysis.lemma for analysis in token.morph), None),
        )
        document.store.add_mention(mention)
        candidate_id = document.store.next_entity_candidate_id()
        candidate = EntityCandidate(
            id=candidate_id,
            kind=EntityKind.ROLE,
            grounding=GroundingKind.OBSERVED,
            canonical_hint=token.text,
            mention_ids=(mention_id,),
            source=self.producer_id,
        )
        document.store.add_entity_candidate(candidate)
        return SentenceEntity(
            id=candidate_id,
            kind=EntityKind.ROLE,
            start_char=start_char,
            end_char=end_char,
        )

    def _role_has_current_descriptor(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        role: SentenceEntity,
    ) -> bool:
        role_token_indexes = [
            index
            for index, token_id in enumerate(sentence.token_ids)
            if role.start_char <= document.store.tokens[token_id].span.start_char < role.end_char
        ]
        if not role_token_indexes:
            return False
        first_role_index = min(role_token_indexes)
        for token_id in sentence.token_ids[max(0, first_role_index - 3) : first_role_index]:
            token = document.store.tokens[token_id]
            if {analysis.lemma for analysis in token.morph} & self._current_descriptor_lemmas:
                return True
        return False

    def _sentence_has_possessive_holder_pronoun_before_char(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        end_char: int,
    ) -> bool:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if token.span.start_char >= end_char:
                break
            token_lower = token.text.casefold()
            if token_lower in {"jej", "jego", "ich"}:
                return True
        return False

    def _previous_sentence_holding_people(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[SentenceEntity, ...]:
        previous_index = sentence.sentence_index - 1
        if previous_index < 0:
            return ()
        people: list[SentenceEntity] = []
        for candidate in document.store.candidates_by_kind(EntityKind.PERSON):
            spans = [
                evidence.span
                for evidence in document.store.evidence_for_entity(candidate.id)
                if evidence.sentence_id is not None
                and document.store.sentences[evidence.sentence_id].sentence_index == previous_index
            ]
            if not spans:
                continue
            people.append(
                SentenceEntity(
                    id=candidate.id,
                    kind=EntityKind.PERSON,
                    start_char=min(span.start_char for span in spans),
                    end_char=max(span.end_char for span in spans),
                )
            )
        return tuple(sorted(people, key=lambda person: person.start_char))

    def _expand_conjunct_people(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        people: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
        local_entities: tuple[SentenceEntity, ...],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        syntax = SyntaxView(document.store)
        token_to_entity: dict[TokenId, SentenceEntity] = {}
        for entity in local_entities:
            if entity.kind != EntityKind.PERSON:
                continue
            binding = syntax.entity_binding(sentence, entity.id)
            if binding is not None:
                token_to_entity[binding.token_id] = entity

        existing_ids: set[EntityCandidateId] = {person.id for person, _ in people}
        expanded: list[tuple[SentenceEntity, tuple[Signal, ...]]] = list(people)

        to_visit: list[TokenId] = []
        for person, _ in people:
            binding = syntax.entity_binding(sentence, person.id)
            if binding is not None:
                to_visit.append(binding.token_id)

        visited: set[TokenId] = set(to_visit)
        while to_visit:
            curr_token_id = to_visit.pop(0)
            for arc in syntax.token_children(
                sentence,
                curr_token_id,
                relations=frozenset({DependencyRelation.CONJ}),
            ):
                dep_id = arc.dependent_token_id
                if dep_id not in visited:
                    visited.add(dep_id)
                    to_visit.append(dep_id)
                    conjunct = token_to_entity.get(dep_id)
                    if conjunct is not None and conjunct.id not in existing_ids:
                        existing_ids.add(conjunct.id)
                        expanded.append((conjunct, (LocalPersonSignal(),)))

        return tuple(expanded)

    def _first_token_start_char_with_lemmas(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        vocabulary: frozenset[str],
    ) -> int | None:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if {analysis.lemma for analysis in token.morph} & vocabulary:
                return token.span.start_char
        return None

    def _clause_end_after_char(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        start_char: int,
    ) -> int:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if token.span.start_char <= start_char:
                continue
            if token.text in {",", ";", "—", "–"}:
                return token.span.start_char
        return sentence.span.end_char

    def _clause_start_before_char(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        end_char: int,
    ) -> int:
        clause_start = sentence.span.start_char
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if token.span.start_char >= end_char:
                break
            if token.text in {",", ";", "-", "—", "–"}:
                clause_start = token.span.end_char
        return clause_start

    def _public_office_role_near_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity_id: EntityCandidateId,
    ) -> str | None:
        person_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(entity_id)
            if evidence.sentence_id == sentence.id
        ]
        if not person_spans:
            return None
        public_office_lemmas = {"burmistrz", "prezydent", "starosta", "wójt"}
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if not any(analysis.lemma in public_office_lemmas for analysis in token.morph):
                continue
            if any(
                abs(token.span.start_char - span.start_char) <= 80
                or abs(token.span.end_char - span.end_char) <= 80
                for span in person_spans
            ):
                return next(
                    analysis.lemma
                    for analysis in token.morph
                    if analysis.lemma in public_office_lemmas
                )
        return None

    def _has_reflexive_particle(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        trigger: Token,
        syntax: SyntaxView,
    ) -> bool:
        for arc in syntax.token_children(sentence, trigger.id):
            child = document.store.tokens[arc.dependent_token_id]
            if child.text.lower() == "się":
                return True
        return False

    def _role_sentence_has_departure_context(
        self,
        document: ArticleDocument,
        role: SentenceEntity,
    ) -> bool:
        role_sentence_id = document.store.sentence_id_for_offset(role.start_char)
        if role_sentence_id is None:
            return False
        role_sentence = document.store.sentences.get(role_sentence_id)
        if role_sentence is None:
            return False
        departure_lemmas = self._dismissal_lemmas | {"pożegnać"}
        return bool(self._sentence_lemmas(document, role_sentence) & departure_lemmas)

    def _entity_source_sentence_id(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> SentenceId | None:
        for evidence in document.store.evidence_for_entity(entity_id):
            if evidence.sentence_id is not None:
                return evidence.sentence_id
        return None

    def _role_sentence_has_departure_context_by_id(
        self,
        document: ArticleDocument,
        role_id: EntityCandidateId,
    ) -> bool:
        sentence_id = self._entity_source_sentence_id(document, role_id)
        if sentence_id is None:
            return False
        sentence = document.store.sentences.get(sentence_id)
        if sentence is None:
            return False
        departure_lemmas = self._dismissal_lemmas | {"pożegnać"}
        return bool(self._sentence_lemmas(document, sentence) & departure_lemmas)

    def _observed_people_in_sentence(
        self,
        document: ArticleDocument,
        sentence_id: SentenceId,
    ) -> frozenset[EntityCandidateId]:
        people: set[EntityCandidateId] = set()
        for candidate in document.store.candidates_by_kind(EntityKind.PERSON):
            if candidate.grounding is not GroundingKind.OBSERVED:
                continue
            for mention in document.store.candidate_mentions(candidate.id):
                evidence = document.store.evidence.get(mention.evidence_id)
                if evidence is not None and evidence.sentence_id == sentence_id:
                    people.add(candidate.id)
        return frozenset(people)

    def _role_id_for_person_in_sentence(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
    ) -> EntityCandidateId | None:
        person_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        ]
        if not person_spans:
            return None
        person_start = min(span.start_char for span in person_spans)
        closest_role_id: EntityCandidateId | None = None
        closest_end: int = -1
        for candidate in document.store.candidates_by_kind(EntityKind.ROLE):
            for evidence in document.store.evidence_for_entity(candidate.id):
                if evidence.sentence_id != sentence.id:
                    continue
                if evidence.span.end_char <= person_start and evidence.span.end_char > closest_end:
                    closest_end = evidence.span.end_char
                    closest_role_id = candidate.id
        return closest_role_id

    def _entity_start_char(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity_id: EntityCandidateId,
    ) -> int:
        spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(entity_id)
            if evidence.sentence_id == sentence.id
        ]
        if spans:
            return min(span.start_char for span in spans)
        spans = [evidence.span for evidence in document.store.evidence_for_entity(entity_id)]
        return min((span.start_char for span in spans), default=0)

    def _sentence_has_governance_role_entity(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> bool:
        retriever = SentenceEntityRetriever(document.store)
        entities = retriever.entities_for_sentence(sentence)
        for entity in entities:
            if entity.kind != EntityKind.ROLE:
                continue
            if self._has_governance_role(document, entity.id):
                return True
            for mention in document.store.candidate_mentions(entity.id):
                for token in document.store.tokens_for_mention(mention.id):
                    if any(
                        analysis.lemma in self._political_role_lemmas for analysis in token.morph
                    ):
                        return True
        return False

    def _sentence_has_inline_person_title(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> bool:
        role_vocab = self._governance_role_lemmas | self._political_role_lemmas
        retriever = SentenceEntityRetriever(document.store)
        people = tuple(
            entity
            for entity in retriever.entities_for_sentence(sentence)
            if entity.kind is EntityKind.PERSON
        )
        sentence_token_ids = list(sentence.token_ids)
        for person in people:
            person_start_index = next(
                (
                    index
                    for index, token_id in enumerate(sentence_token_ids)
                    if document.store.tokens[token_id].span.start_char >= person.start_char
                ),
                None,
            )
            if person_start_index is None or person_start_index == 0:
                continue
            title_token = document.store.tokens[sentence_token_ids[person_start_index - 1]]
            if {analysis.lemma for analysis in title_token.morph} & role_vocab:
                return True
        return False

    def _sentence_has_holding_predicate_title(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> bool:
        return self._holding_predicate_role_entity(document, sentence) is not None

    def _holding_predicate_role_entity(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> SentenceEntity | None:
        role_vocab = self._governance_role_lemmas | self._political_role_lemmas
        trigger = self._first_holding_trigger(document, sentence)
        if trigger is None or trigger.lemma not in {"być", "pozostawać"}:
            return None
        trigger_start_char = trigger.start_char
        trigger_token_index = next(
            (
                index
                for index, token_id in enumerate(sentence.token_ids)
                if document.store.tokens[token_id].span.start_char == trigger_start_char
            ),
            None,
        )
        if trigger_token_index is None:
            return None
        for token_index in range(trigger_token_index - 1, -1, -1):
            token = document.store.tokens[sentence.token_ids[token_index]]
            if {analysis.lemma for analysis in token.morph} & role_vocab:
                return self._materialize_local_role_entity(
                    document=document,
                    sentence=sentence,
                    token_index=token_index,
                )
        return None

    def _sentence_lemmas(self, document: ArticleDocument, sentence: Sentence) -> frozenset[str]:
        lemmas: set[str] = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _matched_detail(self, lemmas: frozenset[str], vocabulary: frozenset[str]) -> str:
        return next(iter(sorted(lemmas & vocabulary)))

    def _is_employment_overlap(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case AppointmentLemmaSignal(lemma="zatrudnić"):
                    return True
        return False

    def _is_generic_appointment_lemma(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case AppointmentLemmaSignal(lemma=lemma) if (
                    lemma in self._generic_appointment_lemmas
                ):
                    return True
        return False

    def _has_governance_role(
        self,
        document: ArticleDocument,
        role_id: EntityCandidateId | None,
    ) -> bool:
        if role_id is None:
            return False
        for mention in document.store.candidate_mentions(role_id):
            for token in document.store.tokens_for_mention(mention.id):
                if any(analysis.lemma in self._governance_role_lemmas for analysis in token.morph):
                    return True
        return False

    def _has_singular_person_role(
        self,
        document: ArticleDocument,
        role_id: EntityCandidateId | None,
    ) -> bool:
        if role_id is None:
            return False
        for mention in document.store.candidate_mentions(role_id):
            for token in document.store.tokens_for_mention(mention.id):
                if any(
                    analysis.lemma in self._singular_person_role_lemmas for analysis in token.morph
                ):
                    return True
        return False

    def _is_descriptor_role_self_pair(
        self,
        document: ArticleDocument,
        person_id: EntityCandidateId,
        role_id: EntityCandidateId | None,
    ) -> bool:
        if role_id is None:
            return False
        person = document.store.entity_candidates.get(person_id)
        role = document.store.entity_candidates.get(role_id)
        if person is None or role is None:
            return False
        if person.grounding is not GroundingKind.INFERRED:
            return False
        person_mentions = tuple(document.store.candidate_mentions(person_id))
        role_mentions = tuple(document.store.candidate_mentions(role_id))
        if len(person_mentions) != 1 or len(role_mentions) != 1:
            return False
        person_mention = person_mentions[0]
        role_mention = role_mentions[0]
        if person_mention.kind is not MentionKind.DESCRIPTOR_NOUN_PHRASE:
            return False
        if person_mention.text.casefold() != role_mention.text.casefold():
            return False
        person_evidence = document.store.evidence.get(person_mention.evidence_id)
        role_evidence = document.store.evidence.get(role_mention.evidence_id)
        if person_evidence is None or role_evidence is None:
            return False
        return (
            person_evidence.sentence_id == role_evidence.sentence_id
            and person_evidence.span == role_evidence.span
        )

    def _restrict_roles_to_clause(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        """Narrow roles to the zasiadać or holding-trigger clause when one is present."""
        zasiadac_start = self._first_token_start_char_with_lemmas(
            document,
            sentence,
            frozenset({"zasiadać"}),
        )
        if zasiadac_start is not None:
            clause_start = self._clause_start_before_char(document, sentence, zasiadac_start)
            clause_end = self._clause_end_after_char(document, sentence, zasiadac_start)
            clause_roles = tuple(
                (role, sigs) for role, sigs in roles if clause_start <= role.start_char < clause_end
            )
            if clause_roles:
                return clause_roles

        holding_trigger = self._first_holding_trigger(document, sentence)
        if holding_trigger is not None and holding_trigger.lemma in {"być", "pozostawać"}:
            clause_start = self._clause_start_before_char(
                document,
                sentence,
                holding_trigger.start_char,
            )
            predicate_roles = tuple(
                (role, sigs)
                for role, sigs in roles
                if (
                    self._entity_source_sentence_id(document, role.id) == sentence.id
                    and clause_start <= role.start_char < holding_trigger.start_char
                )
            )
            if predicate_roles:
                return predicate_roles

        return roles

    def _prior_role_org_ids(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> frozenset[EntityCandidateId]:
        if not (self._sentence_lemmas(document, sentence) & self._appointment_lemmas):
            return frozenset()
        prior_descriptor_lemmas = self._former_descriptor_lemmas | {"dotychczasowy"}
        role_vocab = self._governance_role_lemmas | self._political_role_lemmas
        local_entity_ids = frozenset(
            entity.id
            for entity in SentenceEntityRetriever(document.store).entities_for_sentence(sentence)
            if entity.kind == EntityKind.ORGANIZATION
        )
        tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
        result: set[EntityCandidateId] = set()
        for org_id in local_entity_ids:
            org_evidences = [
                ev
                for ev in document.store.evidence_for_entity(org_id)
                if ev.sentence_id == sentence.id
            ]
            if not org_evidences:
                continue
            org_start = min(ev.span.start_char for ev in org_evidences)
            org_token_index = next(
                (i for i, t in enumerate(tokens) if t.span.start_char >= org_start),
                None,
            )
            if org_token_index is None:
                continue
            window_start = max(0, org_token_index - 10)
            window_tokens = tokens[window_start:org_token_index]
            has_former_descriptor = any(
                self._token_has_former_descriptor(t)
                or any(a.lemma in prior_descriptor_lemmas for a in t.morph)
                for t in window_tokens
            )
            has_role_lemma = any(any(a.lemma in role_vocab for a in t.morph) for t in window_tokens)
            if has_former_descriptor and has_role_lemma:
                result.add(org_id)
        return frozenset(result)


@dataclass(frozen=True, slots=True)
class HoldingTrigger:
    lemma: str
    start_char: int


# Module-level stateless wrappers for stateless heuristics functions used by candidates.py
_heuristics = GovernanceHeuristics()


def sentence_lemmas(document: ArticleDocument, sentence: Sentence) -> frozenset[str]:
    return _heuristics._sentence_lemmas(document, sentence)


def first_holding_trigger(document: ArticleDocument, sentence: Sentence) -> HoldingTrigger | None:
    return _heuristics._first_holding_trigger(document, sentence)


def has_governance_role(document: ArticleDocument, role_id: EntityCandidateId | None) -> bool:
    return _heuristics._has_governance_role(document, role_id)


def has_singular_person_role(document: ArticleDocument, role_id: EntityCandidateId | None) -> bool:
    return _heuristics._has_singular_person_role(document, role_id)


def previous_sentence_holding_people(
    document: ArticleDocument, sentence: Sentence
) -> tuple[SentenceEntity, ...]:
    return _heuristics._previous_sentence_holding_people(document, sentence)


def augment_local_roles_with_person_titles(
    document: ArticleDocument,
    sentence: Sentence,
    local_entities: tuple[SentenceEntity, ...],
    roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
    return _heuristics._augment_local_roles_with_person_titles(
        document=document,
        sentence=sentence,
        local_entities=local_entities,
        roles=roles,
    )


def sentence_is_first_person_departure_report(
    document: ArticleDocument, sentence: Sentence
) -> bool:
    return _heuristics._sentence_is_first_person_departure_report(document, sentence)


def expand_conjunct_people(
    document: ArticleDocument,
    sentence: Sentence,
    people: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    entities: tuple[SentenceEntity, ...],
) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
    return _heuristics._expand_conjunct_people(document, sentence, people, entities)


def clause_end_after_char(document: ArticleDocument, sentence: Sentence, char_idx: int) -> int:
    return _heuristics._clause_end_after_char(document, sentence, char_idx)


def entity_source_sentence_id(
    document: ArticleDocument, entity_id: EntityCandidateId
) -> SentenceId | None:
    return _heuristics._entity_source_sentence_id(document, entity_id)


def observed_people_in_sentence(
    document: ArticleDocument, sentence_id: SentenceId
) -> frozenset[EntityCandidateId]:
    return _heuristics._observed_people_in_sentence(document, sentence_id)


def role_id_for_person_in_sentence(
    document: ArticleDocument, sentence: Sentence, person_id: EntityCandidateId
) -> EntityCandidateId | None:
    return _heuristics._role_id_for_person_in_sentence(document, sentence, person_id)


def entity_start_char(
    document: ArticleDocument, sentence: Sentence, entity_id: EntityCandidateId
) -> int:
    return _heuristics._entity_start_char(document, sentence, entity_id)


def sentence_has_governance_role_entity(document: ArticleDocument, sentence: Sentence) -> bool:
    return _heuristics._sentence_has_governance_role_entity(document, sentence)


def sentence_has_inline_person_title(document: ArticleDocument, sentence: Sentence) -> bool:
    return _heuristics._sentence_has_inline_person_title(document, sentence)


def sentence_has_holding_predicate_title(document: ArticleDocument, sentence: Sentence) -> bool:
    return _heuristics._sentence_has_holding_predicate_title(document, sentence)


def holding_predicate_role_entity(
    document: ArticleDocument, sentence: Sentence
) -> SentenceEntity | None:
    return _heuristics._holding_predicate_role_entity(document, sentence)


def restrict_roles_to_clause(
    document: ArticleDocument,
    sentence: Sentence,
    roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
    return _heuristics._restrict_roles_to_clause(document, sentence, roles)


def sentence_has_dash_apposition_with_current_role(
    document: ArticleDocument, sentence: Sentence
) -> bool:
    return _heuristics._sentence_has_dash_apposition_with_current_role(document, sentence)


def is_former_role_descriptor_trigger(
    document: ArticleDocument, sentence: Sentence, start_char: int
) -> bool:
    token_index = next(
        (
            index
            for index, token_id in enumerate(sentence.token_ids)
            if document.store.tokens[token_id].span.start_char == start_char
        ),
        None,
    )
    if token_index is None:
        return False
    role_vocab = _heuristics._governance_role_lemmas | _heuristics._political_role_lemmas
    return _heuristics._is_former_role_descriptor_trigger(
        document=document,
        sentence=sentence,
        token_index=token_index,
        role_vocab=role_vocab,
    )


def sentence_has_following_finite_noncopular_verb(
    document: ArticleDocument, sentence: Sentence, start_char: int
) -> bool:
    token_index = next(
        (
            index
            for index, token_id in enumerate(sentence.token_ids)
            if document.store.tokens[token_id].span.start_char == start_char
        ),
        None,
    )
    if token_index is None:
        return False
    return _heuristics._sentence_has_following_finite_noncopular_verb(
        document=document,
        sentence=sentence,
        token_index=token_index,
    )


def token_has_instrumental_role_analysis(
    document: ArticleDocument, sentence: Sentence, start_char: int
) -> bool:
    token_index = next(
        (
            index
            for index, token_id in enumerate(sentence.token_ids)
            if document.store.tokens[token_id].span.start_char == start_char
        ),
        None,
    )
    if token_index is None:
        return False
    token = document.store.tokens[sentence.token_ids[token_index]]
    role_vocab = _heuristics._governance_role_lemmas | _heuristics._political_role_lemmas
    return _heuristics._token_has_instrumental_role_analysis(token, role_vocab)


def role_has_former_descriptor(
    document: ArticleDocument, sentence: Sentence, role: SentenceEntity
) -> bool:
    return _heuristics._role_has_former_descriptor(document=document, sentence=sentence, role=role)


def role_is_embedded_under_other_role(
    document: ArticleDocument,
    sentence: Sentence,
    role: SentenceEntity,
    roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...] | None = None,
) -> bool:
    return _heuristics._role_is_embedded_under_other_role(document, sentence, role)


def sentence_has_possessive_holder_pronoun_before_char(
    document: ArticleDocument, sentence: Sentence, char_idx: int
) -> bool:
    return _heuristics._sentence_has_possessive_holder_pronoun_before_char(
        document, sentence, char_idx
    )


def first_token_for_entity(
    document: ArticleDocument, sentence: Sentence, entity: SentenceEntity
) -> Token:
    return _heuristics._first_token_for_entity(document, sentence, entity)


def office_person_for_role(
    document: ArticleDocument,
    role_frame: EventFrame,
    role: SentenceEntity,
    people: tuple[SentenceEntity, ...],
) -> SentenceEntity | None:
    return _heuristics._office_person_for_role(document, role_frame, role, people)


def prior_role_org_ids(
    document: ArticleDocument,
    sentence: Sentence,
) -> frozenset[EntityCandidateId]:
    return _heuristics._prior_role_org_ids(document, sentence)
