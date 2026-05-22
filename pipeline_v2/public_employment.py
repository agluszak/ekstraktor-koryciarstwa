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
    _employment_role_lemmas = frozenset(
        {"doradca", "konsultant", "konsultantka", "pełnomocnik", "radca"}
    )
    _public_org_head_lemmas = frozenset({"gmina", "samorząd", "starostwo", "urząd"})
    _supporting_lemmas = frozenset({"praca", "pracować", "stanowisko", "zostać"})
    _contract_form_lemmas = frozenset({"umowa", "zlecenie"})
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
            "członek",
            "nadzorczy",
            "prezes",
            "rada",
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
        proxy = self._select_proxy_family_person(document, sentence, cue.anchor_char)
        if proxy is not None:
            entity, kinship_lemma = proxy
            return (
                (
                    entity,
                    (
                        ProxyFamilyEntitySignal(),
                        PossessiveKinshipSignal(kinship_lemma=kinship_lemma),
                    ),
                ),
            )

        syntax = SyntaxView(document.store)
        trigger = syntax.first_token_with_lemmas(sentence, self._employment_lemmas)
        entities = retriever.entities_for_sentence(sentence)
        candidates: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        for entity in entities:
            if entity.kind is not EntityKind.PERSON:
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
            if (
                not cue.active_subject_is_employee
                and self._is_nominative_subject_in_active_sentence(document, sentence, entity.id)
            ):
                continue
            candidates.append((entity, (LocalPersonSignal(),)))
        if candidates:
            return self._dedupe_entity_candidates(candidates)

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        people = tuple(entity for entity in window if entity.kind == EntityKind.PERSON)
        if not people:
            return ()
        candidate = people[-1]
        if not cue.active_subject_is_employee and self._is_nominative_subject_in_active_sentence(
            document, sentence, candidate.id
        ):
            return ()
        return ((candidate, (WindowPersonSignal(),)),)

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
            candidates.append((local, (LocalOrganizationSignal(),)))

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
            candidates.append((following_local, (LocalOrganizationSignal(),)))

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
            candidates.append((orgs[-1], (WindowOrganizationSignal(),)))
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

    def _select_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        cue: EmploymentCue,
    ) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
        proxy = self._select_proxy_family_person(document, sentence, cue.anchor_char)
        if proxy is not None:
            entity, kinship_lemma = proxy
            return (
                entity,
                (
                    ProxyFamilyEntitySignal(),
                    PossessiveKinshipSignal(kinship_lemma=kinship_lemma),
                ),
            )

        syntax = SyntaxView(document.store)
        trigger = syntax.first_token_with_lemmas(sentence, self._employment_lemmas)
        entities = retriever.entities_for_sentence(sentence)
        local = self._nearest_following_entity(
            entities,
            cue.anchor_char,
            kinds=frozenset({EntityKind.PERSON}),
        ) or self._nearest_preceding_entity(
            entities,
            cue.anchor_char,
            kinds=frozenset({EntityKind.PERSON}),
        )
        if local is not None:
            relation = (
                syntax.dependency_relation(
                    sentence=sentence,
                    trigger_token_id=trigger.id,
                    entity_id=local.id,
                )
                if trigger is not None
                else None
            )
            if relation is not None and syntax.is_subject_relation(relation):
                if not syntax.is_passive_sentence(sentence, trigger.id if trigger else None):
                    return None
                return local, (DependencySubjectSignal(relation=relation),)
            if relation is not None and syntax.is_object_relation(relation):
                return local, (DependencyObjectSignal(relation=relation),)
            if self._is_nominative_subject_in_active_sentence(document, sentence, local.id):
                return None
            return local, (LocalPersonSignal(),)

        window = retriever.entities_for_sentence_window(sentence, before=3, after=0)
        people = tuple(entity for entity in window if entity.kind == EntityKind.PERSON)
        if people:
            # Check if the window person is the active nominative subject
            candidate = people[-1]
            if self._is_nominative_subject_in_active_sentence(document, sentence, candidate.id):
                return None
            return candidate, (WindowPersonSignal(),)
        return None

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
                if first_token.span.start_char < anchor_char:
                    continue
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
        return min(candidates, key=lambda item: item[0].start_char)

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
            return local, (LocalOrganizationSignal(),)

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
            return following_local, (LocalOrganizationSignal(),)

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
            return closest, (WindowOrganizationSignal(),)
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

    def _nearest_public_org_head_token(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> TokenId | None:
        matches: list[tuple[int, TokenId]] = []
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if not ({analysis.lemma for analysis in token.morph} & self._public_org_head_lemmas):
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
