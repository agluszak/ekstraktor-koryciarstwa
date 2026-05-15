from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument, PipelineInput, RelevanceDecision
from pipeline_v2.ids import DocumentId
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.stages import V2Pipeline


@dataclass(slots=True)
class StaticPreprocessor:
    document: ArticleDocument

    def name(self) -> str:
        return "static_preprocessor"

    def run(self, data: PipelineInput) -> ArticleDocument:
        _ = data
        return self.document


@dataclass(slots=True)
class MarkRelevantStage:
    relevant: bool

    def name(self) -> str:
        return "mark_relevant"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.relevance = RelevanceDecision(is_relevant=self.relevant, score=1.0)
        return document


@dataclass(slots=True)
class CountingStage:
    name_value: str
    calls: int = 0

    def name(self) -> str:
        return self.name_value

    def run(self, document: ArticleDocument) -> ArticleDocument:
        self.calls += 1
        return document


class StepTimer:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.25
        return self.value


def test_v2_pipeline_stops_document_stages_after_irrelevance() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Irrelevant text.",
        paragraphs=("Irrelevant text.",),
    )
    skipped = CountingStage("should_not_run")
    pipeline = V2Pipeline(
        preprocessor=StaticPreprocessor(document),
        stages=(MarkRelevantStage(relevant=False), skipped),
        timer=StepTimer(),
    )

    result = pipeline.run(PipelineInput(raw_html="<html></html>"))

    assert result.relevance.is_relevant is False
    assert skipped.calls == 0
    assert set(result.execution_times) == {"static_preprocessor", "mark_relevant"}


def test_segmenter_populates_sentence_records_with_paragraph_and_offsets() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Pierwsze zdanie. Drugie zdanie!\nNowy akapit?",
        paragraphs=("Pierwsze zdanie. Drugie zdanie!", "Nowy akapit?"),
    )

    ParagraphSentenceSegmenter().run(document)
    sentences = tuple(document.store.sentences.values())

    assert tuple(sentence.text for sentence in sentences) == (
        "Pierwsze zdanie.",
        "Drugie zdanie!",
        "Nowy akapit?",
    )
    assert tuple(sentence.paragraph_index for sentence in sentences) == (0, 0, 1)
    assert document.cleaned_text[sentences[1].span.start_char : sentences[1].span.end_char] == (
        "Drugie zdanie!"
    )
