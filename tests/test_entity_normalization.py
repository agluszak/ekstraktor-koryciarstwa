from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    DocumentID,
    EntityID,
    EntityType,
)
from pipeline.models import ArticleDocument, Entity, Mention
from pipeline.normalization import DocumentEntityCanonicalizer


def test_party_aliases_expand_to_canonical_name() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-party"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="PSL",
        paragraphs=["PSL"],
        entities=[
            Entity(
                entity_id=EntityID("party-1"),
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
                entity_id=EntityID("party-1"),
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
        document_id=DocumentID("doc-normalize-org"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="WFOŚiGW",
        paragraphs=["WFOŚiGW"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="WFOŚiGW",
                normalized_name="WFOŚiGW",
                aliases=[],
                lemmas=["wfośigw"],
            ),
            Entity(
                entity_id=EntityID("org-2"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name=full_surface,
                normalized_name=full_normalized,
                aliases=[],
                lemmas=[
                    "wojewódzki",
                    "fundusz",
                    "ochrona",
                    "środowisko",
                    "gospodarka",
                    "wodny",
                    "lublin",
                ],
            ),
        ],
        mentions=[
            Mention(
                text="WFOŚiGW",
                normalized_text="WFOŚiGW",
                mention_type=EntityType.ORGANIZATION,
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
            Mention(
                text=full_surface,
                normalized_text=full_normalized,
                mention_type=EntityType.ORGANIZATION,
                sentence_index=0,
                entity_id=EntityID("org-2"),
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
        document_id=DocumentID("doc-normalize-natura"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Natura Tour",
        paragraphs=["Natura Tour"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Natura Tour",
                normalized_name="Natura Tour",
            ),
            Entity(
                entity_id=EntityID("org-2"),
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
        document_id=DocumentID("doc-normalize-institution"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="MON i AMW",
        paragraphs=["MON i AMW"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="MON",
                normalized_name="MON",
            ),
            Entity(
                entity_id=EntityID("org-2"),
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
        document_id=DocumentID("doc-normalize-person"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Kosiniak-Kamysz",
        paragraphs=["Kosiniak-Kamysz"],
        entities=[
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Władysława Kosiniaka-Kamysza",
                normalized_name="Władysława Kosiniaka-Kamysza",
            ),
            Entity(
                entity_id=EntityID("person-2"),
                entity_type=EntityType.PERSON,
                canonical_name="Władysław Kosiniak-Kamysz",
                normalized_name="Władysław Kosiniak-Kamysz",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name == "Władysław Kosiniak-Kamysz"


def test_single_token_inflected_person_variants_merge_into_full_name_cluster() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-person-short"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Marek Rząsowski",
        paragraphs=["Marek Rząsowski"],
        entities=[
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marek Rząsowski",
                normalized_name="Marek Rząsowski",
            ),
            Entity(
                entity_id=EntityID("person-2"),
                entity_type=EntityType.PERSON,
                canonical_name="Rząsowskiego",
                normalized_name="Rząsowskiego",
            ),
            Entity(
                entity_id=EntityID("person-3"),
                entity_type=EntityType.PERSON,
                canonical_name="Marku",
                normalized_name="Marku",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name == "Marek Rząsowski"


def test_organization_canonical_prefers_acronym_preserving_alias() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-amw-rewita"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="AMW Rewita",
        paragraphs=["AMW Rewita"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Amw Rewita",
                normalized_name="Amw Rewita",
                aliases=["AMW Rewita"],
            )
        ],
    )

    normalized = canonicalizer.run(document)

    assert normalized.entities[0].canonical_name == "AMW Rewita"


def test_inflected_short_organization_prefers_observed_nominative_alias() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-totalizator"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Totalizatorze Sportowym",
        paragraphs=["Totalizatorze Sportowym"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Totalizatorze Sportowym",
                normalized_name="Totalizatorze Sportowym",
                aliases=["Totalizator Sportowy"],
                lemmas=["totalizator", "sportowy"],
            )
        ],
    )

    normalized = canonicalizer.run(document)

    assert normalized.entities[0].canonical_name == "Totalizator Sportowy"


def test_inflected_party_name_maps_to_configured_canonical_name() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-pis-inflected"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Prawa i Sprawiedliwości",
        paragraphs=["Prawa i Sprawiedliwości"],
        entities=[
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="Prawa i Sprawiedliwości",
                normalized_name="Prawa i Sprawiedliwości",
            )
        ],
    )

    normalized = canonicalizer.run(document)

    assert normalized.entities[0].canonical_name == "Prawo i Sprawiedliwość"


def test_noisy_canonical_candidate_loses_to_clean_alias() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-noisy-person"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Sławomir Czwałga",
        paragraphs=["Sławomir Czwałga"],
        entities=[
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Sławomir Czwalgamateriały",
                normalized_name="Sławomir Czwalgamateriały",
                aliases=["Sławomir Czwałga"],
            )
        ],
    )

    normalized = canonicalizer.run(document)

    assert normalized.entities[0].canonical_name == "Sławomir Czwałga"


def test_multiline_organization_block_does_not_become_joined_canonical_name() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-multiline-org"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Fundacja Lux Veritatis",
        paragraphs=["Fundacja Lux Veritatis"],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Fundacja Lux Veritatis",
                normalized_name="Fundacja Lux Veritatis",
                aliases=["Lux Veritatis"],
                lemmas=["fundacja", "lux", "veritatis"],
            ),
            Entity(
                entity_id=EntityID("org-2"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name=(
                    "Ministerstwo Kultury i Dziedzictwa Narodowego\nFundacja Lux Veritatis\n"
                ),
                normalized_name=(
                    "Ministerstwo Kultury i Dziedzictwa Narodowego\nFundacja Lux Veritatis\n"
                ),
                lemmas=[
                    "ministerstwo",
                    "kultura",
                    "dziedzictwo",
                    "narodowy",
                    "fundacja",
                    "lux",
                    "veritatis",
                ],
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    names = {entity.canonical_name for entity in normalized.entities}
    aliases = {alias for entity in normalized.entities for alias in entity.aliases}
    assert "Fundacja Lux Veritatis" in names
    assert "Ministerstwo Kultury i Dziedzictwa Narodowego" in names
    assert "Ministerstwo Kultury i Dziedzictwa Narodowego Fundacja Lux Veritatis" not in names
    assert "Ministerstwo Kultury i Dziedzictwa Narodowego Fundacja Lux Veritatis" not in aliases
