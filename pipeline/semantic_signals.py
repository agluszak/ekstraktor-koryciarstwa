from __future__ import annotations

from collections.abc import Iterable

PATRONAGE_LANGUAGE_MARKERS = frozenset({"kolesiostwo", "rozdawanie posad"})

PUBLIC_FUND_CONTEXT_MARKERS = frozenset(
    {
        "fundusz",
        "wojewódzki fundusz",
        "narodowy fundusz",
        "wfoś",
        "wfośigw",
        "nfoś",
        "nfośigw",
        "instytucja",
        "urząd marszałkowski",
    }
)

SOFT_GOVERNANCE_CONTEXT_MARKERS = frozenset(
    {
        "bez konkursu",
        "nominacj",
        "będą kierować",
        "pokieruje",
        "pokierują",
        "powoływany jest przez radę nadzorczą",
        "ma zostać",
    }
)

ANTI_CORRUPTION_CONTEXT_MARKERS = frozenset(
    {
        "cba",
        "centralne biuro antykorupcyjne",
        "korupcja",
        "korupcyj",
        "łapówka",
        "łapówki",
        "łapówkę",
        "zamówienia publiczne",
        "zamówień publicznych",
        "ustawianie zleceń",
        "ustawiania zleceń",
        "przekroczenie uprawnień",
        "przekroczenia uprawnień",
    }
)

PUBLIC_OFFICE_ACTOR_MARKERS = frozenset(
    {
        "wójt",
        "wójta",
        "burmistrz",
        "starosta",
        "sekretarz powiatu",
        "marszałek województwa",
        "wojewoda",
    }
)

EMPLOYMENT_CONTEXT_MARKERS = frozenset(
    {
        "prac",
        "zatrudn",
        "praca",
        "etat",
        "stanowisk",
        "koordynator",
        "specjalist",
        "doradc",
        "funkcj",
    }
)

PUBLIC_COUNTERPARTY_MARKERS = frozenset(
    {
        "gmina",
        "miasto",
        "urząd",
        "miejski",
        "miejska",
        "miejskie",
        "komunaln",
        "publiczn",
        "pec",
        "bpk",
        "przedsiębiorstwo komunalne",
    }
)

CONTRACTOR_CONTEXT_MARKERS = frozenset(
    {"firma", "firmy", "firmą", "spółka", "spółki", "spółką", "podmiot"}
)

COMPLAINT_PATRONAGE_MARKERS = frozenset(
    {
        "kolesiostw",
        "rozdawanie posad",
        "rozdawnictwo posad",
        "partyjnych baron",
        "zawłaszczyli",
        "członków jego ekipy",
    }
)

COMPLAINT_POWER_MARKERS = frozenset(
    {
        "prezydent",
        "burmistrz",
        "wójt",
        "starosta",
        "marszałek",
        "przewodnicząc",
        "koalicj",
        "ekipy",
    }
)

COMPLAINT_SPEAKER_MARKERS = frozenset(
    {"napisał", "napisała", "pisze", "wylicza", "próbowała", "prosi", "zada"}
)

GOVERNANCE_TARGET_HEAD_MARKERS = frozenset(
    {"spół", "przedsiębiorstw", "stadnin", "kolej", "wodociąg", "centrum", "hotel", "agencja"}
)

GOVERNANCE_ROLE_SURFACES = frozenset(
    {
        "do rady nadzorczej",
        "członkiem rady",
        "prezesem",
        "prezeską",
        "wiceprezesem",
        "wiceprezeską",
        "dyrektorem",
        "zarządu",
    }
)

OWNER_CONTEXT_EXTRA_TERMS = frozenset(
    {"województw", "urząd marszałkowski", "marszałek województwa", "samorząd", "właściciel"}
)


def matching_markers(text: str, markers: Iterable[str]) -> list[str]:
    lowered = text.casefold()
    return [marker for marker in markers if marker in lowered]


def has_any_marker(text: str, markers: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in markers)
