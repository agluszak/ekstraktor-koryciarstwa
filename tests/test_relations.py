from dataclasses import dataclass

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
from pipeline.runtime import PipelineRuntime
from pipeline.segmentation import ParagraphSentenceSegmenter


@dataclass
class FakeWord:
    id: int
    text: str
    lemma: str
    upos: str
    head: int
    deprel: str
    start_char: int
    end_char: int


@dataclass
class FakeSentence:
    words: list[FakeWord]


@dataclass
class FakeDoc:
    sentences: list[FakeSentence]


class CountingSyntaxPipeline:
    def __init__(self, doc: FakeDoc) -> None:
        self.doc = doc
        self.call_count = 0

    def __call__(self, text: str) -> FakeDoc:
        _ = text
        self.call_count += 1
        return self.doc


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


def test_party_alias_inside_non_party_organization_does_not_retype_whole_entity() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Marcin Horyń złożył rezygnację ze stanowiska prezesa PSL Fundacji Rozwoju."
    document = ArticleDocument(
        document_id="doc-9b",
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
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PSL Fundacji Rozwoju",
                normalized_name="PSL Fundacji Rozwoju",
            ),
        ],
        mentions=[
            Mention(
                text="Marcin Horyń",
                normalized_text="Marcin Horyń",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="PSL Fundacji Rozwoju",
                normalized_text="PSL Fundacji Rozwoju",
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

    assert any(
        entity.canonical_name == "PSL Fundacji Rozwoju"
        and entity.entity_type == EntityType.ORGANIZATION
        for entity in extracted.entities
    )


def test_institution_alias_candidate_is_typed_as_public_institution() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Marcin Horyń został dyrektorem AMW. MON sprawuje nadzór nad agencją."
    document = ArticleDocument(
        document_id="doc-10a",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text="Marcin Horyń został dyrektorem AMW.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=35,
            ),
            SentenceFragment(
                text="MON sprawuje nadzór nad agencją.",
                paragraph_index=0,
                sentence_index=1,
                start_char=36,
                end_char=len(text),
            ),
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AMW",
                normalized_name="AMW",
            ),
            Entity(
                entity_id="org-2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="MON",
                normalized_name="MON",
            ),
        ],
        mentions=[
            Mention(
                text="Marcin Horyń",
                normalized_text="Marcin Horyń",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="AMW",
                normalized_text="AMW",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
            Mention(
                text="MON",
                normalized_text="MON",
                mention_type="Organization",
                sentence_index=1,
                entity_id="org-2",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert extracted.candidate_graph is not None
    public_institutions = {
        candidate.canonical_name
        for candidate in extracted.candidate_graph.candidates
        if candidate.candidate_type == CandidateType.PUBLIC_INSTITUTION
    }
    assert "Agencja Mienia Wojskowego" in public_institutions
    assert "Ministerstwo Obrony Narodowej" in public_institutions


def test_object_appointee_sentence_extracts_appointee_not_appointing_authority() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = (
        "Marcin Horyń złożył rezygnację. "
        "Premier Donald Tusk powołuje go na stanowisko dyrektora AMW."
    )
    document = ArticleDocument(
        document_id="doc-10b",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text="Marcin Horyń złożył rezygnację.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=31,
            ),
            SentenceFragment(
                text="Premier Donald Tusk powołuje go na stanowisko dyrektora AMW.",
                paragraph_index=0,
                sentence_index=1,
                start_char=32,
                end_char=len(text),
            ),
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id="person-2",
                entity_type=EntityType.PERSON,
                canonical_name="Donald Tusk",
                normalized_name="Donald Tusk",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AMW",
                normalized_name="AMW",
            ),
        ],
        mentions=[
            Mention(
                text="Marcin Horyń",
                normalized_text="Marcin Horyń",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="Donald Tusk",
                normalized_text="Donald Tusk",
                mention_type="Person",
                sentence_index=1,
                entity_id="person-2",
            ),
            Mention(
                text="AMW",
                normalized_text="AMW",
                mention_type="Organization",
                sentence_index=1,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]
    entity_names = {entity.entity_id: entity.canonical_name for entity in extracted.entities}

    assert appointments
    assert entity_names[appointments[0].subject_entity_id] == "Marcin Horyń"
    assert appointments[0].value_text == "Dyrektor"


def test_party_affiliation_supports_lider_psl_phrase() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Marcin Horyń, lider PSL, objął stanowisko dyrektora AMW."
    document = ArticleDocument(
        document_id="doc-10c",
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
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id="party-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PSL",
                normalized_name="PSL",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AMW",
                normalized_name="AMW",
            ),
        ],
        mentions=[
            Mention(
                text="Marcin Horyń",
                normalized_text="Marcin Horyń",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type="Organization",
                sentence_index=0,
                entity_id="party-1",
            ),
            Mention(
                text="AMW",
                normalized_text="AMW",
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

    party_facts = [
        fact
        for fact in extracted.facts
        if fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
    ]

    assert party_facts


def test_tie_extractor_supports_zaufany_ludzi_phrase() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Marcin Horyń jest jednym z zaufanych ludzi Władysława Kosiniaka-Kamysza."
    document = ArticleDocument(
        document_id="doc-10d",
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
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id="person-2",
                entity_type=EntityType.PERSON,
                canonical_name="Władysław Kosiniak-Kamysz",
                normalized_name="Władysław Kosiniak-Kamysz",
            ),
        ],
        mentions=[
            Mention(
                text="Marcin Horyń",
                normalized_text="Marcin Horyń",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="Władysława Kosiniaka-Kamysza",
                normalized_text="Władysław Kosiniak-Kamysz",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-2",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert any(fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE for fact in extracted.facts)


def test_relation_extractor_parses_syntax_once_per_document() -> None:
    config = PipelineConfig.from_file("config.yaml")
    syntax_pipeline = CountingSyntaxPipeline(
        FakeDoc(
            sentences=[
                FakeSentence(
                    words=[
                        FakeWord(1, "Jan", "jan", "PROPN", 2, "nsubj", 0, 3),
                        FakeWord(2, "awansował", "awansować", "VERB", 0, "root", 4, 13),
                        FakeWord(3, ".", ".", "PUNCT", 2, "punct", 13, 14),
                    ]
                ),
                FakeSentence(
                    words=[
                        FakeWord(1, "Objął", "objąć", "VERB", 0, "root", 15, 20),
                        FakeWord(2, "stanowisko", "stanowisko", "NOUN", 1, "obj", 21, 31),
                        FakeWord(3, ".", ".", "PUNCT", 1, "punct", 31, 32),
                    ]
                ),
            ]
        )
    )

    def fake_stanza_factory(*args, **kwargs):
        _ = args, kwargs
        return syntax_pipeline

    runtime = PipelineRuntime(config, stanza_factory=fake_stanza_factory)
    extractor = PolishRuleBasedRelationExtractor(config, runtime=runtime)
    text = "Jan awansował. Objął stanowisko."
    document = ArticleDocument(
        document_id="doc-10",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text="Jan awansował.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=14,
            ),
            SentenceFragment(
                text="Objął stanowisko.",
                paragraph_index=0,
                sentence_index=1,
                start_char=15,
                end_char=len(text),
            ),
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Jan",
                normalized_name="Jan",
            )
        ],
        mentions=[
            Mention(
                text="Jan",
                normalized_text="Jan",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            )
        ],
    )

    extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    assert syntax_pipeline.call_count == 1


def test_governance_prefers_specific_company_over_skarb_panstwa() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "A. Góralczyk została prezeską Stadniny Koni Iwno, państwowej spółki Skarbu Państwa."
    document = ArticleDocument(
        document_id="doc-11",
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
                canonical_name="A. Góralczyk",
                normalized_name="A. Góralczyk",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Stadnina Koni Iwno",
                normalized_name="Stadnina Koni Iwno",
            ),
            Entity(
                entity_id="org-2",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Skarbu Państwa",
                normalized_name="Skarbu Państwa",
            ),
        ],
        mentions=[
            Mention(
                text="A. Góralczyk",
                normalized_text="A. Góralczyk",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="Stadniny Koni Iwno",
                normalized_text="Stadnina Koni Iwno",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
            Mention(
                text="Skarbu Państwa",
                normalized_text="Skarbu Państwa",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-2",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]

    assert appointments
    target_ids = {entity.entity_id: entity.canonical_name for entity in extracted.entities}
    assert appointments[0].object_entity_id is not None
    assert target_ids[appointments[0].object_entity_id] == "Stadnina Koni Iwno"
