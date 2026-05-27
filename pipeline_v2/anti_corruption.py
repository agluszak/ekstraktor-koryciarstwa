from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter
from pipeline_v2.ids import EntityCandidateId, EvidenceId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Sentence, Span, Token
from pipeline_v2.retrieval import SentenceEntityRetriever
from pipeline_v2.types import (
    AntiCorruptionInvestigationLemmaSignal,
    AntiCorruptionReferralLemmaSignal,
    EntityKind,
    EventRole,
    FactKind,
    LocalActorSignal,
    LocalInstitutionSignal,
    LocalTargetSignal,
    OversightInstitutionSignal,
    Signal,
)


@dataclass(frozen=True, slots=True)
class InstitutionMatch:
    text: str
    span: Span
    canonical_name: str
    index: int


class AntiCorruptionCandidateStage:
    producer_id = ProducerId("anti_corruption_candidate_stage_v2")

    _referral_lemmas = frozenset(
        {
            "doniesienie",
            "skarga",
            "skierować",
            "wniosek",
            "zawiadomić",
            "zawiadomienie",
            "zgłosić",
            "zgłoszenie",
        }
    )
    _investigation_lemmas = frozenset(
        {
            "audyt",
            "badać",
            "dochodzenie",
            "kontrola",
            "postępowanie",
            "śledztwo",
            "wszcząć",
            "zatrzymać",
        }
    )
    _control_request_lemmas = frozenset(
        {
            "chcieć",
            "domagać",
            "oczekiwać",
            "wnioskować",
            "zażądać",
            "żądać",
        }
    )
    _reporting_lemmas = frozenset(
        {
            "informować",
            "ogłosić",
            "opublikować",
            "podać",
            "poinformować",
            "przedstawić",
        }
    )
    _institution_canonical_names = {
        "cba": "CBA",
        "nik": "NIK",
        "prokurator": "prokuratura",
        "prokuratura": "prokuratura",
        "uokik": "UOKiK",
    }
    _context_pattern = re.compile(r"\bw sprawie\b.+?(?:[.;]|$)", re.IGNORECASE)

    def name(self) -> str:
        return "anti_corruption_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        retriever = SentenceEntityRetriever(document.store)
        for sentence in document.store.sentences.values():
            lemmas = self._sentence_lemmas(document, sentence)
            matched_referral_lemmas = tuple(sorted(lemmas & self._referral_lemmas))
            matched_investigation_lemmas = tuple(sorted(lemmas & self._investigation_lemmas))
            matched_control_request_lemmas = tuple(sorted(lemmas & self._control_request_lemmas))
            if (
                not matched_referral_lemmas
                and not matched_investigation_lemmas
                and not matched_control_request_lemmas
            ):
                continue
            institutions = self._institution_matches(document, sentence)
            if not institutions and not (
                matched_investigation_lemmas and matched_control_request_lemmas
            ):
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
            emitter = DomainEventEmitter(document, self.producer_id)
            entities = retriever.entities_for_sentence(sentence)
            context_text = self._context_text(sentence)
            referral_emitted = False
            if matched_referral_lemmas:
                for institution in institutions:
                    referral_emitted = True
                    institution_id = self._institution_entity_id(document, sentence, institution)

                    actors = tuple(
                        entity
                        for entity in entities
                        if entity.kind
                        in {EntityKind.POLITICAL_PARTY, EntityKind.PERSON, EntityKind.ORGANIZATION}
                        and entity.id != institution_id
                    )
                    targets = tuple(
                        entity
                        for entity in entities
                        if entity.kind in {EntityKind.PERSON, EntityKind.ORGANIZATION}
                        and entity.id != institution_id
                    )
                    signals: list[Signal] = [
                        AntiCorruptionReferralLemmaSignal(
                            lemma=matched_referral_lemmas[0],
                        ),
                        OversightInstitutionSignal(),
                    ]
                    if actors:
                        signals.append(LocalActorSignal())
                    if targets:
                        signals.append(LocalTargetSignal())
                    if institution_id is not None:
                        signals.append(LocalInstitutionSignal())
                    event = emitter.event(
                        kind=FactKind.ANTI_CORRUPTION_REFERRAL,
                        trigger_evidence_id=evidence.id,
                        evidence_ids=(evidence.id,),
                        signals=tuple(signals),
                    )
                    for actor in actors:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.COMPLAINANT,
                            entity_id=actor.id,
                            evidence_ids=(evidence.id,),
                            signals=(LocalActorSignal(),),
                        )
                    for target in targets:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.TARGET,
                            entity_id=target.id,
                            evidence_ids=(evidence.id,),
                            signals=(LocalTargetSignal(),),
                        )
                    if institution_id is not None:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.INSTITUTION,
                            entity_id=institution_id,
                            evidence_ids=(evidence.id,),
                            signals=(LocalInstitutionSignal(),),
                        )
                    elif institution.text:
                        emitter.bind_text(
                            event=event,
                            role=EventRole.INSTITUTION,
                            value=institution.text,
                            evidence_ids=(evidence.id,),
                        )
                    if context_text is not None:
                        emitter.bind_text(
                            event=event,
                            role=EventRole.CONTEXT,
                            value=context_text,
                            evidence_ids=(evidence.id,),
                        )
            if (
                (matched_investigation_lemmas or matched_control_request_lemmas)
                and not referral_emitted
                and not self._has_reporting_lemma(lemmas)
            ):
                investigation_institutions = institutions or (
                    InstitutionMatch(
                        text="",
                        span=sentence.span,
                        canonical_name="",
                        index=0,
                    ),
                )
                for institution in investigation_institutions:
                    institution_id = (
                        self._institution_entity_id(document, sentence, institution)
                        if institution.text
                        else None
                    )
                    targets = tuple(
                        entity
                        for entity in entities
                        if entity.kind in {EntityKind.PERSON, EntityKind.ORGANIZATION}
                        and entity.id != institution_id
                    )
                    if not targets and institution_id is None:
                        continue
                    signals = [
                        AntiCorruptionInvestigationLemmaSignal(
                            lemma=(
                                matched_investigation_lemmas[0]
                                if matched_investigation_lemmas
                                else matched_control_request_lemmas[0]
                            ),
                        ),
                    ]
                    if institution.text:
                        signals.append(OversightInstitutionSignal())
                    if targets:
                        signals.append(LocalTargetSignal())
                    if institution_id is not None:
                        signals.append(LocalInstitutionSignal())
                    event = emitter.event(
                        kind=FactKind.ANTI_CORRUPTION_INVESTIGATION,
                        trigger_evidence_id=evidence.id,
                        evidence_ids=(evidence.id,),
                        signals=tuple(signals),
                    )
                    for target in targets:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.TARGET,
                            entity_id=target.id,
                            evidence_ids=(evidence.id,),
                            signals=(LocalTargetSignal(),),
                        )
                    if institution_id is not None:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.INSTITUTION,
                            entity_id=institution_id,
                            evidence_ids=(evidence.id,),
                            signals=(LocalInstitutionSignal(),),
                        )
                    elif institution.text:
                        emitter.bind_text(
                            event=event,
                            role=EventRole.INSTITUTION,
                            value=institution.text,
                            evidence_ids=(evidence.id,),
                        )
                    if context_text is not None:
                        emitter.bind_text(
                            event=event,
                            role=EventRole.CONTEXT,
                            value=context_text,
                            evidence_ids=(evidence.id,),
                        )
        return document

    def _sentence_lemmas(self, document: ArticleDocument, sentence: Sentence) -> frozenset[str]:
        lemmas: set[str] = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _institution_matches(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[InstitutionMatch, ...]:
        matches: list[InstitutionMatch] = []
        token_ids = sentence.token_ids
        for token_index, token_id in enumerate(token_ids):
            token = document.store.tokens[token_id]
            canonical_name = self._canonical_institution_name(token)
            if canonical_name is None:
                continue
            matches.append(
                InstitutionMatch(
                    text=document.cleaned_text[token.span.start_char : token.span.end_char],
                    span=token.span,
                    canonical_name=canonical_name,
                    index=token_index,
                )
            )
        deduplicated = {
            (match.span.start_char, match.span.end_char, match.canonical_name): match
            for match in matches
        }
        return tuple(deduplicated.values())

    def _canonical_institution_name(self, token: Token) -> str | None:
        text = token.text.casefold()
        if text in self._institution_canonical_names:
            return self._institution_canonical_names[text]
        for analysis in token.morph:
            canonical_name = self._institution_canonical_names.get(analysis.lemma)
            if canonical_name is not None:
                return canonical_name
        return None

    def _has_referral_preposition(
        self,
        document: ArticleDocument,
        token_ids: tuple[TokenId, ...],
        institution_index: int,
    ) -> bool:
        start = max(0, institution_index - 3)
        for previous_index in range(start, institution_index):
            token = document.store.tokens[token_ids[previous_index]]
            if token.text.casefold() == "do":
                return True
        return False

    def _has_reporting_lemma(self, lemmas: frozenset[str]) -> bool:
        return bool(lemmas & self._reporting_lemmas)

    def _institution_entity_id(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        institution: InstitutionMatch,
    ) -> EntityCandidateId | None:
        probe = EvidenceSpan(
            id=EvidenceId("probe"),
            text=institution.text,
            span=institution.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        candidate_ids = document.store.candidate_ids_with_evidence_overlapping_span(probe)
        for candidate_id in candidate_ids:
            candidate = document.store.entity_candidates[candidate_id]
            if candidate.kind == EntityKind.ORGANIZATION:
                return candidate_id
        return None

    def _context_text(self, sentence: Sentence) -> str | None:
        match = self._context_pattern.search(sentence.text)
        if match is None:
            return None
        return match.group(0).strip(" .,;:")
