from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

from pipeline.domain_types import EntityType, FactType

EntityKey = NewType("EntityKey", str)


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
