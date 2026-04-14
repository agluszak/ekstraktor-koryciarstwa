from __future__ import annotations

from dataclasses import dataclass

from pipeline.base import OutputBuilder, Preprocessor, RelevanceFilter
from pipeline.cli import build_pipeline
from pipeline.config import PipelineConfig
from pipeline.models import (
    ArticleDocument,
    ExtractionResult,
    GraphExport,
    PipelineInput,
    RelevanceDecision,
)
from pipeline.runtime import PipelineRuntime


@dataclass
class LoaderCounter:
    spacy_calls: int = 0
    stanza_calls: int = 0
    sentence_transformer_calls: int = 0


def test_pipeline_runtime_loads_models_lazily() -> None:
    config = PipelineConfig.from_file("config.yaml")
    calls = LoaderCounter()

    def fake_spacy_loader(name: str) -> str:
        assert name == config.models.spacy_model
        calls.spacy_calls += 1
        return "spacy-model"

    def fake_stanza_factory(*args, **kwargs) -> str:
        _ = args, kwargs
        calls.stanza_calls += 1
        return "stanza-pipeline"

    def fake_sentence_transformer_loader(name: str) -> str:
        assert name == config.models.sentence_transformer_model
        calls.sentence_transformer_calls += 1
        return "sentence-transformer-model"

    runtime = PipelineRuntime(
        config,
        spacy_loader=fake_spacy_loader,
        stanza_factory=fake_stanza_factory,
        sentence_transformer_loader=fake_sentence_transformer_loader,
    )

    assert not runtime.spacy_loaded
    assert not runtime.stanza_coref_loaded
    assert not runtime.stanza_syntax_loaded
    assert not runtime.sentence_transformer_loaded

    assert runtime.get_spacy_model() == "spacy-model"
    assert runtime.get_spacy_model() == "spacy-model"
    assert runtime.get_stanza_coref_pipeline() == "stanza-pipeline"
    assert runtime.get_stanza_syntax_pipeline() == "stanza-pipeline"
    assert runtime.get_sentence_transformer_model() == "sentence-transformer-model"

    assert calls.spacy_calls == 1
    assert calls.stanza_calls == 2
    assert calls.sentence_transformer_calls == 1
    assert runtime.spacy_loaded
    assert runtime.stanza_coref_loaded
    assert runtime.stanza_syntax_loaded
    assert runtime.sentence_transformer_loaded


class StubPreprocessor(Preprocessor):
    def name(self) -> str:
        return "stub_preprocessor"

    def run(self, data: PipelineInput) -> ArticleDocument:
        return ArticleDocument(
            document_id="doc-1",
            source_url=data.source_url,
            raw_html=data.raw_html,
            title="Test",
            publication_date=None,
            cleaned_text="Irrelevant article text.",
            paragraphs=["Irrelevant article text."],
        )


class StubRelevanceFilter(RelevanceFilter):
    def name(self) -> str:
        return "stub_relevance_filter"

    def run(self, document: ArticleDocument) -> RelevanceDecision:
        return RelevanceDecision(is_relevant=False, score=0.0, reasons=["irrelevant"])


class StubOutputBuilder(OutputBuilder):
    def name(self) -> str:
        return "stub_output_builder"

    def run(self, document: ArticleDocument) -> ExtractionResult:
        return ExtractionResult(
            document_id=document.document_id,
            source_url=document.source_url,
            title=document.title,
            publication_date=document.publication_date,
            relevance=document.relevance or RelevanceDecision(False, 0.0, []),
            entities=[],
            facts=[],
            relations=[],
            events=[],
            score=None,
            graph=GraphExport(nodes=[], edges=[]),
        )


def test_irrelevant_pipeline_run_does_not_load_heavy_models() -> None:
    config = PipelineConfig.from_file("config.yaml")
    calls = LoaderCounter()

    def fake_spacy_loader(name: str) -> str:
        _ = name
        calls.spacy_calls += 1
        return "spacy-model"

    def fake_stanza_factory(*args, **kwargs) -> str:
        _ = args, kwargs
        calls.stanza_calls += 1
        return "stanza-pipeline"

    def fake_sentence_transformer_loader(name: str) -> str:
        _ = name
        calls.sentence_transformer_calls += 1
        return "sentence-transformer-model"

    runtime = PipelineRuntime(
        config,
        spacy_loader=fake_spacy_loader,
        stanza_factory=fake_stanza_factory,
        sentence_transformer_loader=fake_sentence_transformer_loader,
    )
    pipeline = build_pipeline(config, runtime=runtime)
    pipeline.preprocessor = StubPreprocessor()
    pipeline.relevance_filter = StubRelevanceFilter()
    pipeline.output_builder = StubOutputBuilder()

    result = pipeline.run(PipelineInput(raw_html="<html></html>", source_url=None))

    assert result.relevance.is_relevant is False
    assert calls.spacy_calls == 0
    assert calls.stanza_calls == 0
    assert calls.sentence_transformer_calls == 0
