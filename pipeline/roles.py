from __future__ import annotations

from pipeline.base import DocumentStage
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, NERLabel
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Mention
from pipeline.role_matching import match_role_mentions
from pipeline.utils import stable_id


class PolishPositionExtractor(DocumentStage):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_position_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not document.parsed_sentences:
            return document

        entity_index: dict[str, Entity] = {}

        for sentence_index, words in document.parsed_sentences.items():
            sentence = next(
                (s for s in document.sentences if s.sentence_index == sentence_index), None
            )
            if sentence is None:
                continue

            matches = match_role_mentions(words)
            for match in matches:
                canonical_name = match.canonical_name
                # Use canonical name as merge key for roles within a document
                merge_key = canonical_name.lower()
                
                from pipeline.domain_types import EntityID
                
                key = merge_key
                if key not in entity_index:
                    entity_index[key] = Entity(
                        entity_id=EntityID(
                            stable_id(EntityType.POSITION.lower(), document.document_id, merge_key)
                        ),
                        entity_type=EntityType.POSITION,
                        canonical_name=canonical_name,
                        normalized_name=canonical_name,
                        lemmas=[token.lower() for token in canonical_name.split()],
                        role_kind=match.role_kind,
                        role_modifier=match.role_modifier,
                    )
                entity = entity_index[key]
                
                entity.evidence.append(
                    EvidenceSpan(
                        text=sentence.text[
                            match.start - sentence.start_char : match.end - sentence.start_char
                        ],
                        start_char=match.start,
                        end_char=match.end,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                    )
                )
                
                document.mentions.append(
                    Mention(
                        text=sentence.text[
                            match.start - sentence.start_char : match.end - sentence.start_char
                        ],
                        normalized_text=canonical_name,
                        mention_type=EntityType.POSITION,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=match.start,
                        end_char=match.end,
                        entity_id=entity.entity_id,
                        lemmas=entity.lemmas,
                        ner_label=None, # Roles don't have standard NER labels
                    )
                )

        # Merge with existing entities
        document.entities.extend(entity_index.values())
        return document
