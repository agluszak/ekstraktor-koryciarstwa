from unittest.mock import MagicMock

import numpy as np
import pytest

from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.linking.service import SQLiteEntityLinker
from pipeline.models import ArticleDocument, Entity


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    # Mock embedding model to return dummy vector
    model = MagicMock()
    model.encode.return_value = np.zeros(384)
    runtime.get_sentence_transformer_model.return_value = model
    return runtime

@pytest.fixture
def linker(tmp_path, mock_runtime):
    db_path = tmp_path / "test_registry.sqlite3"
    config = PipelineConfig.from_file("config.yaml")
    config.registry.sqlite_path = str(db_path)
    # Ensure seeding happens in the test DB
    linker = SQLiteEntityLinker(config, runtime=mock_runtime)
    return linker

def test_onet_deduplication(linker):
    # Onet (seeded in _seed_knowledge_graph) should be in the DB already.
    # Its lemmas will be ["onet"]
    
    doc = ArticleDocument(
        document_id="test-doc",
        source_url=None,
        raw_html="",
        title="Test Doc",
        publication_date=None,
        cleaned_text="Onetowi Onetem Onet",
        paragraphs=["Onetowi Onetem Onet"],
        entities=[
            Entity(
                entity_id="e1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Onetowi",
                normalized_name="Onetowi",
                aliases=[],
                attributes={"lemmas": ["onet"]}
            ),
            Entity(
                entity_id="e2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Onetem",
                normalized_name="Onetem",
                aliases=[],
                attributes={"lemmas": ["onet"]}
            ),
             Entity(
                entity_id="e3",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Onet",
                normalized_name="Onet",
                aliases=[],
                attributes={"lemmas": ["onet"]}
            )
        ]
    )
    
    linked_doc = linker.run(doc)
    
    # Should result in 1 entity (Onet) after deduplication
    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Onet"
    # The registry_id should be stable across runs for the same seeded data
    assert linked_doc.entities[0].attributes["registry_id"] is not None

def test_wp_deduplication(linker):
    # WP and Wirtualna Polska share same registry_id in seeding.
    doc = ArticleDocument(
        document_id="test-doc-wp",
        source_url=None,
        raw_html="",
        title="Test WP",
        publication_date=None,
        cleaned_text="Wirtualna Polska WP",
        paragraphs=["Wirtualna Polska WP"],
        entities=[
            Entity(
                entity_id="e1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Wp",
                normalized_name="Wp",
                aliases=[],
                attributes={"lemmas": ["wp"]}
            ),
            Entity(
                entity_id="e2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Wirtualna Polska",
                normalized_name="Wirtualna Polska",
                aliases=[],
                attributes={"lemmas": ["wirtualna", "polska"]}
            )
        ]
    )
    
    linked_doc = linker.run(doc)
    
    # Should result in 1 entity (Wirtualna Polska)
    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Wirtualna Polska"

def test_pis_deduplication(linker):
    # Prawo I Sprawiedliwość (seeded)
    doc = ArticleDocument(
        document_id="test-doc-pis",
        source_url=None,
        raw_html="",
        title="Test PiS",
        publication_date=None,
        cleaned_text="Prawa I Sprawiedliwości",
        paragraphs=["Prawa I Sprawiedliwości"],
        entities=[
            Entity(
                entity_id="e1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PiS",
                normalized_name="PiS",
                aliases=[],
                attributes={"lemmas": ["pis"]}
            ),
            Entity(
                entity_id="e2",
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="Prawa I Sprawiedliwości",
                normalized_name="Prawa I Sprawiedliwości",
                aliases=[],
                attributes={"lemmas": ["prawo", "i", "sprawiedliwość"]}
            )
        ]
    )
    
    linked_doc = linker.run(doc)
    
    # Should link to the seeded PoliticalParty "Prawo I Sprawiedliwość"
    # and deduplicate correctly.
    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Prawo I Sprawiedliwość"
