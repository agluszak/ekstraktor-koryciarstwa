from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from pipeline.models import Entity
from pipeline.utils import compact_whitespace, normalize_entity_name, unique_preserve_order

if TYPE_CHECKING:
    from pipeline.nlp_services import MorphologyAnalyzer

GENERIC_ORGANIZATION_TOKENS = frozenset(
    {
        "grupa",
        "holding",
        "instytucja",
        "kompania",
        "koncern",
        "podmiot",
        "przedsiębiorstwo",
        "rząd",
        "spółka",
        "zarząd",
    }
)

PREFERRED_ORGANIZATION_HEADS = frozenset(
    {
        "biuro",
        "fundacja",
        "fundusz",
        "instytut",
        "ministerstwo",
        "miasto",
        "pogotowie",
        "powiat",
        "spółka",
        "stowarzyszenie",
        "urząd",
        "województwo",
    }
)

NOISY_CANONICAL_TOKENS = frozenset(
    {
        "advertisement",
        "czytaj",
        "dotyczące",
        "dyrektora",
        "działań",
        "generalnego",
        "materiały",
        "newsletter",
        "otrzymała",
        "otrzymał",
        "promocyjnych",
        "przez",
        "reklama",
        "subskrybuj",
        "takim",
        "założona",
        "założony",
        "znaczeniu",
        "zobacz",
    }
)

POLISH_ORG_INFLECTION_SUFFIXES = (
    ("owym", "owy"),
    ("owej", "owa"),
    ("ego", "y"),
    ("emu", "y"),
    ("ich", "i"),
    ("iej", "a"),
    ("ym", "y"),
    ("ą", "a"),
    ("ę", "a"),
)

POLISH_ORG_DROP_SUFFIXES = (
    "ach",
    "ami",
    "owi",
    "om",
    "em",
    "u",
)


def is_acronym_like(token: str) -> bool:
    letters = [char for char in token if char.isalpha()]
    if len(letters) >= 2 and all(char.isupper() for char in letters):
        return True
    return any(char.isupper() for char in token[1:])


def org_token_base(token: str, morphology: MorphologyAnalyzer | None = None) -> str:
    if len(token) <= 3:
        return token
    if morphology is not None:
        analysis = morphology.analyze(token)
        if analysis.word_analyses and analysis.word_analyses[0].pos == "NOUN":
            return analysis.word_analyses[0].lemma.lower()
    if token.startswith(("urząd", "urzęd")):
        return "urząd"
    if token.startswith("fundacj"):
        return "fundacja"
    if token.startswith("stowarzyszen"):
        return "stowarzyszenie"
    if token.startswith("pogotowi"):
        return "pogotowie"
    if token.startswith("biur"):
        return "biuro"
    if token.endswith("rze") and len(token) > 5:
        return f"{token[:-3]}r"
    for suffix, replacement in POLISH_ORG_INFLECTION_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return f"{token[: -len(suffix)]}{replacement}"
    for suffix in POLISH_ORG_DROP_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


class OrganizationNamingPolicy:
    def __init__(
        self,
        *,
        institution_lookup: Mapping[str, str],
        known_acronyms: Iterable[str],
        morphology: MorphologyAnalyzer | None = None,
    ) -> None:
        self.institution_lookup = dict(institution_lookup)
        self.known_acronym_lookup = {alias.lower(): alias for alias in known_acronyms}
        self.morphology = morphology

    def best_organization_name(self, entity: Entity, names: list[str]) -> str:
        normalized = [
            normalize_entity_name(name)
            for name in self.candidate_name_parts(names)
            if compact_whitespace(name)
        ]
        specific_candidates = [
            candidate
            for candidate in normalized
            if not self._bare_organization_head_superseded(candidate, normalized)
            and not self._weak_single_token_organization_superseded(candidate, normalized)
        ]
        if specific_candidates:
            normalized = specific_candidates
        if not normalized:
            return entity.canonical_name
        return max(
            normalized,
            key=lambda name: self._organization_name_score(entity, name, normalized),
        )

    def canonical_institution_name(self, entity: Entity, names: list[str]) -> str | None:
        if marshal_office := self._canonical_marshal_office_name(names):
            return marshal_office
        primary_tokens = {
            token.lower()
            for name in (entity.canonical_name, entity.normalized_name)
            for token in normalize_entity_name(name).split()
            if token
        }
        has_multi_token_primary = any(
            len(normalize_entity_name(name).split()) > 1
            for name in (entity.canonical_name, entity.normalized_name)
        )
        for name in self.candidate_name_parts(names):
            normalized = normalize_entity_name(name)
            normalized_tokens = normalized.split()
            if (
                has_multi_token_primary
                and len(normalized_tokens) == 1
                and normalized_tokens[0].lower() in primary_tokens
                and is_acronym_like(normalized_tokens[0])
            ):
                continue
            canonical = self.institution_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
        return None

    def specific_acronym_alias(self, names: list[str]) -> str | None:
        candidates: list[str] = []
        for name in self.candidate_name_parts(names):
            normalized = normalize_entity_name(name)
            tokens = normalized.split()
            if len(tokens) < 2:
                continue
            first = self.known_acronym_lookup.get(tokens[0].lower())
            if first is None:
                continue
            repaired = " ".join([first, *tokens[1:]])
            if repaired.lower() not in self.institution_lookup:
                candidates.append(repaired)
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: (len(candidate.split()), len(candidate)))

    def organization_aliases(self, names: list[str], canonical: str) -> list[str]:
        normalized_aliases = []
        compacted_multiline_names = self.compacted_multiline_names(names)
        for name in names:
            if "\n" in name or "\r" in name:
                continue
            normalized = normalize_entity_name(name)
            if not normalized:
                continue
            if normalized in compacted_multiline_names:
                continue
            normalized_aliases.append(normalized)
        return unique_preserve_order([*normalized_aliases, canonical])

    @staticmethod
    def candidate_name_parts(names: list[str]) -> list[str]:
        candidates: list[str] = []
        compacted_multiline_names = OrganizationNamingPolicy.compacted_multiline_names(names)
        for name in names:
            if not compact_whitespace(name):
                continue
            if "\n" not in name and "\r" not in name:
                if normalize_entity_name(name) in compacted_multiline_names:
                    continue
                candidates.append(name)
                continue
            candidates.extend(
                part for part in (compact_whitespace(line) for line in name.splitlines()) if part
            )
        return unique_preserve_order(candidates)

    @staticmethod
    def compacted_multiline_names(names: list[str]) -> set[str]:
        return {
            normalize_entity_name(name)
            for name in names
            if ("\n" in name or "\r" in name) and compact_whitespace(name)
        }

    def _organization_name_score(
        self,
        entity: Entity,
        name: str,
        candidates: list[str],
    ) -> tuple[int, int, int, int, int, int, int, int, int, int]:
        tokens = [token for token in name.split() if token]
        lower_tokens = {token.lower() for token in tokens}
        generic_count = len(lower_tokens & GENERIC_ORGANIZATION_TOKENS)
        acronym_bonus = sum(1 for token in tokens if is_acronym_like(token))
        noisy_penalty = self._canonical_noise_score(name)
        inflection_penalty = self._organization_inflection_penalty(tokens)
        lemma_match_bonus = self._lemma_match_score(entity, name)
        shape_bonus = self._organization_shape_bonus(name)
        prefix_penalty = self._organization_prefix_junk_penalty(name, candidates)
        foundation_penalty = self._foundation_public_body_penalty(tokens)
        evidence_bonus = self._organization_evidence_bonus(entity, name)
        return (
            -noisy_penalty,
            evidence_bonus,
            shape_bonus,
            -prefix_penalty,
            -foundation_penalty,
            -generic_count,
            len(tokens),
            -inflection_penalty,
            lemma_match_bonus + acronym_bonus,
            len(name),
        )

    @staticmethod
    def _canonical_marshal_office_name(names: list[str]) -> str | None:
        normalized_names = [
            normalize_entity_name(name).casefold() for name in names if compact_whitespace(name)
        ]
        if any(
            "urząd marszałkowski" in name or "urzędu marszałkowskiego" in name
            for name in normalized_names
        ):
            return "Urząd Marszałkowski"
        return None

    @staticmethod
    def _canonical_noise_score(name: str) -> int:
        tokens = [token.lower() for token in name.split()]
        score = sum(3 for token in tokens if token in NOISY_CANONICAL_TOKENS)
        score += sum(2 for token in tokens if len(token) > 24 and token.lower() != token.upper())
        score += sum(
            2 for token in tokens if any(noise in token for noise in NOISY_CANONICAL_TOKENS)
        )
        return score

    def _lemma_match_score(self, entity: Entity, name: str) -> int:
        lemmas = {str(lemma).lower() for lemma in entity.lemmas if isinstance(lemma, str) and lemma}
        if not lemmas:
            return 0
        return sum(
            1 for token in name.split() if org_token_base(token.lower(), self.morphology) in lemmas
        )

    def _organization_inflection_penalty(self, tokens: list[str]) -> int:
        penalty = 0
        for token in tokens:
            lower = token.lower().strip(".,;:")
            if is_acronym_like(token) or len(lower) < 4:
                continue
            if org_token_base(lower, self.morphology) != lower:
                penalty += 1
        return penalty

    def _organization_shape_bonus(self, name: str) -> int:
        bases = [
            org_token_base(token.lower().strip(".,;:"), self.morphology)
            for token in name.split()
            if token
        ]
        if not bases:
            return 0
        if bases[0] in PREFERRED_ORGANIZATION_HEADS:
            return 2
        if len(bases) >= 2 and bases[1] in PREFERRED_ORGANIZATION_HEADS:
            return 2
        return 0

    def _organization_prefix_junk_penalty(self, name: str, candidates: list[str]) -> int:
        bases = [
            org_token_base(token.lower().strip(".,;:"), self.morphology)
            for token in name.split()
            if token
        ]
        penalty = 0
        for candidate in candidates:
            if candidate == name:
                continue
            candidate_bases = [
                org_token_base(token.lower().strip(".,;:"), self.morphology)
                for token in candidate.split()
                if token
            ]
            if len(candidate_bases) < 2 or len(candidate_bases) >= len(bases):
                continue
            if bases[: len(candidate_bases)] == candidate_bases:
                penalty = max(penalty, len(bases) - len(candidate_bases))
        return penalty

    def _foundation_public_body_penalty(self, tokens: list[str]) -> int:
        if len(tokens) < 2:
            return 0
        head = org_token_base(tokens[0].lower().strip(".,;:"), self.morphology)
        second = tokens[1].lower().strip(".,;:")
        if head not in {"fundacja", "stowarzyszenie"}:
            return 0
        if second.startswith(("kancelar", "minister", "urz", "fundusz", "instytut")):
            return 2
        return 0

    def _bare_organization_head_superseded(self, name: str, candidates: list[str]) -> bool:
        tokens = [token for token in name.split() if token]
        if len(tokens) != 1:
            return False
        head = org_token_base(tokens[0].lower(), self.morphology)
        if head not in PREFERRED_ORGANIZATION_HEADS:
            return False
        return any(
            other != name
            and len(other.split()) > 1
            and org_token_base(other.split()[0].lower(), self.morphology) == head
            for other in candidates
        )

    @staticmethod
    def _weak_single_token_organization_superseded(name: str, candidates: list[str]) -> bool:
        tokens = [token for token in name.split() if token]
        if len(tokens) != 1:
            return False
        token = tokens[0].casefold()
        if len(token) < 5 or token.isupper():
            return False
        return any(
            other != name
            and len(other.split()) > 1
            and (
                other.split()[0].casefold().startswith(token[:5])
                or token.startswith(other.split()[0].casefold()[:5])
            )
            for other in candidates
        )

    @staticmethod
    def _organization_evidence_bonus(entity: Entity, name: str) -> int:
        normalized = name.casefold()
        bonus = 0
        for evidence in entity.evidence:
            evidence_name = normalize_entity_name(evidence.text).casefold()
            if not evidence_name:
                continue
            if evidence_name == normalized:
                bonus += 2
            elif normalized in evidence_name or evidence_name in normalized:
                bonus += 1
        return bonus


class LocationNamingPolicy:
    def best_location_name(self, names: list[str]) -> str:
        normalized = [
            normalize_entity_name(name)
            for name in names
            if compact_whitespace(name) and "\n" not in name and "\r" not in name
        ]
        if not normalized:
            return ""
        return max(
            normalized,
            key=lambda name: (
                len(name.split()),
                -self._location_inflection_penalty(name),
                -self._single_token_suffix_penalty(name),
                len(name),
                sum(char.isupper() for char in name),
            ),
        )

    @staticmethod
    def _location_inflection_penalty(name: str) -> int:
        penalty = 0
        for token in name.split():
            lower = token.lower().strip(".,;:")
            if len(lower) < 4:
                continue
            if lower.endswith(("ie", "iu", "ego", "ej", "owi", "ach", "ami", "om")):
                penalty += 1
        return penalty

    @staticmethod
    def _single_token_suffix_penalty(name: str) -> int:
        tokens = [token.lower().strip(".,;:") for token in name.split() if token]
        if len(tokens) != 1:
            return 0
        token = tokens[0]
        if token.endswith(("ie", "iu", "ego", "ej", "owi", "ach", "ami", "om")):
            return 1
        return 0
