from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import ProducerId
from pipeline_v2.nlp import EvidenceSpan
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import (
    EntityKind,
    EventRole,
    ExplicitPatronageLemmaSignal,
    FactKind,
    GroundingKind,
    LocalActorSignal,
    LocalInstitutionSignal,
    LocalObjectSignal,
    LocalSubjectSignal,
    LocalTargetSignal,
    NamedKinshipLemmaSignal,
    PseudonymousSourceSignal,
    RelationshipDetail,
    Signal,
    WindowFallbackSignal,
)


class PersonalTieCandidateStage:
    producer_id = ProducerId("personal_tie_candidate_stage_v2")

    _family_details_by_lemma = {
        "brat": RelationshipDetail.SIBLING,
        "córka": RelationshipDetail.CHILD,
        "dziewczyna": RelationshipDetail.SPOUSE,
        "kuzyn": RelationshipDetail.FAMILY,
        "kuzynka": RelationshipDetail.FAMILY,
        "matka": RelationshipDetail.PARENT,
        "mąż": RelationshipDetail.SPOUSE,
        "ojciec": RelationshipDetail.PARENT,
        "partner": RelationshipDetail.SPOUSE,
        "partnerka": RelationshipDetail.SPOUSE,
        "siostra": RelationshipDetail.SIBLING,
        "syn": RelationshipDetail.CHILD,
        "teść": RelationshipDetail.FAMILY,
        "teściowa": RelationshipDetail.FAMILY,
        "żona": RelationshipDetail.SPOUSE,
    }
    _patronage_lemmas = frozenset(
        {
            "baron",
            "człowiek",
            "kolesiostwo",
            "konkurs",
            "polecenie",
            "posada",
            "rozdawać",
            "powiązać",
            "rekomendacja",
            "układ",
            "współpracownik",
            "znajomy",
            "związany",
        }
    )
    _patronage_preference = (
        "znajomy",
        "współpracownik",
        "rekomendacja",
        "związany",
        "powiązać",
        "polecenie",
        "człowiek",
        "baron",
        "układ",
        "kolesiostwo",
        "konkurs",
        "rozdawać",
        "posada",
    )
    _complaint_lemmas = frozenset(
        {
            "baron",
            "konkurs",
            "kolesiostwo",
            "posada",
            "przyjaciel",
            "rozdawać",
            "układ",
            "znajomy",
        }
    )

    def name(self) -> str:
        return "personal_tie_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        retriever = SentenceEntityRetriever(document.store)
        for sentence in document.store.sentences.values():
            entities = retriever.entities_for_sentence(sentence)
            observed_people = self._observed_people(entities, document)
            candidate_people = self._candidate_people(entities)
            lemmas = self._sentence_lemmas(document, sentence)
            family_detail = self._family_detail(lemmas)
            if family_detail is not None and len(observed_people) >= 2:
                self._add_explicit_tie(
                    document,
                    subject=observed_people[0],
                    object_entity=observed_people[1],
                    sentence=sentence,
                    sentence_id=sentence.id,
                    relationship_detail=family_detail,
                    signal=NamedKinshipLemmaSignal(lemma=family_detail.value),
                )
                continue
            patronage_lemma = self._patronage_detail(lemmas)
            if patronage_lemma is not None and len(candidate_people) >= 2:
                self._add_explicit_tie(
                    document,
                    subject=candidate_people[0],
                    object_entity=candidate_people[1],
                    sentence=sentence,
                    sentence_id=sentence.id,
                    relationship_detail=None,
                    signal=ExplicitPatronageLemmaSignal(lemma=patronage_lemma),
                    context_text=patronage_lemma,
                )
            complaint_lemma = self._patronage_complaint_detail(lemmas)
            if complaint_lemma is not None:
                actor, actor_signals, target, target_signals = self._select_complaint_participants(
                    document=document,
                    sentence=sentence,
                    retriever=retriever,
                )
                self._add_patronage_complaint(
                    document=document,
                    sentence=sentence,
                    actor=actor,
                    actor_signals=actor_signals,
                    target=target,
                    target_signals=target_signals,
                    context_entities=tuple(
                        entity for entity in entities if entity.kind != EntityKind.PERSON
                    ),
                    complaint_lemma=complaint_lemma,
                )
        return document

    def _add_explicit_tie(
        self,
        document: ArticleDocument,
        *,
        subject: SentenceEntity,
        object_entity: SentenceEntity,
        sentence,
        sentence_id,
        relationship_detail: RelationshipDetail | None,
        signal: Signal,
        context_text: str | None = None,
    ) -> None:
        signals: list[Signal] = [
            signal,
            LocalSubjectSignal(),
            LocalObjectSignal(),
        ]
        pseudonymous_signal = self._pseudonymous_source_signal(document, sentence, subject)
        if pseudonymous_signal is not None:
            signals.append(pseudonymous_signal)
        evidence_ids = tuple(
            evidence.id
            for evidence in document.store.evidence_for_entity(subject.id)
            if evidence.sentence_id == sentence_id
        ) or tuple(
            evidence.id
            for evidence in document.store.evidence_for_entity(object_entity.id)
            if evidence.sentence_id == sentence_id
        )
        event = EventCandidate(
            id=document.store.next_event_candidate_id(),
            kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
            trigger_evidence_id=evidence_ids[0] if evidence_ids else None,
            evidence_ids=evidence_ids,
            source=self.producer_id,
            signals=tuple(signals),
        )
        document.store.add_event_candidate(event)
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.SUBJECT,
                filler=EntityFiller(subject.id),
                evidence_ids=evidence_ids,
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.OBJECT,
                filler=EntityFiller(object_entity.id),
                evidence_ids=evidence_ids,
            )
        )
        if relationship_detail is not None:
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.RELATIONSHIP_DETAIL,
                    filler=TextFiller(relationship_detail.value),
                    evidence_ids=evidence_ids,
                )
            )
        if context_text is not None:
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.CONTEXT,
                    filler=TextFiller(context_text),
                    evidence_ids=evidence_ids,
                )
            )

    def _add_patronage_complaint(
        self,
        *,
        document: ArticleDocument,
        sentence,
        actor: SentenceEntity | None,
        actor_signals: tuple[Signal, ...],
        target: SentenceEntity | None,
        target_signals: tuple[Signal, ...],
        context_entities: tuple[SentenceEntity, ...],
        complaint_lemma: str,
    ) -> None:
        sentence_evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=sentence.text,
            span=sentence.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(sentence_evidence)
        participant_evidence_ids = self._participant_evidence_ids_for_sentence(
            document=document,
            sentence_id=sentence.id,
            actor=actor,
            target=target,
        )
        evidence_ids = tuple(dict.fromkeys((sentence_evidence.id, *participant_evidence_ids)))
        institution_entities = tuple(
            entity for entity in context_entities if entity.kind == EntityKind.ORGANIZATION
        )
        shared_signals: list[Signal] = [ExplicitPatronageLemmaSignal(lemma=complaint_lemma)]
        shared_signals.extend(actor_signals)
        shared_signals.extend(target_signals)
        if institution_entities:
            shared_signals.append(LocalInstitutionSignal())

        self._add_patronage_event(
            document=document,
            kind=FactKind.PATRONAGE_ALLEGATION,
            sentence_evidence_id=sentence_evidence.id,
            evidence_ids=evidence_ids,
            shared_signals=tuple(shared_signals),
            primary_left=actor,
            primary_left_role=EventRole.COMPLAINANT,
            primary_left_signals=actor_signals,
            primary_right=target,
            primary_right_role=EventRole.TARGET,
            primary_right_signals=target_signals,
            context_entities=context_entities,
            institution_entities=institution_entities,
            complaint_lemma=complaint_lemma,
        )
        self._add_patronage_event(
            document=document,
            kind=FactKind.PATRONAGE_NETWORK_TIE,
            sentence_evidence_id=sentence_evidence.id,
            evidence_ids=evidence_ids,
            shared_signals=tuple(shared_signals),
            primary_left=actor,
            primary_left_role=EventRole.SUBJECT,
            primary_left_signals=actor_signals,
            primary_right=target,
            primary_right_role=EventRole.OBJECT,
            primary_right_signals=target_signals,
            context_entities=context_entities,
            institution_entities=institution_entities,
            complaint_lemma=complaint_lemma,
        )

    def _add_patronage_event(
        self,
        *,
        document: ArticleDocument,
        kind: FactKind,
        sentence_evidence_id,
        evidence_ids: tuple,
        shared_signals: tuple[Signal, ...],
        primary_left: SentenceEntity | None,
        primary_left_role: EventRole,
        primary_left_signals: tuple[Signal, ...],
        primary_right: SentenceEntity | None,
        primary_right_role: EventRole,
        primary_right_signals: tuple[Signal, ...],
        context_entities: tuple[SentenceEntity, ...],
        institution_entities: tuple[SentenceEntity, ...],
        complaint_lemma: str,
    ) -> None:
        event = EventCandidate(
            id=document.store.next_event_candidate_id(),
            kind=kind,
            trigger_evidence_id=sentence_evidence_id,
            evidence_ids=evidence_ids,
            source=self.producer_id,
            signals=shared_signals,
        )
        document.store.add_event_candidate(event)
        if primary_left is not None:
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=primary_left_role,
                    filler=EntityFiller(primary_left.id),
                    evidence_ids=evidence_ids,
                    signals=primary_left_signals,
                )
            )
        if primary_right is not None:
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=primary_right_role,
                    filler=EntityFiller(primary_right.id),
                    evidence_ids=evidence_ids,
                    signals=primary_right_signals,
                )
            )
        for institution in institution_entities:
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.INSTITUTION,
                    filler=EntityFiller(institution.id),
                    evidence_ids=evidence_ids,
                    signals=(LocalInstitutionSignal(),),
                )
            )
        for context_entity in context_entities:
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.CONTEXT,
                    filler=EntityFiller(context_entity.id),
                    evidence_ids=evidence_ids,
                )
            )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.CONTEXT,
                filler=TextFiller(complaint_lemma),
                evidence_ids=evidence_ids,
            )
        )

    def _pseudonymous_source_signal(
        self,
        document: ArticleDocument,
        sentence,
        subject: SentenceEntity,
    ) -> PseudonymousSourceSignal | None:
        lemmas = self._sentence_lemmas(document, sentence)
        if not (lemmas & {"osoba", "podpisać", "podpisany"}):
            return None
        subject_evidence = document.store.evidence_for_entity(subject.id)
        if not any(evidence.sentence_id == sentence.id for evidence in subject_evidence):
            return None
        if "podpis" not in sentence.text.casefold():
            return None
        return PseudonymousSourceSignal(cue_lemma="podpisać")

    def _observed_people(
        self,
        entities: tuple[SentenceEntity, ...],
        document: ArticleDocument,
    ) -> tuple[SentenceEntity, ...]:
        return tuple(
            entity
            for entity in entities
            if entity.kind == EntityKind.PERSON
            and document.store.entity_candidates[entity.id].grounding is GroundingKind.OBSERVED
        )

    def _candidate_people(self, entities: tuple[SentenceEntity, ...]) -> tuple[SentenceEntity, ...]:
        return tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)

    def _participant_evidence_ids_for_sentence(
        self,
        *,
        document: ArticleDocument,
        sentence_id,
        actor: SentenceEntity | None,
        target: SentenceEntity | None,
    ) -> tuple:
        evidence_ids: list = []
        for participant in tuple(entity for entity in (actor, target) if entity is not None):
            evidence_ids.extend(
                evidence.id
                for evidence in document.store.evidence_for_entity(participant.id)
                if evidence.sentence_id == sentence_id
            )
        return tuple(dict.fromkeys(evidence_ids))

    def _select_complaint_participants(
        self,
        *,
        document: ArticleDocument,
        sentence,
        retriever: SentenceEntityRetriever,
    ) -> tuple[
        SentenceEntity | None,
        tuple[Signal, ...],
        SentenceEntity | None,
        tuple[Signal, ...],
    ]:
        sentence_people = self._candidate_people(retriever.entities_for_sentence(sentence))
        if len(sentence_people) >= 2:
            return (
                sentence_people[0],
                (LocalActorSignal(),),
                sentence_people[1],
                (LocalTargetSignal(),),
            )

        window_people = self._window_people_for_complaint(
            document=document,
            sentence=sentence,
            retriever=retriever,
        )
        if len(sentence_people) == 1:
            local_actor = sentence_people[0]
            fallback_target = next(
                (entity for entity, _distance in window_people if entity.id != local_actor.id),
                None,
            )
            if fallback_target is None:
                return local_actor, (LocalActorSignal(),), None, ()
            fallback_distance = self._minimum_sentence_distance(
                document=document,
                sentence=sentence,
                entity=fallback_target,
            )
            if fallback_distance is None:
                return local_actor, (LocalActorSignal(),), fallback_target, ()
            return (
                local_actor,
                (LocalActorSignal(),),
                fallback_target,
                (WindowFallbackSignal(distance=fallback_distance),),
            )

        if len(window_people) >= 2:
            actor, actor_distance = window_people[0]
            target, target_distance = window_people[1]
            return (
                actor,
                (WindowFallbackSignal(distance=actor_distance),),
                target,
                (WindowFallbackSignal(distance=target_distance),),
            )
        if len(window_people) == 1:
            actor, actor_distance = window_people[0]
            return actor, (WindowFallbackSignal(distance=actor_distance),), None, ()
        return None, (), None, ()

    def _window_people_for_complaint(
        self,
        *,
        document: ArticleDocument,
        sentence,
        retriever: SentenceEntityRetriever,
    ) -> tuple[tuple[SentenceEntity, int], ...]:
        window_entities = self._candidate_people(
            retriever.entities_for_sentence_window(sentence, before=1, after=1)
        )
        by_entity: dict = {}
        for entity in window_entities:
            distance = self._minimum_sentence_distance(
                document=document,
                sentence=sentence,
                entity=entity,
            )
            if distance is None or distance > 1:
                continue
            if not self._entity_in_paragraph(
                document=document,
                entity=entity,
                paragraph_index=sentence.paragraph_index,
            ):
                continue
            existing = by_entity.get(entity.id)
            if existing is None or distance < existing[1]:
                by_entity[entity.id] = (entity, distance)
        return tuple(
            sorted(
                by_entity.values(),
                key=lambda item: (
                    item[1],
                    abs(item[0].start_char - sentence.span.start_char),
                    item[0].start_char,
                ),
            )
        )

    def _minimum_sentence_distance(
        self,
        *,
        document: ArticleDocument,
        sentence,
        entity: SentenceEntity,
    ) -> int | None:
        anchor_index = sentence.sentence_index
        distances = [
            abs(document.store.sentences[evidence.sentence_id].sentence_index - anchor_index)
            for evidence in document.store.evidence_for_entity(entity.id)
            if evidence.sentence_id is not None
            and document.store.sentences[evidence.sentence_id].paragraph_index
            == sentence.paragraph_index
        ]
        if not distances:
            return None
        return min(distances)

    def _entity_in_paragraph(
        self,
        *,
        document: ArticleDocument,
        entity: SentenceEntity,
        paragraph_index: int,
    ) -> bool:
        return any(
            evidence.sentence_id is not None
            and document.store.sentences[evidence.sentence_id].paragraph_index == paragraph_index
            for evidence in document.store.evidence_for_entity(entity.id)
        )

    def _sentence_lemmas(self, document: ArticleDocument, sentence) -> frozenset[str]:
        lemmas: set[str] = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _family_detail(self, lemmas: frozenset[str]) -> RelationshipDetail | None:
        for lemma, relationship_detail in self._family_details_by_lemma.items():
            if lemma in lemmas:
                return relationship_detail
        return None

    def _patronage_detail(self, lemmas: frozenset[str]) -> str | None:
        matched = tuple(lemma for lemma in self._patronage_preference if lemma in lemmas)
        if not matched:
            return None
        return matched[0]

    def _patronage_complaint_detail(self, lemmas: frozenset[str]) -> str | None:
        matched = tuple(sorted(lemmas & self._complaint_lemmas))
        if not matched:
            return None
        return matched[0]
