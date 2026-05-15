from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import spacy
from spacy.language import Language

from pipeline_v2.candidates import EntityCandidate, FullPersonNameKey
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, MentionId, ProducerId
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
            evidence_id = EvidenceId(f"evidence-{len(document.store.evidence)}")
            evidence = EvidenceSpan(
                id=evidence_id,
                text=entity_span.text,
                span=entity_span.span,
                sentence_id=sentence_id,
                paragraph_index=document.store.sentences[sentence_id].paragraph_index,
                source=self.name(),
            )
            document.store.add_evidence(evidence)
            mention_id = MentionId(f"mention-{len(document.store.mentions)}")
            document.store.add_mention(
                self.mention_factory.build_mention(
                    mention_id=mention_id,
                    text=entity_span.text,
                    kind=MentionKind.NER,
                    evidence_id=evidence_id,
                    sentence_id=sentence_id,
                    token_ids=document.store.token_ids_for_span(
                        sentence_id=sentence_id,
                        span=evidence,
                    ),
                )
            )
            entity_kind = ner_label_to_entity_kind(entity_span.label)
            if entity_kind is None:
                continue
            candidate = EntityCandidate(
                id=EntityCandidateId(f"entity-{len(document.store.entity_candidates)}"),
                kind=entity_kind,
                mention_ids=(mention_id,),
                canonical_hint=entity_span.text,
                grounding=GroundingKind.OBSERVED,
                source=self.config.producer_id,
                reuse_key=full_person_reuse_key(document, mention_id, entity_kind),
                blocking_key=full_person_reuse_key(document, mention_id, entity_kind),
            )
            document.store.add_entity_candidate(candidate)
        return document


def spacy_label_to_ner_label(label: str) -> NerLabel | None:
    normalized = label.casefold()
    if normalized in {"date", "time"}:
        return NerLabel(normalized)
    if "pers" in normalized or normalized == "person":
        return NerLabel.PERSON
    if "org" in normalized:
        return NerLabel.ORGANIZATION
    if normalized in {"loc", "gpe", "location", "place"} or "geog" in normalized:
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
