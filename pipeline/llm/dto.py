from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, TypedDict

from pipeline.domain_types import EntityType, FactType

EntityKey = NewType("EntityKey", str)


class LLMEntityPayload(TypedDict):
    key: str
    entity_type: str
    canonical_name: str


class LLMFactPayload(TypedDict, total=False):
    fact_type: str
    subject_key: str
    object_key: str | None
    value_text: str | None
    evidence_quote: str


class LLMExtractionPayload(TypedDict):
    is_relevant: bool
    entities: list[LLMEntityPayload]
    facts: list[LLMFactPayload]


@dataclass(slots=True)
class LLMEntityCandidate:
    key: EntityKey
    entity_type: EntityType
    canonical_name: str


@dataclass(slots=True)
class LLMFactCandidate:
    fact_type: FactType
    subject_key: EntityKey
    object_key: EntityKey | None
    evidence_quote: str
    value_text: str | None = None


@dataclass(slots=True)
class LLMExtractionCandidateSet:
    is_relevant: bool
    entities: list[LLMEntityCandidate]
    facts: list[LLMFactCandidate]
