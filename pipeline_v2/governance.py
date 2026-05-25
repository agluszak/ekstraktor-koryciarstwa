from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import entity_has_lexical_context_proposal
from pipeline_v2.event_frames import EventFrame, EventFrameBuilder, FrameArgumentRole
from pipeline_v2.ids import EntityCandidateId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span, Token
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    AppointerContextSignal,
    AppointmentLemmaSignal,
    DependencyRelation,
    DismissalLemmaSignal,
    EntityKind,
    EntityTag,
    EventRole,
    FactKind,
    GroundingKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    MentionKind,
    PartyOrganizationSignal,
    Signal,
    WeakSyntacticBindingSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


class GovernanceCandidateStage:
    producer_id = ProducerId("governance_candidate_stage_v2")
    _party_like_organization_names = frozenset(
        {
            "koalicja obywatelska",
            "koalicji obywatelskiej",
            "lewica",
            "platforma obywatelska",
            "platformy obywatelskiej",
            "polska 2050",
            "polskie stronnictwo ludowe",
            "polskiego stronnictwa ludowego",
            "prawo i sprawiedliwość",
            "prawa i sprawiedliwości",
            "pis",
            "po",
            "psl",
            "razem",
        }
    )

    _org_like_person_hint_tokens = frozenset(
        {
            "biuro",
            "fundusz",
            "ministerstwo",
            "ofe",
            "pap",
            "spółka",
            "urząd",
        }
    )
    # Person-descriptor common nouns that imply a person role-holder; small
    # stable set tied to the governance domain boundary.
    _person_descriptor_lemmas = frozenset(
        {
            "polityk",
            "działacz",
            "urzędnik",
            "menedżer",
            "manager",
            "kandydat",
            "członek",
        }
    )

    _appointment_lemmas = frozenset(
        {
            "powołać",
            "mianować",
            "zatrudnić",
            "objąć",
            "wybrać",
            "awansować",
            # Nouns and common verbal patterns
            "zostać",  # "zostać prezesem"
            "nominacja",
            "powołanie",
            "wejść",  # "wejść do zarządu"
            "zająć",  # "zajął stanowisko/funkcję prezesa"
        }
    )
    _generic_appointment_lemmas = frozenset({"zostać", "wejść", "nominacja", "zająć"})
    # Lemmas that only trigger appointment when used as temporal phrases (Bug 2).
    _objac_appointment_lemmas = frozenset({"objąć", "objęcie"})
    # Prepositions that mark a temporal use of "objąć/objęcie" ("od objęcia stanowiska").
    _temporal_prepositions = frozenset({"od", "po", "przed", "za", "do"})
    # Successor-pattern lemmas — "następcą zostanie X" (Bug 3).
    _successor_noun_lemmas = frozenset({"następca"})
    # Current-role descriptor adjectives for dash-apposition detection (Bug 4).
    _current_descriptor_lemmas = frozenset({"obecny", "aktualny"})
    # Dash characters used in appositive constructions (Bug 4).
    _dash_chars = frozenset({"—", "–", "-"})
    # Exception-clause lemma: "z wyjątkiem X" means X is NOT dismissed.
    _exception_clause_lemmas = frozenset({"wyjątek"})
    _dismissal_lemmas = frozenset(
        {
            "odwołać",
            "odwoływać",  # imperfective of odwołać
            "zwolnić",
            "zwalniać",  # imperfective of zwolnić
            "usunąć",
            "usuwać",  # imperfective of usunąć
            "zdymisjonować",
            "stracić",
            # Resignation/exit patterns
            "rezygnacja",
            "zrezygnować",
            "rezygnować",  # imperfective of zrezygnować
            "odejść",
            "odchodzić",  # imperfective of odejść
            # Nouns
            "odwołanie",
            "dymisja",
            # Negatable verb: only signals dismissal when negated (checked separately)
            "zasiadać",
        }
    )
    _governance_role_lemmas = frozenset(
        {
            "członek",
            "nadzorczy",
            "prezes",
            "rada",
            "zarząd",
            "dyrektor",
            "wicedyrektor",
            "wiceprezes",
            "kierownik",
            "szef",
        }
    )
    _political_role_lemmas = frozenset(
        {
            "poseł",
            "posłanka",
            "radny",
            "radna",
            "senator",
            "minister",
            "prezydent",
            "wojewoda",
            "wójt",
            "wojt",
            "burmistrz",
            "starosta",
            "sekretarz",
            "marszałek",
        }
    )
    _role_title_only_person_lemmas = frozenset(
        {
            "dyrektor",
            "kierownik",
            "naczelnik",
            "prezes",
            "sekretarz",
            "skarbnik",
            "szef",
            "wicedyrektor",
            "wiceprezes",
            "zastępca",
        }
    )
    # Subset of governance roles that unambiguously refer to a single person;
    # used when synthesising proxy person candidates (collective bodies excluded).
    _singular_person_role_lemmas = frozenset(
        {
            "prezes",
            "dyrektor",
            "wicedyrektor",
            "wiceprezes",
            "kierownik",
            "szef",
        }
    )

    def name(self) -> str:
        return "governance_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            self._add_political_office_candidates(document, sentence)
            kinds = self._candidate_kinds(document, sentence)
            if not kinds:
                continue
            combinations = self._candidate_combinations(document, sentence)
            if not combinations:
                continue
            evidence = EvidenceSpan(
                id=document.store.next_evidence_id(),
                text=sentence.text,
                span=sentence.span,
                sentence_id=sentence.id,
                paragraph_index=sentence.paragraph_index,
                source=self.producer_id,
            )
            document.store.add_evidence(evidence)

            for kind, signals in kinds:
                viable_combinations = [
                    (person_id, organization_id, role_id, entity_signals)
                    for person_id, organization_id, role_id, entity_signals in combinations
                    if not (
                        kind == FactKind.GOVERNANCE_APPOINTMENT
                        and organization_id is None
                        and role_id is None
                    )
                    and not (
                        kind == FactKind.GOVERNANCE_APPOINTMENT
                        and self._is_employment_overlap(signals)
                        and not self._has_governance_role(document, role_id)
                    )
                    and not (
                        kind == FactKind.GOVERNANCE_APPOINTMENT
                        and self._is_generic_appointment_lemma(signals)
                        and not self._has_governance_role(document, role_id)
                        # Successor pattern ("następcą zostanie X") makes 'zostać'
                        # non-generic even without an explicit governance role entity (Bug 3).
                        and not self._sentence_has_successor_pattern(document, sentence)
                    )
                ]
                # Successor pattern: "Jej następcą zostanie Agnieszka Paradyż" — the
                # appointee is the person appearing AFTER the 'zostać' trigger, not a
                # window entity from the previous dismissal sentence (Bug 3).
                if kind == FactKind.GOVERNANCE_APPOINTMENT and self._sentence_has_successor_pattern(
                    document, sentence
                ):
                    zostac_start = next(
                        (
                            document.store.tokens[tid].span.start_char
                            for tid in sentence.token_ids
                            if "zostać"
                            in {analysis.lemma for analysis in document.store.tokens[tid].morph}
                        ),
                        None,
                    )
                    if zostac_start is not None:
                        viable_combinations = [
                            (p, o, r, s)
                            for p, o, r, s in viable_combinations
                            if self._person_appears_after_trigger_in_sentence(
                                document=document,
                                sentence=sentence,
                                person_id=p,
                                trigger_start_char=zostac_start,
                            )
                        ]
                if not viable_combinations:
                    continue
                combos_by_person: dict[EntityCandidateId, list] = {}
                for person_id, organization_id, role_id, entity_signals in viable_combinations:
                    if (
                        kind == FactKind.GOVERNANCE_APPOINTMENT
                        and self._is_generic_appointment_lemma(signals)
                        and self._person_starts_after_dismissal_cue(
                            document=document,
                            sentence=sentence,
                            person_id=person_id,
                        )
                    ):
                        continue
                    if (
                        kind == FactKind.GOVERNANCE_DISMISSAL
                        and self._person_is_in_exception_clause(
                            document=document, sentence=sentence, person_id=person_id
                        )
                    ):
                        continue
                    combos_by_person.setdefault(person_id, []).append(
                        (organization_id, role_id, entity_signals)
                    )

                for person_id, combos in combos_by_person.items():
                    person_bindings: dict[EntityCandidateId, tuple[Signal, ...]] = {}
                    actor_bindings: dict[EntityCandidateId, tuple[Signal, ...]] = {}
                    organization_bindings: dict[EntityCandidateId, tuple[Signal, ...]] = {}
                    context_bindings: dict[EntityCandidateId, tuple[Signal, ...]] = {}
                    role_bindings: dict[EntityCandidateId, tuple[Signal, ...]] = {}

                    for organization_id, role_id, entity_signals in combos:
                        if self._signals_include_active_subject_context(entity_signals):
                            actor_bindings[person_id] = self._merge_binding_signals(
                                actor_bindings.get(person_id, ()),
                                self._actor_binding_signals(entity_signals),
                            )
                        else:
                            person_bindings[person_id] = self._merge_binding_signals(
                                person_bindings.get(person_id, ()),
                                self._person_binding_signals(entity_signals),
                            )
                        if organization_id is not None:
                            organization_signals = self._organization_binding_signals(
                                entity_signals
                            )
                            organization_bindings[organization_id] = self._merge_binding_signals(
                                organization_bindings.get(organization_id, ()),
                                organization_signals,
                            )
                            is_context_org = entity_has_lexical_context_proposal(
                                document, organization_id, EntityTag.GENERIC_OWNER
                            ) or entity_has_lexical_context_proposal(
                                document, organization_id, EntityTag.GOVERNING_BODY
                            )
                            if is_context_org:
                                context_bindings[organization_id] = self._merge_binding_signals(
                                    context_bindings.get(organization_id, ()),
                                    organization_signals,
                                )
                        if role_id is not None:
                            role_bindings[role_id] = self._merge_binding_signals(
                                role_bindings.get(role_id, ()),
                                self._role_binding_signals(entity_signals),
                            )

                    if not person_bindings:
                        continue

                    event = EventCandidate(
                        id=document.store.next_event_candidate_id(),
                        kind=kind,
                        trigger_evidence_id=evidence.id,
                        evidence_ids=(evidence.id,),
                        source=self.producer_id,
                        signals=signals,
                    )
                    document.store.add_event_candidate(event)
                    self._add_governance_bindings(
                        document=document,
                        event=event,
                        role=EventRole.PERSON,
                        bindings=person_bindings,
                        evidence_id=evidence.id,
                    )
                    self._add_governance_bindings(
                        document=document,
                        event=event,
                        role=EventRole.ACTOR,
                        bindings=actor_bindings,
                        evidence_id=evidence.id,
                    )
                    self._add_governance_bindings(
                        document=document,
                        event=event,
                        role=EventRole.ORGANIZATION,
                        bindings=organization_bindings,
                        evidence_id=evidence.id,
                    )
                    self._add_governance_bindings(
                        document=document,
                        event=event,
                        role=EventRole.ROLE,
                        bindings=role_bindings,
                        evidence_id=evidence.id,
                    )
                    self._add_governance_bindings(
                        document=document,
                        event=event,
                        role=EventRole.CONTEXT,
                        bindings=context_bindings,
                        evidence_id=evidence.id,
                    )
        return document

    def _add_governance_bindings(
        self,
        *,
        document: ArticleDocument,
        event: EventCandidate,
        role: EventRole,
        bindings: dict[EntityCandidateId, tuple[Signal, ...]],
        evidence_id,
    ) -> None:
        for entity_id, signals in bindings.items():
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=role,
                    filler=EntityFiller(entity_id),
                    evidence_ids=(evidence_id,),
                    signals=signals,
                )
            )

    def _person_binding_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        filtered: list[Signal] = []
        for signal in signals:
            match signal:
                case LocalPersonSignal() | WindowPersonSignal() | WeakSyntacticBindingSignal():
                    filtered.append(signal)
        return tuple(filtered)

    def _actor_binding_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        filtered: list[Signal] = []
        for signal in signals:
            match signal:
                case AppointerContextSignal() | WeakSyntacticBindingSignal():
                    filtered.append(signal)
        return tuple(filtered)

    def _organization_binding_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        filtered: list[Signal] = []
        for signal in signals:
            match signal:
                case (
                    LocalOrganizationSignal()
                    | WindowOrganizationSignal()
                    | PartyOrganizationSignal()
                ):
                    filtered.append(signal)
        return tuple(filtered)

    def _role_binding_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        filtered: list[Signal] = []
        for signal in signals:
            match signal:
                case LocalRoleSignal() | WindowRoleSignal():
                    filtered.append(signal)
        return tuple(filtered)

    def _signals_include_active_subject_context(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case WeakSyntacticBindingSignal(reason="person is active subject of cue"):
                    return True
                case AppointerContextSignal():
                    return True
        return False

    def _merge_binding_signals(
        self,
        existing: tuple[Signal, ...],
        new: tuple[Signal, ...],
    ) -> tuple[Signal, ...]:
        return tuple(dict.fromkeys([*existing, *new]))

    def _candidate_kinds(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[FactKind, tuple[Signal, ...]], ...]:
        lemmas = self._sentence_lemmas(document, sentence)
        candidates: list[tuple[FactKind, tuple[Signal, ...]]] = []
        if lemmas & self._appointment_lemmas:
            matched_appointment = lemmas & self._appointment_lemmas
            # Suppress appointment when only objąć/objęcie matched and all such tokens
            # are governed by temporal prepositions — e.g. "od objęcia stanowiska" is
            # a temporal clause, not a new appointment event (Bug 2).
            is_temporal_objac = (
                matched_appointment <= self._objac_appointment_lemmas
                and self._objac_tokens_are_temporal(document, sentence)
            )
            if not is_temporal_objac:
                candidates.append(
                    (
                        FactKind.GOVERNANCE_APPOINTMENT,
                        (
                            AppointmentLemmaSignal(
                                lemma=self._matched_detail(lemmas, self._appointment_lemmas),
                            ),
                        ),
                    )
                )
        # Dash-apposition pattern: "PERSON — (obecny|aktualny) ROLE [ORG]" implies an
        # implicit current appointment context (Bug 4).
        if (
            not (lemmas & self._appointment_lemmas)
            and lemmas & self._governance_role_lemmas
            and lemmas & self._current_descriptor_lemmas
            and self._sentence_has_dash_apposition_with_current_role(document, sentence)
        ):
            candidates.append(
                (
                    FactKind.GOVERNANCE_APPOINTMENT,
                    (AppointmentLemmaSignal(lemma="obecny"),),
                )
            )
        # Dismissal lemmas minus `zasiadać` (which is only a dismissal when negated)
        plain_dismissal_lemmas = self._dismissal_lemmas - {"zasiadać"}
        negatable_dismissal_lemmas = {"zasiadać"}
        dismissal_match = lemmas & plain_dismissal_lemmas
        # "odwołać się" (reflexive) means "to appeal", not "to be dismissed".
        # Remove reflexive odwołać/odwoływać from the match when "się" is a syntactic
        # child of the trigger token.
        _odwolac_lemmas = frozenset({"odwołać", "odwoływać"})
        if dismissal_match & _odwolac_lemmas:
            syntax = SyntaxView(document.store)
            trigger = syntax.first_token_with_lemmas(sentence, _odwolac_lemmas)
            if trigger is not None and self._has_reflexive_particle(
                document, sentence, trigger, syntax
            ):
                dismissal_match = dismissal_match - _odwolac_lemmas
        negated_zasiadac = (lemmas & negatable_dismissal_lemmas) and ("nie" in lemmas)
        if dismissal_match or negated_zasiadac:
            matched_lemma = (
                self._matched_detail(lemmas, plain_dismissal_lemmas)
                if dismissal_match
                else "zasiadać"
            )
            candidates.append(
                (
                    FactKind.GOVERNANCE_DISMISSAL,
                    (
                        DismissalLemmaSignal(
                            lemma=matched_lemma,
                        ),
                    ),
                )
            )
            # Passive dismissal constructions ("został odwołany") contain generic
            # appointment lemmas ("zostać") but are not new appointment events.
            # Keep valid mixed-clause sentences such as "X został prezesem po tym,
            # jak odwołano Y" by only suppressing tight generic+dismissal clusters.
            candidates = [
                (kind, sigs)
                for kind, sigs in candidates
                if not (
                    kind == FactKind.GOVERNANCE_APPOINTMENT
                    and (lemmas & self._appointment_lemmas) <= self._generic_appointment_lemmas
                    and self._has_tight_generic_dismissal_cluster(
                        document=document,
                        sentence=sentence,
                        dismissal_lemmas=plain_dismissal_lemmas,
                    )
                )
            ]
        return tuple(candidates)

    def _add_political_office_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> None:
        if not (self._sentence_lemmas(document, sentence) & self._political_role_lemmas):
            return
        frame_builder = EventFrameBuilder(document.store)
        entities = SentenceEntityRetriever(document.store).entities_for_sentence(sentence)
        people = tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)
        roles = tuple(entity for entity in entities if entity.kind == EntityKind.ROLE)
        if not people or not roles:
            return

        bindings: list[tuple[SentenceEntity, SentenceEntity]] = []
        for role in roles:
            if not self._is_political_role(document, role.id):
                continue
            role_frame = frame_builder.frame_for_trigger(
                sentence,
                self._first_token_for_entity(document, sentence, role),
            )
            person = self._office_person_for_role(document, role_frame, role, people)
            if person is not None:
                bindings.append((person, role))

        if not bindings:
            return

        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=sentence.text,
            span=sentence.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        event = EventCandidate(
            id=document.store.next_event_candidate_id(),
            kind=FactKind.POLITICAL_OFFICE,
            trigger_evidence_id=evidence.id,
            evidence_ids=(evidence.id,),
            source=self.producer_id,
            signals=(),
        )
        document.store.add_event_candidate(event)
        for person, role in bindings:
            self._add_governance_bindings(
                document=document,
                event=event,
                role=EventRole.PERSON,
                bindings={person.id: (LocalPersonSignal(),)},
                evidence_id=evidence.id,
            )
            self._add_governance_bindings(
                document=document,
                event=event,
                role=EventRole.ROLE,
                bindings={role.id: (LocalRoleSignal(),)},
                evidence_id=evidence.id,
            )

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
        """True when all tokens with objąć/objęcie lemma are governed by temporal prepositions.

        Checks all morph lemmas of the CASE child rather than the preferred lemma alone,
        because Morfeusz can return multiple lemma candidates (e.g. "od"/"oda") for the
        same surface form.
        """
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
        """True when 'następca' (successor noun) and 'zostać' both appear in the sentence."""
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
        """True when the person has at least one evidence span starting after trigger_start_char."""
        return any(
            evidence.span.start_char > trigger_start_char
            for evidence in document.store.evidence_for_entity(person_id)
            if evidence.sentence_id == sentence.id
        )

    def _sentence_has_dash_apposition_with_current_role(
        self, document: ArticleDocument, sentence: Sentence
    ) -> bool:
        """True when a dash token is followed by current-descriptor + governance-role lemmas."""
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
        """True when the person follows a 'z wyjątkiem' phrase in the same sentence.

        "Z wyjątkiem X" means X is excluded from whatever the main clause describes
        (e.g. dismissal), so X should not be treated as a dismissee.
        """
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

    def _candidate_combinations(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[
        tuple[
            EntityCandidateId,
            EntityCandidateId | None,
            EntityCandidateId | None,
            tuple[Signal, ...],
        ],
        ...,
    ]:
        retriever = SentenceEntityRetriever(document.store)
        entities = retriever.entities_for_sentence(sentence)
        window_entities = retriever.entities_for_sentence_window(sentence, before=1, after=0)

        people = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.PERSON,
            local_signal=LocalPersonSignal(),
            window_signal=WindowPersonSignal(),
        )
        roles = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.ROLE,
            local_signal=LocalRoleSignal(),
            window_signal=WindowRoleSignal(),
        )
        # When no named person is available, synthesise a proxy from a local
        # governance-role entity or a person-descriptor noun (e.g. "polityk").
        if not people:
            proxy = self._synthesize_proxy_person(document, sentence, roles)
            if proxy is not None:
                people = (proxy,)
        if not people:
            return ()

        # Expand conjunct person entities: "powołano m.in. A, B i C" — each
        # person in a CONJ chain shares the same event trigger and should be
        # considered as an independent APPOINTEE candidate.
        people = self._expand_conjunct_people(document, sentence, people, entities)

        organizations = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.ORGANIZATION,
            local_signal=LocalOrganizationSignal(),
            window_signal=WindowOrganizationSignal(),
            # Always include window organisations so that a previous-sentence
            # entity (e.g. WFOŚiGW from sentence N-1) competes with local ones
            # (e.g. PSL) and can win once party/owner signals are applied.
            merge_window_with_local=True,
        )
        roles = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.ROLE,
            local_signal=LocalRoleSignal(),
            window_signal=WindowRoleSignal(),
        )

        combinations = []
        # Identify which persons and roles are sentence-local vs window-only
        local_people_ids = frozenset(e.id for e in entities if e.kind == EntityKind.PERSON)
        local_role_ids = frozenset(e.id for e in entities if e.kind == EntityKind.ROLE)

        # For each window role/org, find which sentence they belong to and
        # whether that sentence has its own person entity.
        def _role_source_sentence_person_ids(
            entity: SentenceEntity,
        ) -> frozenset[EntityCandidateId]:
            """Return observed people from the entity's own source sentence."""
            role_sentence_id = document.store.sentence_id_for_offset(entity.start_char)
            if role_sentence_id is None:
                return frozenset()
            person_ids: set[EntityCandidateId] = set()
            for e in document.store.entity_candidates.values():
                if e.kind != EntityKind.PERSON or e.grounding != GroundingKind.OBSERVED:
                    continue
                for mention in document.store.candidate_mentions(e.id):
                    evidence = document.store.evidence.get(mention.evidence_id)
                    if evidence is not None and evidence.sentence_id == role_sentence_id:
                        person_ids.add(e.id)
            return frozenset(person_ids)

        syntax = SyntaxView(document.store)
        for person, p_signals in people:
            if self._is_implausible_person_candidate(document, person.id):
                continue
            person_is_window_only = person.id not in local_people_ids
            person_negative_signals: list[Signal] = []
            # Exclude appointer (nominative subject in active sentence with appointment lemma)
            trigger_token = syntax.first_token_with_lemmas(sentence, self._appointment_lemmas)
            if trigger_token is not None and not person_is_window_only:
                relation = syntax.dependency_relation(
                    sentence=sentence,
                    trigger_token_id=trigger_token.id,
                    entity_id=person.id,
                )
                if relation is not None and syntax.is_subject_relation(relation):
                    trigger_lemmas = {analysis.lemma for analysis in trigger_token.morph}
                    if not syntax.is_passive_sentence(sentence, trigger_token.id) and not (
                        trigger_lemmas & self._generic_appointment_lemmas
                    ):
                        person_negative_signals.append(
                            WeakSyntacticBindingSignal(reason="person is active subject of cue")
                        )
                trigger_lemmas = (
                    {analysis.lemma for analysis in trigger_token.morph}
                    if trigger_token is not None
                    else set()
                )
                generic_trigger_subject = bool(
                    trigger_lemmas & self._generic_appointment_lemmas
                ) and (
                    relation is not None
                    and syntax.is_subject_relation(relation)
                    or self._person_is_adjacent_before_trigger(
                        document=document,
                        sentence=sentence,
                        person_id=person.id,
                        trigger_start_char=trigger_token.span.start_char,
                    )
                )
                if not generic_trigger_subject and self._is_background_local_person(
                    document,
                    sentence,
                    person,
                    entities,
                    trigger_token.span.start_char,
                ):
                    continue

            role_candidates = self._role_candidates_for_person(
                document=document,
                sentence=sentence,
                person=person,
                roles=roles,
                local_people_ids=local_people_ids,
                local_role_ids=local_role_ids,
                role_source_sentence_person_ids=_role_source_sentence_person_ids,
                trigger_start_char=(
                    trigger_token.span.start_char if trigger_token is not None else None
                ),
            )
            if not role_candidates:
                role_candidates = ((None, ()),)

            for role, r_signals in role_candidates:
                organization_candidates = self._organization_candidates_for_person(
                    document=document,
                    sentence=sentence,
                    person=person,
                    role=role,
                    organizations=organizations,
                    trigger_start_char=(
                        trigger_token.span.start_char if trigger_token is not None else None
                    ),
                )
                if not organization_candidates:
                    organization_candidates = ((None, ()),)
                for org, o_signals in organization_candidates:
                    signals = [*p_signals, *person_negative_signals, *o_signals, *r_signals]
                    appointer_role = self._public_office_role_near_person(
                        document,
                        sentence,
                        person.id,
                    )
                    if (
                        not person_is_window_only
                        and org is not None
                        and org.id not in frozenset(e.id for e in entities)
                        and appointer_role is not None
                        and (
                            role is None
                            or role.id not in local_role_ids
                            or not self._has_governance_role(document, role.id)
                        )
                    ):
                        signals.append(
                            WeakSyntacticBindingSignal(reason="public office actor context")
                        )
                        signals.append(AppointerContextSignal(role_lemma=appointer_role))
                    if (
                        not person_is_window_only
                        and org is not None
                        and org.id not in frozenset(e.id for e in entities)
                        and role is not None
                        and role.id not in local_role_ids
                    ):
                        signals.append(
                            WeakSyntacticBindingSignal(
                                reason="local person with only window organization and role"
                            )
                        )
                        if appointer_role is not None:
                            signals.append(AppointerContextSignal(role_lemma=appointer_role))
                    if org is not None and self._is_party_like_organization(document, org.id):
                        signals.append(PartyOrganizationSignal())
                    combinations.append(
                        (
                            person.id,
                            org.id if org else None,
                            role.id if role else None,
                            tuple(signals),
                        )
                    )
        return tuple(combinations)

    def _role_candidates_for_person(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person: SentenceEntity,
        roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
        local_people_ids: frozenset[EntityCandidateId],
        local_role_ids: frozenset[EntityCandidateId],
        role_source_sentence_person_ids,
        trigger_start_char: int | None,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        compatible_roles: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        for role, role_signals in roles:
            person_is_window_only = person.id not in local_people_ids
            if person_is_window_only and local_people_ids and role.id in local_role_ids:
                continue
            if (
                role.id not in local_role_ids
                and (role_sentence_people := role_source_sentence_person_ids(role))
                and person.id not in role_sentence_people
            ):
                continue
            compatible_roles.append((role, role_signals))
        if not compatible_roles:
            return ()
        _ = trigger_start_char
        return tuple(compatible_roles)

    def _organization_candidates_for_person(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person: SentenceEntity,
        role: SentenceEntity | None,
        organizations: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
        trigger_start_char: int | None,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        # Tag-derived suppression now lives in the inference graph as constraint
        # factors coupling EntityContext variables to RoleFiller variables; the
        # producer no longer attaches per-tag context signals here.
        _ = (document, sentence, person, role, trigger_start_char)
        return organizations

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

    def _select_entities(
        self,
        document: ArticleDocument,
        anchor_sentence: Sentence,
        local_entities: tuple[SentenceEntity, ...],
        window_entities: tuple[SentenceEntity, ...],
        kind: EntityKind,
        *,
        local_signal: Signal,
        window_signal: Signal,
        merge_window_with_local: bool = False,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        local = tuple(entity for entity in local_entities if entity.kind == kind)
        seen_ids: set[EntityCandidateId] = {entity.id for entity in local}
        local_results: list[tuple[SentenceEntity, tuple[Signal, ...]]] = [
            (entity, (local_signal,)) for entity in local
        ]
        if local and not merge_window_with_local:
            return tuple(local_results)
        # Include window entities not already in local.
        window_results: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        for entity in window_entities:
            if entity.kind != kind or entity.id in seen_ids:
                continue
            entity_min_dist = 999
            for evidence in document.store.evidence_for_entity(entity.id):
                if evidence.sentence_id is None:
                    continue
                evidence_sentence = document.store.sentences[evidence.sentence_id]
                if evidence_sentence.paragraph_index != anchor_sentence.paragraph_index:
                    continue
                dist = anchor_sentence.sentence_index - evidence_sentence.sentence_index
                if 0 <= dist < entity_min_dist:
                    entity_min_dist = dist
            if entity_min_dist < 999:
                window_results.append((entity, (window_signal,)))
        if not local_results and not window_results:
            return ()
        return tuple(local_results + window_results)

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
        """Like _has_governance_role but only matches roles that refer to a single
        individual (prezes, dyrektor, etc.) — not collective bodies."""
        if role_id is None:
            return False
        for mention in document.store.candidate_mentions(role_id):
            for token in document.store.tokens_for_mention(mention.id):
                if any(
                    analysis.lemma in self._singular_person_role_lemmas for analysis in token.morph
                ):
                    return True
        return False

    def _synthesize_proxy_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        """When no named person is available, emit an inferred PERSON candidate
        derived from a local singular-person governance-role entity
        (e.g. 'prezes', 'dyrektor') or a person-descriptor common noun
        (e.g. 'polityk').  Collective bodies such as 'zarząd' and 'rada' are
        deliberately excluded to avoid generating spurious events."""
        local_entity_ids = {
            e.id
            for e in document.store.entity_candidates.values()
            if any(
                document.store.evidence.get(m.evidence_id) is not None
                and document.store.evidence[m.evidence_id].sentence_id == sentence.id
                for m in document.store.candidate_mentions(e.id)
            )
        }
        # First, try a singular-person governance-role entity local to the sentence.
        for role_entity, _role_sigs in roles:
            if role_entity.id not in local_entity_ids:
                continue
            if not self._has_singular_person_role(document, role_entity.id):
                continue
            return self._proxy_from_role_entity(document, sentence, role_entity)
        # Second, scan tokens for person-descriptor common nouns.
        return self._proxy_from_descriptor_token(document, sentence)

    def _proxy_from_role_entity(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        role_entity: SentenceEntity,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        """Build an inferred PERSON candidate anchored on a role entity mention."""
        role_candidate = document.store.entity_candidates.get(role_entity.id)
        if role_candidate is None or not role_candidate.mention_ids:
            return None
        role_mention = document.store.mentions.get(role_candidate.mention_ids[0])
        if role_mention is None:
            return None
        role_evidence = document.store.evidence.get(role_mention.evidence_id)
        if role_evidence is None:
            return None
        return self._create_proxy_person_candidate(
            document=document,
            sentence=sentence,
            text=role_mention.text,
            span=role_evidence.span,
            head_lemma=role_mention.head_lemma,
        )

    def _proxy_from_descriptor_token(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        """Build an inferred PERSON candidate from a person-descriptor noun token."""
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            token_lemmas = {analysis.lemma for analysis in token.morph}
            if not (token_lemmas & self._person_descriptor_lemmas):
                continue
            lemma = next(iter(token_lemmas & self._person_descriptor_lemmas))
            span = Span(token.span.start_char, token.span.end_char)
            return self._create_proxy_person_candidate(
                document=document,
                sentence=sentence,
                text=token.text,
                span=span,
                head_lemma=lemma,
            )
        return None

    def _create_proxy_person_candidate(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        *,
        text: str,
        span: Span,
        head_lemma: str | None,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        evidence_id = document.store.next_evidence_id()
        evidence = EvidenceSpan(
            id=evidence_id,
            text=text,
            span=span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        mention = Mention(
            id=mention_id,
            text=text,
            kind=MentionKind.DESCRIPTOR_NOUN_PHRASE,
            evidence_id=evidence_id,
            sentence_id=sentence.id,
            token_ids=tuple(
                token_id
                for token_id in sentence.token_ids
                if not (
                    document.store.tokens[token_id].span.end_char <= span.start_char
                    or document.store.tokens[token_id].span.start_char >= span.end_char
                )
            ),
            head_lemma=head_lemma,
        )
        document.store.add_mention(mention)
        candidate_id = document.store.next_entity_candidate_id()
        candidate = EntityCandidate(
            id=candidate_id,
            kind=EntityKind.PERSON,
            grounding=GroundingKind.INFERRED,
            canonical_hint=text,
            mention_ids=(mention_id,),
            source=self.producer_id,
        )
        document.store.add_entity_candidate(candidate)
        proxy_entity = SentenceEntity(
            id=candidate_id,
            kind=EntityKind.PERSON,
            start_char=span.start_char,
            end_char=span.end_char,
        )
        return (
            proxy_entity,
            (LocalPersonSignal(),),
        )

    def _is_background_local_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person: SentenceEntity,
        entities: tuple[SentenceEntity, ...],
        trigger_start_char: int,
    ) -> bool:
        if person.end_char >= trigger_start_char:
            return False
        for other in entities:
            if other.kind != EntityKind.PERSON or other.id == person.id:
                continue
            if other.start_char <= trigger_start_char:
                continue
            return True
        return False

    def _is_implausible_person_candidate(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates.get(entity_id)
        if candidate is None:
            return False
        canonical_hint = (candidate.canonical_hint or "").casefold()
        hint_tokens = frozenset(canonical_hint.replace(".", " ").split())
        if hint_tokens & self._org_like_person_hint_tokens:
            return True
        if (
            candidate.grounding is GroundingKind.OBSERVED
            and hint_tokens
            and self._person_candidate_is_role_title_only(document, entity_id)
        ):
            return True
        if any(
            token.isupper() and len(token) >= 2
            for token in (candidate.canonical_hint or "").split()[1:]
        ):
            return True
        if candidate.grounding is not GroundingKind.INFERRED:
            return False
        for mention in document.store.candidate_mentions(entity_id):
            if mention.kind is not MentionKind.DESCRIPTOR_NOUN_PHRASE:
                continue
            tokens = document.store.tokens_for_mention(mention.id)
            if not tokens:
                continue
            if all(any(analysis.number == "pl" for analysis in token.morph) for token in tokens):
                return True
        return False

    def _person_candidate_is_role_title_only(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        lemmas: set[str] = set()
        for mention in document.store.candidate_mentions(entity_id):
            for token in document.store.tokens_for_mention(mention.id):
                lemmas.update(analysis.lemma for analysis in token.morph)
        return bool(lemmas) and lemmas <= self._role_title_only_person_lemmas

    def _is_party_like_organization(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates[entity_id]
        canonical_hint = (candidate.canonical_hint or "").casefold()
        if canonical_hint in self._party_like_organization_names:
            return True
        if self._has_governance_role(document, entity_id):
            return True
        return self._overlaps_political_party(document, entity_id)

    def _overlaps_political_party(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        organization_evidence = tuple(document.store.evidence_for_entity(entity_id))
        for candidate in document.store.candidates_by_kind(EntityKind.POLITICAL_PARTY):
            for party_evidence in document.store.evidence_for_entity(candidate.id):
                for organization_span in organization_evidence:
                    if organization_span.sentence_id != party_evidence.sentence_id:
                        continue
                    if organization_span.span.end_char <= party_evidence.span.start_char:
                        continue
                    if party_evidence.span.end_char <= organization_span.span.start_char:
                        continue
                    return True
        return False

    def _is_political_role(self, document: ArticleDocument, role_id: EntityCandidateId) -> bool:
        role_candidate = document.store.entity_candidates[role_id]
        text = (role_candidate.canonical_hint or "").lower()
        lemmas = set()
        for mention_id in role_candidate.mention_ids:
            mention = document.store.mentions[mention_id]
            for token_id in mention.token_ids:
                token = document.store.tokens[token_id]
                for analysis in token.morph:
                    lemmas.add(analysis.lemma.lower())
        return bool(self._political_role_lemmas & lemmas) or any(
            lemma_word in text for lemma_word in self._political_role_lemmas
        )
