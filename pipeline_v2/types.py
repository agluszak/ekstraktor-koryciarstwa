from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class EntityKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    POLITICAL_PARTY = "political_party"
    ROLE = "role"
    MONEY = "money"
    LOCATION = "location"


class EntityTag(StrEnum):
    PUBLIC_INSTITUTION = "public_institution"
    MEDIA_OUTLET = "media_outlet"
    GENERIC_OWNER = "generic_owner"
    GOVERNING_BODY = "governing_body"


class FactKind(StrEnum):
    PARTY_MEMBERSHIP = "party_membership"
    POLITICAL_SUPPORT = "political_support"
    PUBLIC_ROLE_APPOINTMENT = "public_role_appointment"
    PUBLIC_ROLE_HOLDING = "public_role_holding"
    PUBLIC_ROLE_END = "public_role_end"
    PUBLIC_EMPLOYMENT = "public_employment"
    FUNDING = "funding"
    PUBLIC_CONTRACT = "public_contract"
    COMPENSATION = "compensation"
    ANTI_CORRUPTION_REFERRAL = "anti_corruption_referral"
    ANTI_CORRUPTION_INVESTIGATION = "anti_corruption_investigation"
    PUBLIC_PROCUREMENT_ABUSE = "public_procurement_abuse"
    PATRONAGE_ALLEGATION = "patronage_allegation"
    PATRONAGE_NETWORK_TIE = "patronage_network_tie"
    PERSONAL_OR_POLITICAL_TIE = "personal_or_political_tie"
    ELECTION_CANDIDACY = "election_candidacy"
    CORPORATE_OWNERSHIP = "corporate_ownership"
    PARTY_DONATION = "party_donation"
    ASSET_DECLARATION = "asset_declaration"
    KINSHIP_TIE = "kinship_tie"


class PublicRoleDomain(StrEnum):
    POLITICAL_OFFICE = "political_office"
    ADMINISTRATIVE_OFFICE = "administrative_office"
    INSTITUTION_MANAGEMENT = "institution_management"
    SUPERVISORY_BOARD = "supervisory_board"
    PUBLIC_COMPANY_MANAGEMENT = "public_company_management"
    OTHER_PUBLIC_ROLE = "other_public_role"


class PartyMembershipStatus(StrEnum):
    CURRENT = "current"
    FORMER = "former"
    UNKNOWN = "unknown"


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
    RELATIONSHIP_DETAIL = "relationship_detail"
    ROLE_DOMAIN = "role_domain"
    STATUS = "status"


class EventRole(StrEnum):
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
    RELATIONSHIP_DETAIL = "relationship_detail"
    EMPLOYEE = "employee"
    WORKPLACE = "workplace"
    HIRING_AUTHORITY = "hiring_authority"
    ROLE_DOMAIN = "role_domain"
    STATUS = "status"

    @classmethod
    def from_fact_argument_role(cls, role: FactArgumentRole) -> "EventRole":
        return _EVENT_ROLE_BY_FACT_ARGUMENT_ROLE[role]


_EVENT_ROLE_BY_FACT_ARGUMENT_ROLE = {
    FactArgumentRole.SUBJECT: EventRole.SUBJECT,
    FactArgumentRole.OBJECT: EventRole.OBJECT,
    FactArgumentRole.PERSON: EventRole.PERSON,
    FactArgumentRole.ORGANIZATION: EventRole.ORGANIZATION,
    FactArgumentRole.ROLE: EventRole.ROLE,
    FactArgumentRole.AMOUNT: EventRole.AMOUNT,
    FactArgumentRole.FUNDER: EventRole.FUNDER,
    FactArgumentRole.RECIPIENT: EventRole.RECIPIENT,
    FactArgumentRole.CONTRACTOR: EventRole.CONTRACTOR,
    FactArgumentRole.COUNTERPARTY: EventRole.COUNTERPARTY,
    FactArgumentRole.COMPLAINANT: EventRole.COMPLAINANT,
    FactArgumentRole.TARGET: EventRole.TARGET,
    FactArgumentRole.INSTITUTION: EventRole.INSTITUTION,
    FactArgumentRole.ACTOR: EventRole.ACTOR,
    FactArgumentRole.CONTEXT: EventRole.CONTEXT,
    FactArgumentRole.RELATIONSHIP_DETAIL: EventRole.RELATIONSHIP_DETAIL,
    FactArgumentRole.ROLE_DOMAIN: EventRole.ROLE_DOMAIN,
    FactArgumentRole.STATUS: EventRole.STATUS,
}


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
    SAME_FACT = "same_fact"


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


class DependencyRelation(StrEnum):
    ACL = "acl"
    ADVMOD = "advmod"
    AMOD = "amod"
    APPOS = "appos"
    AUX = "aux"
    AUX_PASS = "aux:pass"
    CASE = "case"
    CC = "cc"
    CCOMP = "ccomp"
    CONJ = "conj"
    COP = "cop"
    CSUBJ = "csubj"
    DET = "det"
    FLAT = "flat"
    IOBJ = "iobj"
    MARK = "mark"
    NMOD = "nmod"
    NSUBJ = "nsubj"
    NSUBJ_PASS = "nsubj:pass"
    NUMMOD = "nummod"
    OBJ = "obj"
    OBL = "obl"
    PUNCT = "punct"
    ROOT = "root"
    UNKNOWN = "unknown"

    @classmethod
    def from_raw(cls, raw: str | None) -> "DependencyRelation":
        if raw is None:
            return cls.UNKNOWN
        normalized = raw.casefold()
        if normalized in _DEPENDENCY_RELATION_BY_VALUE:
            return _DEPENDENCY_RELATION_BY_VALUE[normalized]
        return cls.UNKNOWN


_DEPENDENCY_RELATION_BY_VALUE = {relation.value: relation for relation in DependencyRelation}


class SyntaxRelationClass(StrEnum):
    SUBJECT = "subject"
    OBJECT = "object"
    OBLIQUE = "oblique"
    PREPOSITIONAL = "prepositional"
    APPOSITION = "apposition"
    COPULAR = "copular"
    POSSESSIVE = "possessive"
    AUX_PASSIVE = "aux_passive"
    MODIFIER = "modifier"
    OTHER = "other"


class FactResolutionStrategy(StrEnum):
    EXACT_ARGUMENTS = "exact_arguments"
    ENTITY_ALIGNMENT_RELAXED = "entity_alignment_relaxed"
    SPARSE_ARGUMENT_SUBSET = "sparse_argument_subset"
    PARTY_MEMBERSHIP_RESTATEMENT = "party_membership_restatement"
    GOVERNANCE_ROLE_RELAXED = "governance_role_relaxed"
    TIE_CONTEXT_RELAXED = "tie_context_relaxed"
    INVERSE_CHILD_TIE = "inverse_child_tie"
    PROXY_NAMED_TIE = "proxy_named_tie"
    SEMANTIC_EVIDENCE = "semantic_evidence"


class SignalPolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True, kw_only=True)
class Signal:
    polarity: SignalPolarity
    weight: float | None = None

    @property
    def name(self) -> str:
        base_name = re.sub(r"Signal$", "", type(self).__name__)
        return re.sub(r"(?<!^)(?=[A-Z])", "_", base_name).lower()

    def to_json(self) -> dict[str, object]:
        import dataclasses

        data: dict[str, object] = {
            "name": self.name,
            "polarity": self.polarity.value,
            "weight": self.weight,
        }
        details: dict[str, object] = {}
        for field in dataclasses.fields(self):
            if field.name not in {"polarity", "weight"} and not field.name.startswith("_"):
                details[field.name] = _signal_json_value(getattr(self, field.name))
        if details:
            data["details"] = details
        return data


def _signal_json_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _signal_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_signal_json_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class PositiveSignal(Signal):
    polarity: SignalPolarity = SignalPolarity.POSITIVE


@dataclass(frozen=True, slots=True, kw_only=True)
class NegativeSignal(Signal):
    polarity: SignalPolarity = SignalPolarity.NEGATIVE


@dataclass(frozen=True, slots=True, kw_only=True)
class PartyOrganizationSignal(NegativeSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscourseOrganizationSignal(NegativeSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddedInOrganizationNameSignal(NegativeSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class NominalKinshipSignal(PositiveSignal):
    lemma: str


@dataclass(frozen=True, slots=True)
class TextMatchSignal(PositiveSignal):
    text: str

    @property
    def name(self) -> str:
        return "text_match"


@dataclass(frozen=True, slots=True)
class LemmaMatchSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "lemma_match"


@dataclass(frozen=True, slots=True)
class SurnameBaseMatchSignal(PositiveSignal):
    distance: int

    @property
    def name(self) -> str:
        return f"surname_base_match_dist:{self.distance}"


@dataclass(frozen=True, slots=True)
class FullNameReuseMatchSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "full_name_reuse_key_match"


@dataclass(frozen=True, slots=True)
class MoneyAmountSignal(PositiveSignal):
    amount: str

    @property
    def name(self) -> str:
        return "money_amount"


@dataclass(frozen=True, slots=True)
class AppointmentLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "appointment_lemma"


@dataclass(frozen=True, slots=True)
class DismissalLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "dismissal_lemma"


@dataclass(frozen=True, slots=True)
class PublicRoleDomainSignal(PositiveSignal):
    domain: PublicRoleDomain


@dataclass(frozen=True, slots=True)
class PartyMembershipStatusSignal(PositiveSignal):
    status: PartyMembershipStatus


@dataclass(frozen=True, slots=True)
class CompensationLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "compensation_lemma"


@dataclass(frozen=True, slots=True)
class LocalPersonSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_person"


@dataclass(frozen=True, slots=True)
class LocalOrganizationSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_organization"


@dataclass(frozen=True, slots=True)
class WindowPersonSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "discourse_window_person"


@dataclass(frozen=True, slots=True)
class WindowOrganizationSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "discourse_window_organization"


@dataclass(frozen=True, slots=True)
class LocalRoleSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_role"


@dataclass(frozen=True, slots=True)
class PartyAliasMatchSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "party_alias_match"


@dataclass(frozen=True, slots=True)
class CollectivePartyContextSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "collective_party_context"


@dataclass(frozen=True, slots=True, kw_only=True)
class SameNameContradictionSignal(NegativeSignal):
    @property
    def name(self) -> str:
        return "same_name_contradiction"


@dataclass(frozen=True, slots=True, kw_only=True)
class SameNameContrastContextSignal(NegativeSignal):
    @property
    def name(self) -> str:
        return "same_name_contrast_context"


@dataclass(frozen=True, slots=True, kw_only=True)
class ConflictingPartyAffiliationSignal(NegativeSignal):
    left_party_hint: str
    right_party_hint: str

    @property
    def name(self) -> str:
        return "conflicting_party_membership"


@dataclass(frozen=True, slots=True)
class FundingLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "funding_lemma"


@dataclass(frozen=True, slots=True)
class PublicContractLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "public_contract_lemma"


@dataclass(frozen=True, slots=True)
class WindowRoleSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "discourse_window_role"


@dataclass(frozen=True, slots=True)
class CompensationSourceSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_compensation_source"


@dataclass(frozen=True, slots=True)
class CompensationRecipientSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_compensation_recipient"


@dataclass(frozen=True, slots=True)
class ContractCounterpartySignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_contract_counterparty"


@dataclass(frozen=True, slots=True)
class ContractorSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_contractor"


@dataclass(frozen=True, slots=True)
class FunderSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_funder"


@dataclass(frozen=True, slots=True)
class RecipientSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_recipient"


@dataclass(frozen=True, slots=True)
class LocalPhraseFunderSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "local_phrase_funder"


@dataclass(frozen=True, slots=True)
class LocalPhraseRecipientSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "local_phrase_recipient"


@dataclass(frozen=True, slots=True)
class DirectPrepositionalAttachmentSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "direct_prepositional_attachment"


@dataclass(frozen=True, slots=True)
class PartyProfileLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "party_profile_lemma"


@dataclass(frozen=True, slots=True)
class CandidacyContextSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "candidacy_context"


@dataclass(frozen=True, slots=True)
class AntiCorruptionReferralLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "anti_corruption_referral_lemma"


@dataclass(frozen=True, slots=True)
class AntiCorruptionInvestigationLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "anti_corruption_investigation_lemma"


@dataclass(frozen=True, slots=True)
class OversightInstitutionSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "oversight_institution"


@dataclass(frozen=True, slots=True)
class LocalActorSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_actor"


@dataclass(frozen=True, slots=True)
class LocalTargetSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_target"


@dataclass(frozen=True, slots=True)
class LocalInstitutionSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_institution"


@dataclass(frozen=True, slots=True)
class PublicEmploymentLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "public_employment_lemma"


@dataclass(frozen=True, slots=True)
class EmploymentContractFormSignal(PositiveSignal):
    form: str

    @property
    def name(self) -> str:
        return "employment_contract_form"


@dataclass(frozen=True, slots=True)
class ProxyFamilyEntitySignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "proxy_family_entity"


@dataclass(frozen=True, slots=True)
class RelationshipDetailSignal(PositiveSignal):
    detail: RelationshipDetail

    @property
    def name(self) -> str:
        return "relationship_detail"


@dataclass(frozen=True, slots=True)
class NamedKinshipLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "named_kinship_lemma"


@dataclass(frozen=True, slots=True)
class ExplicitPatronageLemmaSignal(PositiveSignal):
    lemma: str

    @property
    def name(self) -> str:
        return "explicit_patronage_lemma"


@dataclass(frozen=True, slots=True)
class LocalSubjectSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_subject"


@dataclass(frozen=True, slots=True)
class LocalObjectSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "sentence_local_object"


@dataclass(frozen=True, slots=True)
class ExplicitNonPartyContextSignal(NegativeSignal):
    @property
    def name(self) -> str:
        return "explicit_nonparty_context"


@dataclass(frozen=True, slots=True)
class MicroAmountSignal(NegativeSignal):
    amount: str

    @property
    def name(self) -> str:
        return f"micro_amount:{self.amount}"


@dataclass(frozen=True, slots=True)
class CoreferenceProviderLinkSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "coreference_provider_link"


@dataclass(frozen=True, slots=True)
class ThirdPersonPronounSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "third_person_pronoun"


@dataclass(frozen=True, slots=True, kw_only=True)
class RelevanceSignal(Signal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class PositiveRelevanceSignal(RelevanceSignal):
    polarity: SignalPolarity = SignalPolarity.POSITIVE


@dataclass(frozen=True, slots=True, kw_only=True)
class NegativeRelevanceSignal(RelevanceSignal):
    polarity: SignalPolarity = SignalPolarity.NEGATIVE


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicMoneyRelevanceSignal(PositiveRelevanceSignal):
    @property
    def name(self) -> str:
        return "public-money context"


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicOrgRelevanceSignal(PositiveRelevanceSignal):
    @property
    def name(self) -> str:
        return "public or organizational context"


@dataclass(frozen=True, slots=True, kw_only=True)
class AppointmentRelevanceSignal(PositiveRelevanceSignal):
    @property
    def name(self) -> str:
        return "appointment or employment context"


@dataclass(frozen=True, slots=True, kw_only=True)
class AntiCorruptionRelevanceSignal(PositiveRelevanceSignal):
    @property
    def name(self) -> str:
        return "anti-corruption context"


@dataclass(frozen=True, slots=True, kw_only=True)
class CombinedRelevanceSignal(PositiveRelevanceSignal):
    @property
    def name(self) -> str:
        return "combined relevance context"


@dataclass(frozen=True, slots=True, kw_only=True)
class StrongCombinedRelevanceSignal(PositiveRelevanceSignal):
    @property
    def name(self) -> str:
        return "strong combined relevance context"


@dataclass(frozen=True, slots=True, kw_only=True)
class LegalNegativeRelevanceSignal(NegativeRelevanceSignal):
    @property
    def name(self) -> str:
        return "legal-analysis negative context"


@dataclass(frozen=True, slots=True, kw_only=True)
class NoRelevanceIndicatorsSignal(NegativeRelevanceSignal):
    @property
    def name(self) -> str:
        return "no relevance indicators found"


@dataclass(frozen=True, slots=True, kw_only=True)
class NearbyPersonCandidateSignal(PositiveSignal):
    @property
    def name(self) -> str:
        return "nearby_person_candidate"


@dataclass(frozen=True, slots=True, kw_only=True)
class DescriptorPersonCandidateSignal(PositiveSignal):
    descriptor_lemma: str
    sentence_distance: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencySubjectSignal(PositiveSignal):
    relation: DependencyRelation


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencyObjectSignal(PositiveSignal):
    relation: DependencyRelation


@dataclass(frozen=True, slots=True, kw_only=True)
class InferredPublicOrganizationSignal(PositiveSignal):
    head_lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LocationContextSignal(PositiveSignal):
    distance: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepositionalOrganizationSignal(PositiveSignal):
    preposition_lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PossessiveKinshipSignal(PositiveSignal):
    kinship_lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WindowFallbackSignal(PositiveSignal):
    distance: int


@dataclass(frozen=True, slots=True, kw_only=True)
class WeakSyntacticBindingSignal(NegativeSignal):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AppointerContextSignal(NegativeSignal):
    role_lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ControllerContextSignal(NegativeSignal):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PseudonymousSourceSignal(NegativeSignal):
    cue_lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfTieContradictionSignal(NegativeSignal):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DuplicateFactSignal(PositiveSignal):
    strategy: FactResolutionStrategy
    fact_kind: FactKind


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticEvidenceSimilaritySignal(PositiveSignal):
    score: float


@dataclass(frozen=True, slots=True, kw_only=True)
class MinistryLemmaSignal(PositiveSignal):
    lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TreasuryLemmaSignal(PositiveSignal):
    lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicInstitutionLemmaSignal(PositiveSignal):
    lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaOutletLemmaSignal(PositiveSignal):
    lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GoverningBodyLemmaSignal(PositiveSignal):
    lemma: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalHintMatchSignal(PositiveSignal):
    hint: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SyntaxPossessorSignal(PositiveSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class StrongPossessorSignal(PositiveSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class MediumPossessorSignal(PositiveSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class WeakPossessorSignal(NegativeSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class NegativePossessorSignal(NegativeSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceTransactionSignal(PositiveSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class GrantTransactionSignal(PositiveSignal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ContractDocumentSignal(PositiveSignal):
    pass
