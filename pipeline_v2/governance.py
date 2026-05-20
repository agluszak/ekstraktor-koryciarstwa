from __future__ import annotations

from pipeline_v2.candidates import GovernanceFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, FactCandidateId, ProducerId
from pipeline_v2.nlp import EvidenceSpan, Sentence
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import (
    AppointmentLemmaSignal,
    DismissalLemmaSignal,
    EntityKind,
    FactKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    Signal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


class GovernanceCandidateStage:
    producer_id = ProducerId("governance_candidate_stage_v2")

    _appointment_lemmas = frozenset(
        {
            "powołać",
            "mianować",
            "zatrudnić",
            "objąć",
            "wybrać",
            "awansować",
        }
    )
    _dismissal_lemmas = frozenset(
        {
            "odwołać",
            "zwolnić",
            "usunąć",
            "zdymisjonować",
            "stracić",
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

    def name(self) -> str:
        return "governance_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            kinds = self._candidate_kinds(document, sentence)
            if not kinds:
                continue
            person_id, organization_id, role_id, entity_signals = self._select_parties(
                document,
                sentence,
            )
            if person_id is None:
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
            for kind, signals in kinds:
                if (
                    kind == FactKind.GOVERNANCE_APPOINTMENT
                    and self._is_employment_overlap(signals)
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
        if lemmas & self._dismissal_lemmas:
            candidates.append(
                (
                    FactKind.GOVERNANCE_DISMISSAL,
                    (
                        DismissalLemmaSignal(
                            lemma=self._matched_detail(lemmas, self._dismissal_lemmas),
                        ),
                    ),
                )
            )
        return tuple(candidates)

    def _select_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[
        EntityCandidateId | None,
        EntityCandidateId | None,
        EntityCandidateId | None,
        tuple[Signal, ...],
    ]:
        retriever = SentenceEntityRetriever(document.store)
        entities = retriever.entities_for_sentence(sentence)
        person, person_signal = self._select_entity(
            entities,
            retriever.entities_for_sentence_window(sentence, before=1, after=0),
            EntityKind.PERSON,
            local_signal=LocalPersonSignal(),
            window_signal=WindowPersonSignal(),
        )
        organization, organization_signal = self._select_entity(
            entities,
            retriever.entities_for_sentence_window(sentence, before=1, after=1),
            EntityKind.ORGANIZATION,
            local_signal=LocalOrganizationSignal(),
            window_signal=WindowOrganizationSignal(),
        )
        role, role_signal = self._select_entity(
            entities,
            retriever.entities_for_sentence_window(sentence, before=1, after=1),
            EntityKind.ROLE,
            local_signal=LocalRoleSignal(),
            window_signal=WindowRoleSignal(),
        )
        person_id = person.id if person is not None else None
        organization_id = organization.id if organization is not None else None
        role_id = role.id if role is not None else None
        signals: list[Signal] = []
        for signal in (person_signal, organization_signal, role_signal):
            if signal is not None:
                signals.append(signal)
        return person_id, organization_id, role_id, tuple(signals)

    def _select_entity(
        self,
        local_entities: tuple[SentenceEntity, ...],
        window_entities: tuple[SentenceEntity, ...],
        kind: EntityKind,
        *,
        local_signal: Signal,
        window_signal: Signal,
    ) -> tuple[SentenceEntity | None, Signal | None]:
        local = tuple(entity for entity in local_entities if entity.kind == kind)
        if local:
            return local[0], local_signal
        window = tuple(entity for entity in window_entities if entity.kind == kind)
        if window:
            return window[0], window_signal
        return None, None

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
