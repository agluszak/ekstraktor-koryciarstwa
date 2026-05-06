from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityID, EntityType, FactType, OrganizationKind
from pipeline.entity_graph_remapper import EntityGraphRemapper
from pipeline.entity_name_policies import PartyNamingPolicy, PersonNamePolicy
from pipeline.entity_naming import (
    LocationNamingPolicy,
    OrganizationNamingPolicy,
    is_acronym_like,
)
from pipeline.models import ArticleDocument, Entity
from pipeline.nlp_services import MorphologyAnalyzer
from pipeline.utils import (
    acronym_from_lemmas,
    compact_whitespace,
    lowercase_signature_tokens,
    normalize_entity_name,
    normalize_party_name,
    unique_preserve_order,
)

ADMIN_UNIT_HEADS = frozenset({"gmina", "miasto", "powiat", "województwo"})
GOVERNING_BODY_TOKENS = frozenset({"komisja", "komitet", "rada", "rn", "zarząd"})


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
        self.ambiguous_person_singletons: set[str] = set()
        self.person_naming = PersonNamePolicy(morphology)
        self.party_naming = PartyNamingPolicy(config.party_aliases)
        self.institution_lookup = {
            normalize_entity_name(alias).lower(): compact_whitespace(canonical)
            for alias, canonical in config.institution_aliases.items()
        }
        self.known_acronyms = {
            alias
            for alias in [*config.institution_aliases, *config.party_aliases]
            if is_acronym_like(alias)
        }
        self.known_acronym_lookup = {alias.lower(): alias for alias in self.known_acronyms}
        for canonical in config.institution_aliases.values():
            normalized_canonical = normalize_entity_name(canonical)
            self.institution_lookup[normalized_canonical.lower()] = compact_whitespace(canonical)
        self.organization_naming = OrganizationNamingPolicy(
            institution_lookup=self.institution_lookup,
            known_acronyms=self.known_acronyms,
        )
        self.location_naming = LocationNamingPolicy()

    def run(self, document: ArticleDocument) -> ArticleDocument:
        if not document.entities:
            return document

        all_person_names = {
            name
            for entity in document.entities
            if entity.entity_type == EntityType.PERSON
            for name in [entity.canonical_name, entity.normalized_name, *entity.aliases]
            if name and compact_whitespace(name)
        }
        self.person_naming.preload(all_person_names)

        for entity in document.entities:
            self.normalize_entity(entity)

        self.ambiguous_person_singletons = self.person_naming.ambiguous_person_singletons(
            document.entities
        )

        remap: dict[EntityID, EntityID] = {}
        deduplicated: list[Entity] = []
        for entity in document.entities:
            match = next(
                (
                    candidate
                    for candidate in deduplicated
                    if self.entities_compatible(candidate, entity)
                ),
                None,
            )
            if match is None:
                deduplicated.append(entity)
                continue
            EntityGraphRemapper.merge_entity(match, entity)
            remap[entity.entity_id] = match.entity_id

        document.entities = deduplicated
        EntityGraphRemapper.remap_mentions(document, remap)
        EntityGraphRemapper.remap_fact_graph(document, remap)
        self._refresh_entity_names(document.entities)
        self._validate_party_membership_objects(document)
        return document

    def normalize_entity(self, entity: Entity) -> None:
        alias_pool = unique_preserve_order(
            [
                entity.canonical_name,
                entity.normalized_name,
                *entity.aliases,
                *self._lemma_name_candidates(entity),
                *self._case_repaired_candidates(entity),
                *self._person_nominative_candidates(self._raw_names_for_entity(entity)),
                *self._morphology_lemma_candidates(self._raw_names_for_entity(entity)),
            ]
        )
        if entity.entity_type == EntityType.POLITICAL_PARTY:
            canonical = self.party_naming.canonical_name(alias_pool)
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            entity.lemmas = [token.lower() for token in canonical.split()]
            return

        if entity.entity_type == EntityType.PERSON:
            canonical = self.person_naming.best_person_name(alias_pool)
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            entity.lemmas = self.person_naming.person_lemmas(canonical)
            return

        if entity.entity_type == EntityType.LOCATION:
            institution_canonical = self._location_public_institution_name(alias_pool)
            if institution_canonical is not None:
                entity.entity_type = EntityType.PUBLIC_INSTITUTION
                entity.canonical_name = institution_canonical
                entity.normalized_name = institution_canonical
                entity.aliases = self.organization_naming.organization_aliases(
                    alias_pool,
                    institution_canonical,
                )
                entity.organization_kind = OrganizationKind.PUBLIC_INSTITUTION
                return
            canonical = self.location_naming.best_location_name(alias_pool)
            if canonical:
                entity.canonical_name = canonical
                entity.normalized_name = canonical
                entity.aliases = unique_preserve_order([*alias_pool, canonical])
            return

        specific_acronym_alias = self.organization_naming.specific_acronym_alias(alias_pool)
        if specific_acronym_alias is not None:
            entity.entity_type = EntityType.ORGANIZATION
            entity.canonical_name = specific_acronym_alias
            entity.normalized_name = specific_acronym_alias
            entity.aliases = self.organization_naming.organization_aliases(
                alias_pool,
                specific_acronym_alias,
            )
            return

        institution_canonical = self.organization_naming.canonical_institution_name(
            entity,
            alias_pool,
        )
        if institution_canonical is not None:
            entity.entity_type = EntityType.PUBLIC_INSTITUTION
            entity.canonical_name = institution_canonical
            entity.normalized_name = institution_canonical
            entity.aliases = self.organization_naming.organization_aliases(
                alias_pool,
                institution_canonical,
            )
            entity.organization_kind = OrganizationKind.PUBLIC_INSTITUTION
            return

        if entity.entity_type in {EntityType.EVENT, EntityType.LAW, EntityType.MONEY}:
            # For these types, pick the longest name as most descriptive
            canonical = max(alias_pool, key=len) if alias_pool else entity.canonical_name
            entity.canonical_name = canonical
            entity.normalized_name = canonical
            entity.aliases = unique_preserve_order([*alias_pool, canonical])
            return

        canonical = self.organization_naming.best_organization_name(entity, alias_pool)
        entity.canonical_name = canonical
        entity.normalized_name = canonical
        entity.aliases = self.organization_naming.organization_aliases(alias_pool, canonical)

    def best_person_name(self, names: list[str]) -> str:
        return self.person_naming.best_person_name(names)

    def best_organization_name(self, entity: Entity, names: list[str]) -> str:
        return self.organization_naming.best_organization_name(entity, names)

    def _morphology_lemma_candidates(self, names: list[str]) -> list[str]:
        if not names:
            return []
        return self.person_naming.morphology_lemma_candidates(names)

    def _person_nominative_candidates(self, names: list[str]) -> list[str]:
        if not names:
            return []
        return self.person_naming.nominative_candidates(names)

    def entities_compatible(self, left: Entity, right: Entity) -> bool:
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
            return self.party_naming.canonical_name(
                self._names_for_entity(left)
            ) == self.party_naming.canonical_name(self._names_for_entity(right))

        if left.entity_type != right.entity_type:
            if {left.entity_type, right.entity_type} <= {
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            }:
                return self._organizations_compatible(left, right)
            return False

        if left.entity_type == EntityType.PERSON:
            return self._persons_compatible(left, right)
        if left.entity_type == EntityType.LOCATION:
            return self._locations_compatible(left, right)
        if left.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            return self._organizations_compatible(left, right)
        return left.normalized_name == right.normalized_name

    def _refresh_entity_names(self, entities: list[Entity]) -> None:
        for entity in entities:
            self.normalize_entity(entity)

    def _persons_compatible(self, left: Entity, right: Entity) -> bool:
        return self.person_naming.persons_compatible(
            left.normalized_name,
            right.normalized_name,
            self.ambiguous_person_singletons,
        )

    def ambiguous_person_names(self, entities: list[Entity]) -> set[str]:
        return self.person_naming.ambiguous_person_singletons(entities)

    def _organizations_compatible(self, left: Entity, right: Entity) -> bool:
        left_names = self._names_for_entity(left)
        right_names = self._names_for_entity(right)
        if left.normalized_name.lower() == right.normalized_name.lower():
            return True
        if self._governing_body_mismatch(left_names, right_names):
            return False

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

    def _locations_compatible(self, left: Entity, right: Entity) -> bool:
        if left.normalized_name.lower() == right.normalized_name.lower():
            return True
        return self._location_signature(left) == self._location_signature(right)

    def _location_public_institution_name(self, names: list[str]) -> str | None:
        exact_alias = self.organization_naming.canonical_institution_name(
            Entity(
                entity_id=EntityID(""),
                entity_type=EntityType.LOCATION,
                canonical_name=names[0] if names else "",
                normalized_name=names[0] if names else "",
            ),
            names,
        )
        if exact_alias is not None:
            return exact_alias
        for name in names:
            normalized = normalize_entity_name(name)
            tokens = normalized.split()
            if len(tokens) < 2:
                continue
            if tokens[0].casefold() in ADMIN_UNIT_HEADS:
                return normalized
        return None

    @staticmethod
    def _governing_body_mismatch(left_names: list[str], right_names: list[str]) -> bool:
        return DocumentEntityCanonicalizer._has_governing_body_marker(
            left_names
        ) != DocumentEntityCanonicalizer._has_governing_body_marker(right_names)

    @staticmethod
    def _has_governing_body_marker(names: list[str]) -> bool:
        for name in names:
            normalized = normalize_entity_name(name).casefold()
            if normalized.startswith("rada nadzorcza"):
                return True
            tokens = set(lowercase_signature_tokens(normalized))
            if tokens.intersection(GOVERNING_BODY_TOKENS):
                return True
        return False

    @staticmethod
    def _lemma_name_candidates(entity: Entity) -> list[str]:
        lemmas = [
            lemma for lemma in entity.lemmas if isinstance(lemma, str) and compact_whitespace(lemma)
        ]
        if not lemmas:
            return []
        if entity.entity_type == EntityType.LOCATION:
            return [normalize_entity_name(" ".join(lemmas))]
        if len(lemmas) < 2 or entity.entity_type != EntityType.POLITICAL_PARTY:
            return []
        if all(len(lemma) <= 1 for lemma in lemmas):
            return []
        return [normalize_entity_name(" ".join(lemmas))]

    def _case_repaired_candidates(self, entity: Entity) -> list[str]:
        if entity.entity_type not in {
            EntityType.ORGANIZATION,
            EntityType.PUBLIC_INSTITUTION,
            EntityType.POLITICAL_PARTY,
            EntityType.LOCATION,
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
    def _location_signature(entity: Entity) -> tuple[str, ...]:
        lemmas = [
            lemma.lower()
            for lemma in entity.lemmas
            if lemma and lemma.lower() not in {"i", "w", "we", "z", "na", "do"}
        ]
        if lemmas:
            return tuple(sorted(dict.fromkeys(lemmas)))
        return tuple(lowercase_signature_tokens(entity.normalized_name))

    @staticmethod
    def _is_acronym_like(token: str) -> bool:
        return is_acronym_like(token)

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
                party_by_name[self.party_naming.lookup_key(name)] = entity
                party_by_name[normalize_party_name(name).casefold()] = entity
            canonical = self.party_naming.canonical_name(self._names_for_entity(entity))
            if canonical:
                party_by_name[self.party_naming.lookup_key(canonical)] = entity
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
            canonical = self.party_naming.canonical_name([name])
            for candidate in (name, canonical):
                normalized = normalize_party_name(candidate).casefold()
                party = party_by_name.get(normalized)
                if party is None:
                    party = party_by_name.get(self.party_naming.lookup_key(candidate))
                if party is not None:
                    return party
        return None
