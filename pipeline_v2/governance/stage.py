from __future__ import annotations

from pipeline_v2.binding_emission import (
    DomainEventEmitter,
    EntityBindingGroup,
    emit_entity_binding_groups,
    merge_binding_signals,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import entity_has_lexical_context_proposal
from pipeline_v2.governance.candidates import (
    add_public_role_holding_candidates,
    collect_governance_candidates,
)
from pipeline_v2.governance.signals import GovernanceSignalAnnotator
from pipeline_v2.ids import EntityCandidateId
from pipeline_v2.nlp import EvidenceSpan
from pipeline_v2.types import (
    EntityTag,
    EventRole,
    FactKind,
    Signal,
    WeakSyntacticBindingSignal,
)


class GovernanceCandidateStage(GovernanceSignalAnnotator):
    def name(self) -> str:
        return "governance_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            add_public_role_holding_candidates(document, sentence)
            kinds = self._candidate_kinds(document, sentence)
            if not kinds:
                continue
            candidates = collect_governance_candidates(document, sentence)
            if not candidates.people:
                continue

            # Standardized EvidenceSpan creation using from_sentence
            evidence = EvidenceSpan.from_sentence(
                evidence_id=document.store.next_evidence_id(),
                sentence=sentence,
                source=self.producer_id,
            )
            document.store.add_evidence(evidence)

            for kind, kind_signals in kinds:
                # Event-level admissibility: employment-overlap or generic-appointment
                # lemmas without a governance role entity present should not produce an event.
                has_any_governance_role = any(
                    self._has_governance_role(document, role_id.id)
                    for role_id, _ in candidates.roles
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
                                    self._is_descriptor_role_self_pair(document, pid, role_id.id)
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
