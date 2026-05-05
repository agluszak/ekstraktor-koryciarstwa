from __future__ import annotations

from pipeline.domain_types import EntityType
from pipeline.entity_naming import NOISY_CANONICAL_TOKENS, org_token_base
from pipeline.models import Entity
from pipeline.nlp_services import MorphologicalAnalysis, MorphologyAnalyzer
from pipeline.utils import compact_whitespace, normalize_entity_name, normalize_party_name

# Kept as a deterministic fallback for when no morphology analyzer is available.
_PARTY_TOKEN_VARIANTS: dict[str, str] = {
    "prawa": "prawo",
    "sprawiedliwości": "sprawiedliwość",
    "platformy": "platforma",
    "obywatelskiej": "obywatelska",
    "lewicy": "lewica",
}


def canonical_noise_score(name: str) -> int:
    tokens = [token.lower() for token in name.split()]
    score = sum(3 for token in tokens if token in NOISY_CANONICAL_TOKENS)
    score += sum(2 for token in tokens if len(token) > 24 and token.lower() != token.upper())
    score += sum(2 for token in tokens if any(noise in token for noise in NOISY_CANONICAL_TOKENS))
    return score


class PartyNamingPolicy:
    def __init__(
        self,
        party_aliases: dict[str, str],
        morphology: MorphologyAnalyzer | None = None,
    ) -> None:
        self.morphology = morphology
        self.party_lookup = {
            normalize_party_name(alias).lower(): compact_whitespace(canonical)
            for alias, canonical in party_aliases.items()
        }
        for canonical in party_aliases.values():
            normalized = normalize_party_name(canonical).lower()
            self.party_lookup[normalized] = compact_whitespace(canonical)

    def canonical_name(self, names: list[str]) -> str:
        for name in names:
            normalized = normalize_party_name(name)
            canonical = self.party_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
            canonical = self.party_lookup.get(self.lookup_key(normalized))
            if canonical is not None:
                return canonical
        normalized_candidates = [
            normalize_party_name(name) for name in names if compact_whitespace(name)
        ]
        if not normalized_candidates:
            return ""
        return max(normalized_candidates, key=self.name_score)

    def lookup_key(self, name: str) -> str:
        normalized = normalize_party_name(name)
        if self.morphology is not None:
            analysis = self.morphology.analyze(normalized)
            if analysis.word_analyses:
                return " ".join(wa.lemma.lower() for wa in analysis.word_analyses)
        tokens = [
            _PARTY_TOKEN_VARIANTS.get(token.lower(), token.lower()) for token in normalized.split()
        ]
        return " ".join(tokens)

    def name_score(self, name: str) -> tuple[int, int, int]:
        tokens = [token for token in name.split() if token]
        return (
            -canonical_noise_score(name),
            sum(1 for token in tokens if token.lower() == self.token_base(token.lower())),
            len(name),
        )

    def token_base(self, token: str) -> str:
        if self.morphology is not None:
            analysis = self.morphology.analyze(token)
            if analysis.word_analyses:
                return analysis.word_analyses[0].lemma.lower()
        mapped = _PARTY_TOKEN_VARIANTS.get(token)
        if mapped is not None:
            return mapped
        return org_token_base(token)


class PersonNamePolicy:
    def __init__(self, morphology: MorphologyAnalyzer | None = None) -> None:
        self.morphology = morphology
        self._gender_cache: dict[str, str | None] = {}
        self._nominative_cache: dict[str, bool] = {}
        self._morphology_cache: dict[str, MorphologicalAnalysis] = {}

    def preload(self, names: set[str]) -> None:
        if self.morphology is None:
            return
        for name in names:
            analysis = self.morphology.analyze(name)
            self._morphology_cache[name] = analysis
            self._gender_cache[name] = analysis.gender
            self._nominative_cache[name] = analysis.is_nominative

    def morphology_lemma_candidates(self, names: list[str]) -> list[str]:
        if self.morphology is None:
            return []
        candidates: list[str] = []
        for name in names:
            if not name or not compact_whitespace(name):
                continue
            analysis = self.morphology.analyze(name)
            lemma = analysis.full_lemma
            if lemma and lemma.lower() != name.lower():
                candidates.append(lemma)
        return candidates

    def nominative_candidates(self, names: list[str]) -> list[str]:
        candidates: list[str] = []
        for name in names:
            if canonical_noise_score(name) > 0:
                continue
            tokens = name.split()
            if len(tokens) < 2:
                continue

            orig_gender = self._gender_cache.get(name)
            stems = [self.person_token_base(token.lower()) for token in tokens]
            if stems[0].endswith("i"):
                first_token = stems[0].capitalize() + "a"
            else:
                first_token = stems[0].capitalize()

            if stems[-1].endswith(("sk", "ck", "dzk")):
                surname_fem = stems[-1].capitalize() + "a"
                surname_masc = stems[-1].capitalize() + "i"
                if orig_gender in {None, "Fem"}:
                    candidates.append(f"{first_token} {surname_fem}")
                if orig_gender in {None, "Masc"}:
                    candidates.append(f"{first_token} {surname_masc}")
            if orig_gender == "Masc" and stems[-1].endswith("kow"):
                surname = f"{stems[-1][:-2]}ów".capitalize()
                candidates.append(f"{first_token} {surname}")
        return candidates

    def best_person_name(self, names: list[str]) -> str:
        normalized = [normalize_entity_name(name) for name in names if compact_whitespace(name)]
        if not normalized:
            return ""
        surface_repair = self.surface_repair_for_broken_name(normalized)
        if surface_repair is not None:
            return surface_repair
        observed_tokens = {
            token.rstrip(".").lower() for name in normalized for token in name.split() if token
        }
        best = max(
            normalized,
            key=lambda name: (
                -canonical_noise_score(name),
                self._nominative_cache.get(name, False),
                not self.looks_like_inflected_single_token(name),
                len(name.split()) >= 2,
                self.observed_variant_bonus(name, observed_tokens),
                self.name_nominality_score(name, gender=self._gender_cache.get(name)),
                len(name),
                sum(1 for token in name.split() if len(token) > 1),
            ),
        )
        if self.is_broken_stem(best):
            for candidate in normalized:
                if self.is_complete_surname_form(candidate, best):
                    return candidate
        return best

    @staticmethod
    def person_lemmas(name: str) -> list[str]:
        return [
            token.lower()
            for token in normalize_entity_name(name).replace("-", " ").split()
            if token
        ]

    @classmethod
    def ambiguous_person_singletons(cls, entities: list[Entity]) -> set[str]:
        surname_to_given_bases: dict[str, set[str]] = {}
        for entity in entities:
            if entity.entity_type != EntityType.PERSON or entity.is_proxy_person:
                continue
            tokens = normalize_entity_name(entity.normalized_name).split()
            if len(tokens) < 2:
                continue
            surname_variants = cls.person_token_variants(tokens[-1].rstrip(".").lower())
            given_base = cls.person_token_base(tokens[0].rstrip(".").lower())
            for surname_variant in surname_variants:
                surname_to_given_bases.setdefault(surname_variant, set()).add(given_base)
        return {
            surname
            for surname, given_bases in surname_to_given_bases.items()
            if len(given_bases) > 1
        }

    @classmethod
    def persons_compatible(
        cls,
        left_name: str,
        right_name: str,
        ambiguous_singletons: set[str],
    ) -> bool:
        left_tokens = left_name.split()
        right_tokens = right_name.split()
        if not left_tokens or not right_tokens:
            return False
        left_full = len(left_tokens) >= 2
        right_full = len(right_tokens) >= 2
        if left_name == right_name:
            return True
        if left_full and right_full:
            return cls.person_tokens_compatible(
                left_tokens[-1],
                right_tokens[-1],
            ) and cls.person_tokens_compatible(left_tokens[0], right_tokens[0])
        if len(left_tokens) == 1 and right_full:
            if cls.person_singleton_is_ambiguous(left_tokens[0], ambiguous_singletons):
                return False
            return cls.single_token_matches_person_cluster(left_tokens[0], right_tokens)
        if len(right_tokens) == 1 and left_full:
            if cls.person_singleton_is_ambiguous(right_tokens[0], ambiguous_singletons):
                return False
            return cls.single_token_matches_person_cluster(right_tokens[0], left_tokens)
        return False

    @classmethod
    def person_singleton_is_ambiguous(cls, token: str, ambiguous_singletons: set[str]) -> bool:
        return bool(cls.person_token_variants(token.rstrip(".").lower()) & ambiguous_singletons)

    @classmethod
    def name_nominality_score(cls, name: str, gender: str | None = None) -> int:
        tokens = [token for token in name.split() if token]
        if not tokens:
            return 0
        score = 0
        for token in tokens:
            base = token.rstrip(".").lower()
            if "-" in base:
                parts = base.split("-")
                if all(cls.person_token_base(part) == part for part in parts):
                    score += 2
                continue
            if cls.person_token_base(base) == base and cls.is_person_base_form(base):
                score += 2
            if base.endswith(("ska", "cka", "dzka", "ski", "cki", "dzki")):
                score += 2
            elif base.endswith("ów"):
                score += 2
            elif base.endswith("owa"):
                score += 2
            elif base.endswith("a") and not base.endswith(("owa", "yna")):
                score += 1
        if len(tokens) >= 2:
            first = tokens[0].rstrip(".").lower()
            last = tokens[-1].rstrip(".").lower()
            if gender == "Fem":
                if first.endswith("a") and last.endswith(("ska", "cka", "dzka")):
                    score += 2
                elif first.endswith("a") or last.endswith(("ska", "cka", "dzka")):
                    score += 1
            elif gender == "Masc":
                if not first.endswith("a") and last.endswith(("ski", "cki", "dzki")):
                    score += 2
                elif not first.endswith("a") or last.endswith(("ski", "cki", "dzki")):
                    score += 1
            else:
                if first.endswith("a") and last.endswith(("ska", "cka", "dzka")):
                    score += 1
                elif not first.endswith("a") and last.endswith(("ski", "cki", "dzki")):
                    score += 1
        return score

    @classmethod
    def observed_variant_bonus(cls, name: str, observed_tokens: set[str]) -> int:
        bonus = 0
        for token in name.split():
            clean = token.rstrip(".").lower()
            for part in clean.split("-"):
                if len(part) < 3:
                    continue
                if part.endswith("a") and f"{part[:-1]}y" in observed_tokens:
                    bonus += 1
                if f"{part}a" in observed_tokens:
                    bonus += 1
        return bonus

    @classmethod
    def person_stem(cls, token: str) -> str:
        normalized = token.rstrip(".").lower()
        if len(normalized) <= 4:
            return normalized
        for suffix in (
            "owego",
            "iego",
            "emu",
            "owi",
            "ego",
            "ami",
            "ach",
            "om",
            "em",
            "ie",
            "iej",
            "ą",
            "ę",
            "a",
            "u",
            "y",
            "ej",
            "i",
            "ska",
            "ski",
            "cka",
            "cki",
        ):
            if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 3:
                return normalized[: -len(suffix)]
        return normalized

    @classmethod
    def person_tokens_compatible(cls, left: str, right: str) -> bool:
        left_clean = left.rstrip(".").lower()
        right_clean = right.rstrip(".").lower()
        fem_endings = ("ska", "cka", "dzka", "ską", "ckiej", "ską")
        masc_endings = ("ski", "cki", "dzki", "skiego", "skiem", "skiemu")
        left_feminine = any(left_clean.endswith(ending) for ending in fem_endings)
        right_feminine = any(right_clean.endswith(ending) for ending in fem_endings)
        left_masculine = any(left_clean.endswith(ending) for ending in masc_endings)
        right_masculine = any(right_clean.endswith(ending) for ending in masc_endings)
        if (left_feminine and right_masculine) or (left_masculine and right_feminine):
            return False
        if left_clean == right_clean:
            return True
        left_stem = cls.person_stem(left_clean)
        right_stem = cls.person_stem(right_clean)
        if left_stem == right_stem:
            return True
        if (
            len(left_stem) >= 4
            and len(right_stem) >= 4
            and abs(len(left_stem) - len(right_stem)) <= 1
        ):
            matches = sum(
                1
                for left_char, right_char in zip(left_stem, right_stem, strict=False)
                if left_char == right_char
            )
            if matches >= max(len(left_stem), len(right_stem)) - 1:
                return True
        if "-" in left_clean or "-" in right_clean:
            left_parts = left_clean.split("-")
            right_parts = right_clean.split("-")
            if len(left_parts) == len(right_parts):
                return all(
                    cls.person_tokens_compatible(left_part, right_part)
                    for left_part, right_part in zip(left_parts, right_parts, strict=True)
                )
        if left_clean[:1] and right_clean[:1] and (len(left_clean) == 1 or len(right_clean) == 1):
            return left_clean[:1] == right_clean[:1]
        return bool(cls.person_token_variants(left_clean) & cls.person_token_variants(right_clean))

    @classmethod
    def person_token_base(cls, token: str) -> str:
        if not token:
            return ""
        if len(token) <= 3:
            return token
        for suffix in (
            "owego",
            "iego",
            "emu",
            "owi",
            "ego",
            "ami",
            "ach",
            "om",
            "em",
            "ie",
            "iej",
            "ą",
            "ę",
            "a",
            "u",
            "y",
            "ej",
            "i",
        ):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                candidate = token[: -len(suffix)]
                if cls.is_person_base_form(candidate):
                    return candidate
        return token

    @staticmethod
    def is_person_base_form(token: str) -> bool:
        if len(token) < 3:
            return False
        return token[-1] not in {"ą", "ę"} and not token.endswith(
            ("ego", "emu", "owi", "ami", "ach")
        )

    @classmethod
    def single_token_matches_person_cluster(
        cls,
        token: str,
        cluster_tokens: list[str],
    ) -> bool:
        cleaned = token.rstrip(".").lower()
        for cluster_token in cluster_tokens:
            if cls.person_tokens_compatible(cleaned, cluster_token.rstrip(".").lower()):
                return True
        if len(cluster_tokens) >= 2:
            return any(
                cls.person_tokens_compatible(cleaned, cluster_token.rstrip(".").lower())
                for cluster_token in (cluster_tokens[0], cluster_tokens[-1])
            )
        return False

    @classmethod
    def looks_like_inflected_single_token(cls, name: str) -> bool:
        tokens = [token for token in name.split() if token]
        if len(tokens) != 1:
            return False
        token = tokens[0].rstrip(".").lower()
        if len(token) < 4:
            return False
        return cls.person_token_base(token) != token

    @classmethod
    def person_token_variants(cls, token: str) -> set[str]:
        if not token:
            return set()
        base = cls.person_token_base(token)
        variants = {token, base}
        if token.endswith("ku") and len(token) >= 4:
            variants.add(f"{token[:-2]}ek")
        if token.endswith("a") and len(token) >= 4:
            variants.add(token[:-1])
        return {variant for variant in variants if len(variant) >= 3}

    @classmethod
    def surface_repair_for_broken_name(cls, names: list[str]) -> str | None:
        repairs = [
            candidate
            for broken in names
            for candidate in names
            if candidate != broken and cls.person_surface_repairs_broken_name(candidate, broken)
        ]
        if not repairs:
            return None
        return max(repairs, key=lambda name: (cls.name_nominality_score(name), len(name)))

    @staticmethod
    def person_name_has_broken_surface_stem(name: str) -> bool:
        tokens = name.split()
        if len(tokens) < 2:
            return False
        return any(
            PersonNamePolicy.person_token_has_broken_surface_stem(token.lower()) for token in tokens
        )

    @classmethod
    def person_surface_repairs_broken_name(cls, candidate: str, broken: str) -> bool:
        candidate_tokens = candidate.split()
        broken_tokens = broken.split()
        if len(candidate_tokens) != len(broken_tokens):
            return False
        repaired = False
        repaired_non_surname_surface = False
        pending_surname_gender_repair = False
        last_index = len(candidate_tokens) - 1
        for index, (candidate_token, broken_token) in enumerate(
            zip(candidate_tokens, broken_tokens, strict=True)
        ):
            candidate_lower = candidate_token.lower()
            broken_lower = broken_token.lower()
            if candidate_lower == broken_lower:
                continue
            if candidate_lower.startswith(broken_lower) and len(candidate_lower) > len(
                broken_lower
            ):
                if len(candidate_tokens) == 1 and not cls.person_token_has_broken_surface_stem(
                    broken_lower
                ):
                    return False
                if index != last_index and not cls.person_token_has_broken_surface_stem(
                    broken_lower
                ):
                    return False
                repaired = True
                if index != last_index:
                    repaired_non_surname_surface = True
                continue
            if candidate_lower.replace("ó", "o").startswith(broken_lower.replace("ó", "o")) and len(
                candidate_lower
            ) > len(broken_lower):
                repaired = True
                if index != last_index:
                    repaired_non_surname_surface = True
                continue
            if broken_lower.endswith("i") and candidate_lower.endswith("a"):
                if broken_lower.endswith(("ski", "cki", "dzki")):
                    pending_surname_gender_repair = True
                    continue
                repaired = True
                continue
            return False
        return repaired and (not pending_surname_gender_repair or repaired_non_surname_surface)

    @staticmethod
    def person_token_has_broken_surface_stem(token: str) -> bool:
        return token.endswith(("szk", "łaz", "ann", "ieszk", "it")) or token in {
            "agnieszk",
            "joann",
            "ogłaz",
            "anit",
        }

    @staticmethod
    def is_broken_stem(name: str) -> bool:
        tokens = name.split()
        if not tokens:
            return False
        last = tokens[-1].lower()
        return last.endswith(("ńk", "ck", "dzk", "sk")) and not name.lower().endswith(
            ("ska", "ski", "cka", "cki")
        )

    @classmethod
    def is_complete_surname_form(cls, candidate: str, stem_name: str) -> bool:
        candidate_tokens = candidate.split()
        stem_tokens = stem_name.split()
        if len(candidate_tokens) != len(stem_tokens) or len(candidate_tokens) < 2:
            return False
        candidate_last = candidate_tokens[-1].lower()
        stem_last = stem_tokens[-1].lower()
        if not candidate_last.startswith(stem_last):
            return False
        return candidate_last.endswith(("ska", "ski", "cka", "cki", "y", "a"))
