from __future__ import annotations

from pipeline.domain_types import EntityType, FactType, Json


def build_llm_response_schema() -> dict[str, Json]:
    entity_schema: dict[str, Json] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["key", "entity_type", "canonical_name"],
        "properties": {
            "key": {"type": "string", "minLength": 1},
            "entity_type": {"type": "string", "enum": [item.value for item in EntityType]},
            "canonical_name": {"type": "string", "minLength": 1},
        },
    }
    fact_schema: dict[str, Json] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["fact_type", "subject_key", "object_key", "evidence_quote"],
        "properties": {
            "fact_type": {"type": "string", "enum": [item.value for item in FactType]},
            "subject_key": {"type": "string", "minLength": 1},
            "object_key": {"type": ["string", "null"]},
            "value_text": {"type": ["string", "null"]},
            "evidence_quote": {"type": "string", "minLength": 1},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["is_relevant", "entities", "facts"],
        "properties": {
            "is_relevant": {"type": "boolean"},
            "entities": {"type": "array", "items": entity_schema},
            "facts": {"type": "array", "items": fact_schema},
        },
    }
