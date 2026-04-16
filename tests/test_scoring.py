from pipeline.config import PipelineConfig
from pipeline.domain_types import FactType, TimeScope
from pipeline.models import ArticleDocument, EvidenceSpan, Fact
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
        facts=[
            Fact(
                fact_id="f1",
                fact_type=FactType.PARTY_MEMBERSHIP,
                subject_entity_id="p1",
                object_entity_id="party1",
                value_text=None,
                value_normalized=None,
                time_scope=TimeScope.CURRENT,
                event_date=None,
                confidence=0.7,
                evidence=EvidenceSpan(text="Polityk PiS"),
            ),
            Fact(
                fact_id="f2",
                fact_type=FactType.APPOINTMENT,
                subject_entity_id="p1",
                object_entity_id="org1",
                value_text=None,
                value_normalized=None,
                time_scope=TimeScope.CURRENT,
                event_date=None,
                confidence=0.7,
                evidence=EvidenceSpan(text="rada nadzorcza"),
                attributes={"board_role": True},
            ),
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
        facts=[
            Fact(
                fact_id="f-dismissal",
                fact_type=FactType.DISMISSAL,
                subject_entity_id="p1",
                object_entity_id="org1",
                value_text=None,
                value_normalized=None,
                time_scope=TimeScope.CURRENT,
                event_date=None,
                confidence=0.8,
                evidence=EvidenceSpan(text="odwołano"),
            )
        ],
    )

    scored = scorer.run(document)

    assert scored.score is not None
    assert scored.score.value == config.score_weights.dismissal_signal
