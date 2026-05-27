from typing import Final

from pipeline_v2.types import RelationshipDetail

PUBLIC_ROLE_TITLE_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "minister",
        "wiceminister",
        "premier",
        "wicepremier",
        "dyrektor",
        "prezes",
        "wiceprezes",
        "kierownik",
        "sekretarz",
        "podsekretarz",
        "wojewoda",
        "wicewojewoda",
        "marszałek",
        "wicemarszałek",
        "starosta",
        "wicestarosta",
        "burmistrz",
        "wiceburmistrz",
        "prezydent",
        "wiceprezydent",
        "wójt",
        "radny",
        "poseł",
        "senator",
        "pełnomocnik",
        "członek",
        "szef",
        "radna",
        "posłanka",
        "senatorka",
        "dyrektorka",
        "kierowniczka",
        "prezeska",
        "ministra",
    }
)

ORGANIZATION_DESCRIPTOR_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "agencja",
        "dealer",
        "firma",
        "fundacja",
        "linia",
        "linie",
        "lotnisko",
        "partia",
        "portal",
        "port",
        "redakcja",
        "spółka",
        "stowarzyszenie",
        "urząd",
    }
)

ORGANIZATION_SUFFIX_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "OFE",
        "S.A.",
        "SA",
        "SKA",
        "Sp.",
        "z.o.o.",
    }
)


def is_role_title_lemma(lemma: str | None) -> bool:
    if not lemma:
        return False
    return lemma.lower() in PUBLIC_ROLE_TITLE_LEMMAS


def is_organization_descriptor_lemma(lemma: str | None) -> bool:
    if not lemma:
        return False
    return lemma.lower() in ORGANIZATION_DESCRIPTOR_LEMMAS


def is_organization_suffix_token(text: str | None) -> bool:
    if not text:
        return False
    return text in ORGANIZATION_SUFFIX_TOKENS


POLITICAL_PARTY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "koalicja obywatelska",
        "koalicji obywatelskiej",
        "lewica",
        "platforma obywatelska",
        "platformy obywatelskiej",
        "polska 2050",
        "polskie stronnictwo ludowe",
        "polskiego stronnictwa ludowego",
        "prawo i sprawiedliwość",
        "prawa i sprawiedliwości",
        "pis",
        "po",
        "psl",
        "razem",
    }
)

FAMILY_RELATION_DETAILS: Final[dict[str, RelationshipDetail]] = {
    "brat": RelationshipDetail.SIBLING,
    "córka": RelationshipDetail.CHILD,
    "dziewczyna": RelationshipDetail.SPOUSE,
    "kuzyn": RelationshipDetail.FAMILY,
    "kuzynka": RelationshipDetail.FAMILY,
    "matka": RelationshipDetail.PARENT,
    "mąż": RelationshipDetail.SPOUSE,
    "narzeczona": RelationshipDetail.SPOUSE,
    "narzeczony": RelationshipDetail.SPOUSE,
    "ojciec": RelationshipDetail.PARENT,
    "partner": RelationshipDetail.SPOUSE,
    "partnerka": RelationshipDetail.SPOUSE,
    "siostra": RelationshipDetail.SIBLING,
    "syn": RelationshipDetail.CHILD,
    "teść": RelationshipDetail.FAMILY,
    "teściowa": RelationshipDetail.FAMILY,
    "żona": RelationshipDetail.SPOUSE,
}
