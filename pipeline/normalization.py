from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityID, EntityType, FactType, OrganizationKind
from pipeline.models import ArticleDocument, Entity, Mention
from pipeline.nlp_services import MorphologicalAnalysis, MorphologyAnalyzer
from pipeline.utils import (
    acronym_from_lemmas,
    compact_whitespace,
    lowercase_signature_tokens,
    normalize_entity_name,
    normalize_party_name,
    unique_preserve_order,
)

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

PARTY_TOKEN_VARIANTS = {
    "prawa": "prawo",
    "sprawiedliwości": "sprawiedliwość",
    "platformy": "platforma",
    "obywatelskiej": "obywatelska",
    "lewicy": "lewica",
}


@dataclass(slots=True)
class _EntityCluster:
    primary: Entity
    aliases: set[str]
    mention_count: int


class DocumentEntityCanonicalizer:
    def __init__(
        self,
        config: PipelineConfig,
        morphology: MorphologyAnalyzer | None = None,
    ) -> None:
        self.config = config
        self.morphology = morphology
        self.ambiguous_person_singletons: set[str] = set()
        self._gender_cache: dict[str, str | None] = {}
        self._nominative_cache: dict[str, bool] = {}
        self._morphology_cache: dict[str, MorphologicalAnalysis] = {}
        self.party_lookup = {
            normalize_party_name(alias).lower(): compact_whitespace(canonical)
            for alias, canonical in config.party_aliases.items()
        }
        for canonical in config.party_aliases.values():
            self.party_lookup[normalize_party_name(canonical).lower()] = compact_whitespace(
                canonical
            )
        self.institution_lookup = {
            normalize_entity_name(alias).lower(): compact_whitespace(canonical)
            for alias, canonical in config.institution_aliases.items()
        }
        self.known_acronyms = {
            alias
            for alias in [*config.institution_aliases, *config.party_aliases]
            if self._is_acronym_like(alias)
        }
        self.known_acronym_lookup = {alias.lower(): alias for alias in self.known_acronyms}
        for canonical in config.institution_aliases.values():
            normalized_canonical = normalize_entity_name(canonical)
            self.institution_lookup[normalized_canonical.lower()] = compact_whitespace(canonical)

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not document.entities:
            return document

        # Pre-calculate morphology for persons if service is available
        if self.morphology:
            all_person_names = {
                name
                for entity in document.entities
                if entity.entity_type == EntityType.PERSON
                for name in [entity.canonical_name, entity.normalized_name, *entity.aliases]
                if name and compact_whitespace(name)
            }
            for name in all_person_names:
                analysis = self.morphology.analyze(name)
                self._morphology_cache[name] = analysis
                self._gender_cache[name] = analysis.gender
                self._nominative_cache[name] = analysis.is_nominative

        for entity in document.entities:
            self._normalize_entity(entity)

        self.ambiguous_person_singletons = self._ambiguous_person_singletons(document.entities)

        remap: dict[str, str] = {}
        deduplicated: list[Entity] = []
        for entity in document.entities:
            match = next(
                (
                    candidate
                    for candidate in deduplicated
                    if self._entities_compatible(candidate, entity)
                ),
                None,
            )
            if match is None:
                deduplicated.append(entity)
                continue
            self._merge_entity(match, entity)
            remap[entity.entity_id] = match.entity_id

        document.entities = deduplicated
        self._remap_mentions(document, remap)
        self._remap_fact_graph(document, remap)
        self._refresh_entity_names(document.entities)
        self._validate_party_membership_objects(document)
        return document

    def _normalize_entity(self, entity: Entity) -> None:
        alias_pool = unique_preserve_order(
            [
                entity.canonical_name,
                entity.normalized_name,
                *entity.aliases,
                *self._lemma_name_candidates(entity),
                *self._case_repaired_candidates(entity),
                *self._person_nominative_candidates(entity),
                *self._morphology_lemma_candidates(entity),
            ]
        )
        if entity.entity_type == EntityType.POLITICAL_PARTY:
            canonical = self._canonical_party_name(alias_pool)
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            entity.lemmas = [token.lower() for token in canonical.split()]
            return

        if entity.entity_type == EntityType.PERSON:
            canonical = self._best_person_name(alias_pool)
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            entity.lemmas = self._person_lemmas(canonical)
            return

        specific_acronym_alias = self._specific_acronym_organization_alias(alias_pool)
        if specific_acronym_alias is not None:
            entity.entity_type = EntityType.ORGANIZATION
            entity.canonical_name = specific_acronym_alias
            entity.normalized_name = specific_acronym_alias
            entity.aliases = self._organization_aliases(alias_pool, specific_acronym_alias)
            return

        institution_canonical = self._canonical_institution_name(entity, alias_pool)
        if institution_canonical is not None:
            entity.entity_type = EntityType.PUBLIC_INSTITUTION
            entity.canonical_name = institution_canonical
            entity.normalized_name = institution_canonical
            entity.aliases = self._organization_aliases(alias_pool, institution_canonical)
            entity.organization_kind = OrganizationKind.PUBLIC_INSTITUTION
            return

        canonical = self._best_organization_name(entity, alias_pool)
        entity.canonical_name = canonical
        entity.normalized_name = canonical
        entity.aliases = self._organization_aliases(alias_pool, canonical)

    def _morphology_lemma_candidates(self, entity: Entity) -> list[str]:
        if not self.morphology or entity.entity_type != EntityType.PERSON:
            return []

        candidates = []
        for name in self._raw_names_for_entity(entity):
            if not name or not compact_whitespace(name):
                continue
            analysis = self.morphology.analyze(name)
            lemma = analysis.full_lemma
            if lemma and lemma.lower() != name.lower():
                candidates.append(lemma)
        return candidates

    def _person_nominative_candidates(self, entity: Entity) -> list[str]:
        if entity.entity_type != EntityType.PERSON:
            return []
        candidates = []
        for name in self._raw_names_for_entity(entity):
            if self._canonical_noise_score(name) > 0:
                continue
            tokens = name.split()
            if not tokens or len(tokens) < 2:
                continue

            orig_gender = self._gender_cache.get(name)

            # Try to build likely nominative versions
            stems = [self._person_token_base(t.lower()) for t in tokens]

            # Try common patterns
            # 1. Fem: stem1 + 'a', stem2 + 'ska'
            if stems[0].endswith("i"):  # e.g. "sylwi"
                f1 = stems[0].capitalize() + "a"
            else:
                f1 = stems[0].capitalize()

            if stems[-1].endswith(("sk", "ck", "dzk")):
                l_fem = stems[-1].capitalize() + "a"
                l_masc = stems[-1].capitalize() + "i"

                # Only add if gender matches or is unknown
                if orig_gender in {None, "Fem"}:
                    candidates.append(f"{f1} {l_fem}")
                if orig_gender in {None, "Masc"}:
                    candidates.append(f"{f1} {l_masc}")
            if orig_gender == "Masc" and stems[-1].endswith("kow"):
                surname = f"{stems[-1][:-2]}ów".capitalize()
                candidates.append(f"{f1} {surname}")

        return candidates

    def _entities_compatible(self, left: Entity, right: Entity) -> bool:
        if (
            left.is_proxy_person
            or right.is_proxy_person
            or left.is_honorific_person_ref
            or right.is_honorific_person_ref
        ):
            return left.entity_id == right.entity_id

        if (
            left.entity_type == EntityType.POLITICAL_PARTY
            or right.entity_type == EntityType.POLITICAL_PARTY
        ):
            if left.entity_type != right.entity_type:
                return False
            return self._canonical_party_name(
                self._names_for_entity(left)
            ) == self._canonical_party_name(self._names_for_entity(right))

        if left.entity_type != right.entity_type:
            if {left.entity_type, right.entity_type} <= {
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            }:
                return self._organizations_compatible(left, right)
            return False

        if left.entity_type == EntityType.PERSON:
            return self._persons_compatible(left, right)
        if left.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            return self._organizations_compatible(left, right)
        return left.normalized_name == right.normalized_name

    def _merge_entity(self, target: Entity, source: Entity) -> None:
        target.aliases = unique_preserve_order(
            [*target.aliases, target.canonical_name, source.canonical_name, *source.aliases]
        )
        target.evidence.extend(source.evidence)
        if len(source.aliases) > len(target.aliases):
            target.lemmas = source.lemmas if source.lemmas else target.lemmas

    def _remap_mentions(self, document: ArticleDocument, remap: dict[str, str]) -> None:
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        deduplicated_mentions: dict[tuple[str | None, int, str], Mention] = {}
        from pipeline.domain_types import EntityID

        for mention in document.mentions:
            if mention.entity_id:
                mention.entity_id = EntityID(remap.get(mention.entity_id, mention.entity_id))
            if mention.entity_id and mention.entity_id in entity_by_id:
                mention.normalized_text = entity_by_id[mention.entity_id].canonical_name
            key = (mention.entity_id, mention.sentence_index, mention.text)
            deduplicated_mentions[key] = mention
        document.mentions = list(deduplicated_mentions.values())

    def _refresh_entity_names(self, entities: list[Entity]) -> None:
        for entity in entities:
            self._normalize_entity(entity)

    def _remap_fact_graph(self, document: ArticleDocument, remap: dict[str, str]) -> None:
        if not remap:
            return
        from pipeline.domain_types import EntityID

        for fact in document.facts:
            fact.subject_entity_id = EntityID(
                remap.get(fact.subject_entity_id, fact.subject_entity_id)
            )
            if fact.object_entity_id:
                fact.object_entity_id = EntityID(
                    remap.get(fact.object_entity_id, fact.object_entity_id)
                )
            for field_name in (
                "position_entity_id",
                "owner_context_entity_id",
                "appointing_authority_entity_id",
                "governing_body_entity_id",
            ):
                val = getattr(fact, field_name)
                if isinstance(val, str):
                    setattr(fact, field_name, EntityID(remap.get(val, val)))

    def _persons_compatible(self, left: Entity, right: Entity) -> bool:
        left_tokens = left.normalized_name.split()
        right_tokens = right.normalized_name.split()
        if not left_tokens or not right_tokens:
            return False
        left_full = len(left_tokens) >= 2
        right_full = len(right_tokens) >= 2
        if left.normalized_name == right.normalized_name:
            return True
        if left_full and right_full:
            return self._person_tokens_compatible(
                left_tokens[-1],
                right_tokens[-1],
            ) and self._person_tokens_compatible(left_tokens[0], right_tokens[0])
        if len(left_tokens) == 1 and right_full:
            if self._person_singleton_is_ambiguous(left_tokens[0]):
                return False
            return self._single_token_matches_person_cluster(left_tokens[0], right_tokens)
        if len(right_tokens) == 1 and left_full:
            if self._person_singleton_is_ambiguous(right_tokens[0]):
                return False
            return self._single_token_matches_person_cluster(right_tokens[0], left_tokens)
        return False

    def _person_singleton_is_ambiguous(self, token: str) -> bool:
        return bool(
            self._person_token_variants(token.rstrip(".").lower())
            & self.ambiguous_person_singletons
        )

    def _organizations_compatible(self, left: Entity, right: Entity) -> bool:
        left_names = self._names_for_entity(left)
        right_names = self._names_for_entity(right)
        if left.normalized_name.lower() == right.normalized_name.lower():
            return True

        left_signature = self._organization_signature(left)
        right_signature = self._organization_signature(right)
        if left_signature and right_signature and left_signature == right_signature:
            return True

        if self._shared_acronym(left_names, right_names):
            return True

        left_tokens = set(lowercase_signature_tokens(left.normalized_name))
        right_tokens = set(lowercase_signature_tokens(right.normalized_name))
        overlap = left_tokens & right_tokens
        if overlap and overlap == min(left_tokens, right_tokens, key=len):
            return True
        return False

    def _best_person_name(self, names: list[str]) -> str:
        normalized = [normalize_entity_name(name) for name in names if compact_whitespace(name)]
        if not normalized:
            return ""
        surface_repair = self._surface_repair_for_broken_person_name(normalized)
        if surface_repair is not None:
            return surface_repair
        observed_tokens = {
            token.rstrip(".").lower() for name in normalized for token in name.split() if token
        }
        best = max(
            normalized,
            key=lambda name: (
                -self._canonical_noise_score(name),
                self._nominative_cache.get(name, False),
                not self._looks_like_inflected_single_token_person(name),
                len(name.split()) >= 2,
                self._person_name_observed_variant_bonus(name, observed_tokens),
                self._person_name_nominality_score(name, gender=self._gender_cache.get(name)),
                len(name),
                sum(1 for token in name.split() if len(token) > 1),
            ),
        )

        # High Fidelity Fallback: if 'best' looks like a broken stem (pdb model artifact),
        # try to find a better surface form in the same cluster.
        if self._is_broken_stem(best):
            for candidate in normalized:
                if self._is_complete_surname_form(candidate, best):
                    return candidate

        return best

    @classmethod
    def _surface_repair_for_broken_person_name(cls, names: list[str]) -> str | None:
        broken_names = [name for name in names if cls._person_name_has_broken_surface_stem(name)]
        if not broken_names:
            return None
        repairs = [
            candidate
            for broken in broken_names
            for candidate in names
            if candidate != broken and cls._person_surface_repairs_broken_name(candidate, broken)
        ]
        if not repairs:
            return None
        return max(
            repairs,
            key=lambda name: (
                cls._person_name_nominality_score(name),
                len(name),
            ),
        )

    @staticmethod
    def _person_name_has_broken_surface_stem(name: str) -> bool:
        tokens = name.split()
        if len(tokens) < 2:
            return False
        return any(
            token.lower().endswith(("szk", "łaz", "ann", "ieszk"))
            or token.lower() in {"agnieszk", "joann", "ogłaz"}
            for token in tokens
        )

    @staticmethod
    def _person_surface_repairs_broken_name(candidate: str, broken: str) -> bool:
        candidate_tokens = candidate.split()
        broken_tokens = broken.split()
        if len(candidate_tokens) != len(broken_tokens):
            return False
        repaired = False
        for candidate_token, broken_token in zip(candidate_tokens, broken_tokens, strict=True):
            candidate_lower = candidate_token.lower()
            broken_lower = broken_token.lower()
            if candidate_lower == broken_lower:
                continue
            if candidate_lower.startswith(broken_lower) and len(candidate_lower) > len(
                broken_lower
            ):
                repaired = True
                continue
            if broken_lower.endswith("i") and candidate_lower.endswith("a"):
                repaired = True
                continue
            return False
        return repaired

    def _is_broken_stem(self, name: str) -> bool:
        """Checks if a name looks like a lemmatization artifact (broken stem)."""
        tokens = name.split()
        if not tokens:
            return False
        last = tokens[-1].lower()
        # Common pdb stems often end in a consonant that usually requires a vowel in Nom
        if last.endswith(("ńk", "ck", "dzk", "sk")) and not name.lower().endswith(
            ("ska", "ski", "cka", "cki")
        ):
            return True
        return False

    def _is_complete_surname_form(self, candidate: str, stem_name: str) -> bool:
        """Checks if candidate is a more complete (nominative-like) form of a broken stem."""
        c_tokens = candidate.split()
        s_tokens = stem_name.split()
        if len(c_tokens) != len(s_tokens) or len(c_tokens) < 2:
            return False

        # Surnames must share the same stem
        c_last = c_tokens[-1].lower()
        s_last = s_tokens[-1].lower()

        if not c_last.startswith(s_last):
            return False

        # Candidate must end in a valid nominative-like suffix
        if c_last.endswith(("ska", "ski", "cka", "cki", "y", "a")):
            return True

        return False

    def _best_organization_name(self, entity: Entity, names: list[str]) -> str:
        normalized = [
            normalize_entity_name(name)
            for name in self._candidate_name_parts(names)
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

    def _organization_name_score(
        self,
        entity: Entity,
        name: str,
        candidates: list[str],
    ) -> tuple[int, int, int, int, int, int, int, int, int, int]:
        tokens = [token for token in name.split() if token]
        lower_tokens = {token.lower() for token in tokens}
        generic_count = len(lower_tokens & GENERIC_ORGANIZATION_TOKENS)
        acronym_bonus = sum(1 for token in tokens if self._is_acronym_like(token))
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

    def _canonical_party_name(self, names: list[str]) -> str:
        for name in names:
            normalized = normalize_party_name(name)
            canonical = self.party_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
            canonical = self.party_lookup.get(self._party_lookup_key(normalized))
            if canonical is not None:
                return canonical
        normalized_candidates: list[str] = [
            normalize_party_name(name) for name in names if compact_whitespace(name)
        ]
        if not normalized_candidates:
            return ""
        return str(max(normalized_candidates, key=self._party_name_score))

    def _canonical_institution_name(self, entity: Entity, names: list[str]) -> str | None:
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
        for name in self._candidate_name_parts(names):
            normalized = normalize_entity_name(name)
            normalized_tokens = normalized.split()
            if (
                has_multi_token_primary
                and len(normalized_tokens) == 1
                and normalized_tokens[0].lower() in primary_tokens
                and self._is_acronym_like(normalized_tokens[0])
            ):
                continue
            canonical = self.institution_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
        return None

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

    def _specific_acronym_organization_alias(self, names: list[str]) -> str | None:
        candidates: list[str] = []
        for name in self._candidate_name_parts(names):
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

    @staticmethod
    def _lemma_name_candidates(entity: Entity) -> list[str]:
        lemmas = [
            lemma for lemma in entity.lemmas if isinstance(lemma, str) and compact_whitespace(lemma)
        ]
        if len(lemmas) < 2:
            return []
        if entity.entity_type != EntityType.POLITICAL_PARTY:
            return []
        if all(len(lemma) <= 1 for lemma in lemmas):
            return []
        return [normalize_entity_name(" ".join(lemmas))]

    def _case_repaired_candidates(self, entity: Entity) -> list[str]:
        if entity.entity_type not in {
            EntityType.ORGANIZATION,
            EntityType.PUBLIC_INSTITUTION,
            EntityType.POLITICAL_PARTY,
        }:
            return []
        candidates: list[str] = []
        for name in self._raw_names_for_entity(entity):
            tokens = []
            changed = False
            for token in normalize_entity_name(name).split():
                repaired = self.known_acronym_lookup.get(token.lower(), token)
                tokens.append(repaired)
                changed = changed or repaired != token
            if changed:
                candidates.append(" ".join(tokens))
        return candidates

    @classmethod
    def _party_lookup_key(cls, name: str) -> str:
        tokens = [
            PARTY_TOKEN_VARIANTS.get(token.lower(), token.lower())
            for token in normalize_party_name(name).split()
        ]
        return " ".join(tokens)

    @classmethod
    def _party_name_score(cls, name: str) -> tuple[int, int, int]:
        tokens = [token for token in name.split() if token]
        return (
            -cls._canonical_noise_score(name),
            sum(1 for token in tokens if token.lower() == cls._party_token_base(token.lower())),
            len(name),
        )

    @staticmethod
    def _canonical_noise_score(name: str) -> int:
        tokens = [token.lower() for token in name.split()]
        score = sum(3 for token in tokens if token in NOISY_CANONICAL_TOKENS)
        score += sum(2 for token in tokens if len(token) > 24 and token.lower() != token.upper())
        score += sum(
            2 for token in tokens if any(noise in token for noise in NOISY_CANONICAL_TOKENS)
        )
        return score

    def _organization_aliases(self, names: list[str], canonical: str) -> list[str]:
        normalized_aliases = []
        compacted_multiline_names = self._compacted_multiline_names(names)
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

    @classmethod
    def _organization_inflection_penalty(cls, tokens: list[str]) -> int:
        penalty = 0
        for token in tokens:
            lower = token.lower().strip(".,;:")
            if cls._is_acronym_like(token) or len(lower) < 4:
                continue
            if cls._org_token_base(lower) != lower:
                penalty += 1
        return penalty

    @classmethod
    def _lemma_match_score(cls, entity: Entity, name: str) -> int:
        lemmas = {str(lemma).lower() for lemma in entity.lemmas if isinstance(lemma, str) and lemma}
        if not lemmas:
            return 0
        return sum(1 for token in name.split() if cls._org_token_base(token.lower()) in lemmas)

    @classmethod
    def _org_token_base(cls, token: str) -> str:
        if len(token) <= 3:
            return token
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

    @classmethod
    def _organization_shape_bonus(cls, name: str) -> int:
        bases = [
            cls._org_token_base(token.lower().strip(".,;:")) for token in name.split() if token
        ]
        if not bases:
            return 0
        if bases[0] in PREFERRED_ORGANIZATION_HEADS:
            return 2
        if len(bases) >= 2 and bases[1] in PREFERRED_ORGANIZATION_HEADS:
            return 2
        return 0

    @classmethod
    def _organization_prefix_junk_penalty(cls, name: str, candidates: list[str]) -> int:
        bases = [
            cls._org_token_base(token.lower().strip(".,;:")) for token in name.split() if token
        ]
        penalty = 0
        for candidate in candidates:
            if candidate == name:
                continue
            candidate_bases = [
                cls._org_token_base(token.lower().strip(".,;:"))
                for token in candidate.split()
                if token
            ]
            if len(candidate_bases) < 2 or len(candidate_bases) >= len(bases):
                continue
            if bases[: len(candidate_bases)] == candidate_bases:
                penalty = max(penalty, len(bases) - len(candidate_bases))
        return penalty

    @classmethod
    def _foundation_public_body_penalty(cls, tokens: list[str]) -> int:
        if len(tokens) < 2:
            return 0
        head = cls._org_token_base(tokens[0].lower().strip(".,;:"))
        second = tokens[1].lower().strip(".,;:")
        if head not in {"fundacja", "stowarzyszenie"}:
            return 0
        if second.startswith(("kancelar", "minister", "urz", "fundusz", "instytut")):
            return 2
        return 0

    @classmethod
    def _bare_organization_head_superseded(cls, name: str, candidates: list[str]) -> bool:
        tokens = [token for token in name.split() if token]
        if len(tokens) != 1:
            return False
        head = cls._org_token_base(tokens[0].lower())
        if head not in PREFERRED_ORGANIZATION_HEADS:
            return False
        return any(
            other != name
            and len(other.split()) > 1
            and cls._org_token_base(other.split()[0].lower()) == head
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

    @classmethod
    def _organization_evidence_bonus(cls, entity: Entity, name: str) -> int:
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

    @classmethod
    def _party_token_base(cls, token: str) -> str:
        mapped = PARTY_TOKEN_VARIANTS.get(token)
        if mapped is not None:
            return mapped
        return cls._org_token_base(token)

    @staticmethod
    def _person_lemmas(name: str) -> list[str]:
        return [
            token.lower()
            for token in normalize_entity_name(name).replace("-", " ").split()
            if token
        ]

    @classmethod
    def _ambiguous_person_singletons(cls, entities: list[Entity]) -> set[str]:
        surname_to_given_bases: dict[str, set[str]] = {}
        for entity in entities:
            if entity.entity_type != EntityType.PERSON or entity.is_proxy_person:
                continue
            tokens = normalize_entity_name(entity.normalized_name).split()
            if len(tokens) < 2:
                continue
            surname_variants = cls._person_token_variants(tokens[-1].rstrip(".").lower())
            given_base = cls._person_token_base(tokens[0].rstrip(".").lower())
            for surname_variant in surname_variants:
                surname_to_given_bases.setdefault(surname_variant, set()).add(given_base)
        return {
            surname
            for surname, given_bases in surname_to_given_bases.items()
            if len(given_bases) > 1
        }

    @classmethod
    def _person_name_nominality_score(cls, name: str, gender: str | None = None) -> int:
        tokens = [token for token in name.split() if token]
        if not tokens:
            return 0
        score = 0
        for token in tokens:
            base = token.rstrip(".").lower()
            if "-" in base:
                parts = base.split("-")
                if all(cls._person_token_base(part) == part for part in parts):
                    score += 2
                continue
            if cls._person_token_base(base) == base and cls._is_person_base_form(base):
                score += 2

            # Bonus for likely nominative endings in Polish
            if base.endswith(("ska", "cka", "dzka", "ski", "cki", "dzki")):
                score += 2
            elif base.endswith("ów"):
                score += 2
            elif base.endswith("a") and not base.endswith(("owa", "yna")):
                score += 1

        # Gender consistency bonus for Polish names
        if len(tokens) >= 2:
            first = tokens[0].rstrip(".").lower()
            last = tokens[-1].rstrip(".").lower()

            # Use high-fidelity gender if available
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
                # Fallback to heuristics
                # Feminine: first name usually ends in 'a', surname in 'ska/cka/dzka'
                if first.endswith("a") and last.endswith(("ska", "cka", "dzka")):
                    score += 1
                # Masculine: first name usually doesn't end in 'a', surname in 'ski/cki/dzki'
                elif not first.endswith("a") and last.endswith(("ski", "cki", "dzki")):
                    score += 1

        return score

    @classmethod
    def _person_name_observed_variant_bonus(
        cls,
        name: str,
        observed_tokens: set[str],
    ) -> int:
        bonus = 0
        for token in name.split():
            clean = token.rstrip(".").lower()
            parts = clean.split("-")
            for part in parts:
                if len(part) < 3:
                    continue
                if part.endswith("a") and f"{part[:-1]}y" in observed_tokens:
                    bonus += 1
                if f"{part}a" in observed_tokens:
                    bonus += 1
        return bonus

    @classmethod
    def _person_stem(cls, token: str) -> str:
        t = token.rstrip(".").lower()
        if len(t) <= 4:
            return t
        # Remove common inflections to get a core stem
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
            if t.endswith(suffix) and len(t) - len(suffix) >= 3:
                return t[: -len(suffix)]
        return t

    @classmethod
    def _person_tokens_compatible(cls, left: str, right: str) -> bool:
        left_clean = left.rstrip(".").lower()
        right_clean = right.rstrip(".").lower()

        # Prevent merging different genders of Polish surnames.
        fem_endings = ("ska", "cka", "dzka", "ską", "ckiej", "ską")
        masc_endings = ("ski", "cki", "dzki", "skiego", "skiem", "skiemu")
        left_feminine = any(left_clean.endswith(e) for e in fem_endings)
        right_feminine = any(right_clean.endswith(e) for e in fem_endings)
        left_masculine = any(left_clean.endswith(e) for e in masc_endings)
        right_masculine = any(right_clean.endswith(e) for e in masc_endings)
        if (left_feminine and right_masculine) or (left_masculine and right_feminine):
            return False

        if left_clean == right_clean:
            return True

        # Fuzzy match for broken lemmas or typos
        l_stem = cls._person_stem(left_clean)
        r_stem = cls._person_stem(right_clean)
        if l_stem == r_stem:
            return True

        # Levenshtein fallback for stems (handling Giermasińk vs Giermasińsk)
        if len(l_stem) >= 4 and len(r_stem) >= 4:
            # We don't want a heavy dependency, so use a simple check for 1-char difference
            if abs(len(l_stem) - len(r_stem)) <= 1:
                matches = 0
                for c1, c2 in zip(l_stem, r_stem):
                    if c1 == c2:
                        matches += 1
                if matches >= max(len(l_stem), len(r_stem)) - 1:
                    return True

        if "-" in left_clean or "-" in right_clean:
            left_parts = left_clean.split("-")
            right_parts = right_clean.split("-")
            if len(left_parts) == len(right_parts):
                return all(
                    cls._person_tokens_compatible(left_part, right_part)
                    for left_part, right_part in zip(left_parts, right_parts, strict=True)
                )
        if left_clean[:1] and right_clean[:1] and (len(left_clean) == 1 or len(right_clean) == 1):
            return left_clean[:1] == right_clean[:1]
        left_variants = cls._person_token_variants(left_clean)
        right_variants = cls._person_token_variants(right_clean)
        return bool(left_variants & right_variants)

    @classmethod
    def _person_token_base(cls, token: str) -> str:
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
                if cls._is_person_base_form(candidate):
                    return candidate
        return token

    @staticmethod
    def _is_person_base_form(token: str) -> bool:
        if len(token) < 3:
            return False
        return token[-1] not in {"ą", "ę"} and not token.endswith(
            ("ego", "emu", "owi", "ami", "ach")
        )

    @classmethod
    def _single_token_matches_person_cluster(
        cls,
        token: str,
        cluster_tokens: list[str],
    ) -> bool:
        t_clean = token.rstrip(".").lower()
        for ct in cluster_tokens:
            ct_clean = ct.rstrip(".").lower()
            if cls._person_tokens_compatible(t_clean, ct_clean):
                return True

        if len(cluster_tokens) >= 2:
            # Check first/last name compatibility
            for ct in (cluster_tokens[0], cluster_tokens[-1]):
                if cls._person_tokens_compatible(t_clean, ct.rstrip(".").lower()):
                    return True
        return False

    @classmethod
    def _looks_like_inflected_single_token_person(cls, name: str) -> bool:
        tokens = [token for token in name.split() if token]
        if len(tokens) != 1:
            return False
        token = tokens[0].rstrip(".").lower()
        if len(token) < 4:
            return False
        return cls._person_token_base(token) != token

    @classmethod
    def _person_token_variants(cls, token: str) -> set[str]:
        if not token:
            return set()
        base = cls._person_token_base(token)
        variants = {token, base}
        if token.endswith("ku") and len(token) >= 4:
            variants.add(f"{token[:-2]}ek")
        if token.endswith("a") and len(token) >= 4:
            variants.add(token[:-1])
        return {variant for variant in variants if len(variant) >= 3}

    @staticmethod
    def _names_for_entity(entity: Entity) -> list[str]:
        return unique_preserve_order(
            name
            for name in [entity.canonical_name, entity.normalized_name, *entity.aliases]
            if compact_whitespace(name) and "\n" not in name and "\r" not in name
        )

    @staticmethod
    def _raw_names_for_entity(entity: Entity) -> list[str]:
        return unique_preserve_order(
            [entity.canonical_name, entity.normalized_name, *entity.aliases]
        )

    @staticmethod
    def _candidate_name_parts(names: list[str]) -> list[str]:
        candidates: list[str] = []
        compacted_multiline_names = DocumentEntityCanonicalizer._compacted_multiline_names(names)
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
    def _compacted_multiline_names(names: list[str]) -> set[str]:
        return {
            normalize_entity_name(name)
            for name in names
            if ("\n" in name or "\r" in name) and compact_whitespace(name)
        }

    @staticmethod
    def _shared_acronym(left_names: list[str], right_names: list[str]) -> bool:
        left_acronyms = {
            acronym
            for name in left_names
            for acronym in DocumentEntityCanonicalizer._name_acronyms(name)
            if acronym
        }
        right_acronyms = {
            acronym
            for name in right_names
            for acronym in DocumentEntityCanonicalizer._name_acronyms(name)
            if acronym
        }
        return bool(left_acronyms & right_acronyms)

    @staticmethod
    def _name_acronyms(name: str) -> set[str]:
        normalized = normalize_entity_name(name)
        tokens = normalized.split()
        acronyms = set()
        if normalized:
            acronym_tokens = DocumentEntityCanonicalizer._acronym_tokens(tokens)
            acronym = acronym_from_lemmas(token.lower() for token in acronym_tokens)
            if acronym:
                acronyms.add(acronym.lower())
        if len(tokens) == 1 and DocumentEntityCanonicalizer._is_acronym_like(tokens[0]):
            acronyms.add(tokens[0].lower())
        return acronyms

    @staticmethod
    def _organization_signature(entity: Entity) -> tuple[str, ...]:
        lemmas = [
            lemma.lower()
            for lemma in entity.lemmas
            if lemma and lemma.lower() not in {"i", "w", "z", "na", "do"}
        ]
        if lemmas:
            return tuple(sorted(dict.fromkeys(lemmas)))
        return tuple(lowercase_signature_tokens(entity.normalized_name))

    @staticmethod
    def _is_acronym_like(token: str) -> bool:
        letters = [char for char in token if char.isalpha()]
        if len(letters) >= 2 and all(char.isupper() for char in letters):
            return True
        return any(char.isupper() for char in token[1:])

    @staticmethod
    def _acronym_tokens(tokens: list[str]) -> list[str]:
        if len(tokens) >= 2 and tokens[-2].lower() in {"w", "we", "z", "na"}:
            tokens = tokens[:-2]
        return [token for token in tokens if token.lower() not in {"w"}]

    def _validate_party_membership_objects(self, document: ArticleDocument) -> None:
        if not document.facts:
            return
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        party_by_name: dict[str, Entity] = {}
        for entity in document.entities:
            if entity.entity_type != EntityType.POLITICAL_PARTY:
                continue
            for name in self._names_for_entity(entity):
                party_by_name[normalize_party_name(name).casefold()] = entity
            canonical = self._canonical_party_name(self._names_for_entity(entity))
            if canonical:
                party_by_name[normalize_party_name(canonical).casefold()] = entity

        validated = []
        for fact in document.facts:
            if fact.fact_type not in {
                FactType.PARTY_MEMBERSHIP,
                FactType.FORMER_PARTY_MEMBERSHIP,
            }:
                validated.append(fact)
                continue
            if fact.object_entity_id is not None:
                entity = entity_by_id.get(fact.object_entity_id)
                if entity is not None and entity.entity_type == EntityType.POLITICAL_PARTY:
                    validated.append(fact)
                    continue

            remap_party = self._party_entity_for_fact(
                fact.party,
                fact.value_normalized,
                party_by_name=party_by_name,
            )
            if remap_party is None:
                continue
            fact.object_entity_id = EntityID(remap_party.entity_id)
            fact.value_text = remap_party.canonical_name
            fact.value_normalized = remap_party.normalized_name
            fact.party = remap_party.canonical_name
            validated.append(fact)
        document.facts = validated

    def _party_entity_for_fact(
        self,
        *names: str | None,
        party_by_name: dict[str, Entity],
    ) -> Entity | None:
        for name in names:
            if not name:
                continue
            canonical = self._canonical_party_name([name])
            for candidate in (name, canonical):
                normalized = normalize_party_name(candidate).casefold()
                party = party_by_name.get(normalized)
                if party is not None:
                    return party
        return None
