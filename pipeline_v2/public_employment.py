from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import PublicEmploymentFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, FactCandidateId, ProducerId
from pipeline_v2.nlp import EvidenceSpan, Sentence
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import (
    EmploymentContractFormSignal,
    EntityKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    PublicEmploymentLemmaSignal,
    Signal,
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
            person = self._select_person(entities, cue.anchor_char)
            organization = self._select_organization(entities, cue.anchor_char)
            if person is None or organization is None:
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
            signals: list[Signal] = [
                PublicEmploymentLemmaSignal(lemma=cue.detail),
                LocalPersonSignal(),
                LocalOrganizationSignal(),
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
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
    ) -> SentenceEntity | None:
        return self._nearest_following_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.PERSON}),
        ) or self._nearest_preceding_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.PERSON}),
        )

    def _select_organization(
        self,
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
    ) -> SentenceEntity | None:
        return self._nearest_preceding_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        ) or self._nearest_following_entity(
            entities,
            anchor_char,
            kinds=frozenset({EntityKind.ORGANIZATION}),
        )

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
