from __future__ import annotations

import trafilatura
from bs4 import BeautifulSoup

from pipeline.base import Preprocessor
from pipeline.models import ArticleDocument, PipelineInput, default_document_id
from pipeline.utils import compact_whitespace


class TrafilaturaPreprocessor(Preprocessor):
    def name(self) -> str:
        return "trafilatura_preprocessor"

    def run(self, data: PipelineInput) -> ArticleDocument:
        extracted_text = trafilatura.extract(
            data.raw_html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
        if not extracted_text:
            raise ValueError("Trafilatura failed to extract article text.")

        soup = BeautifulSoup(data.raw_html, "html.parser")
        title = self._extract_title(soup)
        publication_date = data.publication_date or self._extract_publication_date(soup)
        paragraphs = [
            compact_whitespace(part)
            for part in extracted_text.splitlines()
            if compact_whitespace(part)
        ]

        return ArticleDocument(
            document_id=data.document_id or default_document_id(data.source_url, publication_date),
            source_url=data.source_url or self._extract_canonical_url(soup),
            raw_html=data.raw_html,
            title=title,
            publication_date=publication_date,
            cleaned_text="\n".join(paragraphs),
            paragraphs=paragraphs,
        )

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        for key in ("og:title", "twitter:title"):
            node = soup.find("meta", attrs={"property": key}) or soup.find(
                "meta", attrs={"name": key}
            )
            content = str(node.get("content")) if node and node.get("content") else None
            if content:
                return compact_whitespace(content)
        if soup.title and soup.title.text:
            return compact_whitespace(soup.title.text)
        raise ValueError("Unable to determine article title from HTML metadata.")

    @staticmethod
    def _extract_publication_date(soup: BeautifulSoup) -> str | None:
        for key in ("article:published_time", "og:published_time", "pubdate", "date"):
            node = soup.find("meta", attrs={"property": key}) or soup.find(
                "meta", attrs={"name": key}
            )
            content = str(node.get("content")) if node and node.get("content") else None
            if content:
                return compact_whitespace(content)
        time_node = soup.find("time")
        if time_node:
            value = time_node.get("datetime") or time_node.get_text()
            return compact_whitespace(str(value))
        return None

    @staticmethod
    def _extract_canonical_url(soup: BeautifulSoup) -> str | None:
        canonical = soup.find("link", attrs={"rel": "canonical"})
        return str(canonical.get("href")) if canonical and canonical.get("href") else None
