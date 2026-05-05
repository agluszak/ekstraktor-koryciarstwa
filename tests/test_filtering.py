from __future__ import annotations

from pipeline.config import PipelineConfig
from pipeline.domain_types import DocumentID
from pipeline.filtering import KeywordRelevanceFilter
from pipeline.models import ArticleDocument, SentenceFragment


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

    document = relevance_filter.run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert "contains appointment or dismissal language" in document.relevance.reasons


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

    document = relevance_filter.run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert any("keyword hits" in r for r in document.relevance.reasons)


def test_patronage_complaint_article_passes_relevance_filter() -> None:
    config = PipelineConfig.from_file("config.yaml")
    relevance_filter = KeywordRelevanceFilter(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-patronage"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=(
            "Radna PO napisała do premiera list. "
            "Kolesiostwo, rozdawanie posad, brak wizji działania - wylicza."
        ),
        paragraphs=[
            (
                "Radna PO napisała do premiera list. "
                "Kolesiostwo, rozdawanie posad, brak wizji działania - wylicza."
            )
        ],
    )

    document = relevance_filter.run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert any("patronage language" in r for r in document.relevance.reasons)


def test_cba_procurement_bribery_article_passes_relevance_without_named_person() -> None:
    config = PipelineConfig.from_file("config.yaml")
    relevance_filter = KeywordRelevanceFilter(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-cba-ostrow"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=(
            "CBA zatrzymało wójta gminy Ostrów. "
            "Śledczy opisują łapówki za zamówienia publiczne i ustawianie zleceń."
        ),
        paragraphs=[
            (
                "CBA zatrzymało wójta gminy Ostrów. "
                "Śledczy opisują łapówki za zamówienia publiczne i ustawianie zleceń."
            )
        ],
    )

    document = relevance_filter.run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert any("anti-corruption context" in r for r in document.relevance.reasons)


def test_public_fund_governance_article_passes_relevance_from_lead_signals() -> None:
    config = PipelineConfig.from_file("config.yaml")
    relevance_filter = KeywordRelevanceFilter(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-wfosigw"),
        source_url=None,
        raw_html="",
        title=(
            "Bez konkursu i bez wysłuchania kandydatów. "
            "Tak nowa władza wprowadza swoich ludzi do ważnej instytucji"
        ),
        publication_date=None,
        cleaned_text=(
            "Stanisław Mazur, hotelarz-milioner z Lewicy, "
            "i działacz PSL Andrzej Kloc będą kierować "
            "Wojewódzkim Funduszem Ochrony Środowiska i Gospodarki Wodnej w Lublinie. "
            "Instytucja zostanie obsadzona bez konkursu. "
            "Działacz Lewicy Stanisław Mazur odebrał dziś nominację na prezesa WFOŚiGW w Lublinie."
        ),
        paragraphs=[
            (
                "Stanisław Mazur, hotelarz-milioner z Lewicy, "
                "i działacz PSL Andrzej Kloc będą kierować "
                "Wojewódzkim Funduszem Ochrony Środowiska i Gospodarki Wodnej w Lublinie."
            ),
            "Instytucja zostanie obsadzona bez konkursu.",
            (
                "Działacz Lewicy Stanisław Mazur odebrał dziś nominację "
                "na prezesa WFOŚiGW in Lublinie."
            ),
        ],
        lead_text=("Stanisław Mazur i Andrzej Kloc będą kierować WFOŚiGW w Lublinie bez konkursu."),
        sentences=[
            SentenceFragment(
                text=(
                    "Działacz Lewicy Stanisław Mazur odebrał dziś nominację "
                    "na prezesa WFOŚiGW in Lublinie."
                ),
                paragraph_index=2,
                sentence_index=0,
                start_char=0,
                end_char=100,
            )
        ],
    )

    document = relevance_filter.run(document)

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
