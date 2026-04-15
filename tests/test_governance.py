from pipeline.compensation import CompensationFactBuilder
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, EventType
from pipeline.frames import PolishCompensationFrameExtractor, PolishFundingFrameExtractor
from pipeline.funding import FundingFactBuilder
from pipeline.governance import GovernanceFactBuilder, GovernanceTargetResolver
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    CompensationFrame,
    EntityCluster,
    EvidenceSpan,
    FundingFrame,
    GovernanceFrame,
    ParsedWord,
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
) -> EntityCluster:
    return EntityCluster(
        cluster_id=cluster_id,
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
                entity_id=entity_id or cluster_id.replace("cluster-", "entity-"),
            )
        ],
        attributes={"aliases": [name]},
    )


def clause(text: str = "Jan został prezesem spółki.") -> ClauseUnit:
    return ClauseUnit(
        clause_id="clause-1",
        text=text,
        trigger_head_text="został",
        trigger_head_lemma="zostać",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=len(text),
    )


def document(clusters: list[EntityCluster]) -> ArticleDocument:
    return ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-15",
        cleaned_text="",
        paragraphs=[],
        clusters=clusters,
    )


def test_target_resolver_prefers_stadnina_over_skarb_panstwa() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    target = cluster("cluster-target", "Stadnina Koni Iwno", start_char=20)
    owner = cluster("cluster-owner", "Skarbu Państwa", start_char=50)

    result = resolver.resolve(
        document=document([target, owner]),
        clause=clause("A. Góralczyk została prezeską Stadniny Koni Iwno, spółki Skarbu Państwa."),
        org_clusters=[target, owner],
        role_cluster=None,
    )

    assert result.target_org == target
    assert result.owner_context == owner


def test_target_resolver_prefers_company_over_ministry_owner() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    target = cluster("cluster-target", "Rewita Hoteli", start_char=30)
    owner = cluster("cluster-owner", "Ministerstwo Obrony Narodowej", start_char=60)

    result = resolver.resolve(
        document=document([target, owner]),
        clause=clause("Marcin Horyń został dyrektorem Rewita Hoteli, spółki podległej MON."),
        org_clusters=[target, owner],
        role_cluster=None,
    )

    assert result.target_org == target
    assert result.owner_context == owner


def test_target_resolver_rejects_generic_polska_for_totalizator() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    totalizator = cluster("cluster-target", "Totalizator Sportowy", start_char=20)
    polska = cluster("cluster-polska", "Polska", start_char=45)

    result = resolver.resolve(
        document=document([totalizator, polska]),
        clause=clause("Adam Sekuła został dyrektorem Totalizatora Sportowego w Polsce."),
        org_clusters=[polska, totalizator],
        role_cluster=None,
    )

    assert result.target_org == totalizator


def test_target_resolver_does_not_use_party_as_target() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    party = cluster("cluster-party", "Polskie Stronnictwo Ludowe", start_char=20)

    result = resolver.resolve(
        document=document([party]),
        clause=clause("Jan Kowalski z PSL został powołany."),
        org_clusters=[party],
        role_cluster=None,
    )

    assert result.target_org is None


def test_governance_fact_builder_merges_duplicate_roleless_fact() -> None:
    person = cluster(
        "cluster-person",
        "Jan Kowalski",
        EntityType.PERSON,
        entity_id="person-1",
    )
    organization = cluster("cluster-org", "AMW Rewita", entity_id="org-1")
    role = cluster(
        "cluster-role",
        "Wiceprezes",
        EntityType.POSITION,
        entity_id="position-1",
    )
    doc = document([person, organization, role])
    doc.governance_frames = [
        GovernanceFrame(
            frame_id="frame-roleless",
            event_type=EventType.APPOINTMENT,
            person_cluster_id=person.cluster_id,
            target_org_cluster_id=organization.cluster_id,
            confidence=0.7,
            evidence=[EvidenceSpan(text="Jan trafił do AMW Rewita.", paragraph_index=0)],
        ),
        GovernanceFrame(
            frame_id="frame-role",
            event_type=EventType.APPOINTMENT,
            person_cluster_id=person.cluster_id,
            role_cluster_id=role.cluster_id,
            target_org_cluster_id=organization.cluster_id,
            confidence=0.8,
            evidence=[
                EvidenceSpan(
                    text="Jan został wiceprezesem AMW Rewita.",
                    paragraph_index=0,
                )
            ],
        ),
    ]

    facts = GovernanceFactBuilder().build(doc)

    assert len(facts) == 1
    assert facts[0].value_text == "Wiceprezes"
    assert facts[0].attributes["position_entity_id"] == "position-1"
    assert facts[0].confidence == 0.8


def test_compensation_fact_builder_emits_person_org_salary_fact() -> None:
    person = cluster(
        "cluster-person",
        "Łukasz Bałajewicz",
        EntityType.PERSON,
        entity_id="person-1",
    )
    organization = cluster("cluster-org", "KZN", entity_id="org-1")
    role = cluster("cluster-role", "Prezes", EntityType.POSITION, entity_id="position-1")
    doc = document([person, organization, role])
    doc.compensation_frames = [
        CompensationFrame(
            frame_id="comp-frame-1",
            amount_text="31 tys. zł brutto",
            amount_normalized="31 Tys. Zł Brutto",
            period="Miesięcznie",
            person_cluster_id=person.cluster_id,
            role_cluster_id=role.cluster_id,
            organization_cluster_id=organization.cluster_id,
            confidence=0.85,
            evidence=[
                EvidenceSpan(
                    text="Łukasz Bałajewicz zarabia miesięcznie ponad 31 tys. zł brutto.",
                    paragraph_index=0,
                )
            ],
            attributes={
                "extraction_signal": "syntactic_direct",
                "evidence_scope": "same_clause",
                "score_reason": "person_amount_role_org_same_clause",
            },
        )
    ]

    facts = CompensationFactBuilder().build(doc)

    assert len(facts) == 1
    assert facts[0].fact_type == "COMPENSATION"
    assert facts[0].subject_entity_id == "person-1"
    assert facts[0].object_entity_id == "org-1"
    assert facts[0].attributes["position_entity_id"] == "position-1"
    assert facts[0].attributes["source_extractor"] == "compensation_frame"


def test_compensation_frame_extractor_ignores_funding_amounts() -> None:
    config = PipelineConfig.from_file("config.yaml")
    fundacja = cluster("cluster-org", "Fundacja Lux Veritatis", entity_id="org-1")
    doc = document([fundacja])
    text = "Fundacja dostała 300 tys. zł dotacji na projekt."
    doc.clause_units = [
        ClauseUnit(
            clause_id="clause-comp-1",
            text=text,
            trigger_head_text="dostała",
            trigger_head_lemma="dostać",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=fundacja.mentions,
        )
    ]

    extracted = PolishCompensationFrameExtractor(config).run(doc)

    assert extracted.compensation_frames == []


def test_compensation_frame_extractor_emits_role_only_salary_frame() -> None:
    config = PipelineConfig.from_file("config.yaml")
    role = cluster("cluster-role", "Dyrektor", EntityType.POSITION, entity_id="position-1")
    org = cluster("cluster-org", "Totalizator Sportowy", entity_id="org-1", start_char=40)
    doc = document([role, org])
    text = "Dyrektorzy Totalizatora Sportowego mogą zarobić ponad 20 tys. zł miesięcznie."
    doc.clause_units = [
        ClauseUnit(
            clause_id="clause-comp-2",
            text=text,
            trigger_head_text="zarobić",
            trigger_head_lemma="zarobić",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=[*role.mentions, *org.mentions],
        )
    ]

    extracted = PolishCompensationFrameExtractor(config).run(doc)

    assert len(extracted.compensation_frames) == 1
    assert extracted.compensation_frames[0].role_cluster_id == "cluster-role"
    assert extracted.compensation_frames[0].organization_cluster_id == "cluster-org"
    assert extracted.compensation_frames[0].confidence == 0.66


def test_funding_frame_extractor_emits_grant_frame_without_compensation_frame() -> None:
    config = PipelineConfig.from_file("config.yaml")
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id="org-funder",
    )
    recipient = cluster("cluster-recipient", "Fundacja Lux Veritatis", entity_id="org-recipient")
    text = "WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji."
    doc = document([funder, recipient])
    doc.clause_units = [
        ClauseUnit(
            clause_id="clause-funding-1",
            text=text,
            trigger_head_text="przekazał",
            trigger_head_lemma="przekazać",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=[*funder.mentions, *recipient.mentions],
        )
    ]

    doc = PolishCompensationFrameExtractor(config).run(doc)
    doc = PolishFundingFrameExtractor(config).run(doc)

    assert doc.compensation_frames == []
    assert len(doc.funding_frames) == 1
    assert doc.funding_frames[0].funder_cluster_id == "cluster-funder"
    assert doc.funding_frames[0].recipient_cluster_id == "cluster-recipient"
    assert doc.funding_frames[0].amount_normalized == "300 Tys. Zł"


def test_funding_frame_extractor_handles_postposed_funder_with_relative_token_offsets() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "* Po publikacji otrzymaliśmy potwierdzenie z Fundacji Lux Veritatis, "
        "że 100 tys. zł na Park Pamięci wyłożyły także Jastrzębskie Zakłady Remontowe."
    )
    sentence_start = 8000
    recipient_start = sentence_start + text.index("Fundacji Lux Veritatis")
    funder_start = sentence_start + text.index("Jastrzębskie Zakłady Remontowe")
    recipient = cluster(
        "cluster-recipient",
        "Fundacja Lux Veritatis",
        sentence_index=3,
        start_char=recipient_start,
        end_char=recipient_start + len("Fundacji Lux Veritatis"),
        entity_id="org-recipient",
    )
    funder = cluster(
        "cluster-funder",
        "Jastrzębskie Zakłady Remontowe",
        sentence_index=3,
        start_char=funder_start,
        entity_id="org-funder",
    )
    doc = document([recipient, funder])
    doc.parsed_sentences = {
        3: [
            ParsedWord(
                index=1,
                text="wyłożyły",
                lemma="wyłożyć",
                upos="VERB",
                head=0,
                deprel="root",
                start=text.index("wyłożyły"),
                end=text.index("wyłożyły") + len("wyłożyły"),
            )
        ]
    }
    doc.clause_units = [
        ClauseUnit(
            clause_id="clause-funding-2",
            text=text,
            trigger_head_text="wyłożyły",
            trigger_head_lemma="wyłożyć",
            sentence_index=3,
            paragraph_index=0,
            start_char=sentence_start,
            end_char=sentence_start + len(text),
            cluster_mentions=[*recipient.mentions, *funder.mentions],
        )
    ]

    doc = PolishFundingFrameExtractor(config).run(doc)

    assert len(doc.funding_frames) == 1
    assert doc.funding_frames[0].funder_cluster_id == "cluster-funder"
    assert doc.funding_frames[0].recipient_cluster_id == "cluster-recipient"


def test_funding_fact_builder_emits_recipient_funded_by_funder_fact() -> None:
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id="org-funder",
    )
    recipient = cluster("cluster-recipient", "Fundacja Lux Veritatis", entity_id="org-recipient")
    doc = document([funder, recipient])
    doc.funding_frames = [
        FundingFrame(
            frame_id="funding-frame-1",
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
            attributes={
                "extraction_signal": "syntactic_direct",
                "evidence_scope": "same_clause",
                "score_reason": "funder_recipient_amount_same_clause",
            },
        )
    ]

    facts = FundingFactBuilder().build(doc)

    assert len(facts) == 1
    assert facts[0].fact_type == "FUNDING"
    assert facts[0].subject_entity_id == "org-recipient"
    assert facts[0].object_entity_id == "org-funder"
    assert facts[0].attributes["source_extractor"] == "funding_frame"
