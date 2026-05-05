from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from pipeline.config import PipelineConfig
from pipeline.domain_types import OrganizationKind
from pipeline.relations.org_typing import OrganizationMentionClassifier
from pipeline.runtime import PipelineRuntime


@pytest.fixture
def config():
    return PipelineConfig.from_file("config.yaml")


@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=PipelineRuntime)

    # mock encode_text
    def encode_text(text):
        if any(w in text.lower() for w in ["ministerstwo", "urząd", "agencja"]):
            return np.array([1.0, 0.0, 0.0])
        if any(w in text.lower() for w in ["spółka", "holding", "biznes"]):
            return np.array([0.0, 1.0, 0.0])
        # Neutral
        return np.array([0.5, 0.5, 0.0])

    runtime.encode_text.side_effect = encode_text
    return runtime


def test_org_classifier_semantic_public(config, mock_runtime):
    classifier = OrganizationMentionClassifier(config, runtime=mock_runtime)

    # "Główny Inspektorat" is strong lexical public, so it should be PUBLIC
    res = classifier.classify(
        surface_text="Główny Inspektorat",
        normalized_text="Główny Inspektorat",
        parsed_words=[],
        start_char=0,
        end_char=18,
    )
    assert res.organization_kind == OrganizationKind.PUBLIC_INSTITUTION

    # "Nieznany Resort" - "Resort" is not in heads, but semantically close to public representatives
    # Let's mock "Nieznany Resort" to be close to PUBLIC
    def encode_text_resort(text):
        if "nieznany resort" in text.lower():
            return np.array([0.9, 0.1, 0.0])  # Close to [1, 0, 0]
        if any(w in text.lower() for w in ["ministerstwo", "urząd"]):
            return np.array([1.0, 0.0, 0.0])
        if any(w in text.lower() for w in ["spółka", "holding"]):
            return np.array([0.0, 1.0, 0.0])
        return np.array([0.5, 0.5, 0.0])

    mock_runtime.encode_text.side_effect = encode_text_resort

    res = classifier.classify(
        surface_text="Nieznany Resort",
        normalized_text="Nieznany Resort",
        parsed_words=[],
        start_char=0,
        end_char=15,
    )
    assert res.organization_kind == OrganizationKind.PUBLIC_INSTITUTION


def test_org_classifier_semantic_company(config, mock_runtime):
    classifier = OrganizationMentionClassifier(config, runtime=mock_runtime)

    # "Globalny Gigant" - No lexical clues, but semantically close to company representatives
    def encode_text_gigant(text):
        if "globalny gigant" in text.lower():
            return np.array([0.1, 0.9, 0.0])  # Close to [0, 1, 0]
        if any(w in text.lower() for w in ["ministerstwo", "urząd"]):
            return np.array([1.0, 0.0, 0.0])
        if any(w in text.lower() for w in ["spółka", "holding"]):
            return np.array([0.0, 1.0, 0.0])
        return np.array([0.5, 0.5, 0.0])

    mock_runtime.encode_text.side_effect = encode_text_gigant

    res = classifier.classify(
        surface_text="Globalny Gigant",
        normalized_text="Globalny Gigant",
        parsed_words=[],
        start_char=0,
        end_char=15,
    )
    assert res.organization_kind == OrganizationKind.COMPANY
