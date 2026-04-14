from pipeline.config import PipelineConfig
from pipeline.domain_types import EventType, RelationType
from pipeline.models import ArticleDocument, Event, EvidenceSpan, Relation
from pipeline.scoring import RuleBasedNepotismScorer


def test_rule_based_scorer_counts_expected_signals() -> None:
    config = PipelineConfig.from_file("config.yaml")
    scorer = RuleBasedNepotismScorer(config)
    document = ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Polityk trafił do rady nadzorczej spółki skarbu państwa bez doświadczenia.",
        paragraphs=["Polityk trafił do rady nadzorczej spółki skarbu państwa bez doświadczenia."],
        relations=[
            Relation(
                relation_type=RelationType.AFFILIATED_WITH_PARTY,
                source_entity_id="p1",
                target_entity_id="party1",
                confidence=0.7,
                evidence=EvidenceSpan(text="Polityk PiS"),
            ),
            Relation(
                relation_type=RelationType.MEMBER_OF_BOARD,
                source_entity_id="p1",
                target_entity_id="org1",
                confidence=0.7,
                evidence=EvidenceSpan(text="rada nadzorcza"),
            ),
        ],
        events=[
            Event(
                event_id="event1",
                event_type=EventType.APPOINTMENT,
                person_entity_id="p1",
                organization_entity_id="org1",
                position_entity_id=None,
                event_date=None,
                confidence=0.8,
                evidence=EvidenceSpan(text="powołano"),
            )
        ],
    )

    scored = scorer.run(document)

    assert scored.score is not None
    assert scored.score.value > 0.0


def test_dismissal_increases_score() -> None:
    config = PipelineConfig.from_file("config.yaml")
    scorer = RuleBasedNepotismScorer(config)
    document = ArticleDocument(
        document_id="doc-2",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Prezesa odwołano ze spółki miejskiej.",
        paragraphs=["Prezesa odwołano ze spółki miejskiej."],
        relations=[],
        events=[
            Event(
                event_id="event2",
                event_type=EventType.DISMISSAL,
                person_entity_id="p1",
                organization_entity_id="org1",
                position_entity_id=None,
                event_date=None,
                confidence=0.8,
                evidence=EvidenceSpan(text="odwołano"),
            )
        ],
    )

    scored = scorer.run(document)

    assert scored.score is not None
    assert scored.score.value == config.score_weights.dismissal_signal
