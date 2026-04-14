from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, OrganizationKind
from pipeline.models import ArticleDocument, Entity, Mention
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


@dataclass(slots=True)
class _EntityCluster:
    primary: Entity
    aliases: set[str]
    mention_count: int


class DocumentEntityCanonicalizer:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
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
        for canonical in config.institution_aliases.values():
            normalized_canonical = normalize_entity_name(canonical)
            self.institution_lookup[normalized_canonical.lower()] = compact_whitespace(canonical)

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not document.entities:
            return document

        for entity in document.entities:
            self._normalize_entity(entity)

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
        self._refresh_entity_names(document.entities)
        return document

    def _normalize_entity(self, entity: Entity) -> None:
        alias_pool = unique_preserve_order(
            [
                entity.canonical_name,
                entity.normalized_name,
                *entity.aliases,
            ]
        )
        if entity.entity_type == EntityType.POLITICAL_PARTY:
            canonical = self._canonical_party_name(alias_pool)
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            entity.attributes["lemmas"] = [token.lower() for token in canonical.split()]
            return

        if entity.entity_type == EntityType.PERSON:
            canonical = self._best_person_name(alias_pool)
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            entity.attributes["lemmas"] = self._person_lemmas(canonical)
            return

        institution_canonical = self._canonical_institution_name(alias_pool)
        if institution_canonical is not None:
            entity.entity_type = EntityType.PUBLIC_INSTITUTION
            entity.canonical_name = institution_canonical
            entity.normalized_name = institution_canonical
            entity.aliases = unique_preserve_order([*alias_pool, institution_canonical])
            entity.attributes["organization_kind"] = OrganizationKind.PUBLIC_INSTITUTION
            return

        canonical = self._best_organization_name(entity, alias_pool)
        entity.canonical_name = canonical
        entity.normalized_name = canonical
        entity.aliases = unique_preserve_order([*alias_pool, canonical])

    def _entities_compatible(self, left: Entity, right: Entity) -> bool:
        if (
            left.entity_type == EntityType.POLITICAL_PARTY
            or right.entity_type == EntityType.POLITICAL_PARTY
        ):
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
            target.attributes["lemmas"] = source.attributes.get(
                "lemmas",
                target.attributes.get("lemmas", []),
            )

    def _remap_mentions(self, document: ArticleDocument, remap: dict[str, str]) -> None:
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        deduplicated_mentions: dict[tuple[str | None, int, str], Mention] = {}
        for mention in document.mentions:
            if mention.entity_id:
                mention.entity_id = remap.get(mention.entity_id, mention.entity_id)
            if mention.entity_id and mention.entity_id in entity_by_id:
                mention.normalized_text = entity_by_id[mention.entity_id].canonical_name
            key = (mention.entity_id, mention.sentence_index, mention.text)
            deduplicated_mentions[key] = mention
        document.mentions = list(deduplicated_mentions.values())

    def _refresh_entity_names(self, entities: list[Entity]) -> None:
        for entity in entities:
            self._normalize_entity(entity)

    def _persons_compatible(self, left: Entity, right: Entity) -> bool:
        left_tokens = left.normalized_name.split()
        right_tokens = right.normalized_name.split()
        if not left_tokens or not right_tokens:
            return False
        if left_tokens[-1].lower() != right_tokens[-1].lower():
            if not self._person_tokens_compatible(left_tokens[-1], right_tokens[-1]):
                return False
        if left.normalized_name == right.normalized_name:
            return True
        left_full = len(left_tokens) >= 2
        right_full = len(right_tokens) >= 2
        if left_full and right_full:
            return self._person_tokens_compatible(left_tokens[0], right_tokens[0])
        if len(left_tokens) == 1 and right_full:
            return True
        if len(right_tokens) == 1 and left_full:
            return True
        return False

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
        observed_tokens = {
            token.rstrip(".").lower() for name in normalized for token in name.split() if token
        }
        return max(
            normalized,
            key=lambda name: (
                len(name.split()) >= 2,
                self._person_name_observed_variant_bonus(name, observed_tokens),
                self._person_name_nominality_score(name),
                len(name),
                sum(1 for token in name.split() if len(token) > 1),
            ),
        )

    def _best_organization_name(self, entity: Entity, names: list[str]) -> str:
        normalized = [normalize_entity_name(name) for name in names if compact_whitespace(name)]
        if not normalized:
            return entity.canonical_name
        return max(normalized, key=lambda name: self._organization_name_score(entity, name))

    def _organization_name_score(self, entity: Entity, name: str) -> tuple[int, int, int]:
        tokens = [token for token in name.split() if token]
        lower_tokens = {token.lower() for token in tokens}
        generic_count = len(lower_tokens & GENERIC_ORGANIZATION_TOKENS)
        acronym_bonus = sum(1 for token in tokens if self._is_acronym_like(token))
        return (
            -generic_count,
            len(tokens) + acronym_bonus,
            len(name),
        )

    def _canonical_party_name(self, names: list[str]) -> str:
        for name in names:
            normalized = normalize_party_name(name)
            canonical = self.party_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
        normalized_candidates: list[str] = [
            normalize_party_name(name) for name in names if compact_whitespace(name)
        ]
        if not normalized_candidates:
            return ""
        return str(max(normalized_candidates, key=len))

    def _canonical_institution_name(self, names: list[str]) -> str | None:
        for name in names:
            normalized = normalize_entity_name(name)
            canonical = self.institution_lookup.get(normalized.lower())
            if canonical is not None:
                return canonical
        return None

    @staticmethod
    def _person_lemmas(name: str) -> list[str]:
        return [
            token.lower()
            for token in normalize_entity_name(name).replace("-", " ").split()
            if token
        ]

    @classmethod
    def _person_name_nominality_score(cls, name: str) -> int:
        tokens = [token for token in name.split() if token]
        if not tokens:
            return 0
        score = 0
        for token in tokens:
            base = token.rstrip(".").lower()
            if "-" in base:
                parts = base.split("-")
                if all(cls._person_token_base(part) == part for part in parts):
                    score += 1
                continue
            if cls._person_token_base(base) == base and cls._is_person_base_form(base):
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
    def _person_tokens_compatible(cls, left: str, right: str) -> bool:
        left_clean = left.rstrip(".").lower()
        right_clean = right.rstrip(".").lower()
        if left_clean == right_clean:
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
        left_base = cls._person_token_base(left_clean)
        right_base = cls._person_token_base(right_clean)
        return bool(left_base and right_base and left_base == right_base)

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
            "ą",
            "ę",
            "a",
            "u",
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

    @staticmethod
    def _names_for_entity(entity: Entity) -> list[str]:
        return unique_preserve_order(
            [entity.canonical_name, entity.normalized_name, *entity.aliases]
        )

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
            for lemma in entity.attributes.get("lemmas", [])
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
