from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import spacy
from spacy.language import Language

from pipeline_v2.candidates import EntityCandidate, FullPersonNameKey
from pipeline_v2.catalogues import is_organization_descriptor_lemma, is_role_title_lemma
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    MentionId,
    ProducerId,
    SentenceId,
    TokenId,
)
from pipeline_v2.media import is_media_outlet_name
from pipeline_v2.nlp import EvidenceSpan, MentionFactory, MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.types import EntityKind, GroundingKind, MentionKind, NerLabel


class NamedEntityProvider(Protocol):
    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]: ...


class SpacyNamedEntityProvider:
    def __init__(self, model_name: str = "pl_core_news_lg") -> None:
        self._nlp: Language = spacy.load(model_name)

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        doc = self._nlp(text)
        entities: list[NamedEntitySpan] = []
        for entity in doc.ents:
            label = spacy_label_to_ner_label(entity.label_)
            if label is None:
                continue
            entities.append(
                NamedEntitySpan(
                    text=entity.text,
                    label=label,
                    span=Span(start_char=entity.start_char, end_char=entity.end_char),
                )
            )
        return tuple(entities)


@dataclass(frozen=True, slots=True)
class EntityCandidateProducerConfig:
    producer_id: ProducerId = ProducerId("named_entity_candidate_producer_v2")


class NamedEntityCandidateStage:
    def __init__(
        self,
        *,
        provider: NamedEntityProvider,
        morphology: MorphologyAdapter,
        config: EntityCandidateProducerConfig = EntityCandidateProducerConfig(),
    ) -> None:
        self.provider = provider
        self.mention_factory = MentionFactory(morphology)
        self.config = config

    def name(self) -> str:
        return "named_entity_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for entity_span in self.provider.find_entities(document.cleaned_text):
            sentence_id = document.store.sentence_id_for_offset(entity_span.span.start_char)
            if sentence_id is None:
                continue
            evidence_id = document.store.next_evidence_id()
            sentence = document.store.sentences[sentence_id]
            evidence = EvidenceSpan(
                id=evidence_id,
                text=entity_span.text,
                span=entity_span.span,
                sentence_id=sentence_id,
                paragraph_index=sentence.paragraph_index,
                source=self.config.producer_id,
            )
            entity_kind = ner_label_to_entity_kind(entity_span.label)
            token_ids = document.store.token_ids_for_span(
                sentence_id=sentence_id,
                span=evidence,
            )

            role_token_ids = []
            if entity_kind == EntityKind.PERSON and token_ids:
                first_token = document.store.tokens.get(token_ids[0])
                first_token_lemma = None
                if first_token is not None:
                    first_token_lemma = first_token.preferred_lemma() or first_token.text.lower()
                if first_token is not None and is_role_title_lemma(first_token_lemma):
                    if len(token_ids) == 1:
                        entity_kind = EntityKind.ROLE
                    else:
                        role_token_ids = [token_ids[0]]
                        token_ids = token_ids[1:]
                elif len(token_ids) == 1 and self._has_preceding_org_descriptor(
                    document,
                    sentence_id,
                    token_ids[0],
                ):
                    entity_kind = EntityKind.ORGANIZATION
                elif len(token_ids) == 1 and is_media_outlet_name(entity_span.text):
                    entity_kind = EntityKind.ORGANIZATION

            if role_token_ids:
                # Add a separate ROLE entity and mention for the stripped title
                role_evidence_id = document.store.next_evidence_id()
                role_token = document.store.tokens[role_token_ids[0]]
                role_evidence = EvidenceSpan(
                    id=role_evidence_id,
                    text=role_token.text,
                    span=role_token.span,
                    sentence_id=sentence_id,
                    paragraph_index=sentence.paragraph_index,
                    source=self.config.producer_id,
                )
                document.store.add_evidence(role_evidence)

                role_mention_id = document.store.next_mention_id()
                document.store.add_mention(
                    self.mention_factory.build_mention(
                        mention_id=role_mention_id,
                        text=role_token.text,
                        kind=MentionKind.NER,
                        evidence_id=role_evidence_id,
                        sentence_id=sentence_id,
                        token_ids=tuple(role_token_ids),
                    )
                )

                document.store.add_entity_candidate(
                    EntityCandidate(
                        id=document.store.next_entity_candidate_id(),
                        kind=EntityKind.ROLE,
                        mention_ids=(role_mention_id,),
                        canonical_hint=None,
                        grounding=GroundingKind.OBSERVED,
                        source=self.config.producer_id,
                    )
                )

                # Update main person evidence
                start_token = document.store.tokens[token_ids[0]]
                end_token = document.store.tokens[token_ids[-1]]
                new_text = document.cleaned_text[
                    start_token.span.start_char : end_token.span.end_char
                ]
                evidence = EvidenceSpan(
                    id=evidence_id,
                    text=new_text,
                    span=Span(start_token.span.start_char, end_token.span.end_char),
                    sentence_id=sentence_id,
                    paragraph_index=sentence.paragraph_index,
                    source=self.config.producer_id,
                )
            document.store.add_evidence(evidence)

            mention_kind = MentionKind.NER
            if entity_kind == EntityKind.PERSON and len(token_ids) == 1:
                mention_kind = MentionKind.SURNAME_ONLY

            mention_id = document.store.next_mention_id()
            document.store.add_mention(
                self.mention_factory.build_mention(
                    mention_id=mention_id,
                    text=evidence.text,
                    kind=mention_kind,
                    evidence_id=evidence_id,
                    sentence_id=sentence_id,
                    token_ids=tuple(token_ids),
                )
            )
            if entity_kind is None:
                continue
            candidate = EntityCandidate(
                id=document.store.next_entity_candidate_id(),
                kind=entity_kind,
                mention_ids=(mention_id,),
                canonical_hint=evidence.text,
                grounding=GroundingKind.OBSERVED,
                source=self.config.producer_id,
                reuse_key=full_person_reuse_key(document, mention_id, entity_kind),
                blocking_key=full_person_reuse_key(document, mention_id, entity_kind),
            )
            document.store.add_entity_candidate(candidate)
        return document

    def _has_preceding_org_descriptor(
        self,
        document: ArticleDocument,
        sentence_id: SentenceId,
        token_id: TokenId,
    ) -> bool:
        sentence = document.store.sentences[sentence_id]
        try:
            token_index = sentence.token_ids.index(token_id)
        except ValueError:
            return False
        if token_index == 0:
            return False
        for lookback in range(1, min(token_index, 3) + 1):
            previous_token = document.store.tokens.get(sentence.token_ids[token_index - lookback])
            if previous_token is None:
                continue
            previous_lemma = previous_token.preferred_lemma() or previous_token.text.lower()
            if is_organization_descriptor_lemma(previous_lemma):
                return True
        return False


def spacy_label_to_ner_label(label: str) -> NerLabel | None:
    normalized = label.casefold()
    if normalized in {"date", "time"}:
        return NerLabel(normalized)
    if "pers" in normalized or normalized == "person":
        return NerLabel.PERSON
    if "org" in normalized:
        return NerLabel.ORGANIZATION
    if (
        "loc" in normalized
        or "gpe" in normalized
        or "location" in normalized
        or "place" in normalized
        or "geog" in normalized
    ):
        return NerLabel.LOCATION
    return None


def ner_label_to_entity_kind(label: NerLabel) -> EntityKind | None:
    entity_kind_by_label = {
        NerLabel.PERSON: EntityKind.PERSON,
        NerLabel.ORGANIZATION: EntityKind.ORGANIZATION,
        NerLabel.LOCATION: EntityKind.LOCATION,
    }
    return entity_kind_by_label.get(label)


def full_person_reuse_key(
    document: ArticleDocument,
    mention_id: MentionId,
    entity_kind: EntityKind,
) -> FullPersonNameKey | None:
    if entity_kind != EntityKind.PERSON:
        return None
    tokens = document.store.tokens_for_mention(mention_id)
    if len(tokens) < 2:
        return None
    given_name = tokens[0].preferred_lemma()
    surname = tokens[-1].preferred_lemma()
    if given_name is None or surname is None:
        return None
    return FullPersonNameKey(given_name_lemma=given_name, surname_base=surname)
