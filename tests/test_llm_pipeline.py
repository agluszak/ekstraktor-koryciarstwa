from __future__ import annotations

import argparse
import json

import pytest

from pipeline.cli import select_pipeline
from pipeline.config import (
    LLMConfig,
    ModelConfig,
    PatternConfig,
    PipelineConfig,
    RegistryConfig,
    ScoreConfig,
)
from pipeline.domain_types import EntityType, FactType
from pipeline.llm.adapter import LLMExtractionAdapter, candidates_from_payload
from pipeline.llm.runner import OllamaLLMExtractionPipeline, _configured_ollama_model
from pipeline.llm.schema import build_llm_response_schema
from pipeline.models import ArticleDocument, PipelineInput, SentenceFragment


def make_config() -> PipelineConfig:
    return PipelineConfig(
        models=ModelConfig(
            spacy_model="pl_core_news_lg",
            sentence_transformer_model="sentence-transformers/test",
            stanza_coref_model_path="models/coref.pt",
        ),
        keywords=["prezes", "dotacja", "żona"],
        party_aliases={},
        institution_aliases={},
        patterns=PatternConfig(
            appointment_verbs=[],
            dismissal_verbs=[],
            board_terms=[],
            party_markers=[],
            kinship_terms=[],
            state_company_markers=["spółka"],
            qualification_markers=[],
        ),
        score_weights=ScoreConfig(
            political_tie=0.25,
            family_tie=0.35,
            board_position=0.2,
            state_company=0.15,
            qualification_gap=0.2,
            dismissal_signal=0.1,
        ),
        registry=RegistryConfig(similarity_threshold=0.92),
        llm=LLMConfig(model="gemma4:latest", context_size=4096, max_output_tokens=512),
    )


def make_document() -> ArticleDocument:
    text = (
        "Jan Kowalski został prezesem miejskiej spółki Alfa. "
        "Jego żona Anna Kowalska dostała dotację 100 tys. zł."
    )
    return ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="<html></html>",
        title="Test",
        publication_date="2026-04-27",
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text="Jan Kowalski został prezesem miejskiej spółki Alfa.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=52,
            ),
            SentenceFragment(
                text="Jego żona Anna Kowalska dostała dotację 100 tys. zł.",
                paragraph_index=0,
                sentence_index=1,
                start_char=53,
                end_char=len(text),
            ),
        ],
    )


def test_llm_schema_excludes_hallucination_prone_fields() -> None:
    schema = build_llm_response_schema()
    serialized = json.dumps(schema)

    assert "char_start" not in serialized
    assert "char_end" not in serialized
    assert "sentence_id" not in serialized
    assert "paragraph_id" not in serialized
    assert "fact_id" not in serialized
    assert "entity_id" not in serialized
    assert "execution_times" not in serialized
    assert "relevance_score" not in serialized
    assert "relevance_reasons" not in serialized
    assert "aliases" not in serialized
    assert "mentions" not in serialized
    assert "confidence" not in serialized
    assert "relationship_type" not in serialized
    assert "kinship_detail" not in serialized
    assert "period" not in serialized
    assert '"additionalProperties": false' in serialized


def test_llm_adapter_emits_grounded_entities_and_facts() -> None:
    document = make_document()
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": EntityType.PERSON.value,
                "canonical_name": "jan kowalski",
            },
            {
                "key": "org_1",
                "entity_type": EntityType.ORGANIZATION.value,
                "canonical_name": "Alfa",
            },
        ],
        "facts": [
            {
                "fact_type": FactType.APPOINTMENT.value,
                "subject_key": "person_1",
                "object_key": "org_1",
                "value_text": "prezes",
                "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
            }
        ],
    }

    candidate_set = candidates_from_payload(payload)
    result = LLMExtractionAdapter().apply(document, [candidate_set])

    assert result.relevance is not None
    assert result.relevance.is_relevant is True
    assert result.relevance.score == 1.0
    assert [entity.canonical_name for entity in result.entities] == ["Jan Kowalski", "Alfa"]
    assert len(result.facts) == 1
    assert result.facts[0].source_extractor == "llm_ollama"
    assert result.facts[0].subject_entity_id == result.entities[0].entity_id
    assert result.facts[0].object_entity_id == result.entities[1].entity_id
    assert result.facts[0].evidence.start_char == 0
    assert result.facts[0].role == "prezes"
    assert result.facts[0].confidence == 0.8


def test_llm_adapter_drops_unknown_entity_references() -> None:
    document = make_document()
    candidate_set = candidates_from_payload(
        {
            "is_relevant": True,
            "entities": [
                {
                    "key": "person_1",
                    "entity_type": EntityType.PERSON.value,
                    "canonical_name": "Jan Kowalski",
                }
            ],
            "facts": [
                {
                    "fact_type": FactType.APPOINTMENT.value,
                    "subject_key": "person_1",
                    "object_key": "missing_org",
                    "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
                }
            ],
        }
    )

    result = LLMExtractionAdapter().apply(document, [candidate_set])

    assert result.facts == []


def test_llm_adapter_drops_nonexistent_evidence_quote() -> None:
    document = make_document()
    candidate_set = candidates_from_payload(
        {
            "is_relevant": True,
            "entities": [
                {
                    "key": "person_1",
                    "entity_type": EntityType.PERSON.value,
                    "canonical_name": "Jan Kowalski",
                }
            ],
            "facts": [
                {
                    "fact_type": FactType.PARTY_MEMBERSHIP.value,
                    "subject_key": "person_1",
                    "object_key": None,
                    "evidence_quote": "Tego zdania nie ma w artykule.",
                }
            ],
        }
    )

    result = LLMExtractionAdapter().apply(document, [candidate_set])

    assert result.facts == []


def test_llm_adapter_deduplicates_facts() -> None:
    document = make_document()
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": EntityType.PERSON.value,
                "canonical_name": "Jan Kowalski",
            }
        ],
        "facts": [
            {
                "fact_type": FactType.PARTY_MEMBERSHIP.value,
                "subject_key": "person_1",
                "object_key": None,
                "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
            },
            {
                "fact_type": FactType.PARTY_MEMBERSHIP.value,
                "subject_key": "person_1",
                "object_key": None,
                "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
            },
        ],
    }

    result = LLMExtractionAdapter().apply(document, [candidates_from_payload(payload)])

    assert len(result.facts) == 1


def test_candidates_from_payload_rejects_invalid_enum_without_try_except_flow() -> None:
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": "Alien",
                "canonical_name": "Jan Kowalski",
            }
        ],
        "facts": [],
    }

    with pytest.raises(ValueError, match="Unknown LLM entity type"):
        candidates_from_payload(payload)


def test_engine_rules_is_default_when_selecting_pipeline(monkeypatch) -> None:
    config = make_config()
    args = argparse.Namespace(
        engine="rules",
        llm_model=None,
        llm_host=None,
        llm_model_path=None,
        llm_context_size=None,
        llm_gpu_layers=None,
        llm_max_output_tokens=None,
        llm_chat_format=None,
        llm_temperature=None,
    )
    calls: list[PipelineConfig] = []

    def fake_build_pipeline(selected_config: PipelineConfig):
        calls.append(selected_config)
        return object()

    monkeypatch.setattr("pipeline.cli.build_pipeline", fake_build_pipeline)

    selected = select_pipeline(args, config)

    assert selected is not None
    assert calls == [config]


def test_engine_llm_builds_single_reused_runner(tmp_path) -> None:
    class FakeClient:
        def create_chat_completion(
            self,
            *,
            messages: list[dict[str, str]],
            response_format,
            temperature: float,
            max_tokens: int,
        ):
            assert messages
            assert response_format["type"] == "json_object"
            return {"message": {"content": '{"is_relevant": false, "entities": [], "facts": []}'}}

    config = make_config()
    runner = OllamaLLMExtractionPipeline(config, client_factory=lambda _: FakeClient())
    html_a = tmp_path / "a.html"
    html_b = tmp_path / "b.html"
    html_a.write_text(
        '<html><head><title>A</title><meta name="description" '
        'content="Krótki tekst artykułu o sprawach publicznych."></head></html>',
        encoding="utf-8",
    )
    html_b.write_text(
        '<html><head><title>B</title><meta name="description" '
        'content="Drugi tekst artykułu o sprawach publicznych."></head></html>',
        encoding="utf-8",
    )

    first = runner.run(PipelineInput(raw_html=html_a.read_text(encoding="utf-8"), document_id="a"))
    second = runner.run(PipelineInput(raw_html=html_b.read_text(encoding="utf-8"), document_id="b"))

    assert first.document_id == "a"
    assert second.document_id == "b"
    assert runner.client is runner.client


def test_llm_adapter_maps_value_text_to_amount_for_public_money_fact() -> None:
    document = make_document()
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": EntityType.PERSON.value,
                "canonical_name": "Anna Kowalska",
            }
        ],
        "facts": [
            {
                "fact_type": FactType.COMPENSATION.value,
                "subject_key": "person_1",
                "object_key": None,
                "value_text": "100 tys. zł",
                "evidence_quote": "Jego żona Anna Kowalska dostała dotację 100 tys. zł.",
            }
        ],
    }

    result = LLMExtractionAdapter().apply(document, [candidates_from_payload(payload)])

    assert len(result.facts) == 1
    assert result.facts[0].amount_text == "100 tys. zł"
    assert result.facts[0].value_text == "100 tys. zł"
    assert result.facts[0].role is None


def test_configured_ollama_model_prefers_explicit_model() -> None:
    config = make_config()
    config.llm.model_path = "legacy-model"

    assert _configured_ollama_model(config) == "gemma4:latest"


def test_configured_ollama_model_falls_back_to_legacy_model_path() -> None:
    config = make_config()
    config.llm.model = ""
    config.llm.model_path = "legacy-model"

    assert _configured_ollama_model(config) == "legacy-model"


def test_configured_ollama_model_requires_model() -> None:
    config = make_config()
    config.llm.model = ""
    config.llm.model_path = None

    with pytest.raises(ValueError, match="llm.model"):
        _configured_ollama_model(config)
