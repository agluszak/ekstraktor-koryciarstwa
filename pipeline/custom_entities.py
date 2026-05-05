from __future__ import annotations

import re

from pipeline.base import DocumentStage
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, EntityID
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Mention, ParsedWord
from pipeline.nlp_rules import COMPENSATION_PATTERN
from pipeline.utils import normalize_entity_name, stable_id

EVENT_LEMMAS = frozenset(
    {
        "konkurs",
        "przetarg",
        "wybory",
        "nominacja",
        "nabór",
        "rekrutacja",
        "referendum",
        "głosowanie",
    }
)

LAW_LEMMAS = frozenset(
    {
        "uchwała",
        "ustawa",
        "rozporządzenie",
        "decyzja",
        "wyrok",
        "zarządzenie",
        "przepis",
        "artykuł",
        "paragraf",
    }
)


class CustomEntityExtractor(DocumentStage):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "custom_entity_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        self._extract_money(document)
        self._extract_lemma_entities(document, EVENT_LEMMAS, EntityType.EVENT)
        self._extract_lemma_entities(document, LAW_LEMMAS, EntityType.LAW)
        return document

    def _extract_money(self, document: ArticleDocument) -> None:
        entity_index: dict[str, Entity] = {}
        for sentence in document.sentences:
            for match in COMPENSATION_PATTERN.finditer(sentence.text):
                amount = match.group("amount")
                normalized = amount.title()
                merge_key = normalized.lower()
                
                if merge_key not in entity_index:
                    entity_index[merge_key] = Entity(
                        entity_id=EntityID(
                            stable_id("money", document.document_id, merge_key)
                        ),
                        entity_type=EntityType.MONEY,
                        canonical_name=normalized,
                        normalized_name=normalized,
                        lemmas=[token.lower() for token in normalized.split()],
                    )
                entity = entity_index[merge_key]
                
                abs_start = sentence.start_char + match.start("amount")
                abs_end = sentence.start_char + match.end("amount")
                
                entity.evidence.append(
                    EvidenceSpan(
                        text=amount,
                        start_char=abs_start,
                        end_char=abs_end,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                    )
                )
                
                document.mentions.append(
                    Mention(
                        text=amount,
                        normalized_text=normalized,
                        mention_type=EntityType.MONEY,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=abs_start,
                        end_char=abs_end,
                        entity_id=entity.entity_id,
                    )
                )
        document.entities.extend(entity_index.values())

    def _extract_lemma_entities(
        self, 
        document: ArticleDocument, 
        target_lemmas: frozenset[str], 
        entity_type: EntityType
    ) -> None:
        entity_index: dict[str, Entity] = {}
        
        for sentence_index, words in document.parsed_sentences.items():
            sentence = next(
                (s for s in document.sentences if s.sentence_index == sentence_index), None
            )
            if sentence is None:
                continue
                
            for word in words:
                lemma = (word.lemma or word.text).casefold()
                if lemma not in target_lemmas:
                    continue
                
                phrase_words = self._extract_phrase(word, words)
                if not phrase_words:
                    continue
                    
                text = " ".join(w.text for s, w in phrase_words)
                canonical = normalize_entity_name(
                    " ".join(w.lemma or w.text for s, w in phrase_words)
                )
                merge_key = canonical.lower()
                
                if merge_key not in entity_index:
                    entity_index[merge_key] = Entity(
                        entity_id=EntityID(
                            stable_id(entity_type.lower(), document.document_id, merge_key)
                        ),
                        entity_type=entity_type,
                        canonical_name=canonical,
                        normalized_name=canonical,
                        lemmas=[w.lemma or w.text for s, w in phrase_words],
                    )
                entity = entity_index[merge_key]
                
                abs_start = sentence.start_char + phrase_words[0][1].start
                abs_end = sentence.start_char + phrase_words[-1][1].end
                
                entity.evidence.append(
                    EvidenceSpan(
                        text=text,
                        start_char=abs_start,
                        end_char=abs_end,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                    )
                )
                
                document.mentions.append(
                    Mention(
                        text=text,
                        normalized_text=canonical,
                        mention_type=entity_type,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=abs_start,
                        end_char=abs_end,
                        entity_id=entity.entity_id,
                    )
                )
        document.entities.extend(entity_index.values())

    def _extract_phrase(
        self, 
        head: ParsedWord, 
        all_words: list[ParsedWord]
    ) -> list[tuple[int, ParsedWord]]:
        """Extract a phrase centered around the head word by looking at children in the dep tree."""
        # Find all words that have 'head' as their head (direct children)
        # We only want noun modifiers, adjectives, etc.
        relevant_deps = {"amod", "nmod", "flat", "compound", "nummod", "case", "det"}
        
        phrase_indices = {head.index}
        
        # Simple BFS to find all descendants connected via relevant dependencies
        queue = [head.index]
        while queue:
            curr_idx = queue.pop(0)
            for w in all_words:
                if w.head == curr_idx and (w.deprel.split(":")[0] in relevant_deps):
                    if w.index not in phrase_indices:
                        phrase_indices.add(w.index)
                        queue.append(w.index)
        
        # Return sorted by index
        sorted_words = sorted(
            [(w.index, w) for w in all_words if w.index in phrase_indices],
            key=lambda x: x[0]
        )
        return sorted_words
