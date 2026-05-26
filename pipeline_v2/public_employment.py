from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span, Token
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    DependencyObjectSignal,
    DependencySubjectSignal,
    EmploymentContractFormSignal,
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    InferredPublicOrganizationSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocationContextSignal,
    MentionKind,
    PartyOrganizationSignal,
    PossessiveKinshipSignal,
    ProxyFamilyEntitySignal,
    PublicEmploymentLemmaSignal,
    ReferenceKind,
    Signal,
    WindowOrganizationSignal,
    WindowPersonSignal,
)


@dataclass(frozen=True, slots=True)
class EmploymentCue:
    anchor_char: int
    detail: str
    context_text: str | None = None
    active_subject_is_employee: bool = False


class PublicEmploymentCandidateStage:
    producer_id = ProducerId("public_employment_candidate_stage_v2")

    _employment_lemmas = frozenset({"etat", "posada", "zatrudnić", "zatrudnienie"})
    _employment_action_lemmas = frozenset({"pracować"})
    _employment_role_lemmas = frozenset(
        {
            "doradca",
            "konsultant",
            "konsultantka",
            "pełnomocnik",
            "radca",
            "szef",
            "szefowa",
        }
    )
    _public_org_head_lemmas = frozenset({"gmina", "samorząd", "starostwo", "urząd"})
    _contextual_public_org_head_lemmas = frozenset({"jednostka", "spółka"})
    _public_org_context_lemmas = frozenset(
        {
            "gmina",
            "komunalny",
            "miejski",
            "państwo",
            "powiat",
            "publiczny",
            "samorząd",
            "skarb",
            "województwo",
        }
    )
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
    _supporting_lemmas = frozenset({"praca", "pracować", "stanowisko", "zostać"})
    _contract_form_lemmas = frozenset({"umowa", "zlecenie"})
    _workplace_preposition_lemmas = frozenset({"na", "w"})
    _collective_person_context_lemmas = frozenset({"członek", "polityk", "rodzina", "znajomy"})
    _governance_exclusion_lemmas = frozenset(
        {
            "awansować",
            "mianować",
            "objąć",
            "odwołać",
            "powołać",
            "stracić",
            "usunąć",
            "wybrać",
            "zdymisjonować",
            "zwolnić",
        }
    )
    _governance_role_lemmas = frozenset(
        {
            "burmistrz",
            "członek",
            "nadzorczy",
            "poseł",
            "prezes",
            "rada",
            "starosta",
            "wójt",
            "zarząd",
        }
    )

    def name(self) -> str:
        return "public_employment_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        retriever = SentenceEntityRetriever(document.store)
        for sentence in document.store.sentences.values():
            lemmas = self._sentence_lemmas(document, sentence)
            if lemmas & self._governance_exclusion_lemmas:
                continue
            cue = self._employment_cue(document, sentence, lemmas)
            if cue is None:
                continue
            entities = retriever.entities_for_sentence(sentence)
            employee_candidates = self._employee_candidates(document, sentence, retriever, cue)
            workplace_candidates = self._organization_candidates(
                document, sentence, retriever, cue.anchor_char
            )
            if not employee_candidates or not workplace_candidates:
                continue

            role = self._select_role(entities, cue.anchor_char)
            if self._is_governance_role(document, role.id if role is not None else None):
                if role is not None and role.start_char >= cue.anchor_char:
                    continue
                role = None
            evidence = EvidenceSpan(
                id=document.store.next_evidence_id(),
                text=sentence.text,
                span=sentence.span,
                sentence_id=sentence.id,
                paragraph_index=sentence.paragraph_index,
                source=self.producer_id,
            )
            document.store.add_evidence(evidence)
            event_signals: list[Signal] = [PublicEmploymentLemmaSignal(lemma=cue.detail)]
            if cue.context_text is not None:
                event_signals.append(EmploymentContractFormSignal(form=cue.context_text))
            event = EventCandidate(
                id=document.store.next_event_candidate_id(),
                kind=FactKind.PUBLIC_EMPLOYMENT,
                trigger_evidence_id=evidence.id,
                evidence_ids=(evidence.id,),
                source=self.producer_id,
                signals=tuple(event_signals),
            )
            document.store.add_event_candidate(event)
            for employee, employee_signals in employee_candidates:
                document.store.add_argument_binding(
                    ArgumentBindingCandidate(
                        id=document.store.next_argument_binding_candidate_id(),
                        event_id=event.id,
                        role=EventRole.EMPLOYEE,
                        filler=EntityFiller(employee.id),
                        evidence_ids=(evidence.id,),
                        signals=employee_signals,
                    )
                )
            for workplace, workplace_signals in workplace_candidates:
                document.store.add_argument_binding(
                    ArgumentBindingCandidate(
                        id=document.store.next_argument_binding_candidate_id(),
                        event_id=event.id,
                        role=EventRole.WORKPLACE,
                        filler=EntityFiller(workplace.id),
                        evidence_ids=(evidence.id,),
                        signals=workplace_signals,
                    )
                )
            for authority, authority_signals in self._hiring_authority_candidates(
                document, sentence, entities
            ):
                document.store.add_argument_binding(
                    ArgumentBindingCandidate(
                        id=document.store.next_argument_binding_candidate_id(),
                        event_id=event.id,
                        role=EventRole.HIRING_AUTHORITY,
                        filler=EntityFiller(authority.id),
                        evidence_ids=(evidence.id,),
                        signals=authority_signals,
                    )
                )
            if role is not None:
                document.store.add_argument_binding(
                    ArgumentBindingCandidate(
                        id=document.store.next_argument_binding_candidate_id(),
                        event_id=event.id,
                        role=EventRole.ROLE,
                        filler=EntityFiller(role.id),
                        evidence_ids=(evidence.id,),
                        signals=(LocalRoleSignal(),),
                    )
                )
        return document

    def _employee_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        cue: EmploymentCue,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        proxy = self._select_proxy_family_person(document, sentence, cue.anchor_char)
        if proxy is not None:
            entity, kinship_lemma = proxy
            candidates.append(
                (
                    entity,
                    (
                        ProxyFamilyEntitySignal(),
                        PossessiveKinshipSignal(kinship_lemma=kinship_lemma),
                    ),
                )
            )

        syntax = SyntaxView(document.store)
        trigger = syntax.first_token_with_lemmas(sentence, self._employment_lemmas)
        entities = retriever.entities_for_sentence(sentence)
        role = self._select_role(entities, cue.anchor_char)
        for entity in entities:
            if entity.kind is not EntityKind.PERSON:
                continue
            if role is not None and self._entity_is_farther_from_anchor_than_role(
                entity,
                role,
                cue.anchor_char,
            ):
                continue
            relation = (
                syntax.dependency_relation(
                    sentence=sentence,
                    trigger_token_id=trigger.id,
                    entity_id=entity.id,
                )
                if trigger is not None
                else None
            )
            if relation is not None and syntax.is_subject_relation(relation):
                if not syntax.is_passive_sentence(sentence, trigger.id if trigger else None):
                    continue
                candidates.append((entity, (DependencySubjectSignal(relation=relation),)))
                continue
            if relation is not None and syntax.is_object_relation(relation):
                candidates.append((entity, (DependencyObjectSignal(relation=relation),)))
                continue
            if self._has_collective_person_context(document, sentence):
                continue
            if (
                not cue.active_subject_is_employee
                and self._is_nominative_subject_in_active_sentence(document, sentence, entity.id)
            ):
                continue
            candidates.append((entity, (LocalPersonSignal(),)))
        if candidates:
            return self._dedupe_entity_candidates(candidates)
        if role is not None:
            return ()

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        people = tuple(entity for entity in window if entity.kind == EntityKind.PERSON)
        if not people:
            return ()
        if self._has_collective_person_context(document, sentence):
            return ()
        candidate = people[-1]
        if not cue.active_subject_is_employee and self._is_nominative_subject_in_active_sentence(
            document, sentence, candidate.id
        ):
            return ()
        return ((candidate, (WindowPersonSignal(),)),)

    def _entity_is_farther_from_anchor_than_role(
        self,
        entity: SentenceEntity,
        role: SentenceEntity,
        anchor_char: int,
    ) -> bool:
        entity_distance = min(
            abs(entity.start_char - anchor_char),
            abs(entity.end_char - anchor_char),
        )
        role_distance = min(abs(role.start_char - anchor_char), abs(role.end_char - anchor_char))
        return role_distance < entity_distance

    def _hiring_authority_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entities: tuple[SentenceEntity, ...],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        syntax = SyntaxView(document.store)
        trigger = syntax.first_token_with_lemmas(sentence, self._employment_lemmas)
        if trigger is None or syntax.is_passive_sentence(sentence, trigger.id):
            return ()
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        for entity in entities:
            if entity.kind is not EntityKind.PERSON:
                continue
            relation = syntax.dependency_relation(
                sentence=sentence,
                trigger_token_id=trigger.id,
                entity_id=entity.id,
            )
            if relation is not None and syntax.is_subject_relation(relation):
                candidates.append((entity, (DependencySubjectSignal(relation=relation),)))
        return self._dedupe_entity_candidates(candidates)

    def _organization_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        anchor_char: int,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        entities = retriever.entities_for_sentence(sentence)
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        local = self._nearest_preceding_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )
        if local is not None:
            candidates.append(
                (
                    local,
                    self._organization_binding_signals(
                        document,
                        local.id,
                        LocalOrganizationSignal(),
                    ),
                )
            )

        inferred = self._infer_public_organization(document, sentence, anchor_char)
        if inferred is not None:
            candidates.append(inferred)

        following_local = self._nearest_following_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )
        if (
            following_local is not None
            and not self._is_after_next_employment_cue(
                document,
                sentence,
                anchor_char,
                following_local,
            )
            and not self._crosses_clause_boundary(
                document,
                sentence,
                anchor_char,
                following_local.start_char,
            )
            and following_local.start_char - anchor_char <= 80
        ):
            candidates.append(
                (
                    following_local,
                    self._organization_binding_signals(
                        document,
                        following_local.id,
                        LocalOrganizationSignal(),
                    ),
                )
            )

        location_workplace = self._location_workplace_candidate(
            document,
            sentence,
            retriever,
            anchor_char,
        )
        if location_workplace is not None:
            candidates.append(location_workplace)
            return self._dedupe_entity_candidates(candidates)

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        orgs = tuple(
            entity
            for entity in window
            if entity.kind == EntityKind.ORGANIZATION
            and not (
                entity.start_char > anchor_char
                and self._crosses_clause_boundary(
                    document,
                    sentence,
                    anchor_char,
                    entity.start_char,
                )
            )
        )
        if orgs:
            candidates.append(
                (
                    orgs[-1],
                    self._organization_binding_signals(
                        document,
                        orgs[-1].id,
                        WindowOrganizationSignal(),
                    ),
                )
            )
        return self._dedupe_entity_candidates(candidates)

    def _dedupe_entity_candidates(
        self,
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        merged: dict[EntityCandidateId, tuple[SentenceEntity, tuple[Signal, ...]]] = {}
        for entity, signals in candidates:
            if entity.id not in merged:
                merged[entity.id] = (entity, signals)
        return tuple(merged.values())

    def _employment_cue(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        lemmas: frozenset[str],
    ) -> EmploymentCue | None:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            matched_lemmas = {analysis.lemma for analysis in token.morph} & self._employment_lemmas
            if matched_lemmas:
                detail = next(iter(sorted(matched_lemmas)))
                return EmploymentCue(anchor_char=token.span.start_char, detail=detail)
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            matched_lemmas = {
                analysis.lemma for analysis in token.morph
            } & self._employment_action_lemmas
            if matched_lemmas:
                detail = next(iter(sorted(matched_lemmas)))
                return EmploymentCue(
                    anchor_char=token.span.start_char,
                    detail=detail,
                    active_subject_is_employee=True,
                )
        if self._has_contract_form(lemmas):
            return EmploymentCue(
                anchor_char=sentence.span.start_char,
                detail="umowa-zlecenie",
                context_text="umowa-zlecenie",
            )
        if (lemmas & self._employment_role_lemmas) and (lemmas & self._supporting_lemmas):
            role_token = self._first_token_with_lemmas(
                document,
                sentence,
                self._employment_role_lemmas,
            )
            detail = next(iter(sorted(lemmas & self._employment_role_lemmas)))
            return EmploymentCue(
                anchor_char=(
                    role_token.span.start_char
                    if role_token is not None
                    else sentence.span.start_char
                ),
                detail=detail,
                active_subject_is_employee=True,
            )
        if "zająć" in lemmas and "stanowisko" in lemmas:
            trigger_token = self._first_token_with_lemmas(
                document,
                sentence,
                frozenset({"zająć"}),
            )
            return EmploymentCue(
                anchor_char=(
                    trigger_token.span.start_char
                    if trigger_token is not None
                    else sentence.span.start_char
                ),
                detail="stanowisko",
                active_subject_is_employee=True,
            )
        return None

    def _first_token_with_lemmas(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        lemmas: frozenset[str],
    ) -> Token | None:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if {analysis.lemma for analysis in token.morph} & lemmas:
                return token
        return None

    def _sentence_lemmas(self, document: ArticleDocument, sentence: Sentence) -> frozenset[str]:
        lemmas: set[str] = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _has_contract_form(self, lemmas: frozenset[str]) -> bool:
        return self._contract_form_lemmas <= lemmas

    def _select_proxy_family_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> tuple[SentenceEntity, str] | None:
        candidates: list[tuple[SentenceEntity, str]] = []
        for candidate in document.store.candidates_by_kind(EntityKind.PERSON):
            for reference in document.store.candidate_references(candidate.id):
                if reference.sentence_id != sentence.id:
                    continue
                if reference.kind is not ReferenceKind.PROXY_FAMILY_PHRASE:
                    continue
                if not reference.token_ids:
                    continue
                first_token = document.store.tokens[reference.token_ids[0]]
                last_token = document.store.tokens[reference.token_ids[-1]]
                candidates.append(
                    (
                        SentenceEntity(
                            id=candidate.id,
                            kind=EntityKind.PERSON,
                            start_char=first_token.span.start_char,
                            end_char=last_token.span.end_char,
                        ),
                        reference.head_lemma or "family",
                    )
                )
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (abs(item[0].start_char - anchor_char), item[0].start_char),
        )

    def _is_nominative_subject_in_active_sentence(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity_id: EntityCandidateId,
    ) -> bool:
        is_nominative = False
        for mention in document.store.candidate_mentions(entity_id):
            mention_tokens_are_nominative = True
            for token in document.store.tokens_for_mention(mention.id):
                token_has_nom = False
                for analysis in token.morph:
                    if analysis.case == "nom":
                        token_has_nom = True
                        break
                if not token_has_nom:
                    mention_tokens_are_nominative = False
                    break
            if mention_tokens_are_nominative:
                is_nominative = True
                break

        if not is_nominative:
            return False

        has_passive_aux = False
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                if analysis.lemma in {"zostać", "być"}:
                    has_passive_aux = True
                    break
            if has_passive_aux:
                break

        return not has_passive_aux

    def _select_organization(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        anchor_char: int,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        entities = retriever.entities_for_sentence(sentence)
        local = self._nearest_preceding_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )
        if local is not None:
            return (
                local,
                self._organization_binding_signals(document, local.id, LocalOrganizationSignal()),
            )

        inferred = self._infer_public_organization(document, sentence, anchor_char)
        if inferred is not None:
            entity, signals = inferred
            return entity, signals

        following_local = self._nearest_following_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )
        if (
            following_local is not None
            and not self._is_after_next_employment_cue(
                document,
                sentence,
                anchor_char,
                following_local,
            )
            and not self._crosses_clause_boundary(
                document,
                sentence,
                anchor_char,
                following_local.start_char,
            )
            and following_local.start_char - anchor_char <= 80
        ):
            return (
                following_local,
                self._organization_binding_signals(
                    document,
                    following_local.id,
                    LocalOrganizationSignal(),
                ),
            )

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        orgs = tuple(
            entity
            for entity in window
            if entity.kind == EntityKind.ORGANIZATION
            and not (
                entity.start_char > anchor_char
                and self._crosses_clause_boundary(
                    document,
                    sentence,
                    anchor_char,
                    entity.start_char,
                )
            )
        )
        if orgs:
            # Prefer the closest one by absolute character distance
            anchor = anchor_char
            closest = min(
                orgs,
                key=lambda e: min(abs(e.start_char - anchor), abs(e.end_char - anchor)),
            )
            return (
                closest,
                self._organization_binding_signals(
                    document,
                    closest.id,
                    WindowOrganizationSignal(),
                ),
            )
        return None

    def _is_after_next_employment_cue(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
        organization: SentenceEntity,
    ) -> bool:
        next_employment_anchor = self._next_employment_anchor(document, sentence, anchor_char)
        if next_employment_anchor is None:
            return False
        return organization.start_char >= next_employment_anchor

    def _infer_public_organization(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        head_token_id = self._nearest_public_org_head_token(document, sentence, anchor_char)
        if head_token_id is None:
            return None
        head_token = document.store.tokens[head_token_id]
        canonical_hint = head_token.text
        span = Span(head_token.span.start_char, head_token.span.end_char)
        location_distance = self._nearest_location_distance(document, sentence)
        signals: list[Signal] = [
            LocalOrganizationSignal(),
            InferredPublicOrganizationSignal(
                head_lemma=head_token.preferred_lemma() or head_token.text
            ),
        ]
        if location_distance is not None:
            signals.append(LocationContextSignal(distance=location_distance))
        probe = EvidenceSpan(
            id=EvidenceId("probe"),
            text=head_token.text,
            span=span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        for candidate_id in document.store.candidate_ids_with_evidence_overlapping_span(probe):
            candidate = document.store.entity_candidates[candidate_id]
            if candidate.kind == EntityKind.ORGANIZATION:
                return (
                    SentenceEntity(
                        id=candidate_id,
                        kind=EntityKind.ORGANIZATION,
                        start_char=head_token.span.start_char,
                        end_char=head_token.span.end_char,
                    ),
                    tuple(signals),
                )

        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=head_token.text,
            span=span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        document.store.add_mention(
            Mention(
                id=mention_id,
                text=head_token.text,
                kind=MentionKind.DESCRIPTOR_NOUN_PHRASE,
                evidence_id=evidence.id,
                sentence_id=sentence.id,
                token_ids=(head_token_id,),
                head_lemma=head_token.preferred_lemma(),
            )
        )
        entity_id = document.store.add_entity_candidate(
            EntityCandidate(
                id=document.store.next_entity_candidate_id(),
                kind=EntityKind.ORGANIZATION,
                mention_ids=(mention_id,),
                canonical_hint=canonical_hint,
                grounding=GroundingKind.INFERRED,
                source=self.producer_id,
            )
        )
        return (
            SentenceEntity(
                id=entity_id,
                kind=EntityKind.ORGANIZATION,
                start_char=head_token.span.start_char,
                end_char=head_token.span.end_char,
            ),
            tuple(signals),
        )

    def _location_workplace_candidate(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        anchor_char: int,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        entities = retriever.entities_for_sentence(sentence)
        for location in entities:
            if location.kind is not EntityKind.LOCATION:
                continue
            if not (
                self._preceding_prepositions(document, sentence, location.start_char)
                & self._workplace_preposition_lemmas
            ):
                continue
            synthesized = self._organization_from_location_entity(document, location)
            if synthesized is None:
                continue
            return (
                synthesized,
                (LocalOrganizationSignal(), LocationContextSignal(distance=0)),
            )

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        window_locations = tuple(entity for entity in window if entity.kind is EntityKind.LOCATION)
        if window_locations:
            nearest = min(window_locations, key=lambda entity: abs(entity.start_char - anchor_char))
            synthesized = self._organization_from_location_entity(document, nearest)
            if synthesized is not None:
                return (
                    synthesized,
                    (WindowOrganizationSignal(), LocationContextSignal(distance=1)),
                )
        return None

    def _organization_from_location_entity(
        self,
        document: ArticleDocument,
        location: SentenceEntity,
    ) -> SentenceEntity | None:
        location_candidate = document.store.entity_candidates.get(location.id)
        if location_candidate is None or not location_candidate.mention_ids:
            return None
        location_mention = document.store.mentions.get(location_candidate.mention_ids[0])
        if location_mention is None:
            return None
        location_evidence = document.store.evidence.get(location_mention.evidence_id)
        if location_evidence is None:
            return None

        for candidate in document.store.candidates_by_kind(EntityKind.ORGANIZATION):
            if (candidate.canonical_hint or "") != (location_candidate.canonical_hint or ""):
                continue
            for mention in document.store.candidate_mentions(candidate.id):
                evidence = document.store.evidence.get(mention.evidence_id)
                if evidence is None:
                    continue
                if (
                    evidence.sentence_id == location_evidence.sentence_id
                    and evidence.span.start_char == location_evidence.span.start_char
                    and evidence.span.end_char == location_evidence.span.end_char
                ):
                    return SentenceEntity(
                        id=candidate.id,
                        kind=EntityKind.ORGANIZATION,
                        start_char=location.start_char,
                        end_char=location.end_char,
                    )

        mention_id = document.store.next_mention_id()
        document.store.add_mention(
            Mention(
                id=mention_id,
                text=location_mention.text,
                kind=MentionKind.DESCRIPTOR_NOUN_PHRASE,
                evidence_id=location_mention.evidence_id,
                sentence_id=location_mention.sentence_id,
                token_ids=location_mention.token_ids,
                head_lemma=location_mention.head_lemma,
            )
        )
        entity_id = document.store.add_entity_candidate(
            EntityCandidate(
                id=document.store.next_entity_candidate_id(),
                kind=EntityKind.ORGANIZATION,
                mention_ids=(mention_id,),
                canonical_hint=location_candidate.canonical_hint,
                grounding=GroundingKind.INFERRED,
                source=self.producer_id,
            )
        )
        return SentenceEntity(
            id=entity_id,
            kind=EntityKind.ORGANIZATION,
            start_char=location.start_char,
            end_char=location.end_char,
        )

    def _nearest_public_org_head_token(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> TokenId | None:
        matches: list[tuple[int, TokenId]] = []
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if not self._is_public_org_head_token(document, sentence, token_id):
                continue
            if token.span.start_char > anchor_char and self._crosses_clause_boundary(
                document,
                sentence,
                anchor_char,
                token.span.start_char,
            ):
                continue
            matches.append((abs(token.span.start_char - anchor_char), token_id))
        if not matches:
            return None
        return min(matches, key=lambda item: item[0])[1]

    def _is_public_org_head_token(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        token_id: TokenId,
    ) -> bool:
        token = document.store.tokens[token_id]
        token_lemmas = {analysis.lemma for analysis in token.morph}
        if token_lemmas & self._public_org_head_lemmas:
            return True
        if not (token_lemmas & self._contextual_public_org_head_lemmas):
            return False
        sentence_tokens = tuple(
            document.store.tokens[sent_token_id] for sent_token_id in sentence.token_ids
        )
        token_index = next(
            (
                index
                for index, sentence_token in enumerate(sentence_tokens)
                if sentence_token.id == token_id
            ),
            None,
        )
        if token_index is None:
            return False
        window_tokens = sentence_tokens[max(0, token_index - 3) : token_index + 4]
        context_lemmas = {
            analysis.lemma for window_token in window_tokens for analysis in window_token.morph
        }
        return bool(context_lemmas & self._public_org_context_lemmas)

    def _next_employment_anchor(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> int | None:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if token.span.start_char <= anchor_char:
                continue
            token_lemmas = {analysis.lemma for analysis in token.morph}
            if token_lemmas & self._employment_lemmas:
                return token.span.start_char
            if (
                token_lemmas & self._supporting_lemmas
                and token_lemmas & self._employment_role_lemmas
            ):
                return token.span.start_char
        return None

    def _crosses_clause_boundary(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
        target_char: int,
    ) -> bool:
        between = document.cleaned_text[anchor_char:target_char].casefold()
        if "," not in between and ";" not in between and ":" not in between:
            return False
        return any(conjunction in between for conjunction in (" a ", " ale ", " oraz ", " zaś "))

    def _nearest_location_distance(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> int | None:
        distances: list[int] = []
        for candidate in document.store.candidates_by_kind(EntityKind.LOCATION):
            for evidence in document.store.evidence_for_entity(candidate.id):
                if evidence.sentence_id is None:
                    continue
                evidence_sentence = document.store.sentences[evidence.sentence_id]
                if evidence_sentence.paragraph_index != sentence.paragraph_index:
                    continue
                distance = sentence.sentence_index - evidence_sentence.sentence_index
                if 0 <= distance <= 1:
                    distances.append(distance)
        if not distances:
            return None
        return min(distances)

    def _preceding_prepositions(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity_start_char: int,
    ) -> frozenset[str]:
        tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
        entity_token_index = None
        for index, token in enumerate(tokens):
            if token.span.start_char >= entity_start_char:
                entity_token_index = index
                break
        if entity_token_index is None or entity_token_index == 0:
            return frozenset()

        lemmas: set[str] = set()
        for token in tokens[max(0, entity_token_index - 3) : entity_token_index]:
            lemmas.update(
                analysis.lemma.casefold() for analysis in token.morph if analysis.lemma is not None
            )
        return frozenset(lemmas)

    def _select_role(
        self,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
    ) -> SentenceEntity | None:
        return self._nearest_following_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ROLE}),
        ) or self._nearest_preceding_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ROLE}),
        )

    def _nearest_following_entity(
        self,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
        *,
        kinds: frozenset[EntityKind],
    ) -> SentenceEntity | None:
        for entity in entities:
            if entity.kind in kinds and entity.start_char >= anchor_char:
                return entity
        return None

    def _nearest_preceding_entity(
        self,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
        *,
        kinds: frozenset[EntityKind],
    ) -> SentenceEntity | None:
        for entity in reversed(entities):
            if entity.kind in kinds and entity.start_char < anchor_char:
                return entity
        return None

    def _is_governance_role(
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

    def _has_collective_person_context(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> bool:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                if (
                    analysis.lemma in self._collective_person_context_lemmas
                    and analysis.number == "pl"
                ):
                    return True
        return False

    def _organization_binding_signals(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
        base_signal: Signal,
    ) -> tuple[Signal, ...]:
        signals: list[Signal] = [base_signal]
        if self._is_party_like_organization(document, entity_id):
            signals.append(PartyOrganizationSignal())
        return tuple(signals)

    def _is_party_like_organization(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates[entity_id]
        canonical_hint = (candidate.canonical_hint or "").casefold()
        if canonical_hint in self._party_like_organization_names:
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
