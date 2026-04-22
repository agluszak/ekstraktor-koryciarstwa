from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True, slots=True)
class MorphologicalAnalysis:
    """Detailed morphological data for a span of text."""
    full_lemma: str
    gender: str | None
    is_nominative: bool
    word_analyses: list[WordMorphology]

@dataclass(frozen=True, slots=True)
class WordMorphology:
    """Morphological data for a single word."""
    text: str
    lemma: str
    pos: str
    case: str | None
    gender: str | None
    number: str | None

@runtime_checkable
class MorphologyService(Protocol):
    """Protocol for morphological analysis of text."""
    def analyze(self, text: str) -> MorphologicalAnalysis:
        """Returns detailed morphological analysis for a given text."""
        ...

class StanzaMorphologyService:
    """Stanza-based implementation of the MorphologyService."""
    def __init__(self, stanza_pipeline) -> None:
        self.nlp = stanza_pipeline
        self._cache: dict[str, MorphologicalAnalysis] = {}

    def analyze(self, text: str) -> MorphologicalAnalysis:
        if not text:
            return MorphologicalAnalysis("", None, False, [])
        
        if text in self._cache:
            return self._cache[text]
        
        doc = self.nlp(text)
        if not doc.sentences:
            return MorphologicalAnalysis(text, None, False, [])
        
        words = [word for sent in doc.sentences for word in sent.words]
        if not words:
            return MorphologicalAnalysis(text, None, False, [])
            
        word_analyses = []
        full_lemma_parts = []
        
        for word in words:
            feats = {}
            if word.feats:
                feats = dict(f.split("=") for f in word.feats.split("|") if "=" in f)
            
            analysis = WordMorphology(
                text=word.text,
                lemma=word.lemma or word.text,
                pos=word.upos or "",
                case=feats.get("Case"),
                gender=feats.get("Gender"),
                number=feats.get("Number")
            )
            word_analyses.append(analysis)
            full_lemma_parts.append(analysis.lemma)

        full_lemma = " ".join(full_lemma_parts)
        
        # Detect overall gender from the last word (usually surname)
        gender = word_analyses[-1].gender
        
        # Check if the whole span is nominative (all nouns/adjectives/propns in Nom)
        is_nominative = all(
            wa.case == "Nom" 
            for wa in word_analyses 
            if wa.pos in {"NOUN", "PROPN", "ADJ", "DET"}
        )
        # If no case is found at all, but it is PROPN, we often assume it might be nominative
        # or at least we don't mark it as non-nominative.
        
        res = MorphologicalAnalysis(
            full_lemma=full_lemma,
            gender=gender,
            is_nominative=is_nominative,
            word_analyses=word_analyses
        )
        self._cache[text] = res
        return res

    def get_lemma_and_gender(self, text: str) -> tuple[str, str | None]:
        """Legacy compatibility wrapper."""
        analysis = self.analyze(text)
        return analysis.full_lemma, analysis.gender
