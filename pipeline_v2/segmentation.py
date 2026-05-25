from __future__ import annotations

import re

from pipeline_v2.document import ArticleDocument
from pipeline_v2.nlp import Sentence, Span

UPPERCASE_LETTERS = "A-ZĄĆĘŁŃÓŚŻŹ"
SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[\"’„“”»«]*(?:[–—-]\s*)?[" + UPPERCASE_LETTERS + "])"
)

# Polish abbreviations that end in a dot but are not sentence boundaries.
# Stored without trailing dot; comparison is case-insensitive.
_ABBREVS = frozenset(
    {
        "m.in",
        "n.p.m",
        "n.e",
        "p.n.e",
        "t.j",
        "t.zn",
        "tzw",
        "tzn",
        "np",
        "itd",
        "itp",
        "ok",
        "dr",
        "prof",
        "mgr",
        "inż",
        "hab",
        "lic",
        "min",
        "maks",
        "mln",
        "mld",
        "tys",
        "nr",
        "str",
        "ul",
        "al",
        "os",
        "por",
        "zob",
        "vs",
        "fig",
        "tab",
        "wyd",
        "red",
        "dosł",
        "przen",
        "in",
        "ub",
        "bm",
        "br",
        "jw",
    }
)


def _ends_with_abbreviation(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped or stripped[-1] != ".":
        return False
    last_space = max(stripped.rfind(" "), stripped.rfind("\t"))
    last_token = stripped[last_space + 1 :] if last_space >= 0 else stripped
    token_no_dot = last_token.rstrip(".")
    if token_no_dot.lower() in _ABBREVS:
        return True
    # Single-letter initials: "J.", "A."
    return len(token_no_dot) == 1 and token_no_dot.isalpha()


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
    parts: list[str] = []
    last_end = 0
    for m in SENTENCE_SPLIT_RE.finditer(compacted):
        left = compacted[last_end : m.start()]
        if _ends_with_abbreviation(left):
            continue
        if left.strip():
            parts.append(left.strip())
        last_end = m.end()
    remaining = compacted[last_end:]
    if remaining.strip():
        parts.append(remaining.strip())
    return tuple(parts) if parts else (compacted,)
