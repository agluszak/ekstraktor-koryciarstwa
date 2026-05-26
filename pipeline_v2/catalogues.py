from typing import Final

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
