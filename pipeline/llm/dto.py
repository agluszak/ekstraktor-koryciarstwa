from __future__ import annotations

from typing import NewType

from pydantic import BaseModel, ConfigDict, Field

from pipeline.domain_types import EntityType, FactType

EntityKey = NewType("EntityKey", str)


class LLMEntityCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: EntityKey
    entity_type: EntityType
    canonical_name: str


class LLMFactCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_type: FactType
    subject_key: EntityKey
    object_key: EntityKey | None = None
    value_text: str | None = None
    evidence_quote: str


class LLMExtractionCandidateSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_relevant: bool
    entities: list[LLMEntityCandidate] = Field(default_factory=list)
    facts: list[LLMFactCandidate] = Field(default_factory=list)
