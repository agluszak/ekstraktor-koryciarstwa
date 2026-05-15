from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EntityKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    POLITICAL_PARTY = "political_party"
    ROLE = "role"
    MONEY = "money"
    LOCATION = "location"


class FactKind(StrEnum):
    PARTY_AFFILIATION = "party_affiliation"
    POLITICAL_SUPPORT = "political_support"
    GOVERNANCE_APPOINTMENT = "governance_appointment"
    GOVERNANCE_DISMISSAL = "governance_dismissal"
    PUBLIC_EMPLOYMENT = "public_employment"
    FUNDING = "funding"
    PUBLIC_CONTRACT = "public_contract"
    COMPENSATION = "compensation"
    ANTI_CORRUPTION_REFERRAL = "anti_corruption_referral"
    ANTI_CORRUPTION_INVESTIGATION = "anti_corruption_investigation"
    PUBLIC_PROCUREMENT_ABUSE = "public_procurement_abuse"
    PERSONAL_OR_POLITICAL_TIE = "personal_or_political_tie"


class FactArgumentRole(StrEnum):
    SUBJECT = "subject"
    OBJECT = "object"
    PERSON = "person"
    ORGANIZATION = "organization"
    ROLE = "role"
    AMOUNT = "amount"
    FUNDER = "funder"
    RECIPIENT = "recipient"
    CONTRACTOR = "contractor"
    COUNTERPARTY = "counterparty"
    COMPLAINANT = "complainant"
    TARGET = "target"
    INSTITUTION = "institution"
    ACTOR = "actor"
    CONTEXT = "context"


class NerLabel(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TIME = "time"


class MentionKind(StrEnum):
    NER = "ner"
    MONEY = "money"
    ROLE = "role"
    PROXY_FAMILY_PHRASE = "proxy_family_phrase"
    SURNAME_ONLY = "surname_only"
    HONORIFIC = "honorific"
    PRONOUN = "pronoun"
    POSSESSIVE_PRONOUN = "possessive_pronoun"
    DESCRIPTOR_NOUN_PHRASE = "descriptor_noun_phrase"
    OMITTED_SUBJECT = "omitted_subject"


class ReferenceKind(StrEnum):
    PRONOUN = "pronoun"
    POSSESSIVE_PRONOUN = "possessive_pronoun"
    DESCRIPTOR_NOUN_PHRASE = "descriptor_noun_phrase"
    OMITTED_SUBJECT = "omitted_subject"
    PROXY_FAMILY_PHRASE = "proxy_family_phrase"
    SURNAME_ONLY = "surname_only"
    HONORIFIC = "honorific"


class ResolutionRelation(StrEnum):
    SAME_AS = "same_as"
    ALIAS_OF = "alias_of"
    REFERENT_OF = "referent_of"


class GroundingKind(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    PROXY = "proxy"
    UNRESOLVED_REFERENCE = "unresolved_reference"


class RelationshipDetail(StrEnum):
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    SIBLING = "sibling"
    FAMILY = "family"


class SignalPolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class Signal:
    name: str
    polarity: SignalPolarity
    weight: float | None = None
    details: str | None = None

    def to_json(self) -> dict[str, str | float | None]:
        return {
            "name": self.name,
            "polarity": self.polarity.value,
            "weight": self.weight,
            "details": self.details,
        }


def positive_signal(
    name: str, *, weight: float | None = None, details: str | None = None
) -> Signal:
    return Signal(name=name, polarity=SignalPolarity.POSITIVE, weight=weight, details=details)


def negative_signal(
    name: str, *, weight: float | None = None, details: str | None = None
) -> Signal:
    return Signal(name=name, polarity=SignalPolarity.NEGATIVE, weight=weight, details=details)
