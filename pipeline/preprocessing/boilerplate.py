from __future__ import annotations

import re

GENERIC_JUNK_PATTERNS = (
    re.compile(r"^::addons", re.IGNORECASE),
    re.compile(r"^płatny dostęp do treści$", re.IGNORECASE),
    re.compile(r"^ten artykuł przeczytasz", re.IGNORECASE),
    re.compile(r"^komentarze$", re.IGNORECASE),
    re.compile(r"^reklama$", re.IGNORECASE),
    re.compile(r"^twoje zdanie jest ważne", re.IGNORECASE),
    re.compile(r"^skorzystaj z subskrypcji", re.IGNORECASE),
    re.compile(r"^wiadomości pogodowe$", re.IGNORECASE),
    re.compile(r"^popularne osoby$", re.IGNORECASE),
    re.compile(r"^organizacje$", re.IGNORECASE),
    re.compile(r"^inne tematy$", re.IGNORECASE),
    re.compile(r"^pogoda$", re.IGNORECASE),
    re.compile(r"^z tego artykułu dowiesz się:?$", re.IGNORECASE),
)

UI_NAVIGATION_MARKERS = frozenset(
    {
        "strona główna",
        "zobacz wszystkie",
        "więcej informacji znajdziesz",
        "logowanie",
        "zaloguj",
        "kup subskrypcję",
        "subskrypcj",
        "premium",
        "serwisy partnerskie",
        "pogoda",
        "program tv",
        "czytaj także",
        "przeczytaj także",
        "powiązane artykuły",
        "zobacz również",
        "następny artykuł",
        "poprzedni artykuł",
    }
)

UI_CATEGORY_MARKERS = frozenset(
    {
        "popularne osoby",
        "organizacje",
        "inne tematy",
        "wiadomości pogodowe",
        "komentarze",
        "reklama",
    }
)


def is_boilerplate_paragraph(text: str) -> bool:
    normalized = text.strip()
    lowered = normalized.casefold()
    if any(pattern.search(normalized) for pattern in GENERIC_JUNK_PATTERNS):
        return True

    marker_hits = sum(marker in lowered for marker in UI_NAVIGATION_MARKERS)
    category_hits = sum(marker in lowered for marker in UI_CATEGORY_MARKERS)
    short_ui_block = len(normalized) <= 120 and marker_hits > 0
    dense_ui_block = marker_hits >= 2 or category_hits >= 2
    title_like_menu = (
        normalized == normalized.title() and len(normalized.split()) <= 4 and category_hits > 0
    )

    return short_ui_block or dense_ui_block or title_like_menu
