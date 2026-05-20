from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import EntityCandidate, PublicEmploymentFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    DependencyObjectSignal,
    DependencySubjectSignal,
    EmploymentContractFormSignal,
    EntityKind,
    GroundingKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
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


class PublicEmploymentCandidateStage:
    producer_id = ProducerId("public_employment_candidate_stage_v2")

    _employment_lemmas = frozenset({"etat", "zatrudnić"})
    _employment_role_lemmas = frozenset({"doradca", "konsultant", "konsultantka", "pełnomocnik"})
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
            person_result = self._select_person(document, sentence, retriever, cue)
            organization_result = self._select_organization(
                document, sentence, retriever, cue.anchor_char
            )
            if person_result is None or organization_result is None:
                continue
            person, person_signals = person_result
            organization, organization_signal = organization_result

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
            signals: list[Signal] = [
                PublicEmploymentLemmaSignal(lemma=cue.detail),
                *person_signals,
                organization_signal,
            ]
            if role is not None:
                signals.append(LocalRoleSignal())
            if cue.context_text is not None:
                signals.append(EmploymentContractFormSignal(form=cue.context_text))
            document.store.add_fact_candidate(
                PublicEmploymentFactCandidate(
                    id=document.store.next_fact_candidate_id(),
                    person_entity_id=person.id,
                    organization_entity_id=organization.id,
                    role_entity_id=role.id if role is not None else None,
                    context_text=cue.context_text,
                    evidence_ids=(evidence.id,),
                    source=self.producer_id,
                    signals=tuple(signals),
                )
            )
        return document

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
            detail = next(iter(sorted(lemmas & self._employment_role_lemmas)))
            return EmploymentCue(anchor_char=sentence.span.start_char, detail=detail)
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
    ) -> tuple[SentenceEntity, Signal] | None:
        entities = retriever.entities_for_sentence(sentence)
        local = self._nearest_preceding_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        ) or self._nearest_following_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )
        if local is not None:
            return local, LocalOrganizationSignal()

        inferred = self._infer_public_organization(document, sentence, anchor_char)
        if inferred is not None:
            return inferred, LocalOrganizationSignal()

        # Look both before and after for organizations in nearby sentences.
        # Articles often mention the employing organization before OR after the hiring verb.
        window = retriever.entities_for_sentence_window(sentence, before=3, after=2)
        orgs = tuple(entity for entity in window if entity.kind == EntityKind.ORGANIZATION)
        if orgs:
            # Prefer the closest one by absolute character distance
            anchor = anchor_char
            closest = min(
                orgs,
                key=lambda e: min(abs(e.start_char - anchor), abs(e.end_char - anchor)),
            )
            return closest, WindowOrganizationSignal()
        return None

    def _infer_public_organization(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        anchor_char: int,
    ) -> SentenceEntity | None:
        head_token_id = self._nearest_public_org_head_token(document, sentence, anchor_char)
        if head_token_id is None:
            return None
        head_token = document.store.tokens[head_token_id]
        location_hint = self._nearest_location_hint(document, sentence)
        canonical_hint = head_token.text
        if location_hint is not None and location_hint.casefold() not in canonical_hint.casefold():
            canonical_hint = f"{head_token.text} {location_hint}"
        span = Span(head_token.span.start_char, head_token.span.end_char)
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
                return SentenceEntity(
                    id=candidate_id,
                    kind=EntityKind.ORGANIZATION,
                    start_char=head_token.span.start_char,
                    end_char=head_token.span.end_char,
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
        return SentenceEntity(
            id=entity_id,
            kind=EntityKind.ORGANIZATION,
            start_char=head_token.span.start_char,
            end_char=head_token.span.end_char,
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
            matches.append((abs(token.span.start_char - anchor_char), token_id))
        if not matches:
            return None
        return min(matches, key=lambda item: item[0])[1]

    def _nearest_location_hint(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> str | None:
        location_hints: list[tuple[int, str]] = []
        for candidate in document.store.candidates_by_kind(EntityKind.LOCATION):
            for evidence in document.store.evidence_for_entity(candidate.id):
                if evidence.sentence_id is None:
                    continue
                evidence_sentence = document.store.sentences[evidence.sentence_id]
                distance = abs(evidence_sentence.sentence_index - sentence.sentence_index)
                if distance <= 6 and candidate.canonical_hint is not None:
                    location_hints.append((distance, candidate.canonical_hint))
        if not location_hints:
            return None
        return min(location_hints, key=lambda item: item[0])[1]

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
