MEDIA_OUTLET_TERMS = frozenset(
    {
        "dziennik",
        "gazeta",
        "onet",
        "pap",
        "polsat",
        "press",
        "radio",
        "tvn",
        "tvn24",
        "wirtualna polska",
        "wp",
    }
)


def is_media_outlet_name(name: str | None) -> bool:
    if name is None:
        return False
    normalized = name.casefold()
    return any(term in normalized for term in MEDIA_OUTLET_TERMS)
