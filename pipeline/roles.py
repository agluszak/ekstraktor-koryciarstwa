from __future__ import annotations

from pipeline.base import DocumentStage
from pipeline.config import PipelineConfig
from pipeline.document_graph import sync_entity_mentions
from pipeline.domain_types import EntityType, MentionKind
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
                if match.end <= match.start:
                    continue
                canonical_name = match.canonical_name
                start_char = sentence.start_char + match.start
                end_char = sentence.start_char + match.end
                surface = sentence.text[match.start : match.end]
                if not surface.strip():
                    continue
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
                        text=surface,
                        start_char=start_char,
                        end_char=end_char,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                    )
                )

                document.mentions.append(
                    Mention(
                        text=surface,
                        normalized_text=canonical_name,
                        entity_type=EntityType.POSITION,
                        mention_kind=MentionKind.DERIVED_ENTITY,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=start_char,
                        end_char=end_char,
                        entity_id=entity.entity_id,
                        lemmas=entity.lemmas,
                        ner_label=None,  # Roles don't have standard NER labels
                    )
                )

        # Merge with existing entities
        document.entities.extend(entity_index.values())
        sync_entity_mentions(document)
        return document
