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


def is_role_title_lemma(lemma: str | None) -> bool:
    if not lemma:
        return False
    return lemma.lower() in PUBLIC_ROLE_TITLE_LEMMAS


def is_organization_descriptor_lemma(lemma: str | None) -> bool:
    if not lemma:
        return False
    return lemma.lower() in ORGANIZATION_DESCRIPTOR_LEMMAS
