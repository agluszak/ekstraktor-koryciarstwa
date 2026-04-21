from pipeline.config import PipelineConfig
from pipeline.domain_types import DocumentID
from pipeline.filtering import KeywordRelevanceFilter
from pipeline.models import ArticleDocument


def test_dismissal_article_passes_relevance_filter() -> None:
    config = PipelineConfig.from_file("config.yaml")
    relevance_filter = KeywordRelevanceFilter(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Leszek Ruta został odwołany z zarządu miejskiej spółki transportowej.",
        paragraphs=["Leszek Ruta został odwołany z zarządu miejskiej spółki transportowej."],
    )

    decision = relevance_filter.run(document)

    assert decision.is_relevant is True
    assert decision.score >= 0.4


def test_public_salary_article_passes_relevance_filter() -> None:
    config = PipelineConfig.from_file("config.yaml")
    relevance_filter = KeywordRelevanceFilter(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-salary"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=(
            "Sprawdzili zarobki prezesów miejskich wodociągów. "
            "Wiesław Pancer zarabia ponad 20 tys. zł miesięcznie."
        ),
        paragraphs=[
            (
                "Sprawdzili zarobki prezesów miejskich wodociągów. "
                "Wiesław Pancer zarabia ponad 20 tys. zł miesięcznie."
            )
        ],
    )

    decision = relevance_filter.run(document)

    assert decision.is_relevant is True
    assert decision.score >= 0.4
