from typing import Final

ORG_LIKE_PERSON_HINT_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "biuro",
        "fundusz",
        "ministerstwo",
        "ofe",
        "pap",
        "spółka",
        "urząd",
    }
)

PERSON_DESCRIPTOR_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "polityk",
        "działacz",
        "urzędnik",
        "menedżer",
        "manager",
        "kandydat",
        "członek",
    }
)

APPOINTMENT_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "powołać",
        "mianować",
        "zatrudnić",
        "objąć",
        "wybrać",
        "awansować",
        "zostać",
        "nominacja",
        "powołanie",
        "wejść",
        "zająć",
        "wskoczyć",
    }
)

HOLDING_LEMMAS: Final[frozenset[str]] = frozenset({"być", "pozostawać", "zasiadać"})

FORMER_DESCRIPTOR_LEMMAS: Final[frozenset[str]] = frozenset(
    {"były", "dawny", "wcześniej", "niegdyś", "ex-"}
)

GENERIC_APPOINTMENT_LEMMAS: Final[frozenset[str]] = frozenset(
    {"zostać", "wejść", "nominacja", "zająć"}
)

OBJAC_APPOINTMENT_LEMMAS: Final[frozenset[str]] = frozenset({"objąć", "objęcie"})

TEMPORAL_PREPOSITIONS: Final[frozenset[str]] = frozenset({"od", "po", "przed", "za", "do"})

SUCCESSOR_NOUN_LEMMAS: Final[frozenset[str]] = frozenset({"następca"})

CURRENT_DESCRIPTOR_LEMMAS: Final[frozenset[str]] = frozenset(
    {"obecny", "aktualny", "dotychczasowy"}
)

DASH_CHARS: Final[frozenset[str]] = frozenset({"—", "–", "-"})

EXCEPTION_CLAUSE_LEMMAS: Final[frozenset[str]] = frozenset({"wyjątek"})

DISMISSAL_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "odwołać",
        "odwoływać",
        "zwolnić",
        "zwalniać",
        "usunąć",
        "usuwać",
        "zdymisjonować",
        "stracić",
        "rezygnacja",
        "zrezygnować",
        "rezygnować",
        "odejść",
        "odchodzić",
        "pożegnać",
        "odwołanie",
        "dymisja",
        "zasiadać",
    }
)

GOVERNANCE_ROLE_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "członek",
        "naczelnik",
        "nadzorczy",
        "prezes",
        "rada",
        "sekretarz",
        "zarząd",
        "dyrektor",
        "wicedyrektor",
        "wiceprezes",
        "kierownik",
        "szef",
        "wiceszef",
        "przewodniczący",
        "przewodnicząca",
    }
)

POLITICAL_ROLE_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "poseł",
        "posłanka",
        "radny",
        "radna",
        "senator",
        "minister",
        "prezydent",
        "wojewoda",
        "wójt",
        "burmistrz",
        "starosta",
        "marszałek",
    }
)

VERB_LIKE_POS: Final[frozenset[str]] = frozenset(
    {"fin", "praet", "bedzie", "impt", "imps", "inf", "pcon", "pant", "ger", "pred"}
)

ROLE_TITLE_ONLY_PERSON_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "dyrektor",
        "kierownik",
        "naczelnik",
        "prezes",
        "sekretarz",
        "skarbnik",
        "szef",
        "wicedyrektor",
        "wiceprezes",
        "zastępca",
    }
)

SINGULAR_PERSON_ROLE_LEMMAS: Final[frozenset[str]] = frozenset(
    {
        "prezes",
        "dyrektor",
        "wicedyrektor",
        "wiceprezes",
        "kierownik",
        "szef",
    }
)
