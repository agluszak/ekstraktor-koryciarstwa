from __future__ import annotations

from collections.abc import Mapping

import torch
from stanza.pipeline.coref_processor import extract_text

from pipeline.base import CoreferenceResolver
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, CoreferenceResult, Entity, Mention
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_entity_name


class StanzaCoreferenceResolver(CoreferenceResolver):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)

    def name(self) -> str:
        return "stanza_coreference_resolver"

    def run(self, document: ArticleDocument) -> CoreferenceResult:
        resolved_mentions: list[Mention] = []
        people = [entity for entity in document.entities if entity.entity_type == EntityType.PERSON]
        entity_by_name = {entity.normalized_name: entity for entity in people}
        sentence_map = {sentence.sentence_index: sentence for sentence in document.sentences}
        try:
            with torch.inference_mode():
                nlp_doc = self.runtime.get_stanza_coref_pipeline()(document.cleaned_text)

            for chain in getattr(nlp_doc, "coref", []):
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

        return CoreferenceResult(resolved_mentions=resolved_mentions)

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
    def _mention_offsets(nlp_doc, mention: object) -> tuple[int | None, int | None]:
        sentences = getattr(nlp_doc, "sentences", None)
        if not isinstance(sentences, list):
            return None, None
        sentence_index = getattr(mention, "sentence", None)
        start_word = getattr(mention, "start_word", None)
        end_word = getattr(mention, "end_word", None)
        if (
            not isinstance(sentence_index, int)
            or not isinstance(start_word, int)
            or not isinstance(end_word, int)
            or start_word < 0
            or end_word <= start_word
            or sentence_index < 0
            or sentence_index >= len(sentences)
        ):
            return None, None
        sentence = sentences[sentence_index]
        if end_word > len(sentence.words):
            return None, None
        first_word = sentence.words[start_word]
        last_word = sentence.words[end_word - 1]
        start_char = getattr(first_word, "start_char", None)
        end_char = getattr(last_word, "end_char", None)
        if (
            not isinstance(start_char, int)
            or not isinstance(end_char, int)
            or end_char <= start_char
        ):
            return None, None
        return start_char, end_char
