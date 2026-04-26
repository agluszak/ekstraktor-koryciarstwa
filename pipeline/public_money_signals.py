from __future__ import annotations

from collections.abc import Iterable

from pipeline.domain_types import EntityType, OrganizationKind
from pipeline.entity_classifiers import (
    is_company_like_name,
    is_public_counterparty_name,
)
from pipeline.models import ClauseUnit, EntityCluster
from pipeline.semantic_signals import CONTRACTOR_CONTEXT_MARKERS, PUBLIC_COUNTERPARTY_MARKERS


def cluster_before_offset(
    cluster: EntityCluster,
    offset: int,
    clause: ClauseUnit,
) -> bool:
    return any(
        mention.sentence_index == clause.sentence_index and mention.start_char < offset
        for mention in cluster.mentions
    )


def cluster_after_or_near_trigger(
    cluster: EntityCluster,
    offset: int,
    clause: ClauseUnit,
) -> bool:
    return any(
        mention.sentence_index == clause.sentence_index and mention.end_char >= offset - 12
        for mention in cluster.mentions
    )


def cluster_has_context_marker(
    clause: ClauseUnit,
    cluster: EntityCluster,
    markers: Iterable[str],
    *,
    before: int,
    after: int,
) -> bool:
    lowered = clause.text.lower()
    for mention in cluster.mentions:
        if mention.sentence_index != clause.sentence_index:
            continue
        start = max(0, mention.start_char - clause.start_char)
        end = max(start, mention.end_char - clause.start_char)
        window = lowered[max(0, start - before) : min(len(lowered), end + after)]
        if any(marker in window for marker in markers):
            return True
    return False


def is_company_like_contractor(clause: ClauseUnit, cluster: EntityCluster) -> bool:
    if cluster.organization_kind == OrganizationKind.COMPANY:
        return True
    if is_company_like_name(cluster.normalized_name):
        return True
    return cluster_has_context_marker(
        clause,
        cluster,
        CONTRACTOR_CONTEXT_MARKERS,
        before=18,
        after=6,
    )


def is_public_counterparty(clause: ClauseUnit, cluster: EntityCluster) -> bool:
    if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
        return True
    if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
        return True
    if is_public_counterparty_name(cluster.normalized_name):
        return True
    if any(marker in clause.text.lower() for marker in ("miast", "gmin", "komunal")) and (
        cluster_has_context_marker(
            clause,
            cluster,
            {"spółką", "spółce", "spółka"},
            before=12,
            after=4,
        )
    ):
        return True
    return cluster_has_context_marker(
        clause,
        cluster,
        PUBLIC_COUNTERPARTY_MARKERS,
        before=18,
        after=10,
    )


def has_person_firm_context(clause: ClauseUnit, cluster: EntityCluster) -> bool:
    return cluster_has_context_marker(
        clause,
        cluster,
        {"firma", "firmy", "prowadzona przez", "prowadzonej przez", "należąca do"},
        before=34,
        after=6,
    )
