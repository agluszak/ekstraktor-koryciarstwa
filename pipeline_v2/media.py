from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MediaOutletAlias:
    text: str
    case_sensitive: bool = False


MEDIA_OUTLET_ALIASES = frozenset(
    {
        MediaOutletAlias("Dziennik"),
        MediaOutletAlias("Gazeta", case_sensitive=True),
        MediaOutletAlias("Gazeta Wyborcza"),
        MediaOutletAlias("Niezależna", case_sensitive=True),
        MediaOutletAlias("Niezależna.pl", case_sensitive=True),
        MediaOutletAlias("Onet"),
        MediaOutletAlias("PAP"),
        MediaOutletAlias("Polsat"),
        MediaOutletAlias("Press"),
        MediaOutletAlias("Radio"),
        MediaOutletAlias("Radio Zet"),
        MediaOutletAlias("TVN"),
        MediaOutletAlias("TVN24"),
        MediaOutletAlias("TVN Warszawa"),
        MediaOutletAlias("TVP"),
        MediaOutletAlias("Wirtualna Polska"),
        MediaOutletAlias("WP"),
        MediaOutletAlias("Business Insider"),
        MediaOutletAlias("naTemat"),
        MediaOutletAlias("Gazeta Krakowska"),
        MediaOutletAlias("Polsat Interwencja"),
        MediaOutletAlias("Wprost"),
        MediaOutletAlias("Rzeczpospolita"),
        MediaOutletAlias("Super Express"),
        MediaOutletAlias("Fakt"),
    }
)

MEDIA_OUTLET_LEMMAS = frozenset(
    {
        "dziennik",
        "onet",
        "pap",
        "polsat",
        "portal",
        "radio",
        "telewizja",
        "tvn",
        "tvn24",
        "tvp",
        "tygodnik",
        "wp",
    }
)

_INFLECTIONAL_SUFFIXES = frozenset(
    {
        "a",
        "e",
        "em",
        "ie",
        "owi",
        "u",
    }
)


def is_media_outlet_name(name: str | None) -> bool:
    if name is None:
        return False
    return any(_alias_matches(name, alias) for alias in MEDIA_OUTLET_ALIASES)


def media_outlet_lemmas() -> frozenset[str]:
    return MEDIA_OUTLET_LEMMAS


def _alias_matches(name: str, alias: MediaOutletAlias) -> bool:
    if alias.case_sensitive:
        return _contains_normalized_phrase(
            _normalize_spacing(name),
            _normalize_spacing(alias.text),
        )
    return _contains_normalized_phrase(
        _normalize_spacing(name).casefold(),
        _normalize_spacing(alias.text).casefold(),
    )


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    text_tokens = text.split()
    phrase_tokens = phrase.split()
    if not phrase_tokens or len(phrase_tokens) > len(text_tokens):
        return False
    return any(
        _tokens_match(
            tuple(text_tokens[index : index + len(phrase_tokens)]),
            tuple(phrase_tokens),
        )
        for index in range(len(text_tokens) - len(phrase_tokens) + 1)
    )


def _normalize_spacing(text: str) -> str:
    return " ".join(text.replace(".", " ").split())


def _tokens_match(text_tokens: tuple[str, ...], phrase_tokens: tuple[str, ...]) -> bool:
    if len(text_tokens) != len(phrase_tokens):
        return False
    return all(
        _token_matches_with_inflection(text_token, phrase_token)
        for text_token, phrase_token in zip(text_tokens, phrase_tokens, strict=True)
    )


def _token_matches_with_inflection(text_token: str, phrase_token: str) -> bool:
    if text_token == phrase_token:
        return True
    suffix = text_token[len(phrase_token) :]
    if not text_token.startswith(phrase_token) or not suffix:
        return False
    return suffix in _INFLECTIONAL_SUFFIXES
