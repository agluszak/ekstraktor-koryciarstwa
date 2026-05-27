from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    EntityCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter
from pipeline_v2.ids import EntityCandidateId, EvidenceId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span, Token
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    DependencyObjectSignal,
    DependencySubjectSignal,
    DomainOverlapSuppressionSignal,
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
    WeakSyntacticBindingSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
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
            "ekodoradca",
            "konsultant",
            "konsultantka",
            "koordynator",
            "pełnomocnik",
            "pracownik",
            "radca",
            "specjalista",
            "szef",
            "szefowa",
        }
    )
    _political_role_lemmas = frozenset(
        {
            "burmistrz",
            "marszałek",
            "minister",
            "poseł",
            "posłanka",
            "prezydent",
            "radna",
            "radny",
            "senator",
            "starosta",
            "wojewoda",
            "wójt",
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
    _role_intro_lemmas = frozenset({"jako", "stanowisko"})
    _role_phrase_stop_lemmas = frozenset({"a", "ale", "i", "lub", "oraz", "po", "w", "z"})
    _role_phrase_skip_lemmas = frozenset({"kolejny", "nowy", "przyszły", "swój"})
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
            if not employee_candidates:
                continue

            role_candidates = self._role_candidates(
                document,
                sentence,
                entities,
                cue.anchor_char,
                prefer_following_only=self._has_proxy_family_employee(employee_candidates),
            )
            role_candidates = tuple(
                (
                    role,
                    self._employment_role_signals(
                        document=document,
                        role=role,
                        signals=signals,
                        cue=cue,
                    ),
                )
                for role, signals in role_candidates
            )
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
            emitter = DomainEventEmitter(document, self.producer_id)
            event = emitter.event(
                kind=FactKind.PUBLIC_EMPLOYMENT,
                trigger_evidence_id=evidence.id,
                evidence_ids=(evidence.id,),
                signals=tuple(event_signals),
            )
            for employee, employee_signals in employee_candidates:
                emitter.bind_entity(
                    event=event,
                    role=EventRole.EMPLOYEE,
                    entity_id=employee.id,
                    evidence_ids=(evidence.id,),
                    signals=employee_signals,
                )
            for workplace, workplace_signals in workplace_candidates:
                emitter.bind_entity(
                    event=event,
                    role=EventRole.WORKPLACE,
                    entity_id=workplace.id,
                    evidence_ids=(evidence.id,),
                    signals=workplace_signals,
                )
            employee_ids = frozenset(employee.id for employee, _signals in employee_candidates)
            for authority, authority_signals in self._hiring_authority_candidates(
                document, sentence, entities, excluded_ids=employee_ids
            ):
                emitter.bind_entity(
                    event=event,
                    role=EventRole.HIRING_AUTHORITY,
                    entity_id=authority.id,
                    evidence_ids=(evidence.id,),
                    signals=authority_signals,
                )
            for role, role_signals in role_candidates:
                emitter.bind_entity(
                    event=event,
                    role=EventRole.ROLE,
                    entity_id=role.id,
                    evidence_ids=(evidence.id,),
                    signals=role_signals,
                )
        return document

    def _employment_role_signals(
        self,
        *,
        document: ArticleDocument,
        role: SentenceEntity,
        signals: tuple[Signal, ...],
        cue: EmploymentCue,
    ) -> tuple[Signal, ...]:
        normalized = self._without_domain_overlap(signals) if cue.detail == "pracować" else signals
        if not self._is_governance_role(document, role.id):
            return normalized
        if cue.detail == "pracować":
            return (
                *normalized,
                WeakSyntacticBindingSignal(reason="governance role in employment context"),
            )
        return (
            *normalized,
            DomainOverlapSuppressionSignal(reason="governance role in employment context"),
            WeakSyntacticBindingSignal(reason="governance role in employment context"),
        )

    def _without_domain_overlap(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        return tuple(
            signal for signal in signals if not self._is_domain_overlap_suppression_signal(signal)
        )

    def _is_domain_overlap_suppression_signal(self, signal: Signal) -> bool:
        match signal:
            case DomainOverlapSuppressionSignal():
                return True
            case _:
                return False

    def _employee_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        cue: EmploymentCue,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        proxies = self._proxy_family_people(document, sentence)
        for entity, kinship_lemma in proxies:
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
        role_candidates = self._role_candidates(
            document,
            sentence,
            entities,
            cue.anchor_char,
            prefer_following_only=bool(proxies),
        )
        closest_role = min(
            (role for role, _signals in role_candidates),
            key=lambda role: min(
                abs(role.start_char - cue.anchor_char),
                abs(role.end_char - cue.anchor_char),
            ),
            default=None,
        )
        for entity in entities:
            if entity.kind is not EntityKind.PERSON:
                continue
            if proxies and entity.start_char < cue.anchor_char:
                candidates.append(
                    (
                        entity,
                        (
                            WindowPersonSignal(),
                            WeakSyntacticBindingSignal(
                                reason="preceding person competes with proxy family employee"
                            ),
                        ),
                    )
                )
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
            signals: tuple[Signal, ...] = (LocalPersonSignal(),)
            if closest_role is not None and self._entity_is_farther_from_anchor_than_role(
                entity,
                closest_role,
                cue.anchor_char,
            ):
                signals = (
                    LocalPersonSignal(),
                    WeakSyntacticBindingSignal(reason="person is farther from cue than role"),
                )
            candidates.append((entity, signals))
        if candidates:
            return self._dedupe_entity_candidates(candidates)

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        people = tuple(entity for entity in window if entity.kind == EntityKind.PERSON)
        if not people:
            return ()
        if self._has_collective_person_context(document, sentence):
            return ()
        candidates = []
        for person in people:
            if (
                not cue.active_subject_is_employee
                and self._is_nominative_subject_in_active_sentence(document, sentence, person.id)
            ):
                candidates.append(
                    (
                        person,
                        (
                            WindowPersonSignal(),
                            WeakSyntacticBindingSignal(
                                reason="window person is nominative in active sentence"
                            ),
                        ),
                    )
                )
                continue
            candidates.append((person, (WindowPersonSignal(),)))
        return self._dedupe_entity_candidates(candidates)

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
        *,
        excluded_ids: frozenset[EntityCandidateId],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        syntax = SyntaxView(document.store)
        trigger = syntax.first_token_with_lemmas(sentence, self._employment_lemmas)
        if trigger is None or syntax.is_passive_sentence(sentence, trigger.id):
            return ()
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        for entity in entities:
            if entity.kind is not EntityKind.PERSON:
                continue
            if entity.id in excluded_ids:
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
        for local in self._preceding_entities(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        ):
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

        following_locals = self._following_entities(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )
        for following_local in following_locals:
            if (
                self._is_after_next_employment_cue(
                    document,
                    sentence,
                    anchor_char,
                    following_local,
                )
                or self._crosses_clause_boundary(
                    document,
                    sentence,
                    anchor_char,
                    following_local.start_char,
                )
                or following_local.start_char - anchor_char > 80
            ):
                continue
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
        for org in orgs:
            candidates.append(
                (
                    org,
                    self._organization_binding_signals(
                        document,
                        org.id,
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

    def _proxy_family_people(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[SentenceEntity, str], ...]:
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
        return tuple(candidates)

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

    def _role_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
        *,
        prefer_following_only: bool,
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        phrase_role = self._role_from_local_phrase(document, sentence, anchor_char)
        if phrase_role is not None:
            candidates.append((phrase_role, (LocalRoleSignal(),)))
        for following_role in self._following_entities(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ROLE}),
        ):
            signals: tuple[Signal, ...] = (
                (
                    DomainOverlapSuppressionSignal(reason="political role in employment context"),
                    WeakSyntacticBindingSignal(reason="political role in employment context"),
                )
                if self._is_political_role(document, following_role.id)
                else (LocalRoleSignal(),)
            )
            candidates.append((following_role, signals))
        if not prefer_following_only:
            for preceding_role in self._preceding_entities(
                entities,
                anchor_char,
                kinds=frozenset({EntityKind.ROLE}),
            ):
                signals = (
                    (
                        DomainOverlapSuppressionSignal(
                            reason="political role in employment context"
                        ),
                        WeakSyntacticBindingSignal(reason="political role in employment context"),
                    )
                    if self._is_political_role(document, preceding_role.id)
                    else (WindowRoleSignal(),)
                )
                candidates.append((preceding_role, signals))
        return self._dedupe_entity_candidates(candidates)

    def _role_from_local_phrase(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> SentenceEntity | None:
        phrase_token_ids = self._role_phrase_token_ids(document, sentence, anchor_char)
        if not phrase_token_ids:
            return None
        start_char = document.store.tokens[phrase_token_ids[0]].span.start_char
        end_char = document.store.tokens[phrase_token_ids[-1]].span.end_char
        probe = EvidenceSpan(
            id=EvidenceId("probe"),
            text=document.cleaned_text[start_char:end_char],
            span=Span(start_char, end_char),
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        for candidate_id in document.store.candidate_ids_with_evidence_overlapping_span(probe):
            candidate = document.store.entity_candidates[candidate_id]
            if candidate.kind is not EntityKind.ROLE:
                continue
            return SentenceEntity(
                id=candidate_id,
                kind=EntityKind.ROLE,
                start_char=start_char,
                end_char=end_char,
            )
        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=document.cleaned_text[start_char:end_char],
            span=Span(start_char, end_char),
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        document.store.add_mention(
            Mention(
                id=mention_id,
                text=evidence.text,
                kind=MentionKind.ROLE,
                evidence_id=evidence.id,
                sentence_id=sentence.id,
                token_ids=phrase_token_ids,
                head_lemma=document.store.tokens[phrase_token_ids[0]].preferred_lemma(),
            )
        )
        entity_id = document.store.add_entity_candidate(
            EntityCandidate(
                id=document.store.next_entity_candidate_id(),
                kind=EntityKind.ROLE,
                mention_ids=(mention_id,),
                canonical_hint=evidence.text,
                grounding=GroundingKind.INFERRED,
                source=self.producer_id,
            )
        )
        return SentenceEntity(
            id=entity_id,
            kind=EntityKind.ROLE,
            start_char=start_char,
            end_char=end_char,
        )

    def _role_phrase_token_ids(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> tuple[TokenId, ...]:
        tokens = [document.store.tokens[token_id] for token_id in sentence.token_ids]
        start_index: int | None = None
        skip_first = False
        for index, token in enumerate(tokens):
            if token.span.start_char < anchor_char:
                continue
            token_lemmas = {analysis.lemma for analysis in token.morph}
            if "jako" in token_lemmas:
                start_index = index + 1
                break
            if "stanowisko" in token_lemmas:
                start_index = index + 1
                skip_first = True
                break
        if start_index is None or start_index >= len(tokens):
            return ()
        collected: list[TokenId] = []
        for token in tokens[start_index:]:
            token_lemmas = {analysis.lemma for analysis in token.morph}
            if token.text in {",", ".", ";", ":"}:
                break
            if collected and token_lemmas & self._role_phrase_stop_lemmas:
                break
            if token_lemmas & self._workplace_preposition_lemmas:
                break
            if not self._is_role_phrase_token(token):
                if collected:
                    break
                continue
            if skip_first and not collected and token_lemmas & self._role_phrase_skip_lemmas:
                continue
            collected.append(token.id)
            if len(collected) >= 4:
                break
        return tuple(collected)

    def _is_role_phrase_token(self, token: Token) -> bool:
        if token.text in {",", ".", ";", ":"}:
            return False
        for analysis in token.morph:
            if analysis.pos in {"adj", "subst"}:
                return True
        return False

    def _has_proxy_family_employee(
        self,
        candidates: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
    ) -> bool:
        for _entity, signals in candidates:
            for signal in signals:
                match signal:
                    case ProxyFamilyEntitySignal():
                        return True
        return False

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

    def _following_entities(
        self,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
        *,
        kinds: frozenset[EntityKind],
    ) -> tuple[SentenceEntity, ...]:
        return tuple(
            entity
            for entity in entities
            if entity.kind in kinds and entity.start_char >= anchor_char
        )

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

    def _preceding_entities(
        self,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
        *,
        kinds: frozenset[EntityKind],
    ) -> tuple[SentenceEntity, ...]:
        return tuple(
            entity
            for entity in reversed(entities)
            if entity.kind in kinds and entity.start_char < anchor_char
        )

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

    def _is_political_role(
        self,
        document: ArticleDocument,
        role_id: EntityCandidateId | None,
    ) -> bool:
        if role_id is None:
            return False
        for mention in document.store.candidate_mentions(role_id):
            for token in document.store.tokens_for_mention(mention.id):
                if any(analysis.lemma in self._political_role_lemmas for analysis in token.morph):
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
