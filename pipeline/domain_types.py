from __future__ import annotations

from enum import StrEnum
from typing import NewType

EntityID = NewType("EntityID", str)
FactID = NewType("FactID", str)
ClusterID = NewType("ClusterID", str)
DocumentID = NewType("DocumentID", str)
CandidateID = NewType("CandidateID", str)
ClauseID = NewType("ClauseID", str)
FrameID = NewType("FrameID", str)


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
    PUBLIC_CONTRACT = "PUBLIC_CONTRACT"
    ANTI_CORRUPTION_REFERRAL = "ANTI_CORRUPTION_REFERRAL"
    PARTY_MEMBERSHIP = "PARTY_MEMBERSHIP"
    FORMER_PARTY_MEMBERSHIP = "FORMER_PARTY_MEMBERSHIP"
    ELECTION_CANDIDACY = "ELECTION_CANDIDACY"
    POLITICAL_OFFICE = "POLITICAL_OFFICE"
    PERSONAL_OR_POLITICAL_TIE = "PERSONAL_OR_POLITICAL_TIE"


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
    FAMILY = "family"
    ASSOCIATE = "associate"
    COLLABORATOR = "collaborator"
    FRIEND = "friend"
    ADVISOR = "advisor"
    BODYGUARD = "bodyguard"
    RECOMMENDER = "recommender"
    OFFICE_CHIEF = "office_chief"


class IdentityHypothesisStatus(StrEnum):
    POSSIBLE = "possible"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"


class IdentityHypothesisReason(StrEnum):
    SAME_ANCHOR_COMPATIBLE_FAMILY_PROXY = "same_anchor_compatible_family_proxy"
    SURNAME_COMPATIBLE_FAMILY_PROXY = "surname_compatible_family_proxy"
    SURNAME_COMPATIBLE_NEAR_FAMILY_CONTEXT = "surname_compatible_near_family_context"
    HONORIFIC_SURNAME_ONLY = "honorific_surname_only"


class ProxyKind(StrEnum):
    FAMILY = "family"


class KinshipDetail(StrEnum):
    SPOUSE = "spouse"
    PARTNER = "partner"
    SIBLING_SISTER = "sibling_sister"
    SIBLING_BROTHER = "sibling_brother"
    CHILD_DAUGHTER = "child_daughter"
    CHILD_SON = "child_son"
    COUSIN = "cousin"
    FATHER_IN_LAW = "father_in_law"
    BROTHER_IN_LAW = "brother_in_law"
    SISTER_IN_LAW = "sister_in_law"
    DAUGHTER_IN_LAW = "daughter_in_law"


class RoleModifier(StrEnum):
    DEPUTY = "wice/zastępca"
    ACTING = "p.o."


class RoleKind(StrEnum):
    PREZES = "prezes"
    DYREKTOR = "dyrektor"
    CZLONEK_ZARZADU = "członek zarządu"
    RADA_NADZORCZA = "rada nadzorcza"
    PRZEWODNICZACY_RADY_NADZORCZEJ = "przewodniczący rady nadzorczej"
    RADNY = "radny"
    POSEL = "poseł"
    SENATOR = "senator"
    MINISTER = "minister"
    PREZYDENT_MIASTA = "prezydent miasta"
    WOJEWODA = "wojewoda"
    WOJT = "wójt"
    STAROSTA = "starosta"
    SEKRETARZ_POWIATU = "sekretarz powiatu"
    MARSZALEK_WOJEWODZTWA = "marszałek województwa"
