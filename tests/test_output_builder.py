from pipeline.models import (
    ArticleDocument,
    Entity,
    EvidenceSpan,
    Relation,
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
                entity_type="Person",
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            ),
            Entity(
                entity_id="org-1",
                entity_type="Organization",
                canonical_name="PKN",
                normalized_name="PKN",
            ),
        ],
        relations=[
            Relation(
                relation_type="APPOINTED_TO",
                source_entity_id="person-1",
                target_entity_id="org-1",
                confidence=0.8,
                evidence=EvidenceSpan(text="Jan Kowalski został powołany."),
            )
        ],
        relevance=RelevanceDecision(is_relevant=True, score=1.0, reasons=["test"]),
        score=ScoreResult(value=0.5, reasons=["test"]),
    )

    result = JsonOutputBuilder().run(document)

    assert result.graph.nodes
    assert result.graph.edges
