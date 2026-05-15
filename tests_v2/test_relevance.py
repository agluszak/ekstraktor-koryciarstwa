from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.relevance import ProfileRelevanceFilter


def test_relevance_filter_accepts_public_money_employment_context() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Umowa z urzędu dla fundacji",
        publication_date=None,
        cleaned_text=(
            "Urząd podpisał umowę z fundacją. Na stanowisko zatrudniono osobę "
            "powiązaną z lokalnym politykiem."
        ),
        paragraphs=(
            "Urząd podpisał umowę z fundacją.",
            "Na stanowisko zatrudniono osobę powiązaną z lokalnym politykiem.",
        ),
    )

    ProfileRelevanceFilter().run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert document.relevance.score >= 0.45


def test_relevance_filter_rejects_legal_analysis_without_public_money_or_employment() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Analiza prawna wyroku",
        publication_date=None,
        cleaned_text="Trybunał Konstytucyjny i sąd pracy w analizie prawnej.",
        paragraphs=("Trybunał Konstytucyjny i sąd pracy w analizie prawnej.",),
    )

    ProfileRelevanceFilter().run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is False
    assert "legal-analysis negative context" in document.relevance.reasons
