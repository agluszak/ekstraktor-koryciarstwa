from __future__ import annotations

from pipeline.cli import build_pipeline
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import PipelineInput


def test_roles_extracted_as_first_class_entities():
    config = PipelineConfig.from_file("config.yaml")
    pipeline = build_pipeline(config)

    # Text with a clear role and a person
    content = "Jan Kowalski został prezesem spółki Orlen. To bardzo ważna informacja dla rynku." * 5
    html = (
        f"<html><head><title>Ważna zmiana w Orlenie</title></head>"
        f"<body><article><p>{content}</p></article></body></html>"
    )
    data = PipelineInput(raw_html=html)

    result = pipeline.run(data)

    # Find Position entities
    positions = [e for e in result.entities if e.entity_type == EntityType.POSITION]
    assert len(positions) >= 1
    assert any("prezes" in p.canonical_name.lower() for p in positions)

    # Verify the fact has the position_entity_id
    appointment_facts = [f for f in result.facts if f.fact_type.value == "APPOINTMENT"]
    assert len(appointment_facts) >= 1
    fact = appointment_facts[0]
    assert fact.position_entity_id is not None
    assert "prezes" in fact.role.lower()


def test_roles_clustered_across_sentences():
    config = PipelineConfig.from_file("config.yaml")
    pipeline = build_pipeline(config)

    # Text where the role is mentioned twice
    content = (
        "Jan Kowalski objął stanowisko prezesa. Jako prezes będzie zarządzał spółką Orlen. "
        "To nowa era dla firmy." * 3
    )
    html = (
        f"<html><head><title>Nowy prezes Orlenu</title></head>"
        f"<body><article><p>{content}</p></article></body></html>"
    )
    data = PipelineInput(raw_html=html)

    result = pipeline.run(data)

    # Should have one Position entity with multiple evidence spans
    positions = [e for e in result.entities if e.entity_type == EntityType.POSITION]
    # Filter for the main "prezes" entity
    prezes_entities = [p for p in positions if "prezes" in p.canonical_name.lower()]
    assert len(prezes_entities) == 1
    entity = prezes_entities[0]
    assert len(entity.evidence) >= 2
