from __future__ import annotations

from collections.abc import Iterable, Mapping

from pipeline.domain_types import (
    EntityID,
    EntityType,
    FactType,
    TimeScope,
)
from pipeline.llm.dto import (
    EntityKey,
    LLMEntityCandidate,
    LLMExtractionCandidateSet,
    LLMFactCandidate,
)
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Fact, RelevanceDecision
from pipeline.utils import generate_entity_id, generate_fact_id, normalize_entity_name


class LLMExtractionAdapter:
    FACT_CONFIDENCE = 0.8

    def apply(
        self,
        document: ArticleDocument,
        chunks: Iterable[LLMExtractionCandidateSet],
    ) -> ArticleDocument:
        entities_by_key: dict[EntityKey, Entity] = {}
        facts: list[Fact] = []
        is_relevant = False

        for chunk in chunks:
            is_relevant = is_relevant or chunk.is_relevant
            for candidate in chunk.entities:
                if candidate.key not in entities_by_key:
                    entities_by_key[candidate.key] = self._entity_from_candidate(
                        document,
                        candidate,
                    )
                else:
                    self._merge_entity(entities_by_key[candidate.key], candidate, document)

        for chunk in chunks:
            facts.extend(
                self._facts_from_candidates(
                    document,
                    chunk.facts,
                    entities_by_key,
                )
            )

        document.relevance = RelevanceDecision(
            is_relevant=is_relevant,
            score=1.0 if is_relevant else 0.0,
            reasons=["llm extraction decision"],
        )
        document.entities = list(entities_by_key.values())
        document.facts = _deduplicate_facts(facts)
        return document

    def _entity_from_candidate(
        self,
        document: ArticleDocument,
        candidate: LLMEntityCandidate,
    ) -> Entity:
        canonical_name = normalize_entity_name(candidate.canonical_name)
        entity_id = generate_entity_id(
            "llm_entity",
            str(document.document_id),
            str(candidate.key),
            canonical_name,
        )
        aliases = [canonical_name]
        return Entity(
            entity_id=entity_id,
            entity_type=candidate.entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name.casefold(),
            aliases=aliases,
            evidence=_entity_evidence(document, candidate.canonical_name, canonical_name),
        )

    def _merge_entity(
        self,
        entity: Entity,
        candidate: LLMEntityCandidate,
        document: ArticleDocument,
    ) -> None:
        normalized_name = normalize_entity_name(candidate.canonical_name)
        aliases = _unique_nonempty([*entity.aliases, normalized_name])
        entity.aliases = aliases
        existing_spans = {(span.start_char, span.end_char, span.text) for span in entity.evidence}
        mentions = _unique_nonempty([candidate.canonical_name, normalized_name])
        for mention in mentions:
            span = _first_span(document, mention)
            if span is None:
                continue
            key = (span.start_char, span.end_char, span.text)
            if key not in existing_spans:
                entity.evidence.append(span)
                existing_spans.add(key)

    def _facts_from_candidates(
        self,
        document: ArticleDocument,
        candidates: Iterable[LLMFactCandidate],
        entities_by_key: Mapping[EntityKey, Entity],
    ) -> list[Fact]:
        facts: list[Fact] = []
        for candidate in candidates:
            subject = entities_by_key.get(candidate.subject_key)
            object_entity = (
                entities_by_key.get(candidate.object_key)
                if candidate.object_key is not None
                else None
            )
            if subject is None:
                continue
            if candidate.object_key is not None and object_entity is None:
                continue
            evidence = _first_span(document, candidate.evidence_quote)
            if evidence is None:
                continue
            facts.append(
                self._fact_from_candidate(document, candidate, subject, object_entity, evidence)
            )
        return facts

    @staticmethod
    def _fact_from_candidate(
        document: ArticleDocument,
        candidate: LLMFactCandidate,
        subject: Entity,
        object_entity: Entity | None,
        evidence: EvidenceSpan,
    ) -> Fact:
        value_text = candidate.value_text
        role = _role_value(candidate.fact_type, value_text)
        amount = _amount_value(candidate.fact_type, value_text)
        return Fact(
            fact_id=generate_fact_id(
                "llm_fact",
                str(document.document_id),
                candidate.fact_type.value,
                str(subject.entity_id),
                str(object_entity.entity_id) if object_entity is not None else "",
                evidence.text,
                value_text or "",
            ),
            fact_type=candidate.fact_type,
            subject_entity_id=subject.entity_id,
            object_entity_id=object_entity.entity_id if object_entity is not None else None,
            value_text=value_text,
            value_normalized=value_text.casefold() if value_text else None,
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=LLMExtractionAdapter.FACT_CONFIDENCE,
            evidence=evidence,
            role=role,
            board_role=_looks_like_board_role(role),
            amount_text=amount,
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        )


def candidates_from_payload(payload: object) -> LLMExtractionCandidateSet:
    payload = _object_mapping(payload, "LLM response")
    required_keys = {"is_relevant", "entities", "facts"}
    extra_keys = set(payload) - required_keys
    missing_keys = required_keys - set(payload)
    if extra_keys or missing_keys:
        raise ValueError("LLM response does not match the expected top-level schema")

    entities_payload = payload["entities"]
    facts_payload = payload["facts"]
    if not isinstance(entities_payload, list):
        raise ValueError("LLM response field 'entities' must be a list")
    if not isinstance(facts_payload, list):
        raise ValueError("LLM response field 'facts' must be a list")

    return LLMExtractionCandidateSet(
        is_relevant=_required_bool(payload, "is_relevant"),
        entities=[_entity_candidate(item) for item in entities_payload],
        facts=[_fact_candidate(item) for item in facts_payload],
    )


def _entity_candidate(payload: object) -> LLMEntityCandidate:
    payload = _object_mapping(payload, "LLM entity item")
    required_keys = {"key", "entity_type", "canonical_name"}
    if set(payload) != required_keys:
        raise ValueError("LLM entity item does not match the expected schema")
    entity_type = _entity_type(_required_str(payload, "entity_type"))
    return LLMEntityCandidate(
        key=EntityKey(_required_str(payload, "key")),
        entity_type=entity_type,
        canonical_name=_required_str(payload, "canonical_name"),
    )


def _fact_candidate(payload: object) -> LLMFactCandidate:
    payload = _object_mapping(payload, "LLM fact item")
    allowed_keys = {
        "fact_type",
        "subject_key",
        "object_key",
        "value_text",
        "evidence_quote",
    }
    required_keys = {"fact_type", "subject_key", "object_key", "evidence_quote"}
    if not required_keys.issubset(payload) or set(payload) - allowed_keys:
        raise ValueError("LLM fact item does not match the expected schema")
    return LLMFactCandidate(
        fact_type=_fact_type(_required_str(payload, "fact_type")),
        subject_key=EntityKey(_required_str(payload, "subject_key")),
        object_key=_optional_entity_key(payload.get("object_key")),
        evidence_quote=_required_str(payload, "evidence_quote"),
        value_text=_optional_str(payload.get("value_text")),
    )


def _first_span(document: ArticleDocument, quote: str) -> EvidenceSpan | None:
    normalized_quote = " ".join(quote.split())
    if not normalized_quote:
        return None
    start = document.cleaned_text.find(normalized_quote)
    if start < 0:
        return None
    end = start + len(normalized_quote)
    sentence = next(
        (item for item in document.sentences if item.start_char <= start and end <= item.end_char),
        None,
    )
    return EvidenceSpan(
        text=normalized_quote,
        sentence_index=sentence.sentence_index if sentence is not None else None,
        paragraph_index=sentence.paragraph_index if sentence is not None else None,
        start_char=start,
        end_char=end,
    )


def _entity_type(value: str) -> EntityType:
    by_value = {item.value: item for item in EntityType}
    if value not in by_value:
        raise ValueError(f"Unknown LLM entity type: {value}")
    return by_value[value]


def _fact_type(value: str) -> FactType:
    by_value = {item.value: item for item in FactType}
    if value not in by_value:
        raise ValueError(f"Unknown LLM fact type: {value}")
    return by_value[value]


def _optional_entity_key(value: object) -> EntityKey | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("object_key must be a string or null")
    return EntityKey(value)


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"LLM field {key!r} must be a non-empty string")
    return value


def _object_mapping(payload: object, label: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be an object")
    output: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} object keys must be strings")
        output[key] = value
    return output


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"LLM field {key!r} must be a boolean")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Optional text fields must be strings or null")
    return value or None


def _unique_nonempty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _deduplicate_facts(facts: Iterable[Fact]) -> list[Fact]:
    seen: set[tuple[FactType, EntityID, EntityID | None, str, str | None]] = set()
    output: list[Fact] = []
    for fact in facts:
        key = (
            fact.fact_type,
            fact.subject_entity_id,
            fact.object_entity_id,
            fact.evidence.text,
            fact.value_normalized,
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(fact)
    return output


def _looks_like_board_role(role: str | None) -> bool:
    if role is None:
        return False
    lowered = role.casefold()
    return any(marker in lowered for marker in ("prezes", "zarząd", "rada nadzorcza"))


def _entity_evidence(
    document: ArticleDocument,
    raw_name: str,
    normalized_name: str,
) -> list[EvidenceSpan]:
    evidence: list[EvidenceSpan] = []
    for mention in _unique_nonempty([raw_name, normalized_name]):
        span = _first_span(document, mention)
        if span is None:
            continue
        evidence.append(span)
        if len(evidence) >= 2:
            break
    return evidence


def _role_value(fact_type: FactType, value_text: str | None) -> str | None:
    if value_text is None:
        return None
    if fact_type in {
        FactType.APPOINTMENT,
        FactType.DISMISSAL,
        FactType.ROLE_HELD,
        FactType.POLITICAL_OFFICE,
    }:
        return value_text
    return None


def _amount_value(fact_type: FactType, value_text: str | None) -> str | None:
    if value_text is None:
        return None
    if fact_type in {
        FactType.COMPENSATION,
        FactType.FUNDING,
        FactType.PUBLIC_CONTRACT,
    }:
        return value_text
    return None
