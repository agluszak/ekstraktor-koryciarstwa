"""Compatibility re-export shim. Import directly from pipeline.domains.governance."""

from __future__ import annotations

from pipeline.domains.governance import (
    GovernanceFactBuilder,
    GovernanceOrgRoleEvidence,
    GovernanceTargetResolution,
    GovernanceTargetResolver,
)

__all__ = [
    "GovernanceFactBuilder",
    "GovernanceOrgRoleEvidence",
    "GovernanceTargetResolution",
    "GovernanceTargetResolver",
]
