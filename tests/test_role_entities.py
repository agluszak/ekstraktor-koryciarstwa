from __future__ import annotations

from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, FactType
from pipeline.fact_extractor import PolishFactExtractor
from pipeline.roles import PolishPositionExtractor
from tests.test_relations import (
    prepare_for_relation_extraction,
    prepared_single_clause_document,
    word,
)


def test_roles_extracted_as_first_class_entities() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Jan Kowalski został prezesem spółki Orlen."
    document = prepared_single_clause_document(
        document_id="doc-role-first-class",
        text=text,
        entities=[
            ("Jan Kowalski", EntityType.PERSON, "Jan Kowalski"),
            ("Orlen", EntityType.ORGANIZATION, "Orlen"),
        ],
        parsed_words=[
            word(1, "Jan", "Jan", 0, head=2, deprel="flat", upos="PROPN"),
            word(2, "Kowalski", "Kowalski", 4, head=4, deprel="nsubj", upos="PROPN"),
            word(3, "został", "zostać", 13, head=4, deprel="aux", upos="AUX"),
            word(4, "prezesem", "prezes", 20, upos="NOUN"),
            word(5, "spółki", "spółka", 28, head=4, deprel="nmod"),
            word(6, "Orlen", "Orlen", 35, head=5, deprel="flat", upos="PROPN"),
        ],
    )
    document = PolishPositionExtractor(config).run(document)
    document = prepare_for_relation_extraction(config, document)
    result = PolishFactExtractor(config).run(document)

    positions = [e for e in result.resolved_entities if e.entity_type == EntityType.POSITION]
    assert len(positions) >= 1
    assert any("prezes" in p.canonical_name.lower() for p in positions)

    appointment_facts = [f for f in result.facts if f.fact_type == FactType.APPOINTMENT]
    assert len(appointment_facts) >= 1
    fact = appointment_facts[0]
    assert fact.position_entity_id is not None
    assert fact.role is not None
    assert "prezes" in fact.role.lower()


def test_roles_clustered_across_mentions() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Jan Kowalski objął stanowisko prezesa i jako prezes zarządza spółką Orlen."
    document = prepared_single_clause_document(
        document_id="doc-role-multi-mention",
        text=text,
        entities=[
            ("Jan Kowalski", EntityType.PERSON, "Jan Kowalski"),
            ("Orlen", EntityType.ORGANIZATION, "Orlen"),
        ],
        parsed_words=[
            word(1, "Jan", "Jan", 0, head=2, deprel="flat", upos="PROPN"),
            word(2, "Kowalski", "Kowalski", 4, head=3, deprel="nsubj", upos="PROPN"),
            word(3, "objął", "objąć", 13, upos="VERB"),
            word(4, "stanowisko", "stanowisko", 18, head=3, deprel="obj"),
            word(5, "prezesa", "prezes", 29, head=4, deprel="nmod"),
            word(6, "i", "i", 37, head=3, deprel="cc", upos="CCONJ"),
            word(7, "jako", "jako", 39, head=8, deprel="case", upos="ADP"),
            word(8, "prezes", "prezes", 44, head=3, deprel="obl"),
            word(9, "zarządza", "zarządzać", 51, head=3, deprel="conj", upos="VERB"),
            word(10, "spółką", "spółka", 60, head=9, deprel="obj"),
            word(11, "Orlen", "Orlen", 67, head=10, deprel="flat", upos="PROPN"),
        ],
    )
    document = PolishPositionExtractor(config).run(document)
    document = prepare_for_relation_extraction(config, document)
    result = PolishFactExtractor(config).run(document)

    positions = [e for e in result.resolved_entities if e.entity_type == EntityType.POSITION]
    prezes_entities = [p for p in positions if "prezes" in p.canonical_name.lower()]
    assert len(prezes_entities) == 1
    assert len(prezes_entities[0].mentions) >= 2
