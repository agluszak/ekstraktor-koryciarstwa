from unittest.mock import MagicMock

import numpy as np
import pytest

from pipeline.config import PipelineConfig
from pipeline.domain_types import DocumentID, EntityID, EntityType
from pipeline.linking import InMemoryEntityLinker
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
def linker(mock_runtime):
    config = PipelineConfig.from_file("config.yaml")
    return InMemoryEntityLinker(config, runtime=mock_runtime)


def test_onet_deduplication(linker):
    # Onet (seeded in _seed_knowledge_graph) should be in the DB already.
    # Its lemmas will be ["onet"]

    doc = ArticleDocument(
        document_id=DocumentID("test-doc"),
        source_url=None,
        raw_html="",
        title="Test Doc",
        publication_date=None,
        cleaned_text="Onetowi Onetem Onet",
        paragraphs=["Onetowi Onetem Onet"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Onetowi",
                normalized_name="Onetowi",
                aliases=[],
                lemmas=["onet"],
            ),
            Entity(
                entity_id=EntityID("e2"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Onetem",
                normalized_name="Onetem",
                aliases=[],
                lemmas=["onet"],
            ),
            Entity(
                entity_id=EntityID("e3"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Onet",
                normalized_name="Onet",
                aliases=[],
                lemmas=["onet"],
            ),
        ],
    )

    linked_doc = linker.run(doc)

    # Should result in 1 entity (Onet) after deduplication
    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Onet"
    # The registry_id should be stable across runs for the same seeded data
    assert linked_doc.entities[0].registry_id is not None


def test_wp_deduplication(linker):
    # WP and Wirtualna Polska share same registry_id in seeding.
    doc = ArticleDocument(
        document_id=DocumentID("test-doc-wp"),
        source_url=None,
        raw_html="",
        title="Test WP",
        publication_date=None,
        cleaned_text="Wirtualna Polska WP",
        paragraphs=["Wirtualna Polska WP"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Wp",
                normalized_name="Wp",
                aliases=[],
                lemmas=["wp"],
            ),
            Entity(
                entity_id=EntityID("e2"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Wirtualna Polska",
                normalized_name="Wirtualna Polska",
                aliases=[],
                lemmas=["wirtualna", "polska"],
            ),
        ],
    )

    linked_doc = linker.run(doc)

    # Should result in 1 entity (Wirtualna Polska)
    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Wirtualna Polska"


def test_component_acronym_alias_does_not_steal_subsidiary_identity(linker):
    doc = ArticleDocument(
        document_id=DocumentID("test-doc-amw-rewita"),
        source_url=None,
        raw_html="",
        title="Test AMW Rewita",
        publication_date=None,
        cleaned_text="AMW Rewita",
        paragraphs=["AMW Rewita"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AMW Rewita",
                normalized_name="AMW Rewita",
                aliases=["AMW"],
            )
        ],
    )

    linked_doc = linker.run(doc)

    assert linked_doc.entities[0].canonical_name == "AMW Rewita"


def test_linker_prefers_shared_naming_policy_for_marshal_office_canonical(linker):
    doc = ArticleDocument(
        document_id=DocumentID("test-doc-marshal-office"),
        source_url=None,
        raw_html="",
        title="Test Marshal Office",
        publication_date=None,
        cleaned_text="Urzędu Marszałkowskiego",
        paragraphs=["Urzędu Marszałkowskiego"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Urzędu Marszałkowskiego",
                normalized_name="Urzędu Marszałkowskiego",
                aliases=["Urząd Marszałkowski"],
            )
        ],
    )

    linked_doc = linker.run(doc)

    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Urząd Marszałkowski"


def test_org_typed_party_alias_does_not_link_to_seeded_party(linker):
    # Generic Organization entities are not silently retyped to configured parties.
    # NER/candidate generation is responsible for creating PoliticalParty entities.
    doc = ArticleDocument(
        document_id=DocumentID("test-doc-pis"),
        source_url=None,
        raw_html="",
        title="Test PiS",
        publication_date=None,
        cleaned_text="Prawa I Sprawiedliwości",
        paragraphs=["Prawa I Sprawiedliwości"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PiS",
                normalized_name="PiS",
                aliases=[],
                lemmas=["pis"],
            ),
            Entity(
                entity_id=EntityID("e2"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="Prawa I Sprawiedliwości",
                normalized_name="Prawa I Sprawiedliwości",
                aliases=[],
                lemmas=["prawo", "i", "sprawiedliwość"],
            ),
        ],
    )

    linked_doc = linker.run(doc)

    assert {(entity.entity_type, entity.canonical_name) for entity in linked_doc.entities} == {
        (EntityType.ORGANIZATION, "PiS"),
        (EntityType.POLITICAL_PARTY, "Prawo i Sprawiedliwość"),
    }


def test_exact_duplicate_canonical_names_are_merged_after_linking(linker):
    doc = ArticleDocument(
        document_id=DocumentID("test-doc-duplicate-org"),
        source_url=None,
        raw_html="",
        title="Test Natura Tour",
        publication_date=None,
        cleaned_text="Natura Tour Natura Tour",
        paragraphs=["Natura Tour Natura Tour"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Natura Tour",
                normalized_name="Natura Tour",
                aliases=[],
            ),
            Entity(
                entity_id=EntityID("e2"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Natura Tour",
                normalized_name="Natura Tour",
                aliases=[],
            ),
        ],
    )

    linked_doc = linker.run(doc)

    assert len(linked_doc.entities) == 1
    assert linked_doc.entities[0].canonical_name == "Natura Tour"


def test_exact_name_party_and_organization_are_not_merged_after_linking(linker):
    doc = ArticleDocument(
        document_id=DocumentID("test-doc-party-org-exact"),
        source_url=None,
        raw_html="",
        title="Test KO Org",
        publication_date=None,
        cleaned_text="Koalicja Obywatelska Koalicja Obywatelska",
        paragraphs=["Koalicja Obywatelska Koalicja Obywatelska"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Koalicja Obywatelska",
                normalized_name="Koalicja Obywatelska",
                aliases=[],
            ),
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="KO",
                normalized_name="KO",
                aliases=[],
            ),
        ],
    )

    linked_doc = linker.run(doc)

    assert {(entity.entity_type, entity.canonical_name) for entity in linked_doc.entities} == {
        (EntityType.ORGANIZATION, "Koalicja Obywatelska"),
        (EntityType.POLITICAL_PARTY, "Koalicja Obywatelska"),
    }


def test_seeded_party_canonical_name_is_refreshed_in_registry(linker):
    # Simulate a stale registry entry (wrong capitalisation) for PiS
    # by injecting it via _upsert_registry before seeding runs.
    registry_id = "politicalparty_registry_1a32b79340a35c3d"
    linker._upsert_registry(
        registry_id,
        EntityType.POLITICAL_PARTY.value,
        "Prawo I Sprawiedliwość",
        {},
        [],
    )
    linker._knowledge_seeded = False

    doc = ArticleDocument(
        document_id=DocumentID("test-doc-refresh-party"),
        source_url=None,
        raw_html="",
        title="Test PiS Refresh",
        publication_date=None,
        cleaned_text="PiS",
        paragraphs=["PiS"],
        entities=[
            Entity(
                entity_id=EntityID("e1"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="PiS",
                normalized_name="PiS",
                aliases=[],
                lemmas=["pis"],
            )
        ],
    )

    linked_doc = linker.run(doc)

    assert linked_doc.entities[0].canonical_name == "Prawo i Sprawiedliwość"
