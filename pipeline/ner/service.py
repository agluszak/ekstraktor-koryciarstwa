from __future__ import annotations

import spacy

from pipeline.base import NERExtractor
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Mention
from pipeline.utils import join_hyphenated_parts, normalize_entity_name, stable_id


class SpacyPolishNERExtractor(NERExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.nlp = spacy.load(config.models.spacy_model)

    def name(self) -> str:
        return "spacy_polish_ner_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        parsed = self.nlp(document.cleaned_text)
        entity_index: dict[tuple[str, str], Entity] = {}
        entity_display_score: dict[tuple[str, str], int] = {}

        for ent in parsed.ents:
            entity_type = self._map_label(ent.label_)
            if not entity_type:
                continue
            merge_key, display_name, display_score = self._entity_forms(ent, entity_type)
            key = (entity_type, merge_key)
            if key not in entity_index:
                entity_index[key] = Entity(
                    entity_id=stable_id(entity_type.lower(), document.document_id, merge_key),
                    entity_type=entity_type,
                    canonical_name=display_name,
                    normalized_name=display_name,
                )
                entity_display_score[key] = display_score
            entity = entity_index[key]
            if display_score > entity_display_score[key]:
                entity.canonical_name = display_name
                entity.normalized_name = display_name
                entity_display_score[key] = display_score
            entity.aliases = list(dict.fromkeys([*entity.aliases, ent.text]))
            entity.evidence.append(
                EvidenceSpan(
                    text=ent.text,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    sentence_index=self._sentence_index(document, ent.start_char),
                )
            )
            document.mentions.append(
                Mention(
                    text=ent.text,
                    normalized_text=display_name,
                    mention_type=entity_type,
                    sentence_index=self._sentence_index(document, ent.start_char),
                    entity_id=entity.entity_id,
                )
            )

        document.entities = list(entity_index.values())
        return document

    @staticmethod
    def _map_label(label: str) -> str | None:
        lowered = label.lower()
        if "pers" in lowered or lowered == "person":
            return "Person"
        if "org" in lowered:
            return "Organization"
        return None

    @staticmethod
    def _entity_forms(ent, entity_type: str) -> tuple[str, str, int]:
        if entity_type == "Person":
            merge_key = SpacyPolishNERExtractor._person_merge_key(ent)
            display_name, display_score = SpacyPolishNERExtractor._person_display_name(ent)
            return merge_key, display_name, display_score
        normalized = normalize_entity_name(ent.text)
        return normalized, normalized, 0

    @staticmethod
    def _person_merge_key(ent) -> str:
        parts = [
            token.lemma_.strip() if token.lemma_.strip() else token.text.strip()
            for token in ent
            if token.text.strip()
        ]
        return normalize_entity_name(join_hyphenated_parts(parts))

    @staticmethod
    def _person_display_name(ent) -> tuple[str, int]:
        lexical_tokens = [token for token in ent if token.pos_ != "PUNCT" and token.text.strip()]
        if not lexical_tokens:
            normalized = normalize_entity_name(ent.text)
            return normalized, 0

        all_propn = all(token.pos_ == "PROPN" for token in lexical_tokens)
        has_nom = any("Case=Nom" in token.morph for token in lexical_tokens)
        unchanged_lemma = any(
            token.lemma_.strip() == token.text.strip() for token in lexical_tokens
        )
        single_token = len(lexical_tokens) == 1

        if all_propn and (has_nom or unchanged_lemma or single_token):
            display = SpacyPolishNERExtractor._person_merge_key(ent)
            score = 10
            if has_nom:
                score += 5
            if unchanged_lemma:
                score += 2
            if single_token:
                score += 1
            return display, score

        surface = normalize_entity_name(ent.text)
        score = 0 if all_propn else -5
        return surface, score

    @staticmethod
    def _sentence_index(document: ArticleDocument, start_char: int) -> int:
        for sentence in document.sentences:
            if sentence.start_char <= start_char <= sentence.end_char:
                return sentence.sentence_index
        return 0
