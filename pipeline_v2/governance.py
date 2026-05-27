from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.binding_emission import (
    EntityBindingGroup,
    emit_entity_binding_groups,
    merge_binding_signals,
)
from pipeline_v2.candidates import (
    EntityCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter, EmittedEvent
from pipeline_v2.entity_classification import entity_has_lexical_context_proposal
from pipeline_v2.event_frames import EventFrame, EventFrameBuilder, FrameArgumentRole
from pipeline_v2.ids import EntityCandidateId, ProducerId, SentenceId, TokenId
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
    ImplausiblePersonBindingSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    MentionKind,
    PartyOrganizationSignal,
    PublicRoleDomain,
    PublicRoleDomainSignal,
    Signal,
    WeakSyntacticBindingSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


@dataclass(frozen=True, slots=True)
class HoldingTrigger:
    lemma: str
    start_char: int


@dataclass(frozen=True, slots=True)
class _GovernanceCandidates:
    """Role candidates collected for one sentence, shared across all fact kinds."""

    people: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]
    organizations: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]
    roles: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]


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
    _holding_lemmas = frozenset({"być", "pozostawać", "zasiadać"})
    _former_descriptor_lemmas = frozenset({"były", "dawny", "wcześniej", "niegdyś", "ex-"})
    _generic_appointment_lemmas = frozenset({"zostać", "wejść", "nominacja", "zająć"})
    # Lemmas that only trigger appointment when used as temporal phrases (Bug 2).
    _objac_appointment_lemmas = frozenset({"objąć", "objęcie"})
    # Prepositions that mark a temporal use of "objąć/objęcie" ("od objęcia stanowiska").
    _temporal_prepositions = frozenset({"od", "po", "przed", "za", "do"})
    # Successor-pattern lemmas — "następcą zostanie X" (Bug 3).
    _successor_noun_lemmas = frozenset({"następca"})
    # Current-role descriptor adjectives for dash-apposition detection (Bug 4).
    _current_descriptor_lemmas = frozenset({"obecny", "aktualny", "dotychczasowy"})
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
            "pożegnać",
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
            "naczelnik",
            "nadzorczy",
            "prezes",
            "rada",
            "sekretarz",
            "zarząd",
            "dyrektor",
            "wicedyrektor",
            "wiceprezes",
            "kierownik",
            "szef",
            "wiceszef",
            "przewodniczący",
            "przewodnicząca",
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
            "marszałek",
        }
    )
    _verb_like_pos = frozenset(
        {"fin", "praet", "bedzie", "impt", "imps", "inf", "pcon", "pant", "ger", "pred"}
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
            self._add_public_role_holding_candidates(document, sentence)
            kinds = self._candidate_kinds(document, sentence)
            if not kinds:
                continue
            candidates = self._collect_governance_candidates(document, sentence)
            if not candidates.people:
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

            for kind, kind_signals in kinds:
                # Event-level admissibility: employment-overlap or generic-appointment
                # lemmas without a governance role entity present should not produce an event.
                has_any_governance_role = any(
                    self._has_governance_role(document, role_id) for role_id, _ in candidates.roles
                )
                if (
                    kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                    and self._is_employment_overlap(kind_signals)
                    and not has_any_governance_role
                ):
                    continue
                if (
                    kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                    and self._is_generic_appointment_lemma(kind_signals)
                    and not has_any_governance_role
                    and not self._sentence_has_successor_pattern(document, sentence)
                ):
                    continue

                admitted_people = self._annotate_people_for_kind(
                    document, sentence, kind, kind_signals, candidates.people
                )
                if not admitted_people:
                    continue

                if kind == FactKind.PUBLIC_ROLE_HOLDING:
                    admitted_people = tuple(
                        (
                            pid,
                            merge_binding_signals(
                                sigs,
                                (
                                    WeakSyntacticBindingSignal(
                                        reason="person candidate duplicates role descriptor"
                                    ),
                                )
                                if any(
                                    self._is_descriptor_role_self_pair(document, pid, role_id)
                                    for role_id, _ in candidates.roles
                                )
                                else (),
                            ),
                        )
                        for pid, sigs in admitted_people
                    )

                if (
                    kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                    and not candidates.organizations
                    and not candidates.roles
                ):
                    continue

                actor_bindings: dict[EntityCandidateId, tuple[Signal, ...]] = {}
                for entity_id, p_sigs in admitted_people:
                    if self._signals_include_active_subject_context(p_sigs):
                        actor_bindings[entity_id] = merge_binding_signals(
                            actor_bindings.get(entity_id, ()),
                            self._actor_binding_signals(p_sigs),
                        )

                for person_id, person_sigs in admitted_people:
                    if self._signals_include_active_subject_context(person_sigs):
                        continue

                    person_bindings = ((person_id, self._person_binding_signals(person_sigs)),)
                    if not person_bindings[0][1]:
                        continue

                    org_bindings = tuple(
                        (
                            org_id,
                            self._organization_binding_signals(org_signals),
                        )
                        for org_id, org_signals in self._annotate_orgs_for_person(
                            document,
                            sentence,
                            person_id,
                            candidates.organizations,
                        )
                    )
                    context_bindings = tuple(
                        (org_id, org_signals)
                        for org_id, org_signals in org_bindings
                        if entity_has_lexical_context_proposal(
                            document,
                            org_id,
                            EntityTag.GENERIC_OWNER,
                        )
                        or entity_has_lexical_context_proposal(
                            document,
                            org_id,
                            EntityTag.GOVERNING_BODY,
                        )
                    )

                    person_compatible_roles = self._annotate_roles_for_person(
                        document,
                        sentence,
                        person_id,
                        candidates.roles,
                    )
                    if kind == FactKind.PUBLIC_ROLE_END:
                        person_compatible_roles = self._annotate_roles_for_exit_kind(
                            document,
                            sentence,
                            [person_id],
                            person_compatible_roles,
                        )
                    if kind == FactKind.PUBLIC_ROLE_HOLDING:
                        person_compatible_roles = tuple(
                            (
                                role_id,
                                merge_binding_signals(
                                    role_signals,
                                    (
                                        WeakSyntacticBindingSignal(
                                            reason="role descriptor overlaps holder mention"
                                        ),
                                    )
                                    if self._is_descriptor_role_self_pair(
                                        document,
                                        person_id,
                                        role_id,
                                    )
                                    else (),
                                ),
                            )
                            for role_id, role_signals in person_compatible_roles
                        )
                    role_bindings = tuple(
                        (
                            role_id,
                            self._role_binding_signals(role_signals),
                        )
                        for role_id, role_signals in person_compatible_roles
                    )

                    emitter = DomainEventEmitter(document, self.producer_id)
                    event = emitter.event(
                        kind=kind,
                        trigger_evidence_id=evidence.id,
                        evidence_ids=(evidence.id,),
                        signals=kind_signals,
                    )
                    emit_entity_binding_groups(
                        emitter=emitter,
                        event=event,
                        evidence_id=evidence.id,
                        groups=(
                            EntityBindingGroup(EventRole.PERSON, person_bindings),
                            EntityBindingGroup(
                                EventRole.ACTOR,
                                tuple(actor_bindings.items()),
                            ),
                            EntityBindingGroup(EventRole.ORGANIZATION, org_bindings),
                            EntityBindingGroup(EventRole.CONTEXT, context_bindings),
                            EntityBindingGroup(EventRole.ROLE, role_bindings),
                        ),
                    )
                    self._add_role_domain_bindings(
                        document=document,
                        emitter=emitter,
                        event=event,
                        role_bindings=dict(role_bindings),
                        evidence_id=evidence.id,
                    )
        return document

    def _collect_governance_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> _GovernanceCandidates:
        retriever = SentenceEntityRetriever(document.store)
        entities = retriever.entities_for_sentence(sentence)
        window_entities = retriever.entities_for_sentence_window(sentence, before=1, after=0)
        organization_window_entities = window_entities
        if self._first_holding_trigger(document, sentence) is not None:
            organization_window_entities = retriever.entities_for_sentence_window(
                sentence,
                before=2,
                after=0,
            )

        raw_people = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.PERSON,
            local_signal=LocalPersonSignal(),
            window_signal=WindowPersonSignal(),
        )
        if not any(entity.kind is EntityKind.PERSON for entity in entities):
            if self._first_holding_trigger(document, sentence) is not None:
                seen_ids = {person.id for person, _ in raw_people}
                previous_people = self._previous_sentence_holding_people(document, sentence)
                raw_people = raw_people + tuple(
                    (person, (WindowPersonSignal(),))
                    for person in previous_people
                    if person.id not in seen_ids
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
        if self._sentence_lemmas(document, sentence) & self._dismissal_lemmas or (
            self._first_holding_trigger(document, sentence) is not None
        ):
            roles = self._augment_local_roles_with_person_titles(
                document=document,
                sentence=sentence,
                local_entities=entities,
                roles=roles,
            )

        if not raw_people:
            proxy = None
            if not self._sentence_is_first_person_departure_report(document, sentence):
                proxy = self._synthesize_proxy_person(document, sentence, roles)
            if proxy is not None:
                raw_people = (proxy,)
        if not raw_people:
            return _GovernanceCandidates(people=(), organizations=(), roles=())

        raw_people = self._expand_conjunct_people(document, sentence, raw_people, entities)

        # Apply zasiadać / holding-clause sentence-level role restriction.
        roles = self._restrict_roles_to_clause(document, sentence, roles)

        local_people_ids = frozenset(e.id for e in entities if e.kind == EntityKind.PERSON)
        syntax = SyntaxView(document.store)

        holding_trigger = self._first_holding_trigger(document, sentence)
        holding_clause_end_char = (
            self._clause_end_after_char(document, sentence, holding_trigger.start_char)
            if holding_trigger is not None and holding_trigger.lemma in {"być", "pozostawać"}
            else None
        )
        has_clause_local_post_trigger_person = (
            holding_trigger is not None
            and holding_clause_end_char is not None
            and any(
                self._entity_source_sentence_id(document, person.id) == sentence.id
                and holding_trigger.start_char < person.start_char < holding_clause_end_char
                for person, _ in raw_people
            )
        )
        trigger_token = syntax.first_token_with_lemmas(sentence, self._appointment_lemmas)

        # Build per-person signal lists.
        people_out: list[tuple[EntityCandidateId, tuple[Signal, ...]]] = []
        for person, p_signals in raw_people:
            extra: list[Signal] = []
            if self._is_implausible_person_candidate(document, person.id):
                extra.append(ImplausiblePersonBindingSignal())

            person_is_window_only = person.id not in local_people_ids

            if (
                has_clause_local_post_trigger_person
                and holding_trigger is not None
                and holding_clause_end_char is not None
                and (
                    self._entity_source_sentence_id(document, person.id) != sentence.id
                    or not (
                        holding_trigger.start_char < person.start_char < holding_clause_end_char
                    )
                )
            ):
                extra.append(
                    WeakSyntacticBindingSignal(
                        reason="window person competes with clause-local holder"
                    )
                )

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
                        extra.append(
                            WeakSyntacticBindingSignal(reason="person is active subject of cue")
                        )
                        appointer_role = self._public_office_role_near_person(
                            document,
                            sentence,
                            person.id,
                        )
                        if appointer_role is not None:
                            extra.append(AppointerContextSignal(role_lemma=appointer_role))

                trigger_lemmas = {analysis.lemma for analysis in trigger_token.morph}
                re_relation = syntax.dependency_relation(
                    sentence=sentence,
                    trigger_token_id=trigger_token.id,
                    entity_id=person.id,
                )
                generic_trigger_subject = bool(
                    trigger_lemmas & self._generic_appointment_lemmas
                ) and (
                    re_relation is not None
                    and syntax.is_subject_relation(re_relation)
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
                    extra.append(
                        WeakSyntacticBindingSignal(
                            reason="person appears in background context before cue"
                        )
                    )

            people_out.append((person.id, tuple(p_signals) + tuple(extra)))

        # Organizations with signals.
        organizations_raw = self._select_entities(
            document,
            sentence,
            entities,
            organization_window_entities,
            EntityKind.ORGANIZATION,
            local_signal=LocalOrganizationSignal(),
            window_signal=WindowOrganizationSignal(),
            merge_window_with_local=True,
        )
        if self._sentence_has_holding_predicate_title(document, sentence) and not any(
            entity.kind is EntityKind.ORGANIZATION for entity in entities
        ):
            organizations_raw = tuple(
                (
                    org,
                    (LocalOrganizationSignal(), WindowOrganizationSignal())
                    if org_signals == (WindowOrganizationSignal(),)
                    else org_signals,
                )
                for org, org_signals in organizations_raw
            )
        orgs_out: list[tuple[EntityCandidateId, tuple[Signal, ...]]] = []
        for org, org_signals in organizations_raw:
            sigs: list[Signal] = list(org_signals)
            if self._is_party_like_organization(document, org.id):
                sigs.append(PartyOrganizationSignal())
            orgs_out.append((org.id, tuple(sigs)))

        roles_out = tuple((role.id, role_signals) for role, role_signals in roles)

        return _GovernanceCandidates(
            people=tuple(people_out),
            organizations=tuple(orgs_out),
            roles=roles_out,
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

    def _annotate_people_for_kind(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kind: FactKind,
        kind_signals: tuple[Signal, ...],
        people: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]:
        if kind == FactKind.PUBLIC_ROLE_APPOINTMENT and self._sentence_has_successor_pattern(
            document, sentence
        ):
            zostac_start = next(
                (
                    document.store.tokens[tid].span.start_char
                    for tid in sentence.token_ids
                    if "zostać" in {analysis.lemma for analysis in document.store.tokens[tid].morph}
                ),
                None,
            )
        else:
            zostac_start = None

        admitted: list[tuple[EntityCandidateId, tuple[Signal, ...]]] = []
        for person_id, sigs in people:
            extra: list[Signal] = []
            if (
                kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                and zostac_start is not None
                and not self._person_appears_after_trigger_in_sentence(
                    document=document,
                    sentence=sentence,
                    person_id=person_id,
                    trigger_start_char=zostac_start,
                )
            ):
                extra.append(
                    WeakSyntacticBindingSignal(
                        reason="person appears before successor appointment trigger"
                    )
                )
            if (
                kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                and self._is_generic_appointment_lemma(kind_signals)
                and self._person_starts_after_dismissal_cue(
                    document=document,
                    sentence=sentence,
                    person_id=person_id,
                )
            ):
                extra.append(
                    WeakSyntacticBindingSignal(
                        reason="person follows dismissal cue in generic appointment sentence"
                    )
                )
            if kind == FactKind.PUBLIC_ROLE_END and self._person_is_in_exception_clause(
                document=document,
                sentence=sentence,
                person_id=person_id,
            ):
                extra.append(
                    WeakSyntacticBindingSignal(reason="person appears in exception clause")
                )
            admitted.append((person_id, self._merge_binding_signals(sigs, tuple(extra))))
        return tuple(admitted)

    def _annotate_roles_for_exit_kind(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        admitted_person_ids: list[EntityCandidateId],
        roles: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]:
        if not roles:
            return roles

        if len(admitted_person_ids) > 1:
            roles = tuple(
                (
                    role_id,
                    self._merge_binding_signals(
                        sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="role descriptor overlaps one dismissal candidate"
                            ),
                        )
                        if any(
                            self._is_descriptor_role_self_pair(document, person_id, role_id)
                            for person_id in admitted_person_ids
                        )
                        else (),
                    ),
                )
                for role_id, sigs in roles
            )

        # Prefer roles locally attached to any admitted person.
        attached_role_ids = frozenset(
            role_id
            for role_id, _ in roles
            if any(
                self._role_is_locally_attached_to_person(
                    document=document,
                    sentence=sentence,
                    person_id=person_id,
                    role_id=role_id,
                )
                for person_id in admitted_person_ids
            )
        )
        if attached_role_ids:
            roles = tuple(
                (
                    role_id,
                    sigs
                    if role_id in attached_role_ids
                    else self._merge_binding_signals(
                        sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="role is not locally attached to dismissed person"
                            ),
                        ),
                    ),
                )
                for role_id, sigs in roles
            )

        # Prefer non-alternative departure targets.
        non_alternative_role_ids = frozenset(
            role_id
            for role_id, _ in roles
            if not self._role_is_alternative_departure_target(
                document=document,
                sentence=sentence,
                role_id=role_id,
            )
        )
        if non_alternative_role_ids:
            roles = tuple(
                (
                    role_id,
                    sigs
                    if role_id in non_alternative_role_ids
                    else self._merge_binding_signals(
                        sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="role appears as alternative departure target"
                            ),
                        ),
                    ),
                )
                for role_id, sigs in roles
            )

        return roles

    def _annotate_roles_for_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        roles: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]:
        """Remove window roles whose source sentence has different observed people."""
        local_role_ids = frozenset(
            eid
            for eid, _ in roles
            if any(
                evidence.sentence_id == sentence.id
                for evidence in document.store.evidence_for_entity(eid)
            )
        )
        result: list[tuple[EntityCandidateId, tuple[Signal, ...]]] = []
        for role_id, role_signals in roles:
            if role_id in local_role_ids:
                result.append((role_id, role_signals))
                continue
            role_sentence_id = self._entity_source_sentence_id(document, role_id)
            if role_sentence_id is None:
                result.append((role_id, role_signals))
                continue
            source_people = self._observed_people_in_sentence(document, role_sentence_id)
            if source_people and person_id not in source_people:
                if not self._role_sentence_has_departure_context_by_id(document, role_id):
                    role_signals = self._merge_binding_signals(
                        role_signals,
                        (
                            WeakSyntacticBindingSignal(
                                reason="window role source sentence belongs to another person"
                            ),
                        ),
                    )
            result.append((role_id, role_signals))
        return tuple(result)

    def _annotate_orgs_for_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        organizations: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]:
        """Apply org restriction based on person compatibility and holding clauses."""
        holding_trigger = self._first_holding_trigger(document, sentence)

        if holding_trigger is None:
            return tuple(
                (
                    org_id,
                    org_sigs
                    if self._org_source_compatible_with_person(
                        document, sentence, person_id, org_id
                    )
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason=(
                                    "window organization source sentence belongs to another person"
                                )
                            ),
                        ),
                    ),
                )
                for org_id, org_sigs in organizations
            )
        if holding_trigger.lemma not in {"być", "pozostawać"}:
            return organizations
        role_id = self._role_id_for_person_in_sentence(document, sentence, person_id)
        if role_id is None:
            return organizations
        role_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(role_id)
            if evidence.sentence_id == sentence.id
        ]
        if not role_spans:
            return organizations
        role_start_char = min(span.start_char for span in role_spans)
        if role_start_char >= holding_trigger.start_char:
            return organizations
        # Predicate role is before the trigger — check if orgs are in the predicate clause.
        holding_clause_end = self._clause_end_after_char(
            document, sentence, holding_trigger.start_char
        )
        clause_start = self._clause_start_before_char(
            document, sentence, holding_trigger.start_char
        )
        predicate_orgs = tuple(
            (org_id, org_sigs)
            for org_id, org_sigs in organizations
            if self._entity_source_sentence_id(document, org_id) == sentence.id
            and clause_start
            <= self._entity_start_char(document, sentence, org_id)
            < holding_trigger.start_char
        )
        if predicate_orgs:
            predicate_ids = {org_id for org_id, _ in predicate_orgs}
            return tuple(
                (
                    org_id,
                    org_sigs
                    if org_id in predicate_ids
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="organization is outside holding predicate clause"
                            ),
                        ),
                    ),
                )
                for org_id, org_sigs in organizations
            )
        window_orgs = tuple(
            (org_id, org_sigs)
            for org_id, org_sigs in organizations
            if self._entity_source_sentence_id(document, org_id) != sentence.id
        )
        trailing_local_orgs = tuple(
            (org_id, org_sigs)
            for org_id, org_sigs in organizations
            if self._entity_source_sentence_id(document, org_id) == sentence.id
            and self._entity_start_char(document, sentence, org_id) >= holding_clause_end
        )
        if window_orgs and trailing_local_orgs:
            window_ids = {org_id for org_id, _ in window_orgs}
            return tuple(
                (
                    org_id,
                    org_sigs
                    if org_id in window_ids
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="trailing local organization is outside holder clause"
                            ),
                        ),
                    ),
                )
                for org_id, org_sigs in organizations
            )
        if trailing_local_orgs and self._sentence_has_possessive_holder_pronoun_before_char(
            document, sentence, role_start_char
        ):
            window_ids = {org_id for org_id, _ in window_orgs}
            return tuple(
                (
                    org_id,
                    org_sigs
                    if org_id in window_ids
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="trailing local organization follows possessive holder role"
                            ),
                        ),
                    ),
                )
                for org_id, org_sigs in organizations
            )
        return organizations

    def _org_source_compatible_with_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        org_id: EntityCandidateId,
    ) -> bool:
        """True if the org is local or its source sentence does not belong to a different person."""
        source_sid = self._entity_source_sentence_id(document, org_id)
        if source_sid is None or source_sid == sentence.id:
            return True
        source_people = self._observed_people_in_sentence(document, source_sid)
        return not source_people or person_id in source_people

    def _add_governance_bindings(
        self,
        *,
        document: ArticleDocument,
        emitter: DomainEventEmitter,
        event: EmittedEvent,
        role: EventRole,
        bindings: dict[EntityCandidateId, tuple[Signal, ...]],
        evidence_id,
    ) -> None:
        for entity_id, signals in bindings.items():
            emitter.bind_entity(
                event=event,
                role=role,
                entity_id=entity_id,
                evidence_ids=(evidence_id,),
                signals=signals,
            )

    def _add_role_domain_bindings(
        self,
        *,
        document: ArticleDocument,
        emitter: DomainEventEmitter,
        event: EmittedEvent,
        role_bindings: dict[EntityCandidateId, tuple[Signal, ...]],
        evidence_id,
    ) -> None:
        domains = {
            self._public_role_domain_for_role(document, role_id) for role_id in role_bindings
        }
        domains.discard(None)
        for domain in sorted(domains, key=lambda value: value.value):
            emitter.bind_text(
                event=event,
                role=EventRole.ROLE_DOMAIN,
                value=domain.value,
                evidence_ids=(evidence_id,),
                signals=(PublicRoleDomainSignal(domain=domain),),
            )

    def _person_binding_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        filtered: list[Signal] = []
        for signal in signals:
            match signal:
                case (
                    LocalPersonSignal()
                    | WindowPersonSignal()
                    | WeakSyntacticBindingSignal()
                    | ImplausiblePersonBindingSignal()
                ):
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
                    | WeakSyntacticBindingSignal()
                ):
                    filtered.append(signal)
        return tuple(filtered)

    def _role_binding_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        filtered: list[Signal] = []
        for signal in signals:
            match signal:
                case LocalRoleSignal() | WindowRoleSignal() | WeakSyntacticBindingSignal():
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
        return merge_binding_signals(existing, new)

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
                        FactKind.PUBLIC_ROLE_APPOINTMENT,
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
                    FactKind.PUBLIC_ROLE_HOLDING,
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
                    FactKind.PUBLIC_ROLE_END,
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
                    kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                    and (lemmas & self._appointment_lemmas) <= self._generic_appointment_lemmas
                    and self._has_tight_generic_dismissal_cluster(
                        document=document,
                        sentence=sentence,
                        dismissal_lemmas=plain_dismissal_lemmas,
                    )
                )
            ]
        # Holding patterns: copular clauses ("X jest prezesem"), persistence
        # clauses ("wiceprezesem pozostaje X"), and board-membership clauses
        # ("X zasiada w radzie nadzorczej").
        holding_trigger = self._first_holding_trigger(document, sentence)
        if (
            not (lemmas & self._appointment_lemmas)
            and holding_trigger is not None
            and (
                self._sentence_has_governance_role_entity(document, sentence)
                or self._sentence_has_inline_person_title(document, sentence)
                or self._sentence_has_holding_predicate_title(document, sentence)
            )
        ):
            candidates.append(
                (
                    FactKind.PUBLIC_ROLE_HOLDING,
                    (AppointmentLemmaSignal(lemma=holding_trigger.lemma),),
                )
            )
        return tuple(candidates)

    def _add_public_role_holding_candidates(
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
            if self._role_has_former_descriptor(document, sentence, role):
                continue
            if self._role_is_embedded_under_other_role(document, sentence, role):
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
        emitter = DomainEventEmitter(document, self.producer_id)
        for person, role in bindings:
            event = emitter.event(
                kind=FactKind.PUBLIC_ROLE_HOLDING,
                trigger_evidence_id=evidence.id,
                evidence_ids=(evidence.id,),
                signals=(),
            )
            self._add_governance_bindings(
                document=document,
                emitter=emitter,
                event=event,
                role=EventRole.PERSON,
                bindings={person.id: (LocalPersonSignal(),)},
                evidence_id=evidence.id,
            )
            self._add_governance_bindings(
                document=document,
                emitter=emitter,
                event=event,
                role=EventRole.ROLE,
                bindings={role.id: (LocalRoleSignal(),)},
                evidence_id=evidence.id,
            )
            self._add_role_domain_bindings(
                document=document,
                emitter=emitter,
                event=event,
                role_bindings={role.id: (LocalRoleSignal(),)},
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
        if kind is EntityKind.ORGANIZATION:
            local = tuple(
                entity
                for entity in local
                if not self._is_implausible_organization_candidate(document, entity.id)
            )
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
            if kind is EntityKind.ORGANIZATION and self._is_implausible_organization_candidate(
                document, entity.id
            ):
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

    def _role_sentence_has_departure_context(
        self,
        document: ArticleDocument,
        role: SentenceEntity,
    ) -> bool:
        """True when the role's source sentence contains departure/dismissal language.

        Used in successor-pattern detection: if the role came from a sentence where
        someone was leaving ("pożegnała się ze stanowiskiem", "odszedł z urzędu"),
        the position is considered vacant and can be claimed by a new person.
        """
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
        """Return the first role entity locally attached just before this person."""
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
        """True when the sentence has a ROLE entity with governance or political role lemmas."""
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

    def _is_implausible_organization_candidate(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates.get(entity_id)
        if candidate is None:
            return False
        hint = (candidate.canonical_hint or "").strip()
        if not hint:
            return False
        hint_tokens = hint.split()
        if (
            len(hint_tokens) == 1
            and hint_tokens[0].islower()
            and not entity_has_lexical_context_proposal(
                document,
                entity_id,
                EntityTag.PUBLIC_INSTITUTION,
            )
            and not entity_has_lexical_context_proposal(
                document,
                entity_id,
                EntityTag.MEDIA_OUTLET,
            )
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
        return (
            self._public_role_domain_for_role(document, role_id)
            is PublicRoleDomain.POLITICAL_OFFICE
        )

    def _public_role_domain_for_role(
        self,
        document: ArticleDocument,
        role_id: EntityCandidateId,
    ) -> PublicRoleDomain:
        role_candidate = document.store.entity_candidates[role_id]
        text = (role_candidate.canonical_hint or "").lower()
        lemmas = set()
        for mention_id in role_candidate.mention_ids:
            mention = document.store.mentions[mention_id]
            for token_id in mention.token_ids:
                token = document.store.tokens[token_id]
                for analysis in token.morph:
                    lemmas.add(analysis.lemma.lower())
        if "sekretarz stanu" in text:
            return PublicRoleDomain.POLITICAL_OFFICE
        if bool(self._political_role_lemmas & lemmas) or any(
            lemma_word in text for lemma_word in self._political_role_lemmas
        ):
            return PublicRoleDomain.POLITICAL_OFFICE
        if "rada nadzorcza" in text or {"rada", "nadzorczy"} <= lemmas:
            return PublicRoleDomain.SUPERVISORY_BOARD
        if {"prezes", "wiceprezes", "zarząd"} & lemmas:
            return PublicRoleDomain.PUBLIC_COMPANY_MANAGEMENT
        if {"dyrektor", "wicedyrektor", "kierownik", "szef", "wiceszef"} & lemmas:
            return PublicRoleDomain.INSTITUTION_MANAGEMENT
        if {"sekretarz", "naczelnik", "skarbnik"} & lemmas:
            return PublicRoleDomain.ADMINISTRATIVE_OFFICE
        return PublicRoleDomain.OTHER_PUBLIC_ROLE
