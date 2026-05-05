from __future__ import annotations

import pytest

from pipeline.cli import build_pipeline
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import PipelineInput


def test_custom_entities_extracted():
    config = PipelineConfig.from_file("config.yaml")
    pipeline = build_pipeline(config)
    
    # Text with money, event, and law references + keywords to pass filter
    text = (
        "Jan Kowalski z rady nadzorczej poinformował o zmianach. "
        "Rada Miejska podjęła uchwałę w sprawie budżetu spółki miejskiej. "
        "W ramach konkursu na dyrektora przyznano nagrodę w wysokości 5000 zł brutto. "
        "Ustawa o finansach publicznych reguluje te kwestie. "
        "To kolesiostwo w czystej postaci i skandaliczne rozdawanie posad."
    )
    # Substantial HTML for Trafilatura - use spaces for repetition!
    html = f"<html><head><title>Budżet i Konkursy w Spółce</title></head><body><article><p>{(text + ' ') * 3}</p></article></body></html>"
    data = PipelineInput(raw_html=html)
    
    result = pipeline.run(data)
    
    # Verify relevance passed
    assert result.relevance.is_relevant
    
    # Verify MONEY
    money_entities = [e for e in result.entities if e.entity_type == EntityType.MONEY]
    assert len(money_entities) >= 1
    assert any("5000 zł" in m.canonical_name.lower() for m in money_entities)
    
    # Verify EVENT
    event_entities = [e for e in result.entities if e.entity_type == EntityType.EVENT]
    assert len(event_entities) >= 1
    assert any("konkurs" in e.canonical_name.lower() for e in event_entities)
    
    # Verify LAW
    law_entities = [e for e in result.entities if e.entity_type == EntityType.LAW]
    assert len(law_entities) >= 2
    assert any("uchwał" in l.canonical_name.lower() for l in law_entities)
    assert any("ustaw" in l.canonical_name.lower() for l in law_entities)

def test_event_law_phrase_extraction():
    config = PipelineConfig.from_file("config.yaml")
    pipeline = build_pipeline(config)
    
    text = "Jan Kowalski ogłosił otwarty konkurs na stanowisko prezesa w spółce miejskiej. To skandal i kolesiostwo."
    # Use spaces for repetition!
    html = f"<html><head><title>Konkurs ogłoszony w spółce</title></head><body><article><p>{(text + ' ') * 5}</p></article></body></html>"
    data = PipelineInput(raw_html=html)
    
    result = pipeline.run(data)
    assert result.relevance.is_relevant
    
    event_entities = [e for e in result.entities if e.entity_type == EntityType.EVENT]
    assert len(event_entities) >= 1
    # Check if phrase is extracted (modifiers like "otwarty" should be included)
    assert any("otwarty" in e.canonical_name.lower() and "konkurs" in e.canonical_name.lower() for e in event_entities)
