from __future__ import annotations

import argparse

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
from pipeline.domain_types import FactType
from pipeline.llm.adapter import candidates_from_payload
from pipeline.llm.engine import OllamaLLMEngine

pytestmark = pytest.mark.llm


def make_config() -> PipelineConfig:
    return PipelineConfig(
        models=ModelConfig(
            spacy_model="pl_core_news_lg",
            sentence_transformer_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            stanza_coref_model_path="models/stanza/pl/coref/udcoref_xlm-roberta-lora-v1.12.0.patched.pt",
        ),
        keywords=["prezes", "dotacja", "żona"],
        party_aliases={
            "Razem": "Razem",
            "PO": "Platforma Obywatelska",
            "Platforma Obywatelska": "Platforma Obywatelska",
            "PSL": "Polskie Stronnictwo Ludowe",
            "Polskie Stronnictwo Ludowe": "Polskie Stronnictwo Ludowe",
        },
        institution_aliases={},
        patterns=PatternConfig(
            appointment_verbs=[],
            dismissal_verbs=[],
            board_terms=[],
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


def test_ollama_llm_engine_initialization() -> None:
    config = make_config()
    engine = OllamaLLMEngine(config)
    assert engine.name() == "ollama_llm_engine"


def test_candidates_from_payload_valid() -> None:
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": "Person",
                "canonical_name": "Jan Kowalski",
            }
        ],
        "facts": [
            {
                "fact_type": "APPOINTMENT",
                "subject_key": "person_1",
                "object_key": None,
                "evidence_quote": "Jan Kowalski został powołany",
            }
        ],
    }
    result = candidates_from_payload(payload)
    assert result.is_relevant is True
    assert len(result.entities) == 1
    assert result.entities[0].canonical_name == "Jan Kowalski"
    assert len(result.facts) == 1
    assert result.facts[0].fact_type == FactType.APPOINTMENT


def test_candidates_from_payload_rejects_invalid_schema() -> None:
    payload = {"invalid": "schema"}
    with pytest.raises(ValueError, match="LLM response does not match schema"):
        candidates_from_payload(payload)


def test_candidates_from_payload_rejects_invalid_enum() -> None:
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "alien_1",
                "entity_type": "Alien",
                "canonical_name": "Zorg",
            }
        ],
        "facts": [],
    }

    with pytest.raises(ValueError, match="LLM response does not match schema"):
        candidates_from_payload(payload)


def test_engine_rules_is_default_when_selecting_pipeline(monkeypatch) -> None:
    config = make_config()
    args = argparse.Namespace(
        engine="rules",
        llm_model=None,
        llm_host=None,
        llm_model_path=None,
        llm_context_size=None,
        llm_max_output_tokens=None,
        llm_temperature=None,
    )
    pipeline = select_pipeline(args, config)
    assert any(stage.name() == "spacy_polish_ner_extractor" for stage in pipeline.stages)
    assert not any(stage.name() == "ollama_llm_engine" for stage in pipeline.stages)


def test_engine_llm_is_opt_in_when_selecting_pipeline() -> None:
    config = make_config()
    args = argparse.Namespace(
        engine="llm",
        llm_model="custom-model",
        llm_host="http://localhost:11434",
        llm_model_path=None,
        llm_context_size=8192,
        llm_max_output_tokens=1024,
        llm_temperature=0.7,
    )
    pipeline = select_pipeline(args, config)
    assert config.llm.model == "custom-model"
    assert config.llm.base_url == "http://localhost:11434"
    assert config.llm.context_size == 8192
    assert config.llm.max_output_tokens == 1024
    assert config.llm.temperature == 0.7
    assert any(stage.name() == "ollama_llm_engine" for stage in pipeline.stages)
    assert not any(stage.name() == "spacy_polish_ner_extractor" for stage in pipeline.stages)
