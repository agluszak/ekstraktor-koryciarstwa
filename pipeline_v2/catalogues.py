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


SOCIAL_RELATION_DETAILS: Final[dict[str, RelationshipDetail]] = {
    "kolega": RelationshipDetail.FRIEND,
    "koleżanka": RelationshipDetail.FRIEND,
    "znajomy": RelationshipDetail.FRIEND,
    "znajoma": RelationshipDetail.FRIEND,
    "przyjaciel": RelationshipDetail.FRIEND,
    "przyjaciółka": RelationshipDetail.FRIEND,
    "drużba": RelationshipDetail.FRIEND,
    "druhna": RelationshipDetail.FRIEND,
    "kompan": RelationshipDetail.FRIEND,
    "kompanka": RelationshipDetail.FRIEND,
    "kumpel": RelationshipDetail.FRIEND,
    "kumpela": RelationshipDetail.FRIEND,
    "współwłaściciel": RelationshipDetail.BUSINESS_PARTNER,
    "współwłaścicielka": RelationshipDetail.BUSINESS_PARTNER,
    "akcjonariusz": RelationshipDetail.BUSINESS_PARTNER,
    "akcjonariuszka": RelationshipDetail.BUSINESS_PARTNER,
    "kooperant": RelationshipDetail.BUSINESS_PARTNER,
    "kooperantka": RelationshipDetail.BUSINESS_PARTNER,
    "kontrahent": RelationshipDetail.BUSINESS_PARTNER,
    "kontrahentka": RelationshipDetail.BUSINESS_PARTNER,
    "współposiadacz": RelationshipDetail.BUSINESS_PARTNER,
    "współposiadaczka": RelationshipDetail.BUSINESS_PARTNER,
    "udziałowiec": RelationshipDetail.BUSINESS_PARTNER,
    "udziałowczyni": RelationshipDetail.BUSINESS_PARTNER,
    "towarzysz": RelationshipDetail.ASSOCIATE,
    "towarzyszka": RelationshipDetail.ASSOCIATE,
    "współuczestnik": RelationshipDetail.ASSOCIATE,
    "współuczestniczka": RelationshipDetail.ASSOCIATE,
    "partycypant": RelationshipDetail.ASSOCIATE,
    "partycypantka": RelationshipDetail.ASSOCIATE,
    "powiernik": RelationshipDetail.ASSOCIATE,
    "powierniczka": RelationshipDetail.ASSOCIATE,
}
