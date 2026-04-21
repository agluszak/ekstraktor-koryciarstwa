import pytest

from pipeline.utils import find_dates


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2023-10-15", ["2023-10-15"]),
        ("2023/10/15", ["2023/10/15"]),
        ("2023.10.15", ["2023.10.15"]),
        ("15.10.2023", ["15.10.2023"]),
        ("1.1.2023", ["1.1.2023"]),
        ("15-10-2023", ["15-10-2023"]),
    ],
)
def test_find_dates_valid_formats(text: str, expected: list[str]) -> None:
    assert find_dates(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "15/10/2023",
        "20231015",
        "23-10-15",
        "1999-10-15",
    ],
)
def test_find_dates_invalid_formats(text: str) -> None:
    assert find_dates(text) == []


def test_find_dates_in_text() -> None:
    assert find_dates("some text 2023-10-15 more text") == ["2023-10-15"]
    assert find_dates("Multiple dates: 2023-01-01 and 15.05.2024.") == ["2023-01-01", "15.05.2024"]
