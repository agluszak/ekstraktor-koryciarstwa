from __future__ import annotations

import re
from collections.abc import Mapping

from pipeline.domain_types import RelationshipType, RoleKind

BOARD_ROLE_KINDS = {
    RoleKind.PREZES,
    RoleKind.WICEPREZES,
    RoleKind.CZLONEK_ZARZADU,
    RoleKind.RADA_NADZORCZA,
    RoleKind.WICEPRZEWODNICZACY_RADY_NADZORCZEJ,
    RoleKind.ZASTEPCA_PREZESA,
}

ROLE_PATTERNS: Mapping[RoleKind, re.Pattern[str]] = {
    RoleKind.PREZES: re.compile(r"\bprezes(?:em|a)?\b|\bprezesk(?:ą|a)\b", re.IGNORECASE),
    RoleKind.WICEPREZES: re.compile(
        r"\bwiceprezes(?:em|a)?\b|\bwiceprezesk(?:ą|a)\b",
        re.IGNORECASE,
    ),
    RoleKind.ZASTEPCA_PREZESA: re.compile(
        r"\bzastępc(?:a|ą|y)\s+prezesa\b",
        re.IGNORECASE,
    ),
    RoleKind.DYREKTOR: re.compile(r"\bdyrektor(?:em|a)?\b|\bdyrektork(?:ą|a)\b", re.IGNORECASE),
    RoleKind.CZLONEK_ZARZADU: re.compile(
        r"\bczłonk(?:iem|a)\s+zarządu\b",
        re.IGNORECASE,
    ),
    RoleKind.RADA_NADZORCZA: re.compile(r"\brad(?:y|zie|a)\s+nadzorczej\b", re.IGNORECASE),
    RoleKind.WICEPRZEWODNICZACY_RADY_NADZORCZEJ: re.compile(
        r"\bwiceprzewodnicząc(?:y|ego)\s+rady\s+nadzorczej\b",
        re.IGNORECASE,
    ),
    RoleKind.RADNY: re.compile(r"\bradn(?:y|ego|a|ą)\b", re.IGNORECASE),
    RoleKind.POSEL: re.compile(r"\bpos(?:eł|ła|łem|łanka|łem)\b", re.IGNORECASE),
    RoleKind.SENATOR: re.compile(r"\bsenator(?:em|a)?\b", re.IGNORECASE),
    RoleKind.WICEMINISTER: re.compile(r"\bwiceminister(?:em|a)?\b", re.IGNORECASE),
    RoleKind.MINISTER: re.compile(r"\bminister(?:em|a)?\b", re.IGNORECASE),
    RoleKind.PREZYDENT_MIASTA: re.compile(
        r"\bprezydent(?:em|a)?\s+miasta\b",
        re.IGNORECASE,
    ),
    RoleKind.WICEPREZYDENT: re.compile(r"\bwiceprezydent(?:em|a)?\b", re.IGNORECASE),
    RoleKind.WICEWOJEWODA: re.compile(r"\bwicewojewod(?:a|ą|y)\b", re.IGNORECASE),
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
    }
)
DISMISSAL_TRIGGER_LEMMAS = frozenset({"odwołać", "zrezygnować"})
APPOINTMENT_TRIGGER_TEXTS = frozenset(
    {
        "został prezesem",
        "została prezeską",
        "został wiceprezesem",
        "została wiceprezeską",
        "został dyrektorem",
        "została dyrektorką",
        "odebrał nominację",
        "objął stanowisko",
        "objęła stanowisko",
        "awansował na stanowisko",
        "awansowała na stanowisko",
        "zajął funkcję",
        "zajęła funkcję",
        "ma zostać",
    }
)
DISMISSAL_TRIGGER_TEXTS = frozenset(
    {
        "nie jest już",
        "nie zasiada już",
        "złożył rezygnację",
        "złożyła rezygnację",
        "przyjęła rezygnację",
        "przyjął rezygnację",
    }
)

PARTY_CONTEXT_LEMMAS = frozenset(
    {
        "działacz",
        "lider",
        "polityk",
        "prezes",
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
FORMER_MARKERS = frozenset({"były", "była", "dawny", "dawna", "eks"})
FUNDING_HINTS = frozenset(
    {
        "dotacja",
        "dotacje",
        "dofinansowanie",
        "dofinansowania",
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
