from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedWord:
    index: int
    text: str
    lemma: str
    upos: str
    head: int
    deprel: str
    start: int
    end: int
