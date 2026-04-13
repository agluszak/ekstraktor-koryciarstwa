from __future__ import annotations

import json
import re
from html import unescape

import trafilatura
from bs4 import BeautifulSoup

from pipeline.base import Preprocessor
from pipeline.models import ArticleDocument, PipelineInput, default_document_id
from pipeline.utils import compact_whitespace

SCRIPT_JSON_RE = re.compile(
    r"window\.(?:__newsData|__NEXT_DATA__)\s*=\s*(\{.*?\})\s*;",
    re.DOTALL,
)
AMOUNT_RE = re.compile(r"\b\d+(?:[ .,]\d+)*(?:\s*tys\.)?\s*zł\b", re.IGNORECASE)
JUNK_PATTERNS = (
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
)
FEED_HINTS = (
    "zobacz wszystkie",
    "więcej informacji znajdziesz",
    "strona główna onetu",
    "logowanie",
    "kup subskrypcję",
    "premium",
    "serwisy partnerskie",
    "pogoda ",
    "program tv",
)


class TrafilaturaPreprocessor(Preprocessor):
    def name(self) -> str:
        return "trafilatura_preprocessor"

    def run(self, data: PipelineInput) -> ArticleDocument:
        soup = BeautifulSoup(data.raw_html, "html.parser")
        title = self._extract_title(soup)
        publication_date = data.publication_date or self._extract_publication_date(soup)
        metadata = self._extract_metadata_blocks(data.raw_html, soup)
        trafilatura_paragraphs = self._extract_trafilatura_paragraphs(data.raw_html)
        paragraphs, content_source, quality_flags = self._build_paragraphs(
            title=title,
            trafilatura_paragraphs=trafilatura_paragraphs,
            metadata=metadata,
        )
        if not paragraphs:
            raise ValueError("Trafilatura failed to extract article text.")

        lead_text = metadata.get("lead")
        return ArticleDocument(
            document_id=data.document_id or default_document_id(data.source_url, publication_date),
            source_url=data.source_url or self._extract_canonical_url(soup),
            raw_html=data.raw_html,
            title=title,
            publication_date=publication_date,
            cleaned_text="\n".join(paragraphs),
            paragraphs=paragraphs,
            lead_text=lead_text,
            content_source=content_source,
            content_quality_flags=quality_flags,
        )

    def _build_paragraphs(
        self,
        *,
        title: str,
        trafilatura_paragraphs: list[str],
        metadata: dict[str, str],
    ) -> tuple[list[str], str, list[str]]:
        quality_flags: list[str] = []
        cleaned_trafilatura = self._sanitize_paragraphs(trafilatura_paragraphs)
        if self._looks_usable(cleaned_trafilatura):
            paragraphs = cleaned_trafilatura
            content_source = "trafilatura"
        else:
            if trafilatura_paragraphs:
                quality_flags.append("low_quality_trafilatura")
            paragraphs = []
            content_source = "metadata_recovery"

        recovered = self._metadata_recovery_paragraphs(metadata, title)
        if content_source == "trafilatura" and recovered:
            paragraph_set = {paragraph.lower() for paragraph in paragraphs}
            if metadata.get("lead") and metadata["lead"].lower() not in paragraph_set:
                paragraphs = [metadata["lead"], *paragraphs]
                content_source = "hybrid"
        elif recovered:
            paragraphs = recovered
            quality_flags.append("metadata_recovery_used")

        paragraphs = self._sanitize_paragraphs(paragraphs)
        if metadata.get("lead") and metadata["lead"] not in paragraphs:
            paragraphs = [metadata["lead"], *paragraphs]
            paragraphs = self._sanitize_paragraphs(paragraphs)
            if content_source == "trafilatura":
                content_source = "hybrid"

        if not self._looks_usable(paragraphs):
            quality_flags.append("thin_content")
        return paragraphs, content_source, quality_flags

    @staticmethod
    def _extract_trafilatura_paragraphs(raw_html: str) -> list[str]:
        extracted_text = trafilatura.extract(
            raw_html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
        if not extracted_text:
            return []
        return [
            compact_whitespace(part)
            for part in extracted_text.splitlines()
            if compact_whitespace(part)
        ]

    def _extract_metadata_blocks(self, raw_html: str, soup: BeautifulSoup) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for key in ("og:description", "twitter:description", "description"):
            node = soup.find("meta", attrs={"property": key}) or soup.find(
                "meta",
                attrs={"name": key},
            )
            content = str(node.get("content")) if node and node.get("content") else None
            if content and "description" not in metadata:
                metadata["description"] = compact_whitespace(unescape(content))
                break

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            for payload in self._iter_json_payloads(script.string):
                self._merge_metadata(metadata, payload)

        for match in SCRIPT_JSON_RE.finditer(raw_html):
            for payload in self._iter_json_payloads(match.group(1)):
                self._merge_metadata(metadata, payload)

        script_text = raw_html
        for field in ("lead", "text_paragraph_lead", "articleBody", "description", "body"):
            if field in metadata:
                continue
            pattern = re.compile(
                rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"',
                re.DOTALL,
            )
            script_match = pattern.search(script_text)
            if script_match:
                metadata[field] = compact_whitespace(
                    unescape(bytes(script_match.group(1), "utf-8").decode("unicode_escape"))
                )

        lead = metadata.get("lead") or metadata.get("text_paragraph_lead")
        if lead:
            metadata["lead"] = lead
        elif "description" in metadata:
            metadata["lead"] = metadata["description"]
        return metadata

    @staticmethod
    def _iter_json_payloads(text: str) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return payloads
        if isinstance(decoded, dict):
            payloads.append(decoded)
            graph = decoded.get("@graph")
            if isinstance(graph, list):
                payloads.extend(item for item in graph if isinstance(item, dict))
        elif isinstance(decoded, list):
            payloads.extend(item for item in decoded if isinstance(item, dict))
        return payloads

    @staticmethod
    def _merge_metadata(metadata: dict[str, str], payload: dict[str, object]) -> None:
        field_map = {
            "description": ("description", "abstract"),
            "lead": ("lead", "text_paragraph_lead"),
            "body": ("articleBody", "body", "text"),
        }
        for target, candidates in field_map.items():
            if target in metadata:
                continue
            for candidate in candidates:
                value = payload.get(candidate)
                if isinstance(value, str) and compact_whitespace(value):
                    metadata[target] = compact_whitespace(unescape(value))
                    break

    def _metadata_recovery_paragraphs(self, metadata: dict[str, str], title: str) -> list[str]:
        paragraphs: list[str] = []
        for key in ("lead", "body", "description"):
            value = metadata.get(key)
            if not value:
                continue
            if value != title:
                paragraphs.extend(self._split_metadata_text(value))
        return self._sanitize_paragraphs(paragraphs)

    @staticmethod
    def _split_metadata_text(text: str) -> list[str]:
        normalized = compact_whitespace(text.replace("\\n", "\n"))
        parts = re.split(r"\s*(?:\n+|(?<=\.)\s{2,})\s*", normalized)
        return [compact_whitespace(part) for part in parts if compact_whitespace(part)]

    def _sanitize_paragraphs(self, paragraphs: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for paragraph in paragraphs:
            normalized = compact_whitespace(unescape(paragraph))
            if not normalized:
                continue
            lowered = normalized.lower()
            if any(pattern.search(normalized) for pattern in JUNK_PATTERNS):
                continue
            if any(hint in lowered for hint in FEED_HINTS):
                continue
            if self._looks_like_comment(normalized):
                continue
            if len(normalized) < 20 and not AMOUNT_RE.search(normalized):
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(normalized)
        return cleaned

    @staticmethod
    def _looks_like_comment(paragraph: str) -> bool:
        lowered = paragraph.lower()
        if re.match(r"^[A-ZŁŚŻŹĆŃÓ][\wąćęłńóśźż-]{1,20}\s*-\s*niezalogowany", paragraph):
            return True
        if "niezalogowany" in lowered:
            return True
        if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", paragraph):
            return True
        if lowered.startswith("ja - "):
            return True
        return False

    @staticmethod
    def _looks_usable(paragraphs: list[str]) -> bool:
        if len(paragraphs) >= 2 and sum(len(part) for part in paragraphs[:4]) >= 180:
            return True
        if len(paragraphs) == 1 and len(paragraphs[0]) >= 180:
            return True
        return False

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
