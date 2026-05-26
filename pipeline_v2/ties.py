from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, ProducerId
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


@dataclass(frozen=True, slots=True)
class _ComplaintParticipant:
    entity: SentenceEntity
    sentence_distance: int
    preferred_side: EventRole | None = None


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
        "narzeczona": RelationshipDetail.SPOUSE,
        "narzeczony": RelationshipDetail.SPOUSE,
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
            candidate_people = self._candidate_people(entities, document)
            lemmas = self._sentence_lemmas(document, sentence)
            family_detail = self._family_detail(lemmas)
            if family_detail is not None and len(observed_people) >= 2:
                self._add_kinship_tie(
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
                participants = self._complaint_participant_candidates(
                    document=document,
                    sentence=sentence,
                    retriever=retriever,
                )
                self._add_patronage_complaint(
                    document=document,
                    sentence=sentence,
                    participants=participants,
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
        participants: tuple[_ComplaintParticipant, ...],
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
        participant_evidence_ids = self._participant_evidence_ids_for_complaint(
            document=document,
            sentence=sentence,
            participants=participants,
        )
        evidence_ids = tuple(dict.fromkeys((sentence_evidence.id, *participant_evidence_ids)))
        institution_entities = tuple(
            entity for entity in context_entities if entity.kind == EntityKind.ORGANIZATION
        )
        shared_signals: list[Signal] = [ExplicitPatronageLemmaSignal(lemma=complaint_lemma)]
        if institution_entities:
            shared_signals.append(LocalInstitutionSignal())

        self._add_patronage_event(
            document=document,
            kind=FactKind.PATRONAGE_ALLEGATION,
            sentence_evidence_id=sentence_evidence.id,
            evidence_ids=evidence_ids,
            shared_signals=tuple(shared_signals),
            participants=participants,
            primary_left_role=EventRole.COMPLAINANT,
            primary_right_role=EventRole.TARGET,
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
            participants=participants,
            primary_left_role=EventRole.SUBJECT,
            primary_right_role=EventRole.OBJECT,
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
        participants: tuple[_ComplaintParticipant, ...],
        primary_left_role: EventRole,
        primary_right_role: EventRole,
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
        for participant in participants:
            left_signals = self._complaint_role_signals(
                role=primary_left_role,
                participant=participant,
            )
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=primary_left_role,
                    filler=EntityFiller(participant.entity.id),
                    evidence_ids=evidence_ids,
                    signals=left_signals,
                )
            )
        if len(participants) >= 2:
            for participant in participants:
                right_signals = self._complaint_role_signals(
                    role=primary_right_role,
                    participant=participant,
                )
                document.store.add_argument_binding(
                    ArgumentBindingCandidate(
                        id=document.store.next_argument_binding_candidate_id(),
                        event_id=event.id,
                        role=primary_right_role,
                        filler=EntityFiller(participant.entity.id),
                        evidence_ids=evidence_ids,
                        signals=right_signals,
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

    def _candidate_people(
        self,
        entities: tuple[SentenceEntity, ...],
        document: ArticleDocument,
    ) -> tuple[SentenceEntity, ...]:
        return tuple(
            entity
            for entity in entities
            if entity.kind == EntityKind.PERSON
            and document.store.entity_candidates[entity.id].grounding
            in {GroundingKind.OBSERVED, GroundingKind.PROXY}
        )

    def _participant_evidence_ids_for_complaint(
        self,
        *,
        document: ArticleDocument,
        sentence,
        participants: tuple[_ComplaintParticipant, ...],
    ) -> tuple:
        evidence_ids: list = []
        for participant in participants:
            evidence_ids.extend(
                evidence.id
                for evidence in document.store.evidence_for_entity(participant.entity.id)
                if evidence.sentence_id is not None
                and abs(
                    document.store.sentences[evidence.sentence_id].sentence_index
                    - sentence.sentence_index
                )
                <= 1
                and document.store.sentences[evidence.sentence_id].paragraph_index
                == sentence.paragraph_index
            )
        return tuple(dict.fromkeys(evidence_ids))

    def _complaint_participant_candidates(
        self,
        *,
        document: ArticleDocument,
        sentence,
        retriever: SentenceEntityRetriever,
    ) -> tuple[_ComplaintParticipant, ...]:
        sentence_people = self._candidate_people(
            retriever.entities_for_sentence(sentence),
            document,
        )
        merged: dict[EntityCandidateId, _ComplaintParticipant] = {
            entity.id: _ComplaintParticipant(
                entity=entity,
                sentence_distance=0,
                preferred_side=self._preferred_complaint_side(document, sentence, entity),
            )
            for entity in sentence_people
        }
        for entity, distance in self._window_people_for_complaint(
            document=document,
            sentence=sentence,
            retriever=retriever,
        ):
            current = merged.get(entity.id)
            if current is None or distance < current.sentence_distance:
                merged[entity.id] = _ComplaintParticipant(
                    entity=entity,
                    sentence_distance=distance,
                )
        return tuple(
            sorted(
                merged.values(),
                key=lambda item: (
                    item.sentence_distance,
                    abs(item.entity.start_char - sentence.span.start_char),
                    item.entity.start_char,
                ),
            )
        )

    def _complaint_role_signals(
        self,
        *,
        role: EventRole,
        participant: _ComplaintParticipant,
    ) -> tuple[Signal, ...]:
        left_roles = {EventRole.SUBJECT, EventRole.COMPLAINANT}
        role_side = EventRole.SUBJECT if role in left_roles else EventRole.OBJECT
        if participant.sentence_distance <= 0:
            if participant.preferred_side is None or participant.preferred_side is role_side:
                if role_side is EventRole.SUBJECT:
                    return (LocalActorSignal(),)
                return (LocalTargetSignal(),)
            return (WindowFallbackSignal(distance=1),)
        return (WindowFallbackSignal(distance=participant.sentence_distance),)

    def _preferred_complaint_side(
        self,
        document: ArticleDocument,
        sentence,
        entity: SentenceEntity,
    ) -> EventRole | None:
        cue_spans = [
            token.span
            for token_id in sentence.token_ids
            for token in [document.store.tokens[token_id]]
            if any(
                analysis.lemma in {"oskarżyć", "zarzucić", "zarzucać"} for analysis in token.morph
            )
        ]
        if not cue_spans:
            return None
        cue_start = min(span.start_char for span in cue_spans)
        if entity.end_char <= cue_start:
            return EventRole.SUBJECT
        if entity.start_char >= cue_start:
            return EventRole.OBJECT
        return None

    def _window_people_for_complaint(
        self,
        *,
        document: ArticleDocument,
        sentence,
        retriever: SentenceEntityRetriever,
    ) -> tuple[tuple[SentenceEntity, int], ...]:
        window_entities = self._candidate_people(
            retriever.entities_for_sentence_window(sentence, before=1, after=1),
            document,
        )
        by_entity: dict[EntityCandidateId, tuple[SentenceEntity, int]] = {}
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

    def _add_kinship_tie(
        self,
        document: ArticleDocument,
        *,
        subject: SentenceEntity,
        object_entity: SentenceEntity,
        sentence,
        sentence_id,
        relationship_detail: RelationshipDetail,
        signal: Signal,
    ) -> None:
        signals: list[Signal] = [
            signal,
            LocalSubjectSignal(),
            LocalObjectSignal(),
        ]
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
            kind=FactKind.KINSHIP_TIE,
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
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.RELATIONSHIP_DETAIL,
                filler=TextFiller(relationship_detail.value),
                evidence_ids=evidence_ids,
            )
        )
