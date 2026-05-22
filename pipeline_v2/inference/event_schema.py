from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.types import EntityKind, EventRole, FactArgumentRole, FactKind


@dataclass(frozen=True, slots=True)
class RoleSpec:
    role: EventRole
    output_role: FactArgumentRole
    allowed_entity_kinds: frozenset[EntityKind]
    required: bool = False


@dataclass(frozen=True, slots=True)
class EventSchema:
    fact_kind: FactKind
    roles: tuple[RoleSpec, ...]

    def role_for_argument(self, argument_role: FactArgumentRole) -> EventRole:
        if self.fact_kind is FactKind.PUBLIC_EMPLOYMENT:
            if argument_role is FactArgumentRole.PERSON:
                return EventRole.EMPLOYEE
            if argument_role is FactArgumentRole.ORGANIZATION:
                return EventRole.WORKPLACE
        return EventRole.from_fact_argument_role(argument_role)

    def output_role_for_event_role(self, role: EventRole) -> FactArgumentRole:
        for role_spec in self.roles:
            if role_spec.role is role:
                return role_spec.output_role
        return _FACT_ARGUMENT_ROLE_BY_EVENT_ROLE.get(role, FactArgumentRole.CONTEXT)

    def role_spec_for(self, role: EventRole) -> RoleSpec | None:
        for role_spec in self.roles:
            if role_spec.role is role:
                return role_spec
        return None


_ANY_ENTITY = frozenset(EntityKind)
_PERSON = frozenset({EntityKind.PERSON})
_ORG = frozenset({EntityKind.ORGANIZATION})
_PARTY = frozenset({EntityKind.POLITICAL_PARTY})
_ORG_OR_PARTY = frozenset({EntityKind.ORGANIZATION, EntityKind.POLITICAL_PARTY})
_ORG_OR_PERSON = frozenset({EntityKind.ORGANIZATION, EntityKind.PERSON})
_ROLE = frozenset({EntityKind.ROLE})
_MONEY = frozenset({EntityKind.MONEY})


EVENT_SCHEMAS: dict[FactKind, EventSchema] = {
    FactKind.GOVERNANCE_APPOINTMENT: EventSchema(
        fact_kind=FactKind.GOVERNANCE_APPOINTMENT,
        roles=(
            RoleSpec(EventRole.PERSON, FactArgumentRole.PERSON, _PERSON, required=True),
            RoleSpec(EventRole.ORGANIZATION, FactArgumentRole.ORGANIZATION, _ORG),
            RoleSpec(EventRole.ROLE, FactArgumentRole.ROLE, _ROLE),
            RoleSpec(EventRole.CONTEXT, FactArgumentRole.CONTEXT, _ANY_ENTITY),
        ),
    ),
    FactKind.GOVERNANCE_DISMISSAL: EventSchema(
        fact_kind=FactKind.GOVERNANCE_DISMISSAL,
        roles=(
            RoleSpec(EventRole.PERSON, FactArgumentRole.PERSON, _PERSON, required=True),
            RoleSpec(EventRole.ORGANIZATION, FactArgumentRole.ORGANIZATION, _ORG),
            RoleSpec(EventRole.ROLE, FactArgumentRole.ROLE, _ROLE),
            RoleSpec(EventRole.CONTEXT, FactArgumentRole.CONTEXT, _ANY_ENTITY),
        ),
    ),
    FactKind.PUBLIC_EMPLOYMENT: EventSchema(
        fact_kind=FactKind.PUBLIC_EMPLOYMENT,
        roles=(
            RoleSpec(EventRole.EMPLOYEE, FactArgumentRole.PERSON, _PERSON, required=True),
            RoleSpec(EventRole.WORKPLACE, FactArgumentRole.ORGANIZATION, _ORG, required=True),
            RoleSpec(EventRole.ROLE, FactArgumentRole.ROLE, _ROLE),
            RoleSpec(EventRole.HIRING_AUTHORITY, FactArgumentRole.ACTOR, _PERSON),
        ),
    ),
    FactKind.FUNDING: EventSchema(
        fact_kind=FactKind.FUNDING,
        roles=(
            RoleSpec(EventRole.FUNDER, FactArgumentRole.FUNDER, _ORG),
            RoleSpec(EventRole.RECIPIENT, FactArgumentRole.RECIPIENT, _ORG),
            RoleSpec(EventRole.AMOUNT, FactArgumentRole.AMOUNT, _MONEY, required=True),
        ),
    ),
    FactKind.PUBLIC_CONTRACT: EventSchema(
        fact_kind=FactKind.PUBLIC_CONTRACT,
        roles=(
            RoleSpec(EventRole.COUNTERPARTY, FactArgumentRole.COUNTERPARTY, _ORG),
            RoleSpec(EventRole.CONTRACTOR, FactArgumentRole.CONTRACTOR, _ORG_OR_PERSON),
            RoleSpec(EventRole.AMOUNT, FactArgumentRole.AMOUNT, _MONEY, required=True),
        ),
    ),
    FactKind.COMPENSATION: EventSchema(
        fact_kind=FactKind.COMPENSATION,
        roles=(
            RoleSpec(EventRole.FUNDER, FactArgumentRole.FUNDER, _ORG),
            RoleSpec(EventRole.RECIPIENT, FactArgumentRole.RECIPIENT, _PERSON),
            RoleSpec(EventRole.AMOUNT, FactArgumentRole.AMOUNT, _MONEY, required=True),
        ),
    ),
    FactKind.PARTY_AFFILIATION: EventSchema(
        fact_kind=FactKind.PARTY_AFFILIATION,
        roles=(
            RoleSpec(EventRole.SUBJECT, FactArgumentRole.SUBJECT, _PERSON, required=True),
            RoleSpec(EventRole.OBJECT, FactArgumentRole.OBJECT, _PARTY, required=True),
        ),
    ),
    FactKind.POLITICAL_SUPPORT: EventSchema(
        fact_kind=FactKind.POLITICAL_SUPPORT,
        roles=(
            RoleSpec(EventRole.SUBJECT, FactArgumentRole.SUBJECT, _PERSON, required=True),
            RoleSpec(EventRole.OBJECT, FactArgumentRole.OBJECT, _PERSON, required=True),
        ),
    ),
    FactKind.ANTI_CORRUPTION_REFERRAL: EventSchema(
        fact_kind=FactKind.ANTI_CORRUPTION_REFERRAL,
        roles=(
            RoleSpec(EventRole.COMPLAINANT, FactArgumentRole.COMPLAINANT, _ANY_ENTITY),
            RoleSpec(EventRole.TARGET, FactArgumentRole.TARGET, _ANY_ENTITY),
            RoleSpec(EventRole.INSTITUTION, FactArgumentRole.INSTITUTION, _ORG),
            RoleSpec(EventRole.CONTEXT, FactArgumentRole.CONTEXT, _ANY_ENTITY),
        ),
    ),
    FactKind.ANTI_CORRUPTION_INVESTIGATION: EventSchema(
        fact_kind=FactKind.ANTI_CORRUPTION_INVESTIGATION,
        roles=(
            RoleSpec(EventRole.TARGET, FactArgumentRole.TARGET, _ANY_ENTITY),
            RoleSpec(EventRole.INSTITUTION, FactArgumentRole.INSTITUTION, _ORG),
            RoleSpec(EventRole.CONTEXT, FactArgumentRole.CONTEXT, _ANY_ENTITY),
        ),
    ),
    FactKind.PERSONAL_OR_POLITICAL_TIE: EventSchema(
        fact_kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
        roles=(
            RoleSpec(EventRole.SUBJECT, FactArgumentRole.SUBJECT, _PERSON, required=True),
            RoleSpec(EventRole.OBJECT, FactArgumentRole.OBJECT, _PERSON, required=True),
            RoleSpec(
                EventRole.RELATIONSHIP_DETAIL,
                FactArgumentRole.RELATIONSHIP_DETAIL,
                _ANY_ENTITY,
            ),
            RoleSpec(EventRole.CONTEXT, FactArgumentRole.CONTEXT, _ANY_ENTITY),
        ),
    ),
}

_FACT_ARGUMENT_ROLE_BY_EVENT_ROLE = {
    EventRole.SUBJECT: FactArgumentRole.SUBJECT,
    EventRole.OBJECT: FactArgumentRole.OBJECT,
    EventRole.PERSON: FactArgumentRole.PERSON,
    EventRole.ORGANIZATION: FactArgumentRole.ORGANIZATION,
    EventRole.ROLE: FactArgumentRole.ROLE,
    EventRole.AMOUNT: FactArgumentRole.AMOUNT,
    EventRole.FUNDER: FactArgumentRole.FUNDER,
    EventRole.RECIPIENT: FactArgumentRole.RECIPIENT,
    EventRole.CONTRACTOR: FactArgumentRole.CONTRACTOR,
    EventRole.COUNTERPARTY: FactArgumentRole.COUNTERPARTY,
    EventRole.COMPLAINANT: FactArgumentRole.COMPLAINANT,
    EventRole.TARGET: FactArgumentRole.TARGET,
    EventRole.INSTITUTION: FactArgumentRole.INSTITUTION,
    EventRole.ACTOR: FactArgumentRole.ACTOR,
    EventRole.CONTEXT: FactArgumentRole.CONTEXT,
    EventRole.RELATIONSHIP_DETAIL: FactArgumentRole.RELATIONSHIP_DETAIL,
    EventRole.EMPLOYEE: FactArgumentRole.PERSON,
    EventRole.WORKPLACE: FactArgumentRole.ORGANIZATION,
    EventRole.HIRING_AUTHORITY: FactArgumentRole.ACTOR,
}


def schema_for(kind: FactKind) -> EventSchema:
    return EVENT_SCHEMAS.get(
        kind,
        EventSchema(
            fact_kind=kind,
            roles=(
                RoleSpec(
                    role=EventRole.SUBJECT,
                    output_role=FactArgumentRole.SUBJECT,
                    allowed_entity_kinds=_ANY_ENTITY,
                ),
            ),
        ),
    )
