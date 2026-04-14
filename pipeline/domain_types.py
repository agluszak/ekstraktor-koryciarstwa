from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class EntityType(StrEnum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    POLITICAL_PARTY = "PoliticalParty"
    POSITION = "Position"
    PUBLIC_INSTITUTION = "PublicInstitution"
    EDUCATION = "Education"


class CandidateType(StrEnum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    POLITICAL_PARTY = "PoliticalParty"
    POSITION = "Position"
    PUBLIC_INSTITUTION = "PublicInstitution"


class FactType(StrEnum):
    APPOINTMENT = "APPOINTMENT"
    DISMISSAL = "DISMISSAL"
    ROLE_HELD = "ROLE_HELD"
    COMPENSATION = "COMPENSATION"
    FUNDING = "FUNDING"
    PARTY_MEMBERSHIP = "PARTY_MEMBERSHIP"
    FORMER_PARTY_MEMBERSHIP = "FORMER_PARTY_MEMBERSHIP"
    ELECTION_CANDIDACY = "ELECTION_CANDIDACY"
    POLITICAL_OFFICE = "POLITICAL_OFFICE"
    PERSONAL_OR_POLITICAL_TIE = "PERSONAL_OR_POLITICAL_TIE"


class RelationType(StrEnum):
    APPOINTED_TO = "APPOINTED_TO"
    HOLDS_POSITION = "HOLDS_POSITION"
    MEMBER_OF_BOARD = "MEMBER_OF_BOARD"
    DISMISSED_FROM = "DISMISSED_FROM"
    LEFT_POSITION = "LEFT_POSITION"
    AFFILIATED_WITH_PARTY = "AFFILIATED_WITH_PARTY"
    RELATED_TO = "RELATED_TO"
    RECEIVES_COMPENSATION = "RECEIVES_COMPENSATION"
    FUNDED_BY = "FUNDED_BY"


class EventType(StrEnum):
    APPOINTMENT = "appointment"
    DISMISSAL = "dismissal"


class TimeScope(StrEnum):
    CURRENT = "current"
    FORMER = "former"
    FUTURE = "future"
    UNKNOWN = "unknown"


class OrganizationKind(StrEnum):
    COMPANY = "company"
    PUBLIC_INSTITUTION = "public_institution"
    GOVERNING_BODY = "governing_body"
    ORGANIZATION = "organization"


class RelationshipType(StrEnum):
    ASSOCIATE = "associate"
    COLLABORATOR = "collaborator"
    FRIEND = "friend"
    ADVISOR = "advisor"
    BODYGUARD = "bodyguard"
    RECOMMENDER = "recommender"
    OFFICE_CHIEF = "office_chief"


class RoleKind(StrEnum):
    PREZES = "prezes"
    WICEPREZES = "wiceprezes"
    ZASTEPCA_PREZESA = "zastępca prezesa"
    DYREKTOR = "dyrektor"
    CZLONEK_ZARZADU = "członek zarządu"
    RADA_NADZORCZA = "rada nadzorcza"
    WICEPRZEWODNICZACY_RADY_NADZORCZEJ = "wiceprzewodniczący rady nadzorczej"
    RADNY = "radny"
    POSEL = "poseł"
    SENATOR = "senator"
    WICEMINISTER = "wiceminister"
    MINISTER = "minister"
    PREZYDENT_MIASTA = "prezydent miasta"
    WICEPREZYDENT = "wiceprezydent"
    WICEWOJEWODA = "wicewojewoda"


class EntityAttributes(TypedDict, total=False):
    registry_id: str
    lemmas: list[str]
    organizations: list[str]
    positions: list[str]
    parties: list[str]
    education: list[str]
    organization_kind: OrganizationKind


class ConfidenceBreakdown(TypedDict, total=False):
    person_role: float | None
    role_org: float | None


class CandidateAttributes(TypedDict, total=False):
    organization_kind: OrganizationKind
    role_kind: str


class FactAttributes(TypedDict, total=False):
    position_entity_id: str | None
    role: str | None
    role_kind: str | None
    board_role: bool
    organization_kind: OrganizationKind | None
    confidence_breakdown: ConfidenceBreakdown | None
    party: str | None
    office_type: str | None
    candidacy_scope: str | None
    amount_text: str | None
    period: str | None
    relationship_type: RelationshipType | None


class RelationAttributes(TypedDict, total=False):
    status: str | None
    amount_text: str | None
    period: str | None
    time_scope: TimeScope | None
    relationship: str | RelationshipType | None


class EventAttributes(TypedDict, total=False):
    time_scope: TimeScope | None
    position_entity_id: str | None
    role: str | None
    role_kind: str | None
    board_role: bool
    organization_kind: OrganizationKind | None
    confidence_breakdown: ConfidenceBreakdown | None
