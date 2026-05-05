from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import torch
from stanza.pipeline.coref_processor import extract_text

from pipeline.base import CoreferenceResolver
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, Entity, Mention
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_entity_name


class CorefWord(Protocol):
    start_char: int
    end_char: int


class CorefSentence(Protocol):
    words: list[CorefWord]


class CorefMention(Protocol):
    sentence: int
    start_word: int
    end_word: int


class CorefChain(Protocol):
    representative_text: str
    mentions: list[CorefMention]


class CorefDocument(Protocol):
    sentences: list[CorefSentence]
    coref: list[CorefChain]


class StanzaCoreferenceResolver(CoreferenceResolver):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)

    def name(self) -> str:
        return "stanza_coreference_resolver"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        resolved_mentions: list[Mention] = []
        people = [entity for entity in document.entities if entity.entity_type == EntityType.PERSON]
        entity_by_name = {entity.normalized_name: entity for entity in people}
        sentence_map = {sentence.sentence_index: sentence for sentence in document.sentences}
        try:
            with torch.inference_mode():
                nlp_doc = cast(
                    CorefDocument,
                    self.runtime.get_stanza_coref_pipeline()(document.cleaned_text),
                )

            for chain in nlp_doc.coref:
                representative_text = normalize_entity_name(chain.representative_text)
                representative_entity = entity_by_name.get(representative_text)
                if representative_entity is None:
                    representative_entity = self._match_person_entity(
                        entity_by_name, representative_text
                    )
                if representative_entity is None:
                    continue

                for mention in chain.mentions:
                    sentence_index = mention.sentence
                    sentence = sentence_map.get(sentence_index)
                    mention_text = extract_text(
                        nlp_doc,
                        mention.sentence,
                        mention.start_word,
                        mention.end_word,
                    )
                    start_char, end_char = self._mention_offsets(nlp_doc, mention)
                    resolved = Mention(
                        text=mention_text,
                        normalized_text=normalize_entity_name(mention_text),
                        mention_type="ResolvedPersonReference",
                        sentence_index=sentence_index,
                        paragraph_index=0 if sentence is None else sentence.paragraph_index,
                        start_char=0 if start_char is None else start_char,
                        end_char=0 if end_char is None else end_char,
                        entity_id=representative_entity.entity_id,
                    )
                    resolved_mentions.append(resolved)
        finally:
            self.runtime.reset_stanza_coref_pipeline()

        if resolved_mentions:
            existing_keys = {
                (
                    m.text,
                    m.sentence_index,
                    m.entity_id,
                    m.start_char,
                    m.end_char,
                )
                for m in document.mentions
            }
            for m in resolved_mentions:
                key = (
                    m.text,
                    m.sentence_index,
                    m.entity_id,
                    m.start_char,
                    m.end_char,
                )
                if key not in existing_keys:
                    document.mentions.append(m)
                    existing_keys.add(key)
        return document

    @staticmethod
    def _match_person_entity(
        entity_by_name: Mapping[str, Entity],
        representative_text: str,
    ) -> Entity | None:
        if representative_text in entity_by_name:
            return entity_by_name[representative_text]
        rep_tokens = representative_text.split()
        for candidate_name, entity in entity_by_name.items():
            candidate_tokens = candidate_name.split()
            if rep_tokens == candidate_tokens:
                return entity
            if rep_tokens and candidate_tokens and rep_tokens[-1] == candidate_tokens[-1]:
                if len(rep_tokens) == len(candidate_tokens):
                    return entity
        return None

    @staticmethod
    def _mention_offsets(
        nlp_doc: CorefDocument,
        mention: CorefMention,
    ) -> tuple[int | None, int | None]:
        sentence_index = mention.sentence
        start_word = mention.start_word
        end_word = mention.end_word
        if (
            start_word < 0
            or end_word <= start_word
            or sentence_index < 0
            or sentence_index >= len(nlp_doc.sentences)
        ):
            return None, None
        sentence = nlp_doc.sentences[sentence_index]
        if end_word > len(sentence.words):
            return None, None
        first_word = sentence.words[start_word]
        last_word = sentence.words[end_word - 1]
        start_char = first_word.start_char
        end_char = last_word.end_char
        if end_char <= start_char:
            return None, None
        return start_char, end_char
