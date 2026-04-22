from __future__ import annotations

from typing import Protocol, runtime_checkable

@runtime_checkable
class MorphologyService(Protocol):
    """Protocol for morphological analysis of text."""
    def get_lemma_and_gender(self, text: str) -> tuple[str, str | None]:
        """Returns the lemma and gender (if available) for a given text (usually a name)."""
        ...

class StanzaMorphologyService:
    """Stanza-based implementation of the MorphologyService."""
    def __init__(self, stanza_pipeline) -> None:
        self.nlp = stanza_pipeline
        self._cache: dict[str, tuple[str, str | None]] = {}

    def get_lemma_and_gender(self, text: str) -> tuple[str, str | None]:
        if not text:
            return "", None
        
        if text in self._cache:
            return self._cache[text]
        
        doc = self.nlp(text)
        if not doc.sentences:
            return text, None
        
        # We assume the input is a single entity (e.g., "Sylwię Sobolewską")
        # We take the lemmas of all words and the gender of the last word (usually the surname)
        words = [word for sent in doc.sentences for word in sent.words]
        if not words:
            return text, None
            
        full_lemma = " ".join(word.lemma for word in words)
        
        # Detect gender from the last word's features
        gender = None
        last_word = words[-1]
        if last_word.feats:
            feats = dict(f.split("=") for f in last_word.feats.split("|") if "=" in f)
            gender = feats.get("Gender")
            
        res = (full_lemma, gender)
        self._cache[text] = res
        return res
