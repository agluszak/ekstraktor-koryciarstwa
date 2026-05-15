from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline_v2.candidates import (
    AntiCorruptionInvestigationCandidate,
    AntiCorruptionReferralCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, FactCandidateId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, Sentence, Span, Token
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import EntityKind, Signal, positive_signal


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
            if not matched_referral_lemmas and not matched_investigation_lemmas:
                continue
            institutions = self._institution_matches(document, sentence)
            if not institutions:
                continue
            evidence = EvidenceSpan(
                id=EvidenceId(f"evidence-{len(document.store.evidence)}"),
                text=sentence.text,
                span=sentence.span,
                sentence_id=sentence.id,
                paragraph_index=sentence.paragraph_index,
                source=self.name(),
            )
            document.store.add_evidence(evidence)
            entities = retriever.entities_for_sentence(sentence)
            context_text = self._context_text(sentence)
            referral_emitted = False
            if matched_referral_lemmas:
                for institution in institutions:
                    if not self._has_referral_preposition(
                        document,
                        sentence.token_ids,
                        institution.index,
                    ):
                        continue
                    referral_emitted = True
                    actor, target = self._select_actor_and_target(entities, institution)
                    institution_id = self._institution_entity_id(document, sentence, institution)
                    signals: list[Signal] = [
                        positive_signal(
                            "anti_corruption_referral_lemma",
                            details=matched_referral_lemmas[0],
                        ),
                        positive_signal(
                            "oversight_institution",
                            details=institution.canonical_name,
                        ),
                    ]
                    if actor is not None:
                        signals.append(positive_signal("sentence_local_actor"))
                    if target is not None:
                        signals.append(positive_signal("sentence_local_target"))
                    if institution_id is not None:
                        signals.append(positive_signal("sentence_local_institution"))
                    document.store.add_fact_candidate(
                        AntiCorruptionReferralCandidate(
                            id=FactCandidateId(f"fact-{len(document.store.fact_candidates)}"),
                            actor_entity_id=actor.id if actor is not None else None,
                            target_entity_id=target.id if target is not None else None,
                            institution_entity_id=institution_id,
                            institution_text=(
                                None if institution_id is not None else institution.text
                            ),
                            context_text=context_text,
                            evidence_ids=(evidence.id,),
                            source=self.producer_id,
                            signals=tuple(signals),
                        )
                    )
            if (
                matched_investigation_lemmas
                and not referral_emitted
                and not self._has_reporting_lemma(lemmas)
            ):
                for institution in institutions:
                    institution_id = self._institution_entity_id(document, sentence, institution)
                    target = self._select_investigation_target(
                        entities,
                        institution,
                        institution_id,
                    )
                    signals = [
                        positive_signal(
                            "anti_corruption_investigation_lemma",
                            details=matched_investigation_lemmas[0],
                        ),
                        positive_signal(
                            "oversight_institution",
                            details=institution.canonical_name,
                        ),
                    ]
                    if target is not None:
                        signals.append(positive_signal("sentence_local_target"))
                    if institution_id is not None:
                        signals.append(positive_signal("sentence_local_institution"))
                    document.store.add_fact_candidate(
                        AntiCorruptionInvestigationCandidate(
                            id=FactCandidateId(f"fact-{len(document.store.fact_candidates)}"),
                            target_entity_id=target.id if target is not None else None,
                            institution_entity_id=institution_id,
                            institution_text=(
                                None if institution_id is not None else institution.text
                            ),
                            context_text=context_text,
                            evidence_ids=(evidence.id,),
                            source=self.producer_id,
                            signals=tuple(signals),
                        )
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

    def _select_actor_and_target(
        self,
        entities: tuple[SentenceEntity, ...],
        institution: InstitutionMatch,
    ) -> tuple[SentenceEntity | None, SentenceEntity | None]:
        actor = self._nearest_preceding_entity(
            entities,
            institution.span.start_char,
            kinds=frozenset({EntityKind.PERSON, EntityKind.ORGANIZATION}),
        )
        if actor is None:
            actor = self._nearest_preceding_entity(
                entities,
                institution.span.start_char,
                kinds=frozenset({EntityKind.POLITICAL_PARTY}),
            )
        target = self._nearest_following_entity(
            entities,
            institution.span.end_char,
            kinds=frozenset({EntityKind.PERSON, EntityKind.ORGANIZATION}),
        )
        if actor is not None and target is not None and actor.id == target.id:
            return actor, None
        return actor, target

    def _select_investigation_target(
        self,
        entities: tuple[SentenceEntity, ...],
        institution: InstitutionMatch,
        institution_id: EntityCandidateId | None,
    ) -> SentenceEntity | None:
        candidates = [
            entity
            for entity in entities
            if entity.kind in {EntityKind.PERSON, EntityKind.ORGANIZATION}
            and entity.id != institution_id
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda entity: abs(entity.start_char - institution.span.start_char),
        )

    def _nearest_preceding_entity(
        self,
        entities: tuple[SentenceEntity, ...],
        boundary: int,
        *,
        kinds: frozenset[EntityKind],
    ) -> SentenceEntity | None:
        for entity in reversed(entities):
            if entity.kind in kinds and entity.start_char < boundary:
                return entity
        return None

    def _nearest_following_entity(
        self,
        entities: tuple[SentenceEntity, ...],
        boundary: int,
        *,
        kinds: frozenset[EntityKind],
    ) -> SentenceEntity | None:
        for entity in entities:
            if entity.kind in kinds and entity.start_char >= boundary:
                return entity
        return None

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
            source=self.name(),
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
