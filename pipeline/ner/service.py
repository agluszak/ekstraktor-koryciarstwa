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

        for ent in parsed.ents:
            entity_type = self._map_label(ent.label_)
            if not entity_type:
                continue
            normalized = self._normalize_entity(ent, entity_type)
            key = (entity_type, normalized)
            if key not in entity_index:
                entity_index[key] = Entity(
                    entity_id=stable_id(entity_type.lower(), document.document_id, normalized),
                    entity_type=entity_type,
                    canonical_name=normalized,
                    normalized_name=normalized,
                )
            entity = entity_index[key]
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
                    normalized_text=normalized,
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
    def _normalize_entity(ent, entity_type: str) -> str:
        if entity_type == "Person":
            parts = [
                token.lemma_.strip() if token.lemma_.strip() else token.text.strip()
                for token in ent
                if token.text.strip()
            ]
            return normalize_entity_name(join_hyphenated_parts(parts))
        return normalize_entity_name(ent.text)

    @staticmethod
    def _sentence_index(document: ArticleDocument, start_char: int) -> int:
        for sentence in document.sentences:
            if sentence.start_char <= start_char <= sentence.end_char:
                return sentence.sentence_index
        return 0
