from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_types import CandidateType, OrganizationKind
from pipeline.utils import compact_whitespace, normalize_entity_name, normalize_party_name

from .types import ParsedWord

STRONG_PUBLIC_HEADS = frozenset(
    {
        "urząd",
        "ministerstwo",
        "fundusz",
        "inspektorat",
        "agencja",
        "izba",
        "instytut",
    }
)
MODERATE_PUBLIC_HEADS = frozenset(
    {
        "ośrodek",
        "komisja",
        "zarząd",
        "rząd",
        "inspekcja",
    }
)
PUBLIC_MODIFIERS = frozenset(
    {
        "narodowy",
        "powiatowy",
        "wojewódzki",
        "gminny",
        "miejski",
        "państwowy",
        "fundusz",
        "ośrodek",
        "urząd",
        "ministerstwo",
        "główny",
        "wody",
        "polski",
        "krajowy",
        "agencja",
        "izba",
        "rządowy",
        "komisja",
        "komitet",
        "instytut",
        "naczelny",
        "inspektorat",
    }
)
COMPANY_HEADS = frozenset(
    {
        "spółka",
        "przedsiębiorstwo",
        "holding",
        "stadnina",
        "towarzystwo",
        "fabryka",
        "kolej",
    }
)
PARTY_HEADS = frozenset({"partia", "stronnictwo", "koalicja", "ruch"})
WEAK_PARTY_HEADS = frozenset({"komitet"})
PARTY_MODIFIERS = frozenset({"wyborczy", "polityczny", "obywatelski", "ludowy"})
GOVERNING_BODY_HEADS = frozenset({"zarząd", "rada", "komitet", "komisja"})


@dataclass(slots=True)
class OrganizationTypingResult:
    candidate_type: CandidateType
    organization_kind: OrganizationKind
    canonical_name: str | None = None


@dataclass(slots=True)
class OrganizationMentionFeatures:
    surface_text: str
    normalized_text: str
    lemmas: tuple[str, ...]
    head_lemma: str | None
    modifier_lemmas: tuple[str, ...]


class OrganizationMentionClassifier:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def classify(
        self,
        *,
        surface_text: str,
        normalized_text: str,
        parsed_words: list[ParsedWord],
        start_char: int,
        end_char: int,
    ) -> OrganizationTypingResult:
        features = self._features_for_span(
            surface_text=surface_text,
            parsed_words=parsed_words,
            start_char=start_char,
            end_char=end_char,
        )
        alias_name = self._resolve_party_alias(
            surface_text=surface_text,
            normalized_text=normalized_text,
            features=features,
        )
        if alias_name is not None:
            return OrganizationTypingResult(
                candidate_type=CandidateType.POLITICAL_PARTY,
                organization_kind=OrganizationKind.ORGANIZATION,
                canonical_name=alias_name,
            )
        if self._is_party_like(features):
            return OrganizationTypingResult(
                candidate_type=CandidateType.POLITICAL_PARTY,
                organization_kind=OrganizationKind.ORGANIZATION,
                canonical_name=None,
            )

        organization_kind = self._organization_kind(features)
        candidate_type = (
            CandidateType.PUBLIC_INSTITUTION
            if organization_kind == OrganizationKind.PUBLIC_INSTITUTION
            else CandidateType.ORGANIZATION
        )
        return OrganizationTypingResult(
            candidate_type=candidate_type,
            organization_kind=organization_kind,
            canonical_name=None,
        )

    def _resolve_party_alias(
        self,
        *,
        surface_text: str,
        normalized_text: str,
        features: OrganizationMentionFeatures,
    ) -> str | None:
        candidates = {
            surface_text,
            normalized_text,
            features.normalized_text,
            features.head_lemma or "",
            " ".join(features.lemmas),
        }
        for candidate in candidates:
            if not candidate:
                continue
            normalized = normalize_party_name(candidate)
            party_names = {k.lower() for k in self.config.party_aliases.keys()}.union(
                {v.lower() for v in self.config.party_aliases.values()}
            )
            if normalized.lower() in party_names:
                return normalized
        return None

    @staticmethod
    def _features_for_span(
        *,
        surface_text: str,
        parsed_words: list[ParsedWord],
        start_char: int,
        end_char: int,
    ) -> OrganizationMentionFeatures:
        span_words = [
            word for word in parsed_words if not (word.end <= start_char or word.start >= end_char)
        ]
        if not span_words:
            fallback_lemmas = tuple(
                token.lower()
                for token in compact_whitespace(surface_text).replace('"', "").split()
                if token
            )
            head_lemma = fallback_lemmas[-1] if fallback_lemmas else None
            return OrganizationMentionFeatures(
                surface_text=surface_text,
                normalized_text=normalize_entity_name(surface_text),
                lemmas=fallback_lemmas,
                head_lemma=head_lemma,
                modifier_lemmas=fallback_lemmas[:-1],
            )

        span_indices = {word.index for word in span_words}
        head = next(
            (word for word in span_words if word.head not in span_indices or word.deprel == "root"),
            span_words[-1],
        )
        modifier_lemmas = tuple(
            word.lemma
            for word in span_words
            if word.index != head.index and word.upos in {"ADJ", "NOUN", "PROPN"}
        )
        return OrganizationMentionFeatures(
            surface_text=surface_text,
            normalized_text=normalize_entity_name(surface_text),
            lemmas=tuple(word.lemma for word in span_words),
            head_lemma=head.lemma,
            modifier_lemmas=modifier_lemmas,
        )

    def _is_party_like(self, features: OrganizationMentionFeatures) -> bool:
        if features.head_lemma in PARTY_HEADS:
            return True
        if features.head_lemma in WEAK_PARTY_HEADS and PARTY_MODIFIERS.intersection(
            features.modifier_lemmas
        ):
            return True
        lemmas = set(features.lemmas)
        return bool(PARTY_HEADS.intersection(lemmas) or {"pis", "psl", "po", "ko"} & lemmas)

    @staticmethod
    def _organization_kind(features: OrganizationMentionFeatures) -> OrganizationKind:
        lemmas = set(features.lemmas)
        modifiers = set(features.modifier_lemmas)
        head = features.head_lemma or ""

        if ("wody", "polski") == features.lemmas[:2] or "wody polskie" in " ".join(features.lemmas):
            return OrganizationKind.PUBLIC_INSTITUTION

        public_score = 0.0
        company_score = 0.0
        governing_body_score = 0.0

        if head in STRONG_PUBLIC_HEADS:
            public_score += 3.0
        if head in MODERATE_PUBLIC_HEADS:
            public_score += 1.5
        public_score += min(2.0, len(PUBLIC_MODIFIERS.intersection(lemmas | modifiers)) * 0.8)

        if head in COMPANY_HEADS:
            company_score += 3.0
        if {"spółka", "państwowy"} <= lemmas or {"spółka", "miejski"} <= lemmas:
            company_score += 2.0
        if "skarb" in lemmas and "państwo" in lemmas:
            company_score += 1.5

        if head in GOVERNING_BODY_HEADS:
            governing_body_score += 2.0
        if head in {"komitet", "komisja"} and not PUBLIC_MODIFIERS.intersection(modifiers):
            governing_body_score += 0.5

        if public_score >= max(company_score, governing_body_score) and public_score >= 2.0:
            return OrganizationKind.PUBLIC_INSTITUTION
        if company_score >= max(public_score, governing_body_score) and company_score >= 2.0:
            return OrganizationKind.COMPANY
        if governing_body_score > public_score and governing_body_score >= 2.0:
            return OrganizationKind.GOVERNING_BODY
        return OrganizationKind.ORGANIZATION
