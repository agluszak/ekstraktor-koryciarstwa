import pytest

from pipeline.utils import normalize_party_name


@pytest.mark.parametrize(
    "input_name, expected",
    [
        # Standard casing and connectors
        ("Prawo i Sprawiedliwość", "Prawo i Sprawiedliwość"),
        ("prawo i sprawiedliwość", "Prawo i Sprawiedliwość"),
        ("Platforma Obywatelska", "Platforma Obywatelska"),
        ("koalicja obywatelska", "Koalicja Obywatelska"),

        # Acronyms
        ("PiS", "PiS"),
        ("PO", "PO"),
        ("PSL", "PSL"),
        ("SLD-UP", "SLD-UP"),

        # Whitespace stripping and compacting
        ("  Prawo   i  Sprawiedliwość  ", "Prawo i Sprawiedliwość"),
        ("\tPlatforma\nObywatelska\t", "Platforma Obywatelska"),

        # Punctuation stripping
        ("Koalicja Obywatelska (KO)", "Koalicja Obywatelska KO"),
        ("Polska 2050 Szymona Hołowni", "Polska 2050 Szymona Hołowni"),
        ("Kukiz'15", "Kukiz'15"),

        # Edge cases
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_party_name(input_name: str, expected: str) -> None:
    assert normalize_party_name(input_name) == expected
