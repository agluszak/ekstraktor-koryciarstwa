"""Compatibility re-export shim. Import directly from pipeline.domains.*."""

from __future__ import annotations

from pipeline.domains.anti_corruption import (
    AntiCorruptionInvestigationFactBuilder,
    AntiCorruptionReferralFactBuilder,
    PublicProcurementAbuseFactBuilder,
)
from pipeline.domains.public_employment import PublicEmploymentFactBuilder
from pipeline.domains.public_money import PublicContractFactBuilder

__all__ = [
    "AntiCorruptionInvestigationFactBuilder",
    "AntiCorruptionReferralFactBuilder",
    "PublicContractFactBuilder",
    "PublicEmploymentFactBuilder",
    "PublicProcurementAbuseFactBuilder",
]
