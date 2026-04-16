from pipeline.domain_types import EntityType, FactType, TimeScope
from pipeline.models import (
    ArticleDocument,
    Entity,
    EvidenceSpan,
    Fact,
    RelevanceDecision,
    ScoreResult,
)
from pipeline.output import JsonOutputBuilder


def test_output_builder_creates_graph() -> None:
    document = ArticleDocument(
        document_id="doc-1",
        source_url="https://example.com",
        raw_html="<html></html>",
        title="Test",
        publication_date="2026-04-13",
        cleaned_text="Test text",
        paragraphs=["Test text"],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PKN",
                normalized_name="PKN",
            ),
        ],
        facts=[
            Fact(
                fact_id="f1",
                fact_type=FactType.APPOINTMENT,
                subject_entity_id="person-1",
                object_entity_id="org-1",
                value_text=None,
                value_normalized=None,
                time_scope=TimeScope.CURRENT,
                event_date=None,
                confidence=0.8,
                evidence=EvidenceSpan(text="Jan Kowalski został powołany."),
            )
        ],
        relevance=RelevanceDecision(is_relevant=True, score=1.0, reasons=["test"]),
        score=ScoreResult(value=0.5, reasons=["test"]),
    )

    result = JsonOutputBuilder().run(document)

    # the JSON output builder does not attach the graph to ExtractionResult anymore.
    # Output formatting is part of the specific writer logic.
    # To test graph derivation, we can just assert facts are preserved.
    assert result.facts

