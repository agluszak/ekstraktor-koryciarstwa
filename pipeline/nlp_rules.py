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

ROLE_LEMMAS: list[tuple[RoleKind, RoleModifier | None, tuple[str, ...]]] = [
    (RoleKind.PREZES, None, ("prezes",)),
    (RoleKind.PREZES, None, ("prezeska",)),
    (RoleKind.PREZES, RoleModifier.DEPUTY, ("wiceprezes",)),
    (RoleKind.PREZES, RoleModifier.DEPUTY, ("wiceprezeska",)),
    (RoleKind.PREZES, RoleModifier.DEPUTY, ("zastępca", "prezes")),
    (RoleKind.DYREKTOR, None, ("dyrektor",)),
    (RoleKind.DYREKTOR, None, ("dyrektorka",)),
    (RoleKind.CZLONEK_ZARZADU, None, ("członek", "zarząd")),
    (RoleKind.RADA_NADZORCZA, None, ("rada", "nadzorczy")),
    (RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ, None, ("przewodniczący", "rada", "nadzorczy")),
    (
        RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
        RoleModifier.DEPUTY,
        ("wiceprzewodniczący", "rada", "nadzorczy"),
    ),
    (RoleKind.RADNY, None, ("radny",)),
    (RoleKind.POSEL, None, ("poseł",)),
    (RoleKind.POSEL, None, ("posłanka",)),
    (RoleKind.SENATOR, None, ("senator",)),
    (RoleKind.SENATOR, None, ("senatorka",)),
    (RoleKind.MINISTER, None, ("minister",)),
    (RoleKind.MINISTER, None, ("ministra",)),
    (RoleKind.MINISTER, RoleModifier.DEPUTY, ("wiceminister",)),
    (RoleKind.PREZYDENT_MIASTA, None, ("prezydent", "miasto")),
    (RoleKind.PREZYDENT_MIASTA, RoleModifier.DEPUTY, ("wiceprezydent",)),
    (RoleKind.WOJEWODA, None, ("wojewoda",)),
    (RoleKind.WOJEWODA, RoleModifier.DEPUTY, ("wicewojewoda",)),
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
APPOINTMENT_TRIGGER_TEXTS = frozenset(
    {
        "został prezesem",
        "została prezesem",
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
        "powołany na",
        "powołana na",
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
        "złożył rezygnację",
        "złożyła rezygnację",
        "przyjęła rezygnację",
        "przyjął rezygnację",
        "odwołano",
        "został odwołany",
        "została odwołana",
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
