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
    "brat": RelationshipDetail.FAMILY, # SIBLING
    "córka": RelationshipDetail.FAMILY, # CHILD
    "dziewczyna": RelationshipDetail.FAMILY, # SPOUSE
    "kuzyn": RelationshipDetail.FAMILY,
    "kuzynka": RelationshipDetail.FAMILY,
    "matka": RelationshipDetail.FAMILY, # PARENT
    "mąż": RelationshipDetail.FAMILY, # SPOUSE
    "narzeczona": RelationshipDetail.FAMILY, # SPOUSE
    "narzeczony": RelationshipDetail.FAMILY, # SPOUSE
    "ojciec": RelationshipDetail.FAMILY, # PARENT
    "partner": RelationshipDetail.FAMILY, # SPOUSE
    "partnerka": RelationshipDetail.FAMILY, # SPOUSE
    "siostra": RelationshipDetail.FAMILY, # SIBLING
    "syn": RelationshipDetail.FAMILY, # CHILD
    "teść": RelationshipDetail.FAMILY,
    "teściowa": RelationshipDetail.FAMILY,
    "żona": RelationshipDetail.FAMILY, # SPOUSE
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
    "współwłaściciel": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "współwłaścicielka": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "akcjonariusz": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "akcjonariuszka": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "kooperant": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "kooperantka": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "kontrahent": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "kontrahentka": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "współposiadacz": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "współposiadaczka": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "udziałowiec": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "udziałowczyni": RelationshipDetail.FRIEND, # BUSINESS_PARTNER
    "towarzysz": RelationshipDetail.FRIEND, # ASSOCIATE
    "towarzyszka": RelationshipDetail.FRIEND, # ASSOCIATE
    "współuczestnik": RelationshipDetail.FRIEND, # ASSOCIATE
    "współuczestniczka": RelationshipDetail.FRIEND, # ASSOCIATE
    "partycypant": RelationshipDetail.FRIEND, # ASSOCIATE
    "partycypantka": RelationshipDetail.FRIEND, # ASSOCIATE
    "powiernik": RelationshipDetail.FRIEND, # ASSOCIATE
    "powierniczka": RelationshipDetail.FRIEND, # ASSOCIATE
}
