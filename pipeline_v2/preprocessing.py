from __future__ import annotations

import hashlib
from html import unescape

import trafilatura
from bs4 import BeautifulSoup

from pipeline_v2.document import ArticleDocument, PipelineInput
from pipeline_v2.ids import DocumentId


class HtmlArticlePreprocessor:
    def name(self) -> str:
        return "html_article_preprocessor_v2"

    def run(self, data: PipelineInput) -> ArticleDocument:
        soup = BeautifulSoup(data.raw_html, "html.parser")
        title = self._title(soup)
        paragraphs = self._paragraphs(data.raw_html, soup, title)
        cleaned_text = "\n".join(paragraphs)
        return ArticleDocument(
            document_id=data.document_id or self._document_id(data, cleaned_text),
            source_url=data.source_url or self._canonical_url(soup),
            title=title,
            publication_date=data.publication_date or self._publication_date(soup),
            cleaned_text=cleaned_text,
            paragraphs=paragraphs,
        )

    @classmethod
    def _paragraphs(
        cls,
        raw_html: str,
        soup: BeautifulSoup,
        title: str,
    ) -> tuple[str, ...]:
        extracted = trafilatura.extract(
            raw_html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
        candidates = extracted.splitlines() if extracted else []
        if not candidates:
            candidates = [node.get_text(" ") for node in soup.find_all("p")]
        return cls._clean_paragraphs(candidates, title)

    @staticmethod
    def _clean_paragraphs(candidates: list[str], title: str) -> tuple[str, ...]:
        paragraphs: list[str] = []
        seen: set[str] = set()
        normalized_title = compact_text(title).casefold()
        for candidate in candidates:
            paragraph = compact_text(candidate)
            if not paragraph:
                continue
            lowered = paragraph.casefold()
            if lowered == normalized_title:
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            paragraphs.append(paragraph)
        return tuple(paragraphs)

    @staticmethod
    def _title(soup: BeautifulSoup) -> str:
        for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
            node = soup.select_one(selector)
            if node is not None and node.get("content"):
                return compact_text(str(node["content"]))
        heading = soup.find("h1")
        if heading is not None:
            return compact_text(heading.get_text(" "))
        if soup.title is not None and soup.title.string is not None:
            return compact_text(soup.title.string)
        return ""

    @staticmethod
    def _publication_date(soup: BeautifulSoup) -> str | None:
        for selector in (
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'meta[itemprop="datePublished"]',
        ):
            node = soup.select_one(selector)
            if node is not None and node.get("content"):
                return compact_text(str(node["content"]))
        return None

    @staticmethod
    def _canonical_url(soup: BeautifulSoup) -> str | None:
        node = soup.find("link", rel="canonical")
        if node is not None and node.get("href"):
            return compact_text(str(node["href"]))
        return None

    @staticmethod
    def _document_id(data: PipelineInput, cleaned_text: str) -> DocumentId:
        identity_source = data.source_url or cleaned_text
        digest = hashlib.sha1(identity_source.encode("utf-8")).hexdigest()[:16]
        return DocumentId(f"document-{digest}")


def compact_text(text: str) -> str:
    return " ".join(unescape(text).replace("\xa0", " ").split())
