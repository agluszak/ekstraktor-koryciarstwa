from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, cast

from pipeline.domain_types import (
    CandidateAttributes,
    CandidateType,
    EntityAttributes,
    EntityType,
    EventAttributes,
    EventType,
    FactAttributes,
    FactType,
    TimeScope,
)


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
    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    aliases: list[str] = field(default_factory=list)
    attributes: EntityAttributes = field(default_factory=lambda: cast(EntityAttributes, {}))
    evidence: list[EvidenceSpan] = field(default_factory=list)


@dataclass(slots=True)
class Fact:
    fact_id: str
    fact_type: FactType
    subject_entity_id: str
    object_entity_id: str | None
    value_text: str | None
    value_normalized: str | None
    time_scope: TimeScope
    event_date: str | None
    confidence: float
    evidence: EvidenceSpan
    attributes: FactAttributes = field(default_factory=lambda: cast(FactAttributes, {}))


@dataclass(slots=True)
class Event:
    event_id: str
    event_type: EventType
    person_entity_id: str | None
    organization_entity_id: str | None
    position_entity_id: str | None
    event_date: str | None
    confidence: float
    evidence: EvidenceSpan
    attributes: EventAttributes = field(default_factory=lambda: cast(EventAttributes, {}))


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
class EntityCandidate:
    candidate_id: str
    entity_id: str | None
    candidate_type: CandidateType
    canonical_name: str
    normalized_name: str
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int
    source: str
    attributes: CandidateAttributes = field(default_factory=lambda: cast(CandidateAttributes, {}))


@dataclass(slots=True)
class CandidateEdge:
    edge_type: str
    source_candidate_id: str
    target_candidate_id: str
    confidence: float
    sentence_index: int
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateGraph:
    candidates: list[EntityCandidate] = field(default_factory=list)
    edges: list[CandidateEdge] = field(default_factory=list)


@dataclass(slots=True)
class SentenceFragment:
    text: str
    paragraph_index: int
    sentence_index: int
    start_char: int
    end_char: int
    is_candidate: bool = False


@dataclass(slots=True)
class ParsedWord:
    index: int
    text: str
    lemma: str
    upos: str
    head: int
    deprel: str
    start: int
    end: int


@dataclass(slots=True)
class ParsedSentence:
    start_char: int
    end_char: int
    words: list[ParsedWord]


@dataclass(slots=True)
class Mention:
    text: str
    normalized_text: str
    mention_type: str
    sentence_index: int
    entity_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClusterMention:
    text: str
    entity_type: EntityType
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int
    entity_id: str | None = None


@dataclass(slots=True)
class EntityCluster:
    cluster_id: str
    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    mentions: list[ClusterMention]
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClauseUnit:
    clause_id: str
    text: str
    trigger_head_text: str
    trigger_head_lemma: str
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int
    cluster_mentions: list[ClusterMention] = field(default_factory=list)
    mention_roles: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class GovernanceFrame:
    frame_id: str
    event_type: EventType
    person_cluster_id: str | None = None
    role_cluster_id: str | None = None
    target_org_cluster_id: str | None = None
    owner_context_cluster_id: str | None = None
    governing_body_cluster_id: str | None = None
    appointing_authority_cluster_id: str | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompensationFrame:
    frame_id: str
    amount_text: str
    amount_normalized: str
    period: str | None = None
    person_cluster_id: str | None = None
    role_cluster_id: str | None = None
    organization_cluster_id: str | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FundingFrame:
    frame_id: str
    amount_text: str | None = None
    amount_normalized: str | None = None
    funder_cluster_id: str | None = None
    recipient_cluster_id: str | None = None
    project_cluster_id: str | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)
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
    candidate_graph: CandidateGraph | None = None
    facts: list[Fact] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    relevance: RelevanceDecision | None = None
    score: ScoreResult | None = None
    clusters: list[EntityCluster] = field(default_factory=list)
    parsed_sentences: dict[int, list[ParsedWord]] = field(default_factory=dict)
    clause_units: list[ClauseUnit] = field(default_factory=list)
    governance_frames: list[GovernanceFrame] = field(default_factory=list)
    compensation_frames: list[CompensationFrame] = field(default_factory=list)
    funding_frames: list[FundingFrame] = field(default_factory=list)


@dataclass(slots=True)
class ExtractionResult:
    document_id: str
    source_url: str | None
    title: str
    publication_date: str | None
    relevance: RelevanceDecision
    entities: list[Entity]
    facts: list[Fact]
    events: list[Event]
    score: ScoreResult | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_document_id(source_url: str | None, publication_date: str | None) -> str:
    slug = (source_url or "local-document").rstrip("/").split("/")[-1] or "document"
    date_prefix = publication_date or date.today().isoformat()
    return f"{date_prefix}:{slug}"
