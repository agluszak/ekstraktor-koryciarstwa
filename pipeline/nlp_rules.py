from __future__ import annotations

import re
from collections.abc import Mapping

from pipeline.domain_types import RelationshipType, RoleKind, RoleModifier

BOARD_ROLE_KINDS = {
    RoleKind.PREZES,
    RoleKind.CZLONEK_ZARZADU,
    RoleKind.RADA_NADZORCZA,
    RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
}

ROLE_PATTERNS: list[tuple[RoleKind, RoleModifier | None, re.Pattern[str]]] = [
    (
        RoleKind.PREZES,
        None,
        re.compile(r"\bprezes(?:em|a)?\b|\bprezesk(?:ą|a)\b", re.IGNORECASE),
    ),
    (
        RoleKind.PREZES,
        RoleModifier.DEPUTY,
        re.compile(r"\bwiceprezes(?:em|a)?\b|\bwiceprezesk(?:ą|a)\b", re.IGNORECASE),
    ),
    (
        RoleKind.PREZES,
        RoleModifier.DEPUTY,
        re.compile(r"\bzastępc(?:a|ą|y)\s+prezesa\b", re.IGNORECASE),
    ),
    (
        RoleKind.DYREKTOR,
        None,
        re.compile(r"\bdyrektor(?:em|a)?\b|\bdyrektork(?:ą|a)\b", re.IGNORECASE),
    ),
    (
        RoleKind.CZLONEK_ZARZADU,
        None,
        re.compile(r"\bczłonk(?:iem|a)\s+zarządu\b", re.IGNORECASE),
    ),
    (
        RoleKind.RADA_NADZORCZA,
        None,
        re.compile(r"\brad(?:y|zie|a)\s+nadzorczej\b", re.IGNORECASE),
    ),
    (
        RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
        None,
        re.compile(r"\bprzewodnicząc(?:y|ego)\s+rady\s+nadzorczej\b", re.IGNORECASE),
    ),
    (
        RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
        RoleModifier.DEPUTY,
        re.compile(r"\bwiceprzewodnicząc(?:y|ego)\s+rady\s+nadzorczej\b", re.IGNORECASE),
    ),
    (RoleKind.RADNY, None, re.compile(r"\bradn(?:y|ego|a|ą)\b", re.IGNORECASE)),
    (RoleKind.POSEL, None, re.compile(r"\bpos(?:eł|ła|łem|łanka|łem)\b", re.IGNORECASE)),
    (RoleKind.SENATOR, None, re.compile(r"\bsenator(?:em|a)?\b", re.IGNORECASE)),
    (RoleKind.MINISTER, None, re.compile(r"\bminister(?:em|a)?\b", re.IGNORECASE)),
    (
        RoleKind.MINISTER,
        RoleModifier.DEPUTY,
        re.compile(r"\bwiceminister(?:em|a)?\b", re.IGNORECASE),
    ),
    (
        RoleKind.PREZYDENT_MIASTA,
        None,
        re.compile(r"\bprezydent(?:em|a)?\s+miasta\b", re.IGNORECASE),
    ),
    (
        RoleKind.PREZYDENT_MIASTA,
        RoleModifier.DEPUTY,
        re.compile(r"\bwiceprezydent(?:em|a)?\b", re.IGNORECASE),
    ),
    (RoleKind.WOJEWODA, None, re.compile(r"\bwojewod(?:a|ą|y)\b", re.IGNORECASE)),
    (
        RoleKind.WOJEWODA,
        RoleModifier.DEPUTY,
        re.compile(r"\bwicewojewod(?:a|ą|y)\b", re.IGNORECASE),
    ),
]


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
    "narzeczona": RelationshipType.FAMILY,
    "narzeczony": RelationshipType.FAMILY,
    "żona": RelationshipType.FAMILY,
    "mąż": RelationshipType.FAMILY,
}

KINSHIP_LEMMAS = frozenset(
    {
        "żona",
        "mąż",
        "syn",
        "córka",
        "brat",
        "siostra",
        "szwagier",
        "szwagierka",
        "kuzyn",
        "kuzynka",
        "partnerka",
        "partner",
        "narzeczona",
        "narzeczony",
    }
)
