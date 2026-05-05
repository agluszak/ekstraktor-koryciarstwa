from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import torch
from stanza.pipeline.coref_processor import extract_text

from pipeline.base import CoreferenceResolver
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, CoreferenceResult, Entity, Mention
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_entity_name

# Short common-noun anaphors that Stanza's coref may use as representative text for an
# org chain, but which are too ambiguous to resolve reliably (e.g. "spółka" could be
# any org in the document).  These are skipped in org chain resolution.
_GENERIC_ORG_NOUNS = frozenset(
    {
        "spółka",
        "firma",
        "instytucja",
        "organizacja",
        "stowarzyszenie",
        "fundacja",
        "podmiot",
        "przedsiębiorstwo",
        "zakład",
        "towarzystwo",
        "urząd",
    }
)


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

    def run(self, document: ArticleDocument) -> CoreferenceResult:
        resolved_mentions: list[Mention] = []
        # Build lookup maps for person and organization entities so that Stanza coref
        # chains can be resolved for both entity types.
        people = [entity for entity in document.entities if entity.entity_type == EntityType.PERSON]
        orgs = [
            entity
            for entity in document.entities
            if entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        ]
        person_by_name = {entity.normalized_name: entity for entity in people}
        org_by_name = {entity.normalized_name: entity for entity in orgs}
        sentence_map = {sentence.sentence_index: sentence for sentence in document.sentences}
        try:
            with torch.inference_mode():
                nlp_doc = cast(
                    CorefDocument,
                    self.runtime.get_stanza_coref_pipeline()(document.cleaned_text),
                )

            for chain in nlp_doc.coref:
                representative_text = normalize_entity_name(chain.representative_text)
                representative_entity = person_by_name.get(representative_text)
                if representative_entity is None:
                    representative_entity = self._match_person_entity(
                        person_by_name, representative_text
                    )
                if representative_entity is None:
                    # Try organization entities for this chain.  We only do this when the
                    # representative text is not a bare generic noun (too ambiguous).
                    representative_entity = self._match_org_entity(org_by_name, representative_text)
                    if representative_entity is not None:
                        mention_type = "ResolvedOrgReference"
                    else:
                        continue
                else:
                    mention_type = "ResolvedPersonReference"

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
                        mention_type=mention_type,
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
    def _match_org_entity(
        org_by_name: Mapping[str, Entity],
        representative_text: str,
    ) -> Entity | None:
        """Match org chains by representative text, skipping generic bare nouns.

        We require either an exact match against a known org or a multi-token
        representative (≥2 words) whose suffix matches a known org name, to avoid
        binding generic demonstratives like 'ta spółka' to a randomly chosen org.
        """
        if not representative_text:
            return None
        # Reject if any token of the representative text is a generic bare noun.
        # Multi-word representatives like "ta spółka" are caught by the per-token check.
        if any(token in _GENERIC_ORG_NOUNS for token in representative_text.split()):
            return None
        if representative_text in org_by_name:
            return org_by_name[representative_text]
        rep_tokens = representative_text.split()
        # Multi-word representative: try exact and suffix matching
        if len(rep_tokens) < 2:
            return None
        for candidate_name, entity in org_by_name.items():
            candidate_tokens = candidate_name.split()
            if rep_tokens == candidate_tokens:
                return entity
            # suffix match: representative ends with all tokens of candidate
            if len(rep_tokens) >= len(candidate_tokens) >= 2:
                if rep_tokens[-len(candidate_tokens) :] == candidate_tokens:
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
