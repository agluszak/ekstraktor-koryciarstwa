from __future__ import annotations

import re

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import SentenceId
from pipeline_v2.nlp import Sentence, Span

UPPERCASE_LETTERS = "A-ZĄĆĘŁŃÓŚŻŹ"
SENTENCE_SPLIT_RE = re.compile(rf"(?<=[.!?])\s+(?=[\"'„“”»«]*(?:[–—-]\s*)?[{UPPERCASE_LETTERS}])")


class ParagraphSentenceSegmenter:
    def name(self) -> str:
        return "paragraph_sentence_segmenter_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        running_offset = 0
        for paragraph_index, paragraph in enumerate(document.paragraphs):
            local_offset = document.cleaned_text.find(paragraph, running_offset)
            if local_offset < 0:
                local_offset = running_offset
            cursor = local_offset
            for sentence_text in split_sentences(paragraph):
                start_char = document.cleaned_text.find(sentence_text, cursor)
                if start_char < 0:
                    start_char = cursor
                end_char = start_char + len(sentence_text)
                document.store.add_sentence(
                    Sentence(
                        id=document.store.next_sentence_id(),
                        sentence_index=len(document.store.sentences),
                        paragraph_index=paragraph_index,
                        text=sentence_text,
                        span=Span(start_char=start_char, end_char=end_char),
                    )
                )
                cursor = end_char
            running_offset = cursor
        return document


def split_sentences(paragraph: str) -> tuple[str, ...]:
    compacted = " ".join(paragraph.split())
    if not compacted:
        return ()
    return tuple(part.strip() for part in SENTENCE_SPLIT_RE.split(compacted) if part.strip())
