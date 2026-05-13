from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from pipeline.clustering import PolishEntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    DocumentID,
    EntityID,
    EntityResolutionReason,
    EntityResolutionStatus,
    EntityType,
)
from pipeline.extraction_context import ExtractionContext
from pipeline.models import ArticleDocument, Entity, EvidenceSpan
from pipeline.runtime import PipelineRuntime


@pytest.fixture
def config():
    return PipelineConfig.from_file("config.yaml")


@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=PipelineRuntime)
    model = MagicMock()
    runtime.get_sentence_transformer_model.return_value = model
    return runtime


def test_polish_entity_clusterer_emits_hypothesis_for_semantic_similarity(config, mock_runtime):
    # Two organizations that are semantically similar but rule-based canonicalizer
    # might not merge them (no shared acronym, no exact match).
    org1 = Entity(
        entity_id=EntityID("org-1"),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Narodowy Fundusz Zdrowia",
        normalized_name="Narodowy Fundusz Zdrowia",
        evidence=[EvidenceSpan(text="Narodowy Fundusz Zdrowia", sentence_index=0)],
    )
    org2 = Entity(
        entity_id=EntityID("org-2"),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Centralna Instytucja Medyczna",
        normalized_name="Centralna Instytucja Medyczna",
        evidence=[EvidenceSpan(text="Centralna Instytucja Medyczna", sentence_index=1)],
    )

    # Mock embeddings to be very similar
    def mock_encode(text, **kwargs):
        if "Zdrowia" in text or "Medyczna" in text:
            return np.array([1.0, 0.0, 0.0])
        else:
            return np.array([0.0, 1.0, 0.0])

    mock_runtime.encode_text.side_effect = mock_encode

    clusterer = PolishEntityClusterer(config, runtime=mock_runtime)
    doc = ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="...",
        paragraphs=["..."],
        entities=[org1, org2],
        mentions=[],
    )

    result = clusterer.run(doc)

    assert len(result.clusters) == 2
    assert len(result.entity_resolution_hypotheses) == 1
    hypothesis = result.entity_resolution_hypotheses[0]
    assert hypothesis.status == EntityResolutionStatus.PROBABLE
    assert hypothesis.reason == EntityResolutionReason.SEMANTIC_ORGANIZATION_SIMILARITY
    assert {hypothesis.left_entity_id, hypothesis.right_entity_id} == {"org-1", "org-2"}


def test_polish_entity_clusterer_does_not_merge_dissimilar_orgs(config, mock_runtime):
    org1 = Entity(
        entity_id=EntityID("org-1"),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Orlen",
        normalized_name="Orlen",
        evidence=[EvidenceSpan(text="Orlen", sentence_index=0)],
    )
    org2 = Entity(
        entity_id=EntityID("org-2"),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="KGHM",
        normalized_name="KGHM",
        evidence=[EvidenceSpan(text="KGHM", sentence_index=1)],
    )

    # Mock embeddings to be dissimilar
    def mock_encode(text, **kwargs):
        if "Orlen" in text:
            return np.array([1.0, 0.0, 0.0])
        else:
            return np.array([0.0, 1.0, 0.0])

    mock_runtime.encode_text.side_effect = mock_encode

    clusterer = PolishEntityClusterer(config, runtime=mock_runtime)
    doc = ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="...",
        paragraphs=["..."],
        entities=[org1, org2],
        mentions=[],
    )

    result = clusterer.run(doc)

    # Should have 2 clusters
    assert len(result.clusters) == 2
    assert result.entity_resolution_hypotheses == []


def test_polish_entity_clusterer_merges_exact_acronym_match(config):
    org1 = Entity(
        entity_id=EntityID("org-1"),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Krajowy Ośrodek Wsparcia Rolnictwa",
        normalized_name="Krajowy Ośrodek Wsparcia Rolnictwa",
        aliases=["KOWR"],
        evidence=[EvidenceSpan(text="Krajowy Ośrodek Wsparcia Rolnictwa", sentence_index=0)],
    )
    org2 = Entity(
        entity_id=EntityID("org-2"),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="KOWR",
        normalized_name="KOWR",
        evidence=[EvidenceSpan(text="KOWR", sentence_index=1)],
    )

    clusterer = PolishEntityClusterer(config)
    doc = ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="...",
        paragraphs=["..."],
        entities=[org1, org2],
        mentions=[],
    )

    result = clusterer.run(doc)

    assert len(result.clusters) == 1
    assert (
        ExtractionContext.build(result).canonical_name_for_cluster(result.clusters[0])
        == "Krajowy Ośrodek Wsparcia Rolnictwa"
    )
