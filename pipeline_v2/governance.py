from __future__ import annotations

from pipeline_v2.candidates import GovernanceFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, ProducerId
from pipeline_v2.nlp import EvidenceSpan, Sentence
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    AppointerContextSignal,
    AppointmentLemmaSignal,
    DiscourseOrganizationSignal,
    DismissalLemmaSignal,
    EntityKind,
    FactKind,
    GroundingKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    PartyOrganizationSignal,
    Signal,
    WeakSyntacticBindingSignal,
    WindowFallbackSignal,
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
        }
    )
    _generic_appointment_lemmas = frozenset({"zostać", "wejść", "nominacja"})
    _dismissal_lemmas = frozenset(
        {
            "odwołać",
            "zwolnić",
            "usunąć",
            "zdymisjonować",
            "stracić",
            # Resignation/exit patterns
            "rezygnacja",
            "zrezygnować",
            "odejść",
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
    _governing_body_head_lemmas = frozenset(
        {
            "rada",
            "zarząd",
            "komisja",
            "komitet",
        }
    )

    def name(self) -> str:
        return "governance_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            kinds = self._candidate_kinds(document, sentence)
            if not kinds:
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

            for person_id, organization_id, role_id, entity_signals in self._candidate_combinations(
                document,
                sentence,
            ):
                for kind, signals in kinds:
                    if kind == FactKind.GOVERNANCE_APPOINTMENT and (
                        organization_id is None and role_id is None
                    ):
                        continue
                    if (
                        kind == FactKind.GOVERNANCE_APPOINTMENT
                        and self._is_employment_overlap(signals)
                        and not self._has_governance_role(document, role_id)
                    ):
                        continue
                    if (
                        kind == FactKind.GOVERNANCE_APPOINTMENT
                        and self._is_generic_appointment_lemma(signals)
                        and not self._has_governance_role(document, role_id)
                    ):
                        continue
                    document.store.add_fact_candidate(
                        GovernanceFactCandidate(
                            id=document.store.next_fact_candidate_id(),
                            kind=kind,
                            person_entity_id=person_id,
                            organization_entity_id=organization_id,
                            role_entity_id=role_id,
                            evidence_ids=(evidence.id,),
                            source=self.producer_id,
                            signals=(*signals, *entity_signals),
                        )
                    )
        return document

    def _candidate_kinds(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[FactKind, tuple[Signal, ...]], ...]:
        lemmas = self._sentence_lemmas(document, sentence)
        candidates: list[tuple[FactKind, tuple[Signal, ...]]] = []
        if lemmas & self._appointment_lemmas:
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
        # Dismissal lemmas minus `zasiadać` (which is only a dismissal when negated)
        plain_dismissal_lemmas = self._dismissal_lemmas - {"zasiadać"}
        negatable_dismissal_lemmas = {"zasiadać"}
        dismissal_match = lemmas & plain_dismissal_lemmas
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
        return tuple(candidates)

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
        window_entities = retriever.entities_for_sentence_window(sentence, before=3, after=0)

        people = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.PERSON,
            local_signal=LocalPersonSignal(),
            window_signal=WindowPersonSignal(),
        )
        if not people:
            return ()

        organizations = self._select_entities(
            document,
            sentence,
            entities,
            window_entities,
            EntityKind.ORGANIZATION,
            local_signal=LocalOrganizationSignal(),
            window_signal=WindowOrganizationSignal(),
        )
        if not organizations:
            fallback_org = self._find_fallback_organization(document, sentence)
            if fallback_org is not None:
                organization, distance = fallback_org
                organizations = (
                    (
                        organization,
                        (
                            DiscourseOrganizationSignal(),
                            WindowFallbackSignal(distance=distance),
                        ),
                    ),
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
            person_is_window_only = person.id not in local_people_ids
            # Exclude appointer (nominative subject in active sentence with appointment lemma)
            trigger_token = syntax.first_token_with_lemmas(sentence, self._appointment_lemmas)
            if trigger_token is not None and not person_is_window_only:
                relation = syntax.dependency_relation(
                    sentence=sentence,
                    trigger_token_id=trigger_token.id,
                    entity_id=person.id,
                )
                if relation is not None and syntax.is_subject_relation(relation):
                    if not syntax.is_passive_sentence(sentence, trigger_token.id):
                        # Person is the appointer, skip them as a governance appointment candidate
                        continue
                if self._is_background_local_person(
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
                    signals = [*p_signals, *o_signals, *r_signals]
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
                        continue
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
        best_role, best_signals = min(
            compatible_roles,
            key=lambda item: self._role_score(
                person=person,
                role=item[0],
                trigger_start_char=trigger_start_char,
            ),
        )
        return ((best_role, best_signals),)

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
        viable_organizations = tuple(
            (organization, signals)
            for organization, signals in organizations
            if not self._is_governing_body_organization(document, organization.id)
        )
        if not viable_organizations:
            return ()
        best_organization, best_signals = min(
            viable_organizations,
            key=lambda item: self._organization_score(
                person=person,
                role=role,
                organization=item[0],
                trigger_start_char=trigger_start_char,
            ),
        )
        return ((best_organization, best_signals),)

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
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        local = tuple(entity for entity in local_entities if entity.kind == kind)
        if local:
            return tuple((entity, (local_signal,)) for entity in local)
        window = tuple(entity for entity in window_entities if entity.kind == kind)
        if window:
            results: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
            for entity in window:
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
                    signal = local_signal if entity_min_dist == 0 else window_signal
                    results.append((entity, (signal,)))
            return tuple(results)
        return ()

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
                case AppointmentLemmaSignal(lemma=lemma) if lemma in {"zatrudnić", "etat", "zatrudnienie"}:
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

    def _organization_lemmas(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> frozenset[str]:
        lemmas: set[str] = set()
        for mention in document.store.candidate_mentions(entity_id):
            for token in document.store.tokens_for_mention(mention.id):
                for analysis in token.morph:
                    lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _is_governing_body_organization(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates[entity_id]
        canonical_hint = (candidate.canonical_hint or "").casefold()
        if canonical_hint.startswith("rada ") or canonical_hint.startswith("zarząd "):
            return True
        lemmas = self._organization_lemmas(document, entity_id)
        if not lemmas:
            return False
        if "nadzorczy" in lemmas and "rada" in lemmas:
            return True
        return bool(lemmas & self._governing_body_head_lemmas and lemmas & {"nadzorczy", "członek"})

    @staticmethod
    def _entity_midpoint(entity: SentenceEntity) -> int:
        return (entity.start_char + entity.end_char) // 2

    def _role_score(
        self,
        *,
        person: SentenceEntity,
        role: SentenceEntity,
        trigger_start_char: int | None,
    ) -> tuple[int, int, int]:
        person_distance = abs(self._entity_midpoint(role) - self._entity_midpoint(person))
        trigger_distance = (
            abs(self._entity_midpoint(role) - trigger_start_char)
            if trigger_start_char is not None
            else 9999
        )
        return (person_distance, trigger_distance, role.start_char)

    def _organization_score(
        self,
        *,
        person: SentenceEntity,
        role: SentenceEntity | None,
        organization: SentenceEntity,
        trigger_start_char: int | None,
    ) -> tuple[int, int, int]:
        anchor_char = (
            self._entity_midpoint(role) if role is not None else self._entity_midpoint(person)
        )
        anchor_distance = abs(self._entity_midpoint(organization) - anchor_char)
        trigger_distance = (
            abs(self._entity_midpoint(organization) - trigger_start_char)
            if trigger_start_char is not None
            else 9999
        )
        return (anchor_distance, trigger_distance, organization.start_char)

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

    def _find_fallback_organization(
        self,
        document: ArticleDocument,
        anchor_sentence: Sentence,
    ) -> tuple[SentenceEntity, int] | None:
        retriever = SentenceEntityRetriever(document.store)
        same_paragraph_sentences = sorted(
            (
                sentence
                for sentence in document.store.sentences.values()
                if sentence.paragraph_index == anchor_sentence.paragraph_index
                and sentence.sentence_index < anchor_sentence.sentence_index
            ),
            key=lambda sentence: sentence.sentence_index,
            reverse=True,
        )
        for sentence in same_paragraph_sentences:
            organization = self._fallback_organization_in_sentence(
                document,
                retriever,
                sentence,
            )
            if organization is not None:
                return (
                    organization,
                    anchor_sentence.sentence_index - sentence.sentence_index,
                )

        for paragraph_index in range(anchor_sentence.paragraph_index - 1, -1, -1):
            lead_sentence = self._paragraph_lead_sentence(document, paragraph_index)
            if lead_sentence is None:
                continue
            organization = self._fallback_organization_in_sentence(
                document,
                retriever,
                lead_sentence,
            )
            if organization is not None:
                return (
                    organization,
                    anchor_sentence.sentence_index - lead_sentence.sentence_index,
                )
        return None

    def _fallback_organization_in_sentence(
        self,
        document: ArticleDocument,
        retriever: SentenceEntityRetriever,
        sentence: Sentence,
    ) -> SentenceEntity | None:
        organizations = tuple(
            entity
            for entity in retriever.entities_for_sentence(sentence)
            if entity.kind == EntityKind.ORGANIZATION
            and not self._is_party_like_organization(document, entity.id)
        )
        if organizations:
            return organizations[-1]
        return None

    @staticmethod
    def _paragraph_lead_sentence(
        document: ArticleDocument,
        paragraph_index: int,
    ) -> Sentence | None:
        paragraph_sentences = tuple(
            sentence
            for sentence in document.store.sentences.values()
            if sentence.paragraph_index == paragraph_index
        )
        if not paragraph_sentences:
            return None
        return min(paragraph_sentences, key=lambda sentence: sentence.sentence_index)
