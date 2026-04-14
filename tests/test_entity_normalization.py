from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, Entity, Mention
from pipeline.normalization import DocumentEntityCanonicalizer


def test_party_aliases_expand_to_canonical_name() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id="doc-normalize-party",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="PSL",
        paragraphs=["PSL"],
        entities=[
            Entity(
                entity_id="party-1",
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="PSL",
                normalized_name="PSL",
                aliases=[],
            )
        ],
        mentions=[
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type=EntityType.POLITICAL_PARTY,
                sentence_index=0,
                entity_id="party-1",
            )
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name == "Polskie Stronnictwo Ludowe"
    assert normalized.mentions[0].normalized_text == "Polskie Stronnictwo Ludowe"


def test_wfosigw_acronym_and_full_name_are_deduplicated() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    full_surface = "Wojewódzkim Funduszu Ochrony Środowiska i Gospodarki Wodnej w Lublinie"
    full_normalized = "Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Lublinie"
    document = ArticleDocument(
        document_id="doc-normalize-org",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="WFOŚiGW",
        paragraphs=["WFOŚiGW"],
        entities=[
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="WFOŚiGW",
                normalized_name="WFOŚiGW",
                aliases=[],
                attributes={"lemmas": ["wfośigw"]},
            ),
            Entity(
                entity_id="org-2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name=full_surface,
                normalized_name=full_normalized,
                aliases=[],
                attributes={
                    "lemmas": [
                        "wojewódzki",
                        "fundusz",
                        "ochrona",
                        "środowisko",
                        "gospodarka",
                        "wodny",
                        "lublin",
                    ]
                },
            ),
        ],
        mentions=[
            Mention(
                text="WFOŚiGW",
                normalized_text="WFOŚiGW",
                mention_type=EntityType.ORGANIZATION,
                sentence_index=0,
                entity_id="org-1",
            ),
            Mention(
                text=full_surface,
                normalized_text=full_normalized,
                mention_type=EntityType.ORGANIZATION,
                sentence_index=0,
                entity_id="org-2",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name.startswith("Wojewódzk")
    assert normalized.mentions[0].entity_id == normalized.mentions[1].entity_id


def test_duplicate_organization_aliases_collapse_to_one_entity() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id="doc-normalize-natura",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Natura Tour",
        paragraphs=["Natura Tour"],
        entities=[
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Natura Tour",
                normalized_name="Natura Tour",
            ),
            Entity(
                entity_id="org-2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Natura Tour",
                normalized_name="Natura Tour",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name == "Natura Tour"


def test_institution_aliases_expand_and_retype_to_public_institution() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id="doc-normalize-institution",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="MON i AMW",
        paragraphs=["MON i AMW"],
        entities=[
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="MON",
                normalized_name="MON",
            ),
            Entity(
                entity_id="org-2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AMW",
                normalized_name="AMW",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    entities = {entity.canonical_name: entity.entity_type for entity in normalized.entities}
    assert entities["Ministerstwo Obrony Narodowej"] == EntityType.PUBLIC_INSTITUTION
    assert entities["Agencja Mienia Wojskowego"] == EntityType.PUBLIC_INSTITUTION


def test_inflected_full_person_name_variants_merge_to_nominative_canonical() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id="doc-normalize-person",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Kosiniak-Kamysz",
        paragraphs=["Kosiniak-Kamysz"],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Władysława Kosiniaka-Kamysza",
                normalized_name="Władysława Kosiniaka-Kamysza",
            ),
            Entity(
                entity_id="person-2",
                entity_type=EntityType.PERSON,
                canonical_name="Władysław Kosiniak-Kamysz",
                normalized_name="Władysław Kosiniak-Kamysz",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name == "Władysław Kosiniak-Kamysz"
