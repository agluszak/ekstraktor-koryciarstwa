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
    assert document.paragraphs == ("Pierwszy akapit tekstu.", "Drugi akapit z kwotą.")
    assert document.cleaned_text == "Pierwszy akapit tekstu.\nDrugi akapit z kwotą."


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
