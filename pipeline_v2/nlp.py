from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import morfeusz2

from pipeline_v2.ids import EvidenceId, MentionId, SentenceId, TokenId
from pipeline_v2.types import MentionKind, NerLabel, ReferenceKind, RelationshipDetail


@dataclass(frozen=True, slots=True)
class Span:
    start_char: int
    end_char: int

    def contains(self, other: "Span") -> bool:
        return self.start_char <= other.start_char and other.end_char <= self.end_char


@dataclass(frozen=True, slots=True)
class MorphAnalysis:
    lemma: str
    pos: str | None = None
    case: str | None = None
    gender: str | None = None
    number: str | None = None
    person: str | None = None
    backend: str | None = None
    tag: str | None = None
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MorphToken:
    text: str
    analyses: tuple[MorphAnalysis, ...]


@dataclass(frozen=True, slots=True)
class Token:
    id: TokenId
    sentence_id: SentenceId
    text: str
    span: Span
    morph: tuple[MorphAnalysis, ...] = ()

    def preferred_lemma(self) -> str | None:
        for analysis in self.morph:
            if "nazwisko" in analysis.labels or "imię" in analysis.labels:
                return analysis.lemma
        for analysis in self.morph:
            if analysis.pos == "subst":
                return analysis.lemma
        return self.morph[0].lemma if self.morph else None


@dataclass(frozen=True, slots=True)
class DependencyArc:
    head_token_id: TokenId | None
    dependent_token_id: TokenId
    relation: str
    backend: str


@dataclass(frozen=True, slots=True)
class ParsedDependencyToken:
    token_index: int
    text: str
    lemma: str
    upos: str
    head_index: int
    relation: str


@dataclass(frozen=True, slots=True)
class ParsedDependencySentence:
    sentence_index: int
    tokens: tuple[ParsedDependencyToken, ...]


@dataclass(frozen=True, slots=True)
class Sentence:
    id: SentenceId
    sentence_index: int
    paragraph_index: int
    text: str
    span: Span
    token_ids: tuple[TokenId, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    id: EvidenceId
    text: str
    span: Span
    sentence_id: SentenceId | None = None
    paragraph_index: int | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class Mention:
    id: MentionId
    text: str
    kind: MentionKind
    evidence_id: EvidenceId
    sentence_id: SentenceId
    token_ids: tuple[TokenId, ...] = ()
    head_lemma: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceMention:
    id: MentionId
    text: str
    kind: ReferenceKind
    evidence_id: EvidenceId
    sentence_id: SentenceId
    token_ids: tuple[TokenId, ...] = ()
    head_lemma: str | None = None
    modifier_lemmas: tuple[str, ...] = ()
    relationship_detail: RelationshipDetail | None = None


@dataclass(frozen=True, slots=True)
class CorefLink:
    left_mention_id: MentionId
    right_mention_id: MentionId
    backend: str


@dataclass(frozen=True, slots=True)
class CoreferenceSpanLink:
    antecedent_text: str
    antecedent_span: Span
    reference_text: str
    reference_span: Span
    reference_kind: ReferenceKind
    relationship_detail: RelationshipDetail | None = None


@dataclass(frozen=True, slots=True)
class NamedEntitySpan:
    text: str
    label: NerLabel
    span: Span


class MorphologyAdapter(Protocol):
    backend_name: str

    def analyze_token(self, text: str) -> tuple[MorphAnalysis, ...]: ...

    def analyze_text(self, text: str) -> tuple[MorphToken, ...]: ...


class Morfeusz2MorphologyAdapter:
    backend_name = "morfeusz2"

    def __init__(self) -> None:
        self._analyzer = morfeusz2.Morfeusz()

    def analyze_token(self, text: str) -> tuple[MorphAnalysis, ...]:
        tokens = self.analyze_text(text)
        if len(tokens) == 1:
            return tokens[0].analyses
        analyses: list[MorphAnalysis] = []
        for token in tokens:
            analyses.extend(token.analyses)
        return tuple(dict.fromkeys(analyses))

    def analyze_text(self, text: str) -> tuple[MorphToken, ...]:
        grouped: dict[tuple[int, int, str], list[MorphAnalysis]] = {}
        for start, end, interpretation in self._analyzer.analyse(text):
            surface, lemma, tag, labels, _qualifiers = interpretation
            key = (start, end, surface)
            grouped.setdefault(key, []).append(
                self._to_morph_analysis(lemma=lemma, tag=tag, labels=tuple(labels))
            )
        return tuple(
            MorphToken(text=surface, analyses=tuple(dict.fromkeys(analyses)))
            for (_start, _end, surface), analyses in sorted(grouped.items())
        )

    @classmethod
    def _to_morph_analysis(
        cls,
        *,
        lemma: str,
        tag: str,
        labels: tuple[str, ...],
    ) -> MorphAnalysis:
        tag_parts = tag.split(":")
        return MorphAnalysis(
            lemma=cls._normalize_lemma(lemma),
            pos=tag_parts[0] if tag_parts else None,
            number=cls._first_matching_tag_value(tag_parts, {"sg", "pl"}),
            case=cls._first_matching_tag_value(
                tag_parts,
                {"nom", "gen", "dat", "acc", "inst", "loc", "voc"},
            ),
            gender=cls._first_matching_tag_value(
                tag_parts,
                {"m1", "m2", "m3", "f", "n", "p1", "p2", "p3"},
            ),
            person=cls._first_matching_tag_value(tag_parts, {"pri", "sec", "ter"}),
            backend=cls.backend_name,
            tag=tag,
            labels=labels,
        )

    @staticmethod
    def _normalize_lemma(lemma: str) -> str:
        base, _separator, _marker = lemma.partition(":")
        return base.casefold()

    @staticmethod
    def _first_matching_tag_value(
        tag_parts: list[str],
        allowed_values: set[str],
    ) -> str | None:
        for part in tag_parts:
            if "." in part:
                for nested_part in part.split("."):
                    if nested_part in allowed_values:
                        return nested_part
            if part in allowed_values:
                return part
        return None


class MentionFactory:
    def __init__(self, morphology: MorphologyAdapter) -> None:
        self.morphology = morphology

    def build_mention(
        self,
        *,
        mention_id: MentionId,
        text: str,
        kind: MentionKind,
        evidence_id: EvidenceId,
        sentence_id: SentenceId,
        token_ids: tuple[TokenId, ...] = (),
    ) -> Mention:
        return Mention(
            id=mention_id,
            text=text,
            kind=kind,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
            token_ids=token_ids,
            head_lemma=self.head_lemma(text),
        )

    def head_lemma(self, text: str) -> str | None:
        tokens = self.morphology.analyze_text(text)
        if not tokens:
            return None
        head_token = tokens[-1]
        preferred = self._preferred_head_analysis(head_token.analyses)
        return preferred.lemma if preferred is not None else None

    @staticmethod
    def _preferred_head_analysis(
        analyses: tuple[MorphAnalysis, ...],
    ) -> MorphAnalysis | None:
        for analysis in analyses:
            if "nazwisko" in analysis.labels:
                return analysis
        for analysis in analyses:
            if analysis.pos == "subst":
                return analysis
        return analyses[0] if analyses else None
