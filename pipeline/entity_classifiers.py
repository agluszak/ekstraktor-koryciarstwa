from __future__ import annotations

from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import PUBLIC_EMPLOYER_TERMS
from pipeline.semantic_signals import GOVERNANCE_TARGET_HEAD_MARKERS, PUBLIC_COUNTERPARTY_MARKERS

COMPANY_NAME_MARKERS = frozenset({"consulting", "group", "spół", "firma"})
MEDIA_SOURCE_MARKERS = frozenset(
    {"onet", "pap", "wp", "wirtualna polska", "rzeczpospolita", "fakt", "tvn", "tvp", "interia"}
)
PARTY_NAME_HEADS = frozenset({"partia", "stronnictwo", "koalicja", "ruch"})
EMPLOYER_NAME_MARKERS = frozenset(
    {
        "sejm",
        "senat",
        "kancelari",
        "wodociąg",
        "kanaliz",
        "przedsiębiorstw",
        "zarząd",
        "centrum",
        "kolej",
        "pogotow",
        "instytut",
        "szpital",
        "port",
    }
)
PUBLIC_FUNDER_NAME_MARKERS = frozenset(
    {"minister", "fundusz", "urząd", "nfoś", "wfoś", "spółka", "agencja", "krajowy"}
)


def is_party_like_name(name: str, config: PipelineConfig | None = None) -> bool:
    lowered = name.casefold().strip()
    aliases: set[str] = set()
    if config is not None:
        aliases.update(alias.casefold() for alias in config.party_aliases)
        aliases.update(canonical.casefold() for canonical in config.party_aliases.values())
    if lowered in aliases:
        return True
    return any(head in lowered for head in PARTY_NAME_HEADS | {"koalicj"})


def is_media_like_name(name: str) -> bool:
    lowered = name.casefold()
    return any(marker in lowered for marker in MEDIA_SOURCE_MARKERS)


def is_public_employer_name(name: str) -> bool:
    lowered = name.casefold()
    return any(term in lowered for term in PUBLIC_EMPLOYER_TERMS)


def is_public_counterparty_name(name: str) -> bool:
    lowered = name.casefold()
    return is_public_employer_name(lowered) or any(
        marker in lowered for marker in PUBLIC_COUNTERPARTY_MARKERS
    )


def is_company_like_name(name: str) -> bool:
    lowered = name.casefold()
    return any(marker in lowered for marker in COMPANY_NAME_MARKERS)


def is_employer_like_name(name: str) -> bool:
    lowered = name.casefold()
    return (
        is_public_employer_name(lowered)
        or is_company_like_name(lowered)
        or any(marker in lowered for marker in EMPLOYER_NAME_MARKERS)
    )


def is_public_funder_name(name: str) -> bool:
    lowered = name.casefold()
    return is_public_counterparty_name(lowered) or any(
        marker in lowered for marker in PUBLIC_FUNDER_NAME_MARKERS
    )


def is_target_organization_name(name: str) -> bool:
    lowered = name.casefold()
    return is_company_like_name(lowered) or any(
        marker in lowered for marker in GOVERNANCE_TARGET_HEAD_MARKERS
    )
