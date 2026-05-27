from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.nlp import (
    Morfeusz2MorphologyAdapter,
    NamedEntitySpan,
    ParsedDependencySentence,
)
from pipeline_v2.segmentation import ParagraphSentenceSegmenter


@dataclass(frozen=True, slots=True)
class StaticDependencyProvider:
    parsed: tuple[ParsedDependencySentence, ...]

    def parse(self, text: str) -> tuple[ParsedDependencySentence, ...]:
        _ = text
        return self.parsed


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def setup_base_test_document(
    text: str,
    paragraphs: tuple[str, ...] | None = None,
) -> ArticleDocument:
    actual_paragraphs = paragraphs or (text,)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=actual_paragraphs,
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    return document
