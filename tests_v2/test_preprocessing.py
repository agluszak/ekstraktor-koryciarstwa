from __future__ import annotations

from pipeline_v2.document import PipelineInput
from pipeline_v2.ids import DocumentId
from pipeline_v2.preprocessing import HtmlArticlePreprocessor


def test_html_preprocessor_builds_document_from_article_html() -> None:
    raw_html = """
    <html>
      <head>
        <meta property="og:title" content="  Tytuł&nbsp;artykułu  ">
        <meta property="article:published_time" content="2026-05-14">
        <link rel="canonical" href="https://example.test/article">
      </head>
      <body>
        <article>
          <h1>Tytuł artykułu</h1>
          <p>Pierwszy akapit tekstu.</p>
          <p>Pierwszy akapit tekstu.</p>
          <p>Drugi akapit z&nbsp;kwotą.</p>
        </article>
      </body>
    </html>
    """

    document = HtmlArticlePreprocessor().run(PipelineInput(raw_html=raw_html))

    assert document.title == "Tytuł artykułu"
    assert document.source_url == "https://example.test/article"
    assert document.publication_date == "2026-05-14"
    assert document.paragraphs == (
        "Tytuł artykułu",
        "Pierwszy akapit tekstu.",
        "Drugi akapit z kwotą.",
    )
    assert document.cleaned_text == "Tytuł artykułu\nPierwszy akapit tekstu.\nDrugi akapit z kwotą."


def test_html_preprocessor_respects_explicit_input_metadata() -> None:
    raw_html = """
    <html>
      <head><title>HTML title</title></head>
      <body><p>Treść artykułu.</p></body>
    </html>
    """

    document = HtmlArticlePreprocessor().run(
        PipelineInput(
            raw_html=raw_html,
            source_url="https://input.test/article",
            publication_date="2025-01-02",
            document_id=DocumentId("explicit-document"),
        )
    )

    assert document.document_id == DocumentId("explicit-document")
    assert document.source_url == "https://input.test/article"
    assert document.publication_date == "2025-01-02"


def test_html_preprocessor_generates_stable_document_id() -> None:
    first = HtmlArticlePreprocessor().run(
        PipelineInput(raw_html="<html><body><p>Tekst.</p></body></html>")
    )
    second = HtmlArticlePreprocessor().run(
        PipelineInput(raw_html="<html><body><p>Tekst.</p></body></html>")
    )

    assert first.document_id == second.document_id


def test_html_preprocessor_filters_boilerplate_and_comments() -> None:
    raw_html = """
    <html>
      <head>
        <meta property="og:title" content="Tytuł artykułu">
      </head>
      <body>
        <p>Tytuł artykułu</p>
        <p>Pierwszy prawdziwy akapit o ważnych sprawach publicznych.</p>
        <p>komentarze</p>
        <p>Jan Kowalski - niezalogowany</p>
        <p>2026-05-14 12:34:56</p>
        <p>Krótka</p>
        <p>Reklama</p>
        <p>Twoje zdanie jest ważne</p>
        <p>Drugi akapit o wartości 123 tys. zł brutto.</p>
      </body>
    </html>
    """

    document = HtmlArticlePreprocessor().run(PipelineInput(raw_html=raw_html))

    assert document.paragraphs == (
        "Tytuł artykułu",
        "Pierwszy prawdziwy akapit o ważnych sprawach publicznych.",
        "Drugi akapit o wartości 123 tys. zł brutto.",
    )


def test_html_preprocessor_survives_important_short_paragraphs() -> None:
    raw_html = """
    <html>
      <body>
        <p>50 mln zł</p>
        <p>12 mln PLN</p>
        <p>300 tys. USD</p>
        <p>Wójt gminy</p>
        <p>Prezes zarządu</p>
        <p>Dnia 2026-05-14 podjęto decyzję.</p>
      </body>
    </html>
    """
    document = HtmlArticlePreprocessor().run(PipelineInput(raw_html=raw_html))
    assert "50 mln zł" in document.paragraphs
    assert "12 mln PLN" in document.paragraphs
    assert "300 tys. USD" in document.paragraphs
    assert "Wójt gminy" in document.paragraphs
    assert "Prezes zarządu" in document.paragraphs
    assert "Dnia 2026-05-14 podjęto decyzję." in document.paragraphs


def test_html_preprocessor_filters_photo_credit_paragraphs() -> None:
    raw_html = """
    <html>
      <head>
        <meta property="og:title" content="Tytuł artykułu">
      </head>
      <body>
        <p>Lotnisko Ławica w PoznaniuPiotr Skórnicki / Agencja Wyborcza.pl</p>
        <p>Prezes Ławicy odpowiada na zarzuty pracowników.</p>
      </body>
    </html>
    """

    document = HtmlArticlePreprocessor().run(PipelineInput(raw_html=raw_html))

    assert document.paragraphs == (
        "Tytuł artykułu",
        "Prezes Ławicy odpowiada na zarzuty pracowników.",
    )
