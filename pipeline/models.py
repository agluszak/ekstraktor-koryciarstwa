from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class PipelineInput:
    raw_html: str
    source_url: str | None = None
    publication_date: str | None = None
    document_id: str | None = None


@dataclass(slots=True)
class EvidenceSpan:
    text: str
    sentence_index: int | None = None
    paragraph_index: int | None = None
    start_char: int | None = None
    end_char: int | None = None


@dataclass(slots=True)
class Entity:
    entity_id: str
    entity_type: str
    canonical_name: str
    normalized_name: str
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceSpan] = field(default_factory=list)


@dataclass(slots=True)
class Relation:
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    confidence: float
    evidence: EvidenceSpan
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Fact:
    fact_id: str
    fact_type: str
    subject_entity_id: str
    object_entity_id: str | None
    value_text: str | None
    value_normalized: str | None
    time_scope: str
    event_date: str | None
    confidence: float
    evidence: EvidenceSpan
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Event:
    event_id: str
    event_type: str
    person_entity_id: str | None
    organization_entity_id: str | None
    position_entity_id: str | None
    event_date: str | None
    confidence: float
    evidence: EvidenceSpan
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreResult:
    value: float
    reasons: list[str]


@dataclass(slots=True)
class GraphNode:
    node_id: str
    label: str
    properties: dict[str, Any]


@dataclass(slots=True)
class GraphEdge:
    edge_id: str
    edge_type: str
    source: str
    target: str
    properties: dict[str, Any]


@dataclass(slots=True)
class GraphExport:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass(slots=True)
class SentenceFragment:
    text: str
    paragraph_index: int
    sentence_index: int
    start_char: int
    end_char: int
    is_candidate: bool = False


@dataclass(slots=True)
class Mention:
    text: str
    normalized_text: str
    mention_type: str
    sentence_index: int
    entity_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RelevanceDecision:
    is_relevant: bool
    score: float
    reasons: list[str]


@dataclass(slots=True)
class CoreferenceResult:
    mention_links: dict[int, str]
    resolved_mentions: list[Mention]


@dataclass(slots=True)
class ArticleDocument:
    document_id: str
    source_url: str | None
    raw_html: str
    title: str
    publication_date: str | None
    cleaned_text: str
    paragraphs: list[str]
    lead_text: str | None = None
    content_source: str = "trafilatura"
    content_quality_flags: list[str] = field(default_factory=list)
    sentences: list[SentenceFragment] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    relevance: RelevanceDecision | None = None
    score: ScoreResult | None = None


@dataclass(slots=True)
class ExtractionResult:
    document_id: str
    source_url: str | None
    title: str
    publication_date: str | None
    relevance: RelevanceDecision
    entities: list[Entity]
    facts: list[Fact]
    relations: list[Relation]
    events: list[Event]
    score: ScoreResult | None
    graph: GraphExport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_document_id(source_url: str | None, publication_date: str | None) -> str:
    slug = (source_url or "local-document").rstrip("/").split("/")[-1] or "document"
    date_prefix = publication_date or date.today().isoformat()
    return f"{date_prefix}:{slug}"
