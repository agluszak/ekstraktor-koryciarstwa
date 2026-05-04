from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-llm",
        action="store_true",
        default=False,
        help="run tests marked as requiring the LLM test suite",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-llm"):
        return
    skip_llm = pytest.mark.skip(reason="requires --run-llm")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)
