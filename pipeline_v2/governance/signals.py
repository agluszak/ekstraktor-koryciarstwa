from __future__ import annotations

from pipeline_v2.binding_emission import merge_binding_signals
from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter, EmittedEvent
from pipeline_v2.governance.heuristics import GovernanceHeuristics
from pipeline_v2.ids import EntityCandidateId, EvidenceId
from pipeline_v2.nlp import Sentence
from pipeline_v2.retrieval import SentenceEntity
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    AppointerContextSignal,
    AppointmentLemmaSignal,
    DismissalLemmaSignal,
    EventRole,
    FactKind,
    ImplausiblePersonBindingSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    PartyOrganizationSignal,
    PublicRoleDomainSignal,
    Signal,
    WeakSyntacticBindingSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


class GovernanceSignalAnnotator(GovernanceHeuristics):
    def _annotate_people_for_kind(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kind: FactKind,
        kind_signals: tuple[Signal, ...],
        people: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
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
        for person, sigs in people:
            extra: list[Signal] = []
            if (
                kind == FactKind.PUBLIC_ROLE_APPOINTMENT
                and zostac_start is not None
                and not self._person_appears_after_trigger_in_sentence(
                    document=document,
                    sentence=sentence,
                    person_id=person.id,
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
                    person_id=person.id,
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
                person_id=person.id,
            ):
                extra.append(
                    WeakSyntacticBindingSignal(reason="person appears in exception clause")
                )
            admitted.append((person.id, self._merge_binding_signals(sigs, tuple(extra))))
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
        roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]:
        local_role_ids = frozenset(
            role.id
            for role, _ in roles
            if any(
                evidence.sentence_id == sentence.id
                for evidence in document.store.evidence_for_entity(role.id)
            )
        )
        result: list[tuple[EntityCandidateId, tuple[Signal, ...]]] = []
        for role, role_signals in roles:
            if role.id in local_role_ids:
                result.append((role.id, role_signals))
                continue
            role_sentence_id = self._entity_source_sentence_id(document, role.id)
            if role_sentence_id is None:
                result.append((role.id, role_signals))
                continue
            source_people = self._observed_people_in_sentence(document, role_sentence_id)
            if source_people and person_id not in source_people:
                if not self._role_sentence_has_departure_context_by_id(document, role.id):
                    role_signals = self._merge_binding_signals(
                        role_signals,
                        (
                            WeakSyntacticBindingSignal(
                                reason="window role source sentence belongs to another person"
                            ),
                        ),
                    )
            result.append((role.id, role_signals))
        return tuple(result)

    def _annotate_orgs_for_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        organizations: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    ) -> tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]:
        holding_trigger = self._first_holding_trigger(document, sentence)

        if holding_trigger is None:
            return tuple(
                (
                    org.id,
                    org_sigs
                    if self._org_source_compatible_with_person(
                        document, sentence, person_id, org.id
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
                for org, org_sigs in organizations
            )
        if holding_trigger.lemma not in {"być", "pozostawać"}:
            return tuple((org.id, sigs) for org, sigs in organizations)
        role_id = self._role_id_for_person_in_sentence(document, sentence, person_id)
        if role_id is None:
            return tuple((org.id, sigs) for org, sigs in organizations)
        role_spans = [
            evidence.span
            for evidence in document.store.evidence_for_entity(role_id)
            if evidence.sentence_id == sentence.id
        ]
        if not role_spans:
            return tuple((org.id, sigs) for org, sigs in organizations)
        role_start_char = min(span.start_char for span in role_spans)
        if role_start_char >= holding_trigger.start_char:
            return tuple((org.id, sigs) for org, sigs in organizations)

        holding_clause_end = self._clause_end_after_char(
            document, sentence, holding_trigger.start_char
        )
        clause_start = self._clause_start_before_char(
            document, sentence, holding_trigger.start_char
        )
        predicate_orgs = tuple(
            (org.id, org_sigs)
            for org, org_sigs in organizations
            if self._entity_source_sentence_id(document, org.id) == sentence.id
            and clause_start
            <= self._entity_start_char(document, sentence, org.id)
            < holding_trigger.start_char
        )
        if predicate_orgs:
            predicate_ids = {org_id for org_id, _ in predicate_orgs}
            return tuple(
                (
                    org.id,
                    org_sigs
                    if org.id in predicate_ids
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="organization is outside holding predicate clause"
                            ),
                        ),
                    ),
                )
                for org, org_sigs in organizations
            )
        window_orgs = tuple(
            (org.id, org_sigs)
            for org, org_sigs in organizations
            if self._entity_source_sentence_id(document, org.id) != sentence.id
        )
        trailing_local_orgs = tuple(
            (org.id, org_sigs)
            for org, org_sigs in organizations
            if self._entity_source_sentence_id(document, org.id) == sentence.id
            and self._entity_start_char(document, sentence, org.id) >= holding_clause_end
        )
        if window_orgs and trailing_local_orgs:
            window_ids = {org_id for org_id, _ in window_orgs}
            return tuple(
                (
                    org.id,
                    org_sigs
                    if org.id in window_ids
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="trailing local organization is outside holder clause"
                            ),
                        ),
                    ),
                )
                for org, org_sigs in organizations
            )
        if trailing_local_orgs and self._sentence_has_possessive_holder_pronoun_before_char(
            document, sentence, role_start_char
        ):
            window_ids = {org_id for org_id, _ in window_orgs}
            return tuple(
                (
                    org.id,
                    org_sigs
                    if org.id in window_ids
                    else self._merge_binding_signals(
                        org_sigs,
                        (
                            WeakSyntacticBindingSignal(
                                reason="trailing local organization follows possessive holder role"
                            ),
                        ),
                    ),
                )
                for org, org_sigs in organizations
            )
        return tuple((org.id, sigs) for org, sigs in organizations)

    def _org_source_compatible_with_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person_id: EntityCandidateId,
        org_id: EntityCandidateId,
    ) -> bool:
        source_sid = self._entity_source_sentence_id(document, org_id)
        if source_sid is None or source_sid == sentence.id:
            return True
        source_people = self._observed_people_in_sentence(document, source_sid)
        return not source_people or person_id in source_people

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
        plain_dismissal_lemmas = self._dismissal_lemmas - {"zasiadać"}
        negatable_dismissal_lemmas = {"zasiadać"}
        dismissal_match = lemmas & plain_dismissal_lemmas
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

    def _add_role_domain_bindings(
        self,
        *,
        document: ArticleDocument,
        emitter: DomainEventEmitter,
        event: EmittedEvent,
        role_bindings: dict[EntityCandidateId, tuple[Signal, ...]],
        evidence_id: EvidenceId,
    ) -> None:
        from pipeline_v2.governance.candidates import public_role_domain_for_role

        domains = {public_role_domain_for_role(document, role_id) for role_id in role_bindings}
        domains.discard(None)
        for domain in sorted(domains, key=lambda value: value.value):
            emitter.bind_text(
                event=event,
                role=EventRole.ROLE_DOMAIN,
                value=domain.value,
                evidence_ids=(evidence_id,),
                signals=(PublicRoleDomainSignal(domain=domain),),
            )
