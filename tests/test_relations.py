from pipeline.config import PipelineConfig
from pipeline.domain_types import CandidateType, EntityType, FactType, RelationType
from pipeline.models import (
    ArticleDocument,
    CoreferenceResult,
    Entity,
    Mention,
    SentenceFragment,
)
from pipeline.relations import PolishRuleBasedRelationExtractor
from pipeline.segmentation import ParagraphSentenceSegmenter


def test_party_aliases_match_whole_tokens_only() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    document = ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Jan Kowalski, polityk PiS, został powołany.",
        paragraphs=["Jan Kowalski, polityk PiS, został powołany."],
        sentences=[
            SentenceFragment(
                text="Jan Kowalski, polityk PiS, został powołany.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=43,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            )
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            )
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )
    party_names = sorted(
        entity.canonical_name
        for entity in extracted.entities
        if entity.entity_type == "PoliticalParty"
    )

    assert party_names == ["Prawo i Sprawiedliwość"]


def test_syndrom_does_not_trigger_fake_syn_relation() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = 'Jest to niestety prosta droga do "syndromu Rybnika" - pisze Dorota Połedniok.'
    document = ArticleDocument(
        document_id="doc-2",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=81,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Dorota Połedniok",
                normalized_name="Dorota Połedniok",
            )
        ],
        mentions=[
            Mention(
                text="Dorota Połedniok",
                normalized_text="Dorota Połedniok",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            )
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert not any(
        relation.relation_type == RelationType.RELATED_TO for relation in extracted.relations
    )


def test_compensation_relation_is_extracted() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Łukasz Bałajewicz zarabia miesięcznie ponad 31 tys. zł brutto jako prezes KZN."
    document = ArticleDocument(
        document_id="doc-3",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=82,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Łukasz Bałajewicz",
                normalized_name="Łukasz Bałajewicz",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="KZN",
                normalized_name="KZN",
            ),
        ],
        mentions=[
            Mention(
                text="Łukasz Bałajewicz",
                normalized_text="Łukasz Bałajewicz",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="KZN",
                normalized_text="KZN",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    compensation_relations = [
        relation
        for relation in extracted.relations
        if relation.relation_type == "RECEIVES_COMPENSATION"
    ]

    assert compensation_relations
    assert compensation_relations[0].attributes["amount_text"] == "31 Tys. Zł Brutto"


def test_party_cannot_become_appointment_destination() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Stanisław Mazur, polityk Lewicy, został prezesem."
    document = ArticleDocument(
        document_id="doc-4",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(text),
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Stanisław Mazur",
                normalized_name="Stanisław Mazur",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Lewicy",
                normalized_name="Lewicy",
            ),
        ],
        mentions=[
            Mention(
                text="Stanisław Mazur",
                normalized_text="Stanisław Mazur",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="Lewicy",
                normalized_text="Lewicy",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert not any(fact.fact_type == FactType.APPOINTMENT for fact in extracted.facts)
    assert not any(
        relation.relation_type == RelationType.APPOINTED_TO for relation in extracted.relations
    )


def test_party_membership_requires_local_structural_support() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Donald Tusk skrytykował PSL za decyzję w sprawie budżetu."
    document = ArticleDocument(
        document_id="doc-5",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(text),
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Donald Tusk",
                normalized_name="Donald Tusk",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PSL",
                normalized_name="PSL",
            ),
        ],
        mentions=[
            Mention(
                text="Donald Tusk",
                normalized_text="Donald Tusk",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert not any(
        fact.fact_type in {"PARTY_MEMBERSHIP", "FORMER_PARTY_MEMBERSHIP"}
        for fact in extracted.facts
    )


def test_initials_and_paragraph_carryover_support_governance_fact() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = (
        "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie. "
        "Teraz awansowała na stanowisko zastępcy prezesa. "
        "Chodzi o Stadninę Koni Iwno."
    )
    document = ArticleDocument(
        document_id="doc-6",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text="A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=62,
            ),
            SentenceFragment(
                text="Teraz awansowała na stanowisko zastępcy prezesa.",
                paragraph_index=0,
                sentence_index=1,
                start_char=63,
                end_char=113,
            ),
            SentenceFragment(
                text="Chodzi o Stadninę Koni Iwno.",
                paragraph_index=0,
                sentence_index=2,
                start_char=114,
                end_char=len(text),
            ),
        ],
        entities=[
            Entity(
                entity_id="person-initial",
                entity_type=EntityType.PERSON,
                canonical_name="A",
                normalized_name="A",
            ),
            Entity(
                entity_id="person-surname",
                entity_type=EntityType.PERSON,
                canonical_name="Góralczyk",
                normalized_name="Góralczyk",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Stadnina Koni Iwno",
                normalized_name="Stadnina Koni Iwno",
            ),
        ],
        mentions=[
            Mention(
                text="A",
                normalized_text="A",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-initial",
            ),
            Mention(
                text="Góralczyk",
                normalized_text="Góralczyk",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-surname",
            ),
            Mention(
                text="Stadninę Koni Iwno",
                normalized_text="Stadnina Koni Iwno",
                mention_type="Organization",
                sentence_index=2,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]

    assert appointments
    assert appointments[0].attributes["role"] == "Zastępca Prezesa"
    assert any(entity.canonical_name == "A. Góralczyk" for entity in extracted.entities)


def test_segmenter_keeps_initials_with_surname() -> None:
    config = PipelineConfig.from_file("config.yaml")
    segmenter = ParagraphSentenceSegmenter(config)
    text = (
        "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie. "
        "Teraz awansowała na stanowisko prezesa."
    )
    document = ArticleDocument(
        document_id="doc-7",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
    )

    segmented = segmenter.run(document)

    assert segmented.sentences[0].text.startswith("A. Góralczyk")


def test_inflected_public_institution_is_typed_from_lemmas() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    institution_surface = "Wojewódzkim Funduszu Ochrony Środowiska i Gospodarki Wodnej w Lublinie"
    institution_normalized = "Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Lublinie"
    text = f"Stanisław Mazur odebrał nominację w {institution_surface}."
    document = ArticleDocument(
        document_id="doc-8",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(text),
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Stanisław Mazur",
                normalized_name="Stanisław Mazur",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name=institution_surface,
                normalized_name=institution_normalized,
            ),
        ],
        mentions=[
            Mention(
                text="Stanisław Mazur",
                normalized_text="Stanisław Mazur",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text=institution_surface,
                normalized_text=institution_normalized,
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert extracted.candidate_graph is not None
    assert any(
        candidate.candidate_type == CandidateType.PUBLIC_INSTITUTION
        for candidate in extracted.candidate_graph.candidates
    )


def test_party_like_organization_can_be_detected_without_alias_lookup() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Jan Kowalski, polityk Koalicji 15 Października, został powołany."
    document = ArticleDocument(
        document_id="doc-9",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(text),
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Koalicji 15 Października",
                normalized_name="Koalicja 15 Października",
            ),
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="Koalicji 15 Października",
                normalized_text="Koalicja 15 Października",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert extracted.candidate_graph is not None
    assert any(
        candidate.candidate_type == CandidateType.POLITICAL_PARTY
        and "Koalicja" in candidate.canonical_name
        for candidate in extracted.candidate_graph.candidates
    )
