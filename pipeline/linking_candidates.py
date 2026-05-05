"""Candidate-generation strategy for alias-based entity linking."""

from __future__ import annotations

from pipeline.base import CandidateGenerator, EntityKnowledgeBase
from pipeline.domain_types import EntityType
from pipeline.linking_kb import token_bases_for
from pipeline.models import Entity, EntityCluster, EntityFingerprint, KBEntityRecord

_ORG_GENERIC_HEADS = frozenset(
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


class AliasCandidateGenerator(CandidateGenerator):
    """Generates KB candidate records from a cluster's surface forms.

    Delegates the actual KB lookup to the injected :class:`EntityKnowledgeBase`.
    """

    def __init__(self, kb: EntityKnowledgeBase) -> None:
        self._kb = kb

    # ------------------------------------------------------------------
    # CandidateGenerator ABC
    # ------------------------------------------------------------------

    def candidates_for_cluster(self, cluster: EntityCluster) -> list[KBEntityRecord]:
        return self._kb.get_candidates(cluster)

    # ------------------------------------------------------------------
    # Name-set generation
    # ------------------------------------------------------------------

    def alias_search_names_from_entity(self, entity: Entity) -> set[str]:
        """Return the deduplicated set of alias strings to search for *entity*."""
        primary_names = {
            name
            for name in {entity.canonical_name, entity.normalized_name}
            if "\n" not in name and "\r" not in name
        }
        if entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            primary_names = {
                name for name in primary_names if self.is_specific_organization_alias(name)
            }
        primary_tokens = {
            token.lower() for name in primary_names for token in name.split() if token
        }
        has_multi_token_primary = any(len(name.split()) > 1 for name in primary_names)
        names = set(primary_names)
        for alias in entity.aliases:
            if "\n" in alias or "\r" in alias:
                continue
            alias_tokens = alias.split()
            alias_is_component_acronym = (
                has_multi_token_primary
                and len(alias_tokens) == 1
                and alias_tokens[0].lower() in primary_tokens
                and alias_tokens[0].isupper()
            )
            alias_allowed = True
            if entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                alias_allowed = self.is_specific_organization_alias(alias)
            if alias_allowed and not alias_is_component_acronym:
                names.add(alias)
        return names

    def alias_search_names_from_cluster(self, cluster: EntityCluster) -> set[str]:
        """Return the deduplicated set of alias strings to search for *cluster*."""
        primary_names = {
            name
            for name in {cluster.canonical_name, cluster.normalized_name}
            if "\n" not in name and "\r" not in name
        }
        if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
            primary_names = {
                name for name in primary_names if self.is_specific_organization_alias(name)
            }
        primary_tokens = {
            token.lower() for name in primary_names for token in name.split() if token
        }
        has_multi_token_primary = any(len(name.split()) > 1 for name in primary_names)
        names = set(primary_names)
        for alias in cluster.aliases:
            if "\n" in alias or "\r" in alias:
                continue
            alias_tokens = alias.split()
            alias_is_component_acronym = (
                has_multi_token_primary
                and len(alias_tokens) == 1
                and alias_tokens[0].lower() in primary_tokens
                and alias_tokens[0].isupper()
            )
            alias_allowed = True
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                alias_allowed = self.is_specific_organization_alias(alias)
            if alias_allowed and not alias_is_component_acronym:
                names.add(alias)
        return names

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    @staticmethod
    def fingerprint_from_entity(entity: Entity) -> EntityFingerprint:
        tokens = entity.normalized_name.split()
        return {
            "normalized_name": entity.normalized_name,
            "name_tokens": tokens,
            "lemmas": entity.lemmas,
        }

    @staticmethod
    def fingerprint_from_cluster(cluster: EntityCluster) -> EntityFingerprint:
        tokens = cluster.normalized_name.split()
        return {
            "normalized_name": cluster.normalized_name,
            "name_tokens": tokens,
            "lemmas": cluster.lemmas,
        }

    @staticmethod
    def fingerprint_from_name(normalized_name: str) -> EntityFingerprint:
        tokens = normalized_name.split()
        return {"normalized_name": normalized_name, "name_tokens": tokens}

    # ------------------------------------------------------------------
    # Alias classification helpers
    # ------------------------------------------------------------------

    def is_specific_organization_alias(self, alias: str) -> bool:
        """Return True when *alias* is specific enough to use as a KB lookup key."""
        tokens = [token for token in alias.split() if token]
        if not tokens:
            return False
        if len(tokens) == 1:
            token = tokens[0]
            return token.isupper() or (
                len(token) <= 4 and token[:1].isupper() and token[1:].islower()
            )
        bases = token_bases_for(tokens)
        meaningful = {base for base in bases if base not in _ORG_GENERIC_HEADS}
        return len(meaningful) >= 2
