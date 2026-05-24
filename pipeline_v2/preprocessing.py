from __future__ import annotations

import hashlib
import re
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
        if not candidates:
            desc = cls._description(soup)
            if desc:
                candidates = [desc]
        body = cls._clean_paragraphs(candidates, title)
        # Prepend the title as the first paragraph so NER, morphology, and
        # governance extraction see it as processable text.  Body paragraphs
        # that duplicate the title are already stripped by _clean_paragraphs.
        if title:
            return (title,) + body
        return body

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
            if is_boilerplate_paragraph(paragraph):
                continue
            if _looks_like_comment(paragraph):
                continue
            if len(paragraph) < 20 and not (
                AMOUNT_RE.search(paragraph) or ROLE_SHORT_RE.search(paragraph)
            ):
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
    def _description(soup: BeautifulSoup) -> str:
        for selector in (
            'meta[property="og:description"]',
            'meta[name="description"]',
            'meta[name="twitter:description"]',
        ):
            node = soup.select_one(selector)
            if node is not None and node.get("content"):
                return compact_text(str(node["content"]))
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


GENERIC_JUNK_PATTERNS = (
    re.compile(r"^::addons", re.IGNORECASE),
    re.compile(r"^płatny dostęp do treści$", re.IGNORECASE),
    re.compile(r"^ten artykuł przeczytasz", re.IGNORECASE),
    re.compile(r"^komentarze$", re.IGNORECASE),
    re.compile(r"^reklama$", re.IGNORECASE),
    re.compile(r"^twoje zdanie jest ważne", re.IGNORECASE),
    re.compile(r"^skorzystaj z subskrypcji", re.IGNORECASE),
    re.compile(r"^wiadomości pogodowe$", re.IGNORECASE),
    re.compile(r"^popularne osoby$", re.IGNORECASE),
    re.compile(r"^organizacje$", re.IGNORECASE),
    re.compile(r"^inne tematy$", re.IGNORECASE),
    re.compile(r"^pogoda$", re.IGNORECASE),
    re.compile(r"^z tego artykułu dowiesz się:?$", re.IGNORECASE),
)

UI_SUBSTRING_MARKERS = frozenset(
    {
        "strona główna",
        "zobacz wszystkie",
        "więcej informacji znajdziesz",
        "serwisy partnerskie",
        "powiązane artykuły",
        "zobacz również",
        "następny artykuł",
        "poprzedni artykuł",
        "kup subskrypcję",
        "płatny dostęp do treści",
        "skorzystaj z subskrypcji",
    }
)

UI_EXACT_MARKERS = frozenset(
    {
        "premium",
        "pogoda",
        "organizacje",
        "komentarze",
        "reklama",
        "popularne osoby",
        "inne tematy",
        "wiadomości pogodowe",
        "logowanie",
        "zaloguj",
        "program tv",
        "subskrypcja",
        "subskrypcje",
        "subskrypcji",
        "subskrybuj",
    }
)

UI_PREFIX_MARKERS = frozenset(
    {
        "czytaj także",
        "przeczytaj także",
    }
)

AMOUNT_RE = re.compile(
    r"\b\d+(?:[ .,]\d+)*(?:\s*(?:tys\.?|mln|miliard\w*))?\s*(?:zł|złotych|pln|usd|eur|€|\$)\b",
    re.IGNORECASE,
)

ROLE_SHORT_RE = re.compile(
    r"\b(?:wójt|burmistrz|prezydent|starost|marszał|wojewod|radn|pos[eł]|posłan|senator|prezes|minist|dyrektor|człon)\w*\b",
    re.IGNORECASE,
)


def is_boilerplate_paragraph(text: str) -> bool:
    normalized = text.strip()
    lowered = normalized.casefold()
    if any(pattern.search(normalized) for pattern in GENERIC_JUNK_PATTERNS):
        return True

    substring_hits = sum(marker in lowered for marker in UI_SUBSTRING_MARKERS)
    exact_hits = sum(lowered == marker for marker in UI_EXACT_MARKERS)
    prefix_hits = sum(lowered.startswith(marker) for marker in UI_PREFIX_MARKERS)
    total_hits = substring_hits + exact_hits + prefix_hits

    short_ui_block = len(normalized) <= 120 and total_hits > 0
    dense_ui_block = total_hits >= 2
    title_like_menu = (
        normalized == normalized.title()
        and len(normalized.split()) <= 4
        and lowered in UI_EXACT_MARKERS
    )

    return short_ui_block or dense_ui_block or title_like_menu


def _looks_like_comment(paragraph: str) -> bool:
    lowered = paragraph.lower()
    if re.match(r"^[A-ZŁŚŻŹĆŃÓ][\wąćęłńóśźż-]{1,20}\s*-\s*niezalogowany", paragraph):
        return True
    if "niezalogowany" in lowered:
        return True
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?$", paragraph.strip()):
        return True
    if lowered.startswith("ja - "):
        return True
    return False
