from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pipeline.config import PipelineConfig
from pipeline.domain_types import CandidateType, OrganizationKind
from pipeline.models import ParsedWord
from pipeline.runtime import PipelineRuntime
from pipeline.utils import compact_whitespace, normalize_entity_name, normalize_party_name

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

PUBLIC_REPRESENTATIVES = (
    "ministerstwo",
    "urząd miejski",
    "agencja państwowa",
    "instytut narodowy",
    "inspektorat",
    "rząd",
)

COMPANY_REPRESENTATIVES = (
    "spółka z o.o.",
    "przedsiębiorstwo prywatne",
    "holding finansowy",
    "fabryka maszyn",
    "zakłady produkcyjne",
    "sklep",
    "biuro",
)


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
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime
        self.institution_lookup = {
            normalize_entity_name(alias).lower(): normalize_entity_name(canonical)
            for alias, canonical in config.institution_aliases.items()
        }
        for canonical in config.institution_aliases.values():
            normalized_canonical = normalize_entity_name(canonical)
            self.institution_lookup[normalized_canonical.lower()] = normalized_canonical

        self._public_embeddings: list[np.ndarray] = []
        self._company_embeddings: list[np.ndarray] = []

    def resolve_party_name(
        self,
        *,
        surface_text: str,
        normalized_text: str,
        features: OrganizationMentionFeatures | None = None,
    ) -> str | None:
        if features is None:
            features = OrganizationMentionFeatures(
                surface_text=surface_text,
                normalized_text=normalized_text,
                lemmas=tuple(normalized_text.lower().split()),
                head_lemma=normalized_text.lower().split()[-1] if normalized_text else None,
                modifier_lemmas=tuple(normalized_text.lower().split()[:-1]),
            )
        return self._resolve_party_alias(
            surface_text=surface_text,
            normalized_text=normalized_text,
            features=features,
        )

    def resolve_institution_name(
        self,
        *,
        surface_text: str,
        normalized_text: str,
        features: OrganizationMentionFeatures | None = None,
    ) -> str | None:
        if features is None:
            features = OrganizationMentionFeatures(
                surface_text=surface_text,
                normalized_text=normalized_text,
                lemmas=tuple(normalized_text.lower().split()),
                head_lemma=normalized_text.lower().split()[-1] if normalized_text else None,
                modifier_lemmas=tuple(normalized_text.lower().split()[:-1]),
            )
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
            normalized = normalize_entity_name(candidate)
            canonical = self.institution_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
        return None

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
        alias_name = self.resolve_party_name(
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
        institution_name = self.resolve_institution_name(
            surface_text=surface_text,
            normalized_text=normalized_text,
            features=features,
        )
        if institution_name is not None:
            return OrganizationTypingResult(
                candidate_type=CandidateType.PUBLIC_INSTITUTION,
                organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
                canonical_name=institution_name,
            )
        if self._is_party_like(features):
            return OrganizationTypingResult(
                candidate_type=CandidateType.POLITICAL_PARTY,
                organization_kind=OrganizationKind.ORGANIZATION,
                canonical_name=normalize_entity_name(" ".join(features.lemmas)),
            )

        organization_kind = self._organization_kind(features)

        # Semantic fallback if lexical scoring is weak or tied
        if self.runtime is not None and organization_kind == OrganizationKind.ORGANIZATION:
            semantic_kind = self._semantic_organization_kind(features)
            if semantic_kind != OrganizationKind.ORGANIZATION:
                organization_kind = semantic_kind

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

    def _semantic_organization_kind(
        self, features: OrganizationMentionFeatures
    ) -> OrganizationKind:
        if self.runtime is None:
            return OrganizationKind.ORGANIZATION

        if not self._public_embeddings:
            self._public_embeddings = self.runtime.encode_texts(list(PUBLIC_REPRESENTATIVES))
            self._company_embeddings = self.runtime.encode_texts(list(COMPANY_REPRESENTATIVES))

        text_to_check = " ".join(features.lemmas)
        if not text_to_check:
            return OrganizationKind.ORGANIZATION

        emb = self.runtime.encode_text(text_to_check)

        def max_sim(target_embs: list[np.ndarray]) -> float:
            return max((float(np.dot(emb, target)) for target in target_embs), default=0.0)

        public_sim = max_sim(self._public_embeddings)
        company_sim = max_sim(self._company_embeddings)

        if public_sim > company_sim and public_sim >= 0.72:
            return OrganizationKind.PUBLIC_INSTITUTION
        if company_sim > public_sim and company_sim >= 0.72:
            return OrganizationKind.COMPANY

        return OrganizationKind.ORGANIZATION

    def _resolve_party_alias(
        self,
        *,
        surface_text: str,
        normalized_text: str,
        features: OrganizationMentionFeatures,
    ) -> str | None:
        canonical_by_name: dict[str, str] = {}
        for alias, canonical in self.config.party_aliases.items():
            canonical_by_name[alias.lower()] = canonical
            canonical_by_name[canonical.lower()] = canonical
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
            canonical = canonical_by_name.get(normalized.lower())
            if canonical is not None:
                return canonical
            for alias, canonical_name in canonical_by_name.items():
                if self._looks_like_inflected_party_alias(normalized.lower(), alias):
                    return canonical_name
        return None

    @staticmethod
    def _looks_like_inflected_party_alias(surface: str, party_name: str) -> bool:
        surface_tokens = surface.split()
        party_tokens = party_name.split()
        if len(surface_tokens) != len(party_tokens) or not party_tokens:
            return False
        matched = 0
        for surface_token, party_token in zip(surface_tokens, party_tokens, strict=True):
            if len(party_token) < 4:
                if surface_token == party_token:
                    matched += 1
                continue
            stem = party_token[: max(4, len(party_token) - 1)]
            if surface_token.startswith(stem):
                matched += 1
        return matched == len(party_tokens)

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
        return bool(PARTY_HEADS.intersection(lemmas))

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
