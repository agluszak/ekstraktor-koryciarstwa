from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import torch
from stanza.pipeline.coref_processor import extract_text

from pipeline.base import CoreferenceResolver
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityID, EntityType
from pipeline.models import ArticleDocument, Entity, Mention
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

_ORG_ANAPHOR_MARKERS = (
    "tej spółki",
    "tej spółce",
    "tą spółką",
    "tej fundacji",
    "wspomnianej fundacji",
    "jej zarząd",
    "jej rad",
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

    def run(self, document: ArticleDocument) -> ArticleDocument:
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

        # Add rule-based organization anaphor resolution
        resolved_mentions.extend(self._resolve_rule_based_org_anaphors(document, orgs))

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
    def _resolve_rule_based_org_anaphors(
        document: ArticleDocument,
        org_entities: list[Entity],
    ) -> list[Mention]:
        resolved: list[Mention] = []
        if not org_entities:
            return resolved

        # Track last mention sentence index for each entity
        entity_last_pos: dict[EntityID, int] = {}
        for entity in org_entities:
            last = -1
            for evidence in entity.evidence:
                if evidence.sentence_index is not None and evidence.sentence_index > last:
                    last = evidence.sentence_index
            entity_last_pos[entity.entity_id] = last

        # Also track already resolved mentions to avoid duplicates
        existing_offsets: set[tuple[int, int, int]] = {
            (m.sentence_index, m.start_char, m.end_char) for m in document.mentions
        }

        for sentence in document.sentences:
            lowered = sentence.text.lower()
            for marker in _ORG_ANAPHOR_MARKERS:
                start_idx = lowered.find(marker)
                if start_idx < 0:
                    continue

                abs_start = sentence.start_char + start_idx
                abs_end = abs_start + len(marker)

                if (sentence.sentence_index, abs_start, abs_end) in existing_offsets:
                    continue

                # Find the nearest preceding org entity
                candidates: list[tuple[EntityID, int]] = [
                    (eid, pos)
                    for eid, pos in entity_last_pos.items()
                    if pos <= sentence.sentence_index
                ]
                if not candidates:
                    continue

                # Closest by sentence distance
                best_eid: EntityID = max(candidates, key=lambda x: (x[1], x[0]))[0]

                resolved.append(
                    Mention(
                        text=sentence.text[start_idx : start_idx + len(marker)],
                        normalized_text=normalize_entity_name(marker),
                        mention_type="ResolvedOrgAnaphor",
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=abs_start,
                        end_char=abs_end,
                        entity_id=best_eid,
                    )
                )
                existing_offsets.add((sentence.sentence_index, abs_start, abs_end))

        return resolved

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
