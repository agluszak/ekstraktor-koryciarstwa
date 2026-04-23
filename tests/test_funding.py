from pipeline.domain_types import (
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FrameID,
    OrganizationKind,
)
from pipeline.funding import FundingFactBuilder
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    EntityCluster,
    EvidenceSpan,
    FundingFrame,
)


def cluster(
    cluster_id: str,
    name: str,
    entity_type: EntityType = EntityType.ORGANIZATION,
    *,
    sentence_index: int = 0,
    start_char: int = 0,
    end_char: int | None = None,
    entity_id: str | None = None,
    organization_kind: OrganizationKind | None = None,
) -> EntityCluster:
    return EntityCluster(
        cluster_id=ClusterID(cluster_id),
        entity_type=entity_type,
        canonical_name=name,
        normalized_name=name,
        mentions=[
            ClusterMention(
                text=name,
                entity_type=entity_type,
                sentence_index=sentence_index,
                paragraph_index=0,
                start_char=start_char,
                end_char=end_char if end_char is not None else start_char + len(name),
                entity_id=EntityID(entity_id)
                if entity_id
                else EntityID(cluster_id.replace("cluster-", "entity-")),
            )
        ],
        aliases=[name],
        organization_kind=organization_kind,
    )


def document(clusters: list[EntityCluster]) -> ArticleDocument:
    return ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url="http://test.com",
        raw_html="",
        title="Test Doc",
        publication_date="2024-01-01",
        cleaned_text="",
        paragraphs=[],
        clusters=clusters,
    )


def test_funding_fact_builder_emits_recipient_funded_by_funder_fact() -> None:
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id=EntityID("org-funder"),
    )
    recipient = cluster(
        "cluster-recipient", "Fundacja Lux Veritatis", entity_id=EntityID("org-recipient")
    )
    doc = document([funder, recipient])
    doc.funding_frames = [
        FundingFrame(
            frame_id=FrameID("funding-frame-1"),
            amount_text="300 tys. zł",
            amount_normalized="300 Tys. Zł",
            funder_cluster_id=funder.cluster_id,
            recipient_cluster_id=recipient.cluster_id,
            confidence=0.82,
            evidence=[
                EvidenceSpan(
                    text="WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji.",
                    paragraph_index=0,
                )
            ],
            extraction_signal="syntactic_direct",
            evidence_scope="same_clause",
            score_reason="funder_recipient_amount_same_clause",
        )
    ]

    facts = FundingFactBuilder().build(doc)

    assert len(facts) == 1
    assert facts[0].fact_type == "FUNDING"
    assert facts[0].subject_entity_id == "org-recipient"
    assert facts[0].object_entity_id == "org-funder"
    assert facts[0].source_extractor == "funding_frame"


def test_funding_fact_builder_no_subject_id_returns_none() -> None:
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id=EntityID("org-funder"),
    )
    doc = document([funder])
    doc.funding_frames = [
        FundingFrame(
            frame_id=FrameID("funding-frame-1"),
            amount_text="300 tys. zł",
            amount_normalized="300 Tys. Zł",
            funder_cluster_id=funder.cluster_id,
            recipient_cluster_id=None,
            project_cluster_id=None,
            confidence=0.82,
            evidence=[
                EvidenceSpan(
                    text="WFOŚiGW przekazał 300 tys. zł dotacji.",
                    paragraph_index=0,
                )
            ],
        )
    ]

    facts = FundingFactBuilder().build(doc)
    assert len(facts) == 0


def test_funding_fact_builder_get_best_entity_id() -> None:
    # 1. Has common entity id
    c1 = cluster("cluster-1", "A")
    c1.mentions = [
        ClusterMention("A", EntityType.ORGANIZATION, 0, 0, 0, 1, EntityID("e1")),
        ClusterMention("A", EntityType.ORGANIZATION, 0, 0, 0, 1, EntityID("e1")),
        ClusterMention("A", EntityType.ORGANIZATION, 0, 0, 0, 1, EntityID("e2")),
    ]
    assert FundingFactBuilder._get_best_entity_id(c1) == "e1"

    # 2. Falls back to cluster id
    c2 = cluster("cluster-2", "B")
    c2.mentions = [
        ClusterMention("B", EntityType.ORGANIZATION, 0, 0, 0, 1, None),
    ]
    assert FundingFactBuilder._get_best_entity_id(c2) == "cluster-2"


def test_funding_fact_builder_deduplication() -> None:
    funder = cluster("cluster-funder", "WFOŚiGW", entity_id=EntityID("org-funder"))
    recipient = cluster(
        "cluster-recipient", "Fundacja Lux Veritatis", entity_id=EntityID("org-recipient")
    )
    doc = document([funder, recipient])

    # Create two identical frames (same subject, object, normalized amount, and evidence text),
    # but with different confidences. The one with higher confidence should be kept.
    frame_low_conf = FundingFrame(
        frame_id=FrameID("funding-frame-low"),
        amount_normalized="300 Tys. Zł",
        funder_cluster_id=funder.cluster_id,
        recipient_cluster_id=recipient.cluster_id,
        confidence=0.5,
        evidence=[
            EvidenceSpan(text="WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji.")
        ],
    )
    frame_high_conf = FundingFrame(
        frame_id=FrameID("funding-frame-high"),
        amount_normalized="300 Tys. Zł",
        funder_cluster_id=funder.cluster_id,
        recipient_cluster_id=recipient.cluster_id,
        confidence=0.9,
        evidence=[
            EvidenceSpan(text="WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji.")
        ],
    )

    doc.funding_frames = [frame_low_conf, frame_high_conf]
    facts = FundingFactBuilder().build(doc)

    assert len(facts) == 1
    assert facts[0].confidence == 0.9


def test_funding_fact_builder_extracts_funder_organization_kind() -> None:
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id=EntityID("org-funder"),
        organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
    )
    recipient = cluster(
        "cluster-recipient", "Fundacja Lux Veritatis", entity_id=EntityID("org-recipient")
    )
    doc = document([funder, recipient])
    doc.funding_frames = [
        FundingFrame(
            frame_id=FrameID("funding-frame-1"),
            amount_text="300 tys. zł",
            amount_normalized="300 Tys. Zł",
            funder_cluster_id=funder.cluster_id,
            recipient_cluster_id=recipient.cluster_id,
            confidence=0.82,
            evidence=[EvidenceSpan(text="WFOŚiGW przekazał 300 tys. zł dotacji.")],
        )
    ]

    facts = FundingFactBuilder().build(doc)

    assert len(facts) == 1
    assert facts[0].organization_kind == OrganizationKind.PUBLIC_INSTITUTION
