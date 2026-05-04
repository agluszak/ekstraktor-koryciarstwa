from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    ClauseID,
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FactID,
    FactType,
    FrameID,
    GovernanceSignal,
    IdentityHypothesisReason,
    IdentityHypothesisStatus,
    KinshipDetail,
    NERLabel,
    OrganizationKind,
    ProxyKind,
    PublicEmploymentSignal,
    RelationshipType,
    RoleKind,
    RoleModifier,
    TimeScope,
)


@dataclass(slots=True)
class PipelineInput:
    raw_html: str
    source_url: str | None = None
    publication_date: str | None = None
    document_id: DocumentID | str | None = None


@dataclass(slots=True)
class EvidenceSpan:
    text: str
    sentence_index: int | None = None
    paragraph_index: int | None = None
    start_char: int | None = None
    end_char: int | None = None


@dataclass(slots=True)
class TemporalExpression:
    text: str
    label: NERLabel
    normalized_value: str | None = None
    sentence_index: int | None = None
    paragraph_index: int | None = None
    start_char: int | None = None
    end_char: int | None = None


@dataclass(slots=True)
class Entity:
    entity_id: EntityID
    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    aliases: list[str] = field(default_factory=list)
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    registry_id: str | None = None
    lemmas: list[str] = field(default_factory=list)
    organization_kind: OrganizationKind | None = None
    is_proxy_person: bool = False
    is_honorific_person_ref: bool = False
    proxy_kind: ProxyKind | None = None
    kinship_detail: KinshipDetail | None = None
    proxy_anchor_entity_id: EntityID | None = None
    proxy_surface: str | None = None
    role_kind: RoleKind | None = None
    role_modifier: RoleModifier | None = None


@dataclass(slots=True)
class IdentityHypothesis:
    left_entity_id: EntityID
    right_entity_id: EntityID
    confidence: float
    reason: IdentityHypothesisReason
    evidence: list[EvidenceSpan] = field(default_factory=list)
    status: IdentityHypothesisStatus = IdentityHypothesisStatus.POSSIBLE


@dataclass(slots=True)
class ConfidenceBreakdown:
    person_role: float | None = None
    role_org: float | None = None


@dataclass(slots=True)
class IdentityResolutionMetadata:
    matched_entity_id: EntityID
    confidence: float
    status: IdentityHypothesisStatus


@dataclass(slots=True)
class Fact:
    fact_id: FactID
    fact_type: FactType
    subject_entity_id: EntityID
    object_entity_id: EntityID | None
    value_text: str | None
    value_normalized: str | None
    time_scope: TimeScope
    event_date: str | None
    confidence: float
    evidence: EvidenceSpan
    position_entity_id: EntityID | None = None
    role: str | None = None
    role_kind: RoleKind | None = None
    role_modifier: RoleModifier | None = None
    board_role: bool = False
    organization_kind: OrganizationKind | None = None
    owner_context_entity_id: EntityID | None = None
    appointing_authority_entity_id: EntityID | None = None
    governing_body_entity_id: EntityID | None = None
    confidence_breakdown: ConfidenceBreakdown | None = None
    party: str | None = None
    office_type: str | None = None
    candidacy_scope: str | None = None
    amount_text: str | None = None
    period: str | None = None
    relationship_type: RelationshipType | None = None
    kinship_detail: KinshipDetail | None = None
    identity_resolution: IdentityResolutionMetadata | None = None
    possible_identity_matches: list[EntityID] = field(default_factory=list)
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    overlaps_governance: bool = False
    source_extractor: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class ScoreResult:
    value: float
    reasons: list[str]


@dataclass(slots=True)
class EntityCandidate:
    candidate_id: CandidateID
    entity_id: EntityID | None
    candidate_type: CandidateType
    canonical_name: str
    normalized_name: str
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int
    source: str

    # Inlined attributes
    organization_kind: OrganizationKind | None = None
    role_kind: RoleKind | None = None
    role_modifier: RoleModifier | None = None
    is_proxy_person: bool = False
    kinship_detail: KinshipDetail | None = None
    mention_type: EntityType | str | None = None
    ner_label: NERLabel | None = None


@dataclass(slots=True)
class CandidateEdge:
    edge_type: str
    source_candidate_id: CandidateID
    target_candidate_id: CandidateID
    confidence: float
    sentence_index: int


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
    feats: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedSentence:
    start_char: int
    end_char: int
    words: list[ParsedWord]


@dataclass(slots=True)
class Mention:
    text: str
    normalized_text: str
    mention_type: EntityType | str
    sentence_index: int
    paragraph_index: int = 0
    start_char: int = 0
    end_char: int = 0
    entity_id: EntityID | None = None

    # Inlined attributes
    lemmas: list[str] = field(default_factory=list)
    ner_label: NERLabel | None = None


@dataclass(slots=True)
class ClusterMention:
    text: str
    entity_type: EntityType
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int
    entity_id: EntityID | None = None
    ner_label: NERLabel | None = None


@dataclass(slots=True)
class EntityCluster:
    cluster_id: ClusterID
    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    mentions: list[ClusterMention]

    # Inlined attributes
    aliases: list[str] = field(default_factory=list)
    lemmas: list[str] = field(default_factory=list)
    organization_kind: OrganizationKind | None = None
    is_proxy_person: bool = False
    proxy_entity_id: EntityID | None = None
    proxy_kind: ProxyKind | None = None
    kinship_detail: KinshipDetail | None = None
    proxy_anchor_entity_id: EntityID | None = None
    role_kind: RoleKind | None = None
    role_modifier: RoleModifier | None = None


@dataclass(slots=True)
class ClauseUnit:
    clause_id: ClauseID
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
    frame_id: FrameID
    signal: GovernanceSignal
    person_cluster_id: ClusterID | None = None
    role_cluster_id: ClusterID | None = None
    target_org_cluster_id: ClusterID | None = None
    owner_context_cluster_id: ClusterID | None = None
    governing_body_cluster_id: ClusterID | None = None
    appointing_authority_cluster_id: ClusterID | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    target_resolution: str | None = None
    found_role: str | None = None
    role_modifier: RoleModifier | None = None
    evidence_scope: str | None = None


@dataclass(slots=True)
class CompensationFrame:
    frame_id: FrameID
    amount_text: str
    amount_normalized: str
    period: str | None = None
    person_cluster_id: ClusterID | None = None
    role_cluster_id: ClusterID | None = None
    organization_cluster_id: ClusterID | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None
    context_reason: str | None = None


@dataclass(slots=True)
class FundingFrame:
    frame_id: FrameID
    amount_text: str | None = None
    amount_normalized: str | None = None
    funder_cluster_id: ClusterID | None = None
    recipient_cluster_id: ClusterID | None = None
    project_cluster_id: ClusterID | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class PublicContractFrame:
    frame_id: FrameID
    contractor_cluster_id: ClusterID
    counterparty_cluster_id: ClusterID
    amount_text: str | None = None
    amount_normalized: str | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class AntiCorruptionReferralFrame:
    frame_id: FrameID
    complainant_cluster_id: ClusterID
    target_cluster_id: ClusterID
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class AntiCorruptionInvestigationFrame:
    frame_id: FrameID
    institution_cluster_id: ClusterID
    target_cluster_id: ClusterID
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class PublicProcurementAbuseFrame:
    frame_id: FrameID
    actor_cluster_id: ClusterID
    public_context_cluster_id: ClusterID | None = None
    amount_text: str | None = None
    amount_normalized: str | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class PublicEmploymentFrame:
    frame_id: FrameID
    signal: PublicEmploymentSignal
    employee_cluster_id: ClusterID
    employer_cluster_id: ClusterID
    role_label: str | None = None
    role_cluster_id: ClusterID | None = None
    confidence: float = 0.0
    evidence: list[EvidenceSpan] = field(default_factory=list)

    # Inlined attributes
    extraction_signal: str | None = None
    evidence_scope: str | None = None
    score_reason: str | None = None


@dataclass(slots=True)
class RelevanceDecision:
    is_relevant: bool
    score: float
    reasons: list[str]


@dataclass(slots=True)
class CoreferenceResult:
    resolved_mentions: list[Mention]


@dataclass(slots=True)
class ArticleDocument:
    document_id: DocumentID | str
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
    temporal_expressions: list[TemporalExpression] = field(default_factory=list)
    relevance: RelevanceDecision | None = None
    score: ScoreResult | None = None
    clusters: list[EntityCluster] = field(default_factory=list)
    parsed_sentences: dict[int, list[ParsedWord]] = field(default_factory=dict)
    clause_units: list[ClauseUnit] = field(default_factory=list)
    governance_frames: list[GovernanceFrame] = field(default_factory=list)
    compensation_frames: list[CompensationFrame] = field(default_factory=list)
    funding_frames: list[FundingFrame] = field(default_factory=list)
    public_contract_frames: list[PublicContractFrame] = field(default_factory=list)
    anti_corruption_referral_frames: list[AntiCorruptionReferralFrame] = field(default_factory=list)
    anti_corruption_investigation_frames: list[AntiCorruptionInvestigationFrame] = field(
        default_factory=list
    )
    public_procurement_abuse_frames: list[PublicProcurementAbuseFrame] = field(default_factory=list)
    public_employment_frames: list[PublicEmploymentFrame] = field(default_factory=list)
    identity_hypotheses: list[IdentityHypothesis] = field(default_factory=list)
    execution_times: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionResult:
    document_id: DocumentID | str
    source_url: str | None
    title: str
    publication_date: str | None
    relevance: RelevanceDecision
    entities: list[Entity]
    facts: list[Fact]
    score: ScoreResult | None
    identity_hypotheses: list[IdentityHypothesis] = field(default_factory=list)
    execution_times: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extraction_result_from_document(document: ArticleDocument) -> ExtractionResult:
    return ExtractionResult(
        document_id=document.document_id,
        source_url=document.source_url,
        title=document.title,
        publication_date=document.publication_date,
        relevance=document.relevance or RelevanceDecision(False, 0.0, []),
        entities=document.entities,
        facts=document.facts,
        score=document.score,
        identity_hypotheses=document.identity_hypotheses,
        execution_times=document.execution_times,
    )
