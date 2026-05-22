from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pipeline_v2.types import EntityTag, EventRole, FactKind


@dataclass(frozen=True, slots=True)
class EntityContextRolePolicy:
    """Per-(tag, fact_kind, role) potential for the constraint factor that
    couples an `EntityContext(entity, tag)=TRUE` state to a `RoleFiller` state
    binding that entity in that role.

    A potential of 1.0 means the policy has no opinion (the factor is a no-op
    for that combination).  A value below 1.0 suppresses the binding; a value
    above 1.0 boosts it.  Inference normalizes potentials globally, so
    boost-style values participate in the same scale as suppression values.
    """

    table: Mapping[tuple[EntityTag, FactKind, EventRole], float]

    def potential(self, *, tag: EntityTag, fact_kind: FactKind, role: EventRole) -> float:
        return self.table.get((tag, fact_kind, role), 1.0)


# Suppression values.  These are joint-factor potentials applied when
# `EntityContext=TRUE` AND the role binds the tagged entity, so they compound
# with the EntityContext prior (typically 0.75–0.95).  We pick values low
# enough that the marginalised joint effect matches the old per-binding
# −0.85 weight-policy contribution that drove the role prior floor to 0.05.
_STRONG_SUPPRESS = 0.02
_MILD_SUPPRESS = 0.05
# Positive boost values: > 1.0 raises this filler relative to alternatives.
_STRONG_BOOST = 1.5
_MILD_BOOST = 1.3


_DEFAULT_TABLE: Mapping[tuple[EntityTag, FactKind, EventRole], float] = {
    # Media outlets reporting on a story should not be treated as funders or
    # recipients of funding mentioned in that story.
    (EntityTag.MEDIA_OUTLET, FactKind.FUNDING, EventRole.FUNDER): _STRONG_SUPPRESS,
    (EntityTag.MEDIA_OUTLET, FactKind.FUNDING, EventRole.RECIPIENT): _STRONG_SUPPRESS,
    (EntityTag.MEDIA_OUTLET, FactKind.PUBLIC_CONTRACT, EventRole.COUNTERPARTY): _MILD_SUPPRESS,
    (EntityTag.MEDIA_OUTLET, FactKind.PUBLIC_CONTRACT, EventRole.CONTRACTOR): _MILD_SUPPRESS,
    (EntityTag.MEDIA_OUTLET, FactKind.COMPENSATION, EventRole.FUNDER): _STRONG_SUPPRESS,
    # Generic-owner organizations (Skarb Państwa, MAP, MF) almost never *are*
    # the appointing/dismissing org; they're the surrounding ownership context.
    # They can still be a workplace for public employment, so we don't suppress
    # that role.
    (EntityTag.GENERIC_OWNER, FactKind.GOVERNANCE_APPOINTMENT, EventRole.ORGANIZATION): (
        _STRONG_SUPPRESS
    ),
    (EntityTag.GENERIC_OWNER, FactKind.GOVERNANCE_DISMISSAL, EventRole.ORGANIZATION): (
        _STRONG_SUPPRESS
    ),
    # Governing-body organizations (rada nadzorcza, zarząd) are the *body that
    # appoints*, not the organization being appointed into.  Suppress them as
    # the appointed-org role.
    (EntityTag.GOVERNING_BODY, FactKind.GOVERNANCE_APPOINTMENT, EventRole.ORGANIZATION): (
        _STRONG_SUPPRESS
    ),
    (EntityTag.GOVERNING_BODY, FactKind.GOVERNANCE_DISMISSAL, EventRole.ORGANIZATION): (
        _STRONG_SUPPRESS
    ),
    # Public institutions ARE the typical workplace for `public_employment`
    # and the typical org being appointed into for governance: positive boosts.
    (EntityTag.PUBLIC_INSTITUTION, FactKind.PUBLIC_EMPLOYMENT, EventRole.WORKPLACE): (
        _STRONG_BOOST
    ),
    (EntityTag.PUBLIC_INSTITUTION, FactKind.GOVERNANCE_APPOINTMENT, EventRole.ORGANIZATION): (
        _MILD_BOOST
    ),
    (EntityTag.PUBLIC_INSTITUTION, FactKind.GOVERNANCE_DISMISSAL, EventRole.ORGANIZATION): (
        _MILD_BOOST
    ),
}


DEFAULT_ENTITY_CONTEXT_ROLE_POLICY = EntityContextRolePolicy(table=_DEFAULT_TABLE)
