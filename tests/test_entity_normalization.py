from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    DocumentID,
    EntityID,
    EntityType,
    FactID,
    FactType,
    TimeScope,
)
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Fact, Mention
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


def test_different_full_people_with_shared_surname_do_not_merge() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-stefaniuk"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Renata Stefaniuk Dariusz Stefaniuk",
        paragraphs=["Renata Stefaniuk Dariusz Stefaniuk"],
        entities=[
            Entity(
                entity_id=EntityID("person-renata"),
                entity_type=EntityType.PERSON,
                canonical_name="Renata Stefaniuk",
                normalized_name="Renata Stefaniuk",
            ),
            Entity(
                entity_id=EntityID("person-dariusz"),
                entity_type=EntityType.PERSON,
                canonical_name="Dariusz Stefaniuk",
                normalized_name="Dariusz Stefaniuk",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert {entity.canonical_name for entity in normalized.entities} == {
        "Renata Stefaniuk",
        "Dariusz Stefaniuk",
    }


def test_inflected_full_person_name_merges_when_given_and_surname_are_compatible() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-dariusz"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Dariusz Stefaniuk Dariusza Stefaniuka",
        paragraphs=["Dariusz Stefaniuk Dariusza Stefaniuka"],
        entities=[
            Entity(
                entity_id=EntityID("person-dariusz"),
                entity_type=EntityType.PERSON,
                canonical_name="Dariusz Stefaniuk",
                normalized_name="Dariusz Stefaniuk",
            ),
            Entity(
                entity_id=EntityID("person-dariusza"),
                entity_type=EntityType.PERSON,
                canonical_name="Dariusza Stefaniuka",
                normalized_name="Dariusza Stefaniuka",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert len(normalized.entities) == 1
    assert normalized.entities[0].canonical_name == "Dariusz Stefaniuk"


def test_ambiguous_surname_only_person_reference_does_not_hard_merge() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-stefaniuk-short"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Renata Stefaniuk Dariusz Stefaniuk Stefaniuk",
        paragraphs=["Renata Stefaniuk Dariusz Stefaniuk Stefaniuk"],
        entities=[
            Entity(
                entity_id=EntityID("person-renata"),
                entity_type=EntityType.PERSON,
                canonical_name="Renata Stefaniuk",
                normalized_name="Renata Stefaniuk",
            ),
            Entity(
                entity_id=EntityID("person-dariusz"),
                entity_type=EntityType.PERSON,
                canonical_name="Dariusz Stefaniuk",
                normalized_name="Dariusz Stefaniuk",
            ),
            Entity(
                entity_id=EntityID("person-short"),
                entity_type=EntityType.PERSON,
                canonical_name="Stefaniuk",
                normalized_name="Stefaniuk",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert {entity.canonical_name for entity in normalized.entities} == {
        "Renata Stefaniuk",
        "Dariusz Stefaniuk",
        "Stefaniuk",
    }


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


def test_person_canonical_prefers_observed_surface_over_broken_lemma_stem() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-observed-surface"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Agnieszka Królikowska Szymon Ogłaza Joanna Pszczółkowska",
        paragraphs=["Agnieszka Królikowska Szymon Ogłaza Joanna Pszczółkowska"],
        entities=[
            Entity(
                entity_id=EntityID("person-agnieszka"),
                entity_type=EntityType.PERSON,
                canonical_name="Agnieszk Królikowski",
                normalized_name="Agnieszk Królikowski",
                aliases=["Agnieszka Królikowska"],
            ),
            Entity(
                entity_id=EntityID("person-szymon"),
                entity_type=EntityType.PERSON,
                canonical_name="Szymon Ogłaz",
                normalized_name="Szymon Ogłaz",
                aliases=["Szymon Ogłaza"],
            ),
            Entity(
                entity_id=EntityID("person-joanna"),
                entity_type=EntityType.PERSON,
                canonical_name="Joann Pszczółkowski",
                normalized_name="Joann Pszczółkowski",
                aliases=["Joanna Pszczółkowska"],
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert {entity.canonical_name for entity in normalized.entities} == {
        "Agnieszka Królikowska",
        "Szymon Ogłaza",
        "Joanna Pszczółkowska",
    }


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


def test_party_and_organization_with_same_name_do_not_deduplicate() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-party-org-separate"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Koalicja Obywatelska",
        paragraphs=["Koalicja Obywatelska"],
        entities=[
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="KO",
                normalized_name="KO",
            ),
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Koalicja Obywatelska",
                normalized_name="Koalicja Obywatelska",
            ),
        ],
    )

    normalized = canonicalizer.run(document)

    assert {(entity.entity_type, entity.canonical_name) for entity in normalized.entities} == {
        (EntityType.POLITICAL_PARTY, "Koalicja Obywatelska"),
        (EntityType.ORGANIZATION, "Koalicja Obywatelska"),
    }


def test_party_membership_fact_object_is_remapped_to_party_entity() -> None:
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-normalize-party-fact"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-21",
        cleaned_text="Karol Wilczyński z Koalicji Obywatelskiej",
        paragraphs=["Karol Wilczyński z Koalicji Obywatelskiej"],
        entities=[
            Entity(
                entity_id=EntityID("person-karol"),
                entity_type=EntityType.PERSON,
                canonical_name="Karol Wilczyński",
                normalized_name="Karol Wilczyński",
            ),
            Entity(
                entity_id=EntityID("org-muzeum"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Muzeum Wsi Kieleckiej",
                normalized_name="Muzeum Wsi Kieleckiej",
            ),
            Entity(
                entity_id=EntityID("party-ko"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="KO",
                normalized_name="KO",
            ),
        ],
        facts=[
            Fact(
                fact_id=FactID("fact-party"),
                fact_type=FactType.PARTY_MEMBERSHIP,
                subject_entity_id=EntityID("person-karol"),
                object_entity_id=EntityID("org-muzeum"),
                value_text="Koalicja Obywatelska",
                value_normalized="Koalicja Obywatelska",
                time_scope=TimeScope.CURRENT,
                event_date="2026-04-21",
                confidence=0.92,
                evidence=EvidenceSpan(text="Karol Wilczyński z Koalicji Obywatelskiej"),
                party="Koalicja Obywatelska",
            )
        ],
    )

    normalized = canonicalizer.run(document)
    entity_by_id = {entity.entity_id: entity for entity in normalized.entities}

    assert normalized.facts[0].object_entity_id is not None
    object_entity = entity_by_id[normalized.facts[0].object_entity_id]
    assert object_entity.entity_type == EntityType.POLITICAL_PARTY
    assert normalized.facts[0].party == "Koalicja Obywatelska"


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
