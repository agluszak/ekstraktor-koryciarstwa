from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from pipeline.base import Preprocessor, RelevanceFilter
from pipeline.cli import build_pipeline
from pipeline.config import PipelineConfig
from pipeline.coref import StanzaCoreferenceResolver
from pipeline.domain_types import (
    DocumentID,
    EntityID,
    EntityType,
)
from pipeline.models import (
    ArticleDocument,
    Entity,
    Mention,
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
            document_id=DocumentID("doc-1"),
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

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.relevance = RelevanceDecision(is_relevant=False, score=0.0, reasons=["irrelevant"])
        return document


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
    pipeline.stages[1] = StubRelevanceFilter()

    result = pipeline.run(PipelineInput(raw_html="<html></html>", source_url=None))

    assert result.relevance.is_relevant is False
    assert calls.spacy_calls == 0
    assert calls.stanza_calls == 0
    assert calls.sentence_transformer_calls == 0


def test_coref_resolver_uses_inference_mode_and_resets_pipeline() -> None:
    config = PipelineConfig.from_file("config.yaml")
    observed_grad_enabled: list[bool] = []
    factory_calls = 0

    @dataclass
    class FakeCorefMention:
        sentence: int
        start_word: int
        end_word: int

    @dataclass
    class FakeCorefChain:
        representative_text: str
        mentions: list[FakeCorefMention]

    @dataclass
    class FakeWord:
        start_char: int
        end_char: int

    @dataclass
    class FakeSentence:
        words: list[FakeWord]

    @dataclass
    class FakeDoc:
        sentences: list[FakeSentence]
        coref: list[FakeCorefChain]

    class FakePipeline:
        def __call__(self, text: str) -> FakeDoc:
            _ = text
            import torch

            observed_grad_enabled.append(torch.is_grad_enabled())
            return FakeDoc(
                sentences=[
                    FakeSentence(
                        words=[
                            FakeWord(start_char=0, end_char=3),
                            FakeWord(start_char=4, end_char=12),
                        ]
                    )
                ],
                coref=[
                    FakeCorefChain(
                        representative_text="Jan Kowalski",
                        mentions=[FakeCorefMention(sentence=0, start_word=0, end_word=1)],
                    )
                ],
            )

    def fake_stanza_factory(*args, **kwargs):
        nonlocal factory_calls
        _ = args, kwargs
        factory_calls += 1
        return FakePipeline()

    runtime = PipelineRuntime(config, stanza_factory=fake_stanza_factory)
    resolver = StanzaCoreferenceResolver(config, runtime=runtime)
    document = ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Jan Kowalski został powołany.",
        paragraphs=["Jan Kowalski został powołany."],
        entities=[
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            )
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-1"),
            )
        ],
    )

    with patch("pipeline.coref.extract_text", return_value="Jan Kowalski"):
        result = resolver.run(document)

    assert isinstance(result, ArticleDocument)
    assert observed_grad_enabled == [False]
    assert factory_calls == 1
    assert runtime.stanza_coref_loaded is False


def test_runtime_can_rebuild_coref_pipeline_after_reset() -> None:
    config = PipelineConfig.from_file("config.yaml")
    factory_calls = 0

    class FakePipeline:
        pass

    def fake_stanza_factory(*args, **kwargs):
        nonlocal factory_calls
        _ = args, kwargs
        factory_calls += 1
        return FakePipeline()

    runtime = PipelineRuntime(config, stanza_factory=fake_stanza_factory)

    first = runtime.get_stanza_coref_pipeline()
    assert runtime.stanza_coref_loaded is True

    runtime.reset_stanza_coref_pipeline()
    assert runtime.stanza_coref_loaded is False

    second = runtime.get_stanza_coref_pipeline()
    assert runtime.stanza_coref_loaded is True
    assert first is not second
    assert factory_calls == 2
