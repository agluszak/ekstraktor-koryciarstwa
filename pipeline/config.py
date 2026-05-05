from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class ModelConfig:
    spacy_model: str
    sentence_transformer_model: str
    stanza_coref_model_path: str


@dataclass(slots=True)
class PatternConfig:
    appointment_verbs: list[str]
    dismissal_verbs: list[str]
    board_terms: list[str]
    state_company_markers: list[str]
    qualification_markers: list[str]


@dataclass(slots=True)
class ScoreConfig:
    political_tie: float
    family_tie: float
    board_position: float
    state_company: float
    qualification_gap: float
    dismissal_signal: float


@dataclass(slots=True)
class RegistryConfig:
    similarity_threshold: float
    db_path: str | None = None


@dataclass(slots=True)
class LLMConfig:
    model: str = "gemma4:latest"
    base_url: str = "http://127.0.0.1:11434"
    model_path: str | None = None
    context_size: int = 16384
    max_output_tokens: int = 4096
    temperature: float = 0.0
    request_timeout_seconds: int = 300


@dataclass(slots=True)
class PipelineConfig:
    models: ModelConfig
    keywords: list[str]
    party_aliases: dict[str, str]
    institution_aliases: dict[str, str]
    patterns: PatternConfig
    score_weights: ScoreConfig
    registry: RegistryConfig
    llm: LLMConfig

    @classmethod
    def from_file(cls, path: str | Path) -> "PipelineConfig":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            models=ModelConfig(**payload["models"]),
            keywords=payload["keywords"],
            party_aliases=payload["party_aliases"],
            institution_aliases=payload.get("institution_aliases", {}),
            patterns=PatternConfig(**payload["patterns"]),
            score_weights=ScoreConfig(**payload["score_weights"]),
            registry=RegistryConfig(**payload["registry"]),
            llm=LLMConfig(**payload.get("llm", {})),
        )
