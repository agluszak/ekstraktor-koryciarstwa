from __future__ import annotations

import re
from collections.abc import Mapping

from pipeline.domain_types import RelationshipType, RoleKind

BOARD_ROLE_KINDS = {
    RoleKind.PREZES,
    RoleKind.CZLONEK_ZARZADU,
    RoleKind.RADA_NADZORCZA,
    RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
}

APPOINTMENT_TRIGGER_LEMMAS = frozenset(
    {
        "powołać",
        "powoływać",
        "objąć",
        "wybrać",
        "mianować",
        "trafić",
        "zająć",
        "awansować",
        "zostać",
        "zatrudnić",
        "zatrudnienie",
        "pracować",
    }
)
DISMISSAL_TRIGGER_LEMMAS = frozenset({"odwołać", "odwoływać", "zrezygnować"})
APPOINTMENT_NOUN_LEMMAS = frozenset({"nominacja", "stanowisko", "funkcja", "praca"})
DISMISSAL_NOUN_LEMMAS = frozenset({"rezygnacja"})
APPOINTMENT_TRIGGER_TEXTS = frozenset(
    {
        "odebrał nominację",
        "zasiądzie w",
        "zasiadł w",
        "zasiadła w",
        "ma zostać",
        "jest zatrudniona",
        "była zatrudniona",
        "jest zatrudniony",
        "był zatrudniony",
        "pracuje w",
        "pracowała w",
    }
)
DISMISSAL_TRIGGER_TEXTS = frozenset(
    {
        "nie jest już",
        "nie zasiada już",
    }
)

PARTY_CONTEXT_LEMMAS = frozenset(
    {
        "działacz",
        "działaczka",
        "lider",
        "liderka",
        "polityk",
        "polityczka",
        "prezes",
        "członek",
        "członkini",
        "poseł",
        "posłanka",
        "senator",
        "senatorka",
        "partia",
        "radny",
        "radna",
        "wicewojewoda",
        "wiceminister",
    }
)
PARTY_PROFILE_CONTEXT_LEMMAS = PARTY_CONTEXT_LEMMAS - frozenset({"prezes"})
FORMER_MARKERS = frozenset({"były", "była", "dawny", "dawna", "eks"})
FUNDING_HINTS = frozenset(
    {
        "dotacja",
        "dofinansowanie",
        "wyłożyć",
        "przekazać",
        "sfinansować",
        "pochłonąć",
    }
)
COMPENSATION_PATTERN = re.compile(
    r"\b(?P<amount>\d+(?:[ .,]\d+)*(?:\s*tys\.)?\s*zł(?:\s*brutto)?)"
    r"(?:\s*(?P<period>miesięcznie|mies\.|rocznie|za rok \d{4}|za miesiąc))?",
    re.IGNORECASE,
)
OFFICE_CANDIDACY_LEMMAS = frozenset({"kandydować", "startować", "ubiegać"})

OWNER_CONTEXT_TERMS = frozenset(
    {
        "ministerstwo",
        "minister",
        "krajowy ośrodek",
        "krajowy ośrodek wsparcia rolnictwa",
        "kowr",
        "krajowy zasób",
        "skarbu państwa",
        "nadzór",
        "właścicielski",
        "podległ",
        "podlega",
        "nadzorowan",
        "kontrolowan",
        "należąc",
        "spółki podległej",
        "spółka skarbu państwa",
    }
)
BODY_CONTEXT_TERMS = frozenset({"rada", "rada nadzorcza", "zarząd", "komitet", "komisja"})
TARGET_CONTEXT_TERMS = frozenset(
    {
        "spółk",
        "spółce",
        "fundusz",
        "agencj",
        "stadnin",
        "hotel",
        "rewita",
        "tour",
        "wodociąg",
        "kanaliz",
        "wtc",
        "grup",
    }
)

TIE_WORDS: Mapping[str, RelationshipType] = {
    "zaufany": RelationshipType.ASSOCIATE,
    "znajomy": RelationshipType.ASSOCIATE,
    "współpracownik": RelationshipType.COLLABORATOR,
    "przyjaciel": RelationshipType.FRIEND,
    "doradca": RelationshipType.ADVISOR,
    "ochroniarz": RelationshipType.BODYGUARD,
    "rekomendować": RelationshipType.RECOMMENDER,
    "rekomendacja": RelationshipType.RECOMMENDER,
    "szef gabinetu": RelationshipType.OFFICE_CHIEF,
    "gabinet polityczny": RelationshipType.OFFICE_CHIEF,
    "szef biura": RelationshipType.OFFICE_CHIEF,
}

APPOINTING_AUTHORITY_LEMMAS = frozenset(
    {"powołać", "mianować", "nominować", "obsadzić", "wybrać", "wskazać"}
)
APPOINTING_AUTHORITY_TITLE_LEMMAS = frozenset(
    {"prezydent", "burmistrz", "wójt", "wojt", "starosta", "marszałek", "wojewoda", "minister"}
)
