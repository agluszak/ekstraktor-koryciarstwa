from __future__ import annotations

import re

from pipeline.base import Segmenter
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, SentenceFragment
from pipeline.utils import compact_whitespace


class ParagraphSentenceSegmenter(Segmenter):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.sentence_split_re = re.compile(r"(?<=[.!?])\s+(?=[A-ZŁŚŻŹĆŃÓ])")

    def name(self) -> str:
        return "paragraph_sentence_segmenter"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        fragments: list[SentenceFragment] = []
        running_offset = 0
        for paragraph_index, paragraph in enumerate(document.paragraphs):
            raw_sentences = [
                compact_whitespace(part)
                for part in self.sentence_split_re.split(paragraph)
                if compact_whitespace(part)
            ]
            sentences = self._merge_sentence_fragments(raw_sentences)
            local_offset = document.cleaned_text.find(paragraph, running_offset)
            if local_offset < 0:
                local_offset = running_offset
            cursor = local_offset
            for sentence_index, sentence in enumerate(sentences, start=len(fragments)):
                start_char = document.cleaned_text.find(sentence, cursor)
                if start_char < 0:
                    start_char = cursor
                end_char = start_char + len(sentence)
                lowered = sentence.lower()
                is_candidate = any(keyword.lower() in lowered for keyword in self.config.keywords)
                fragments.append(
                    SentenceFragment(
                        text=sentence,
                        paragraph_index=paragraph_index,
                        sentence_index=sentence_index,
                        start_char=start_char,
                        end_char=end_char,
                        is_candidate=is_candidate,
                    )
                )
                cursor = end_char
            running_offset = cursor
        document.sentences = fragments
        return document

    @classmethod
    def _merge_sentence_fragments(cls, parts: list[str]) -> list[str]:
        merged: list[str] = []
        pending_prefix: str | None = None
        for part in parts:
            candidate = f"{pending_prefix} {part}" if pending_prefix is not None else part
            pending_prefix = None
            if cls._is_prefix_fragment(candidate):
                pending_prefix = candidate
                continue
            merged.append(candidate)
        if pending_prefix is not None:
            merged.append(pending_prefix)
        return merged

    @staticmethod
    def _is_prefix_fragment(text: str) -> bool:
        stripped = compact_whitespace(text)
        if not stripped:
            return False
        if re.fullmatch(r"[A-ZŁŚŻŹĆŃÓ]\.", stripped):
            return True
        if re.fullmatch(r"(?:k|m|nr)\.", stripped, re.IGNORECASE):
            return True
        return bool(re.search(r"\([a-z]\.$", stripped, re.IGNORECASE))
