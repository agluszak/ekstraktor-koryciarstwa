from __future__ import annotations

import re

BOARD_ROLE_NAMES = {
    "prezes",
    "wiceprezes",
    "członek zarządu",
    "rada nadzorcza",
    "wiceprzewodniczący rady nadzorczej",
    "zastępca prezesa",
}

ROLE_PATTERNS = {
    "prezes": re.compile(r"\bprezes(?:em|a)?\b", re.IGNORECASE),
    "wiceprezes": re.compile(r"\bwiceprezes(?:em|a)?\b", re.IGNORECASE),
    "zastępca prezesa": re.compile(
        r"\bzastępc(?:a|ą|y)\s+prezesa\b",
        re.IGNORECASE,
    ),
    "dyrektor": re.compile(r"\bdyrektor(?:em|a)?\b", re.IGNORECASE),
    "członek zarządu": re.compile(r"\bczłonk(?:iem|a)\s+zarządu\b", re.IGNORECASE),
    "rada nadzorcza": re.compile(r"\brad(?:y|zie|a)\s+nadzorczej\b", re.IGNORECASE),
    "wiceprzewodniczący rady nadzorczej": re.compile(
        r"\bwiceprzewodnicząc(?:y|ego)\s+rady\s+nadzorczej\b",
        re.IGNORECASE,
    ),
    "radny": re.compile(r"\bradn(?:y|ego|a|ą)\b", re.IGNORECASE),
    "poseł": re.compile(r"\bpos(?:eł|ła|łem|łanka|łem)\b", re.IGNORECASE),
    "senator": re.compile(r"\bsenator(?:em|a)?\b", re.IGNORECASE),
    "wiceminister": re.compile(r"\bwiceminister(?:em|a)?\b", re.IGNORECASE),
    "minister": re.compile(r"\bminister(?:em|a)?\b", re.IGNORECASE),
    "prezydent miasta": re.compile(r"\bprezydent(?:em|a)?\s+miasta\b", re.IGNORECASE),
    "wiceprezydent": re.compile(r"\bwiceprezydent(?:em|a)?\b", re.IGNORECASE),
    "wicewojewoda": re.compile(r"\bwicewojewod(?:a|ą|y)\b", re.IGNORECASE),
}

APPOINTMENT_LEMMAS = {
    "powołać",
    "objąć",
    "wybrać",
    "mianować",
    "trafić",
    "zająć",
    "awansować",
}
APPOINTMENT_TEXTS = {
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

DISMISSAL_LEMMAS = {"odwołać", "zrezygnować"}
DISMISSAL_TEXTS = {
    "nie jest już",
    "złożył rezygnację",
    "złożyła rezygnację",
    "przyjęła rezygnację",
    "przyjął rezygnację",
}

PARTY_CONTEXT_WORDS = {
    "działacz",
    "polityk",
    "poseł",
    "posłanka",
    "senator",
    "senatorka",
    "radny",
    "radna",
    "wicewojewoda",
    "wiceminister",
}

FORMER_MARKERS = {"były", "była", "dawny", "dawna", "eks"}

TIE_WORDS = {
    "znajomy": "associate",
    "współpracownik": "collaborator",
    "przyjaciel": "friend",
    "doradca": "advisor",
    "ochroniarz": "bodyguard",
    "rekomendować": "recommender",
    "rekomendacja": "recommender",
    "szef biura": "office_chief",
}

FUNDING_HINTS = {
    "dotacja",
    "dotacje",
    "dofinansowanie",
    "dofinansowania",
    "wyłożyć",
    "przekazać",
    "sfinansować",
    "pochłonąć",
}

COMPENSATION_PATTERN = re.compile(
    r"\b(?P<amount>\d+(?:[ .,]\d+)*(?:\s*tys\.)?\s*zł(?:\s*brutto)?)"
    r"(?:\s*(?P<period>miesięcznie|mies\.|rocznie|za rok \d{4}|za miesiąc))?",
    re.IGNORECASE,
)

OFFICE_CANDIDACY_LEMMAS = {"kandydować", "startować", "ubiegać"}

SHORT_PARTY_ALIASES = {"PO", "PSL", "PIS", "PiS", "KO"}
