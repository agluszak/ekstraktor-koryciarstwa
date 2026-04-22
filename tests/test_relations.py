from dataclasses import dataclass

from pipeline.clustering import PolishEntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    CandidateType,
    ClauseID,
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FactType,
    OrganizationKind,
    RoleKind,
    RoleModifier,
    TimeScope,
)
from pipeline.frames import PolishFrameExtractor
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    CoreferenceResult,
    Entity,
    EntityCluster,
    Mention,
    ParsedWord,
    SentenceFragment,
)
from pipeline.relations import PolishFactExtractor
from pipeline.relations.candidate_graph import CandidateGraphBuilder
from pipeline.role_matching import match_role_mentions
from pipeline.runtime import PipelineRuntime
from pipeline.segmentation.service import ParagraphSentenceSegmenter
from pipeline.syntax import StanzaClauseParser


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


def word(
    index: int,
    text: str,
    lemma: str,
    start: int,
    *,
    head: int = 0,
    deprel: str = "root",
    upos: str = "NOUN",
) -> ParsedWord:
    return ParsedWord(
        index=index,
        text=text,
        lemma=lemma,
        upos=upos,
        head=head,
        deprel=deprel,
        start=start,
        end=start + len(text),
    )


def prepare_for_relation_extraction(
    config: PipelineConfig,
    document: ArticleDocument,
    runtime: PipelineRuntime | None = None,
) -> ArticleDocument:
    shared_runtime = runtime or PipelineRuntime(config)
    document = PolishEntityClusterer(config).run(document)
    document = StanzaClauseParser(config, shared_runtime).run(document)
    return PolishFrameExtractor(config).run(document)


def prepared_single_clause_document(
    *,
    document_id: str,
    text: str,
    entities: list[tuple[str, EntityType, str]],
    parsed_words: list[ParsedWord] | None = None,
) -> ArticleDocument:
    sentence = SentenceFragment(
        text=text,
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len(text),
    )
    document = ArticleDocument(
        document_id=DocumentID(document_id),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[sentence],
    )
    cluster_mentions: list[ClusterMention] = []
    for index, (surface, entity_type, canonical_name) in enumerate(entities):
        start = text.index(surface)
        end = start + len(surface)
        entity_id = EntityID(f"entity-{index}")
        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name,
        )
        document.entities.append(entity)
        document.mentions.append(
            Mention(
                text=surface,
                normalized_text=canonical_name,
                mention_type=entity_type,
                sentence_index=0,
                paragraph_index=0,
                start_char=start,
                end_char=end,
                entity_id=entity_id,
            )
        )
        cluster_mention = ClusterMention(
            text=surface,
            entity_type=entity_type,
            sentence_index=0,
            paragraph_index=0,
            start_char=start,
            end_char=end,
            entity_id=entity_id,
        )
        cluster_mentions.append(cluster_mention)
        document.clusters.append(
            EntityCluster(
                cluster_id=ClusterID(f"cluster-{index}"),
                entity_type=entity_type,
                canonical_name=canonical_name,
                normalized_name=canonical_name,
                mentions=[cluster_mention],
            )
        )
    document.parsed_sentences = {0: parsed_words or []}
    root = (
        parsed_words
        or [ParsedWord(1, text.split()[0], text.split()[0].lower(), "", 0, "root", 0, 1)]
    )[0]
    document.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-1"),
            text=text,
            trigger_head_text=root.text,
            trigger_head_lemma=root.lemma,
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=cluster_mentions,
        )
    ]
    return document


def test_role_matcher_uses_wojewoda_lemma_for_inflected_surface() -> None:
    matches = match_role_mentions([word(1, "wojewodą", "wojewoda", 0)])

    assert len(matches) == 1
    assert matches[0].canonical_name == "Wojewoda"
    assert matches[0].role_kind == RoleKind.WOJEWODA
    assert matches[0].role_modifier is None
    assert matches[0].start == 0
    assert matches[0].end == len("wojewodą")


def test_role_matcher_handles_public_office_roles() -> None:
    cases = [
        ([word(1, "wójta", "wójt", 0)], RoleKind.WOJT, "Wójt"),
        ([word(1, "starosta", "starosta", 0)], RoleKind.STAROSTA, "Starosta"),
        (
            [
                word(1, "sekretarz", "sekretarz", 0),
                word(2, "powiatu", "powiat", 10),
            ],
            RoleKind.SEKRETARZ_POWIATU,
            "Sekretarz Powiatu",
        ),
        (
            [
                word(1, "marszałkiem", "marszałek", 0),
                word(2, "województwa", "województwo", 12),
            ],
            RoleKind.MARSZALEK_WOJEWODZTWA,
            "Marszałek Województwa",
        ),
        ([word(1, "wojewodą", "wojewoda", 0)], RoleKind.WOJEWODA, "Wojewoda"),
    ]

    for parsed_words, role_kind, canonical_name in cases:
        matches = match_role_mentions(parsed_words)

        assert len(matches) == 1
        assert matches[0].role_kind == role_kind
        assert matches[0].canonical_name == canonical_name


def test_candidate_graph_uses_wicewojewoda_lemma_for_deputy_role() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Anna Nowak została wicewojewodą."
    role_start = text.index("wicewojewodą")
    document = ArticleDocument(
        document_id=DocumentID("doc-role-wicewojewoda"),
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
    )
    parsed_words = [
        word(1, "Anna", "Anna", 0, head=3, deprel="nsubj", upos="PROPN"),
        word(2, "została", "zostać", text.index("została"), head=3, deprel="aux", upos="AUX"),
        word(3, "wicewojewodą", "wicewojewoda", role_start),
    ]

    candidate_graph = CandidateGraphBuilder(config).build(
        document=document,
        coreference=CoreferenceResult(resolved_mentions=[]),
        parsed_sentences={0: parsed_words},
    )
    positions = [
        candidate
        for candidate in candidate_graph.candidates
        if candidate.candidate_type == CandidateType.POSITION
    ]

    assert len(positions) == 1
    assert positions[0].canonical_name == "wice/zastępca Wojewoda"
    assert positions[0].role_kind == RoleKind.WOJEWODA
    assert positions[0].role_modifier == RoleModifier.DEPUTY
    assert positions[0].start_char == role_start
    assert positions[0].end_char == role_start + len("wicewojewodą")


def test_role_title_surface_is_not_derived_as_person() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Sekretarz Powiatu podpisała dokumenty."
    document = ArticleDocument(
        document_id=DocumentID("doc-role-not-person"),
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
    )
    document.parsed_sentences = {
        0: [
            word(1, "Sekretarz", "sekretarz", 0),
            word(2, "Powiatu", "powiat", 10),
            word(3, "podpisała", "podpisać", 18, upos="VERB"),
        ]
    }

    candidate_graph = CandidateGraphBuilder(config).build(
        document=document,
        coreference=CoreferenceResult(resolved_mentions=[]),
        parsed_sentences=document.parsed_sentences,
    )

    assert not any(
        candidate.candidate_type == CandidateType.PERSON
        and candidate.canonical_name == "Sekretarz Powiatu"
        for candidate in candidate_graph.candidates
    )
    assert any(
        candidate.candidate_type == CandidateType.POSITION
        and candidate.role_kind == RoleKind.SEKRETARZ_POWIATU
        for candidate in candidate_graph.candidates
    )


def test_role_matcher_handles_inflected_prezes_family() -> None:
    cases = [
        ("prezesem", "prezes", "Prezes", RoleKind.PREZES, None),
        ("prezeską", "prezeska", "Prezes", RoleKind.PREZES, None),
        (
            "wiceprezesem",
            "wiceprezes",
            "wice/zastępca Prezes",
            RoleKind.PREZES,
            RoleModifier.DEPUTY,
        ),
        (
            "wiceprezeską",
            "wiceprezeska",
            "wice/zastępca Prezes",
            RoleKind.PREZES,
            RoleModifier.DEPUTY,
        ),
    ]
    for surface, lemma, canonical, role_kind, role_modifier in cases:
        matches = match_role_mentions([word(1, surface, lemma, 4)])

        assert len(matches) == 1
        assert matches[0].canonical_name == canonical
        assert matches[0].role_kind == role_kind
        assert matches[0].role_modifier == role_modifier
        assert matches[0].start == 4
        assert matches[0].end == 4 + len(surface)


def test_role_matcher_prefers_longest_board_role_span() -> None:
    parsed_words = [
        word(1, "wiceprzewodniczącą", "wiceprzewodniczący", 0),
        word(2, "rady", "rada", 19),
        word(3, "nadzorczej", "nadzorczy", 24),
    ]

    matches = match_role_mentions(parsed_words)

    assert len(matches) == 1
    assert matches[0].canonical_name == "wice/zastępca Przewodniczący Rady Nadzorczej"
    assert matches[0].start == 0
    assert matches[0].end == 34


def test_party_aliases_match_whole_tokens_only() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-1"),
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
                entity_id=EntityID("person-1"),
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
                entity_id=EntityID("person-1"),
            )
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )
    party_names = sorted(
        entity.canonical_name
        for entity in extracted.entities
        if entity.entity_type == "PoliticalParty"
    )

    assert party_names == ["Prawo i Sprawiedliwość"]


def test_syndrom_does_not_trigger_fake_syn_relation() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = 'Jest to niestety prosta droga do "syndromu Rybnika" - pisze Dorota Połedniok.'
    document = ArticleDocument(
        document_id=DocumentID("doc-2"),
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
                entity_id=EntityID("person-1"),
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
                entity_id=EntityID("person-1"),
            )
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    assert not any(fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE for fact in extracted.facts)


def test_compensation_relation_is_extracted() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Łukasz Bałajewicz zarabia miesięcznie ponad 31 tys. zł brutto jako prezes KZN."
    document = ArticleDocument(
        document_id=DocumentID("doc-3"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Łukasz Bałajewicz",
                normalized_name="Łukasz Bałajewicz",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="KZN",
                normalized_text="KZN",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    compensation_facts = [
        fact for fact in extracted.facts if fact.fact_type == FactType.COMPENSATION
    ]
    assert compensation_facts
    assert compensation_facts[0].amount_text == "31 Tys. Zł Brutto"
    assert compensation_facts[0].confidence >= 0.7
    assert compensation_facts[0].source_extractor == "compensation_frame"
    assert compensation_facts[0].extraction_signal in {
        "syntactic_direct",
        "dependency_edge",
    }


def test_party_cannot_become_appointment_destination() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Stanisław Mazur, polityk Lewicy, został prezesem."
    document = ArticleDocument(
        document_id=DocumentID("doc-4"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Stanisław Mazur",
                normalized_name="Stanisław Mazur",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Lewicy",
                normalized_text="Lewicy",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    assert not any(fact.fact_type == FactType.APPOINTMENT for fact in extracted.facts)


def test_party_membership_requires_local_structural_support() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Donald Tusk skrytykował PSL za decyzję w sprawie budżetu."
    document = ArticleDocument(
        document_id=DocumentID("doc-5"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Donald Tusk",
                normalized_name="Donald Tusk",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    assert not any(
        fact.fact_type in {"PARTY_MEMBERSHIP", "FORMER_PARTY_MEMBERSHIP"}
        for fact in extracted.facts
    )


def test_direct_party_profile_fact_has_high_confidence_metadata() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Jan Kowalski, działacz PSL, został powołany do rady."
    document = ArticleDocument(
        document_id=DocumentID("doc-party-score"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            ),
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PSL",
                normalized_name="PSL",
            ),
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("party-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    party_facts = [
        fact
        for fact in extracted.facts
        if fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
    ]

    assert party_facts
    assert party_facts[0].confidence >= 0.7
    assert party_facts[0].source_extractor == "political_profile"
    assert party_facts[0].extraction_signal in {
        "syntactic_direct",
        "appositive_context",
        "dependency_edge",
    }


def test_initials_and_paragraph_carryover_support_governance_fact() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = (
        "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie. "
        "Teraz awansowała na stanowisko zastępcy prezesa. "
        "Chodzi o Stadninę Koni Iwno."
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-6"),
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
                entity_id=EntityID("person-initial"),
                entity_type=EntityType.PERSON,
                canonical_name="A",
                normalized_name="A",
            ),
            Entity(
                entity_id=EntityID("person-surname"),
                entity_type=EntityType.PERSON,
                canonical_name="Góralczyk",
                normalized_name="Góralczyk",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-initial"),
            ),
            Mention(
                text="Góralczyk",
                normalized_text="Góralczyk",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-surname"),
            ),
            Mention(
                text="Stadninę Koni Iwno",
                normalized_text="Stadnina Koni Iwno",
                mention_type="Organization",
                sentence_index=2,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    appointments = [
        fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT and fact.role
    ]

    assert appointments
    assert appointments[0].role == "wice/zastępca Prezes"
    assert any(entity.canonical_name == "A. Góralczyk" for entity in extracted.entities)


def test_headline_party_context_links_next_sentence_person() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = (
        "Działaczka Polskiego Stronnictwa Ludowego A. Góralczyk awansowała na stanowisko prezesa."
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-party-discourse"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[
            "Działaczka Polskiego Stronnictwa Ludowego",
            "A. Góralczyk awansowała na stanowisko prezesa.",
        ],
        sentences=[
            SentenceFragment(
                text="Działaczka Polskiego Stronnictwa Ludowego",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=41,
            ),
            SentenceFragment(
                text="A. Góralczyk awansowała na stanowisko prezesa.",
                paragraph_index=1,
                sentence_index=1,
                start_char=42,
                end_char=len(text),
            ),
        ],
        entities=[
            Entity(
                entity_id=EntityID("party-org"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Polskiego Stronnictwa Ludowego",
                normalized_name="Polskiego Stronnictwa Ludowego",
            ),
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="A. Góralczyk",
                normalized_name="A. Góralczyk",
            ),
        ],
        mentions=[
            Mention(
                text="Polskiego Stronnictwa Ludowego",
                normalized_text="Polskiego Stronnictwa Ludowego",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("party-org"),
            ),
            Mention(
                text="A. Góralczyk",
                normalized_text="A. Góralczyk",
                mention_type="Person",
                sentence_index=1,
                entity_id=EntityID("person-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    party_facts = [fact for fact in extracted.facts if fact.fact_type == FactType.PARTY_MEMBERSHIP]
    entity_names = {entity.entity_id: entity.canonical_name for entity in extracted.entities}

    assert party_facts
    assert party_facts[0].object_entity_id is not None
    assert entity_names[party_facts[0].object_entity_id] == "Polskie Stronnictwo Ludowe"


def test_segmenter_keeps_initials_with_surname() -> None:
    config = PipelineConfig.from_file("config.yaml")
    segmenter = ParagraphSentenceSegmenter(config)
    text = (
        "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie. "
        "Teraz awansowała na stanowisko prezesa."
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-7"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
    )

    segmented = segmenter.run(document)

    assert segmented.sentences[0].text.startswith("A. Góralczyk")


def test_segmenter_splits_sentence_before_quote_dash() -> None:
    config = PipelineConfig.from_file("config.yaml")
    segmenter = ParagraphSentenceSegmenter(config)
    text = "Pierwsza umowa dotyczyła Bartków. – Łącznie firma podpisała dwie umowy."
    document = ArticleDocument(
        document_id=DocumentID("doc-quote-dash"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
    )

    segmented = segmenter.run(document)

    assert [sentence.text for sentence in segmented.sentences] == [
        "Pierwsza umowa dotyczyła Bartków.",
        "– Łącznie firma podpisała dwie umowy.",
    ]


def test_inflected_public_institution_is_typed_from_lemmas() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    institution_surface = "Wojewódzkim Funduszu Ochrony Środowiska i Gospodarki Wodnej w Lublinie"
    institution_normalized = "Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Lublinie"
    text = f"Stanisław Mazur odebrał nominację w {institution_surface}."
    document = ArticleDocument(
        document_id=DocumentID("doc-8"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Stanisław Mazur",
                normalized_name="Stanisław Mazur",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text=institution_surface,
                normalized_text=institution_normalized,
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    candidate_graph = CandidateGraphBuilder(config).build(
        document=extracted,
        coreference=CoreferenceResult(resolved_mentions=[]),
        parsed_sentences=extracted.parsed_sentences,
    )
    assert any(
        candidate.candidate_type == CandidateType.PUBLIC_INSTITUTION
        for candidate in candidate_graph.candidates
    )


def test_party_like_organization_can_be_detected_without_alias_lookup() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Jan Kowalski, polityk Koalicji 15 Października, został powołany."
    document = ArticleDocument(
        document_id=DocumentID("doc-9"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Koalicji 15 Października",
                normalized_text="Koalicja 15 Października",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    candidate_graph = CandidateGraphBuilder(config).build(
        document=extracted,
        coreference=CoreferenceResult(resolved_mentions=[]),
        parsed_sentences=extracted.parsed_sentences,
    )
    assert any(
        candidate.candidate_type == CandidateType.POLITICAL_PARTY
        and "Koalicja" in candidate.canonical_name
        for candidate in candidate_graph.candidates
    )


def test_party_alias_inside_non_party_organization_does_not_retype_whole_entity() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Marcin Horyń złożył rezygnację ze stanowiska prezesa PSL Fundacji Rozwoju."
    document = ArticleDocument(
        document_id=DocumentID("doc-9b"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="PSL Fundacji Rozwoju",
                normalized_text="PSL Fundacji Rozwoju",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    assert any(
        entity.canonical_name == "PSL Fundacji Rozwoju"
        and entity.entity_type == EntityType.ORGANIZATION
        for entity in extracted.entities
    )


def test_institution_alias_candidate_is_typed_as_public_institution() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Marcin Horyń został dyrektorem AMW. MON sprawuje nadzór nad agencją."
    document = ArticleDocument(
        document_id=DocumentID("doc-10a"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AMW",
                normalized_name="AMW",
            ),
            Entity(
                entity_id=EntityID("org-2"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="AMW",
                normalized_text="AMW",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
            Mention(
                text="MON",
                normalized_text="MON",
                mention_type="Organization",
                sentence_index=1,
                entity_id=EntityID("org-2"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    candidate_graph = CandidateGraphBuilder(config).build(
        document=extracted,
        coreference=CoreferenceResult(resolved_mentions=[]),
        parsed_sentences=extracted.parsed_sentences,
    )
    public_institutions = {
        candidate.canonical_name
        for candidate in candidate_graph.candidates
        if candidate.candidate_type == CandidateType.PUBLIC_INSTITUTION
    }
    assert "Agencja Mienia Wojskowego" in public_institutions
    assert "Ministerstwo Obrony Narodowej" in public_institutions


def test_object_appointee_sentence_extracts_appointee_not_appointing_authority() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = (
        "Marcin Horyń złożył rezygnację. "
        "Premier Donald Tusk powołuje go na stanowisko dyrektora AMW."
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-10b"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id=EntityID("person-2"),
                entity_type=EntityType.PERSON,
                canonical_name="Donald Tusk",
                normalized_name="Donald Tusk",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Donald Tusk",
                normalized_text="Donald Tusk",
                mention_type="Person",
                sentence_index=1,
                entity_id=EntityID("person-2"),
            ),
            Mention(
                text="AMW",
                normalized_text="AMW",
                mention_type="Organization",
                sentence_index=1,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]
    entity_names = {entity.entity_id: entity.canonical_name for entity in extracted.entities}

    assert appointments
    assert entity_names[appointments[0].subject_entity_id] == "Marcin Horyń"
    assert appointments[0].value_text == "Dyrektor"


def test_party_affiliation_supports_lider_psl_phrase() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Marcin Horyń, lider PSL, objął stanowisko dyrektora AMW."
    document = ArticleDocument(
        document_id=DocumentID("doc-10c"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PSL",
                normalized_name="PSL",
            ),
            Entity(
                entity_id=EntityID("org-1"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("party-1"),
            ),
            Mention(
                text="AMW",
                normalized_text="AMW",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    party_facts = [
        fact
        for fact in extracted.facts
        if fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
    ]

    assert party_facts


def test_tie_extractor_supports_zaufany_ludzi_phrase() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Marcin Horyń jest jednym z zaufanych ludzi Władysława Kosiniaka-Kamysza."
    document = ArticleDocument(
        document_id=DocumentID("doc-10d"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id=EntityID("person-2"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Władysława Kosiniaka-Kamysza",
                normalized_text="Władysław Kosiniak-Kamysz",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-2"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    tie_facts = [
        fact for fact in extracted.facts if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
    ]

    assert tie_facts
    assert tie_facts[0].confidence >= 0.55
    assert tie_facts[0].source_extractor == "tie"
    assert tie_facts[0].extraction_signal in {
        "dependency_edge",
        "syntactic_direct",
    }


def test_clause_parser_parses_syntax_once_per_document() -> None:
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
    clause_parser = StanzaClauseParser(config, runtime)
    extractor = PolishFactExtractor(config)
    text = "Jan awansował. Objął stanowisko."
    document = ArticleDocument(
        document_id=DocumentID("doc-10"),
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
                entity_id=EntityID("person-1"),
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
                entity_id=EntityID("person-1"),
            )
        ],
    )

    document = clause_parser.run(document)
    extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    assert syntax_pipeline.call_count == 1


def test_governance_prefers_specific_company_over_skarb_panstwa() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "A. Góralczyk została prezeską Stadniny Koni Iwno, państwowej spółki Skarbu Państwa."
    document = ArticleDocument(
        document_id=DocumentID("doc-11"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="A. Góralczyk",
                normalized_name="A. Góralczyk",
            ),
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Stadnina Koni Iwno",
                normalized_name="Stadnina Koni Iwno",
            ),
            Entity(
                entity_id=EntityID("org-2"),
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
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Stadniny Koni Iwno",
                normalized_text="Stadnina Koni Iwno",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
            Mention(
                text="Skarbu Państwa",
                normalized_text="Skarbu Państwa",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-2"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]

    assert appointments
    target_ids = {entity.entity_id: entity.canonical_name for entity in extracted.entities}
    assert appointments[0].object_entity_id is not None
    assert target_ids[appointments[0].object_entity_id] == "Stadnina Koni Iwno"


def test_governance_keeps_owner_context_without_replacing_target() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = (
        "Marcin Horyń został dyrektorem Rewita Hoteli, "
        "spółki podległej Ministerstwu Obrony Narodowej."
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-12"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Marcin Horyń",
                normalized_name="Marcin Horyń",
            ),
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Rewita Hoteli",
                normalized_name="Rewita Hoteli",
                organization_kind=OrganizationKind.COMPANY,
            ),
            Entity(
                entity_id=EntityID("org-2"),
                entity_type=EntityType.PUBLIC_INSTITUTION,
                canonical_name="Ministerstwo Obrony Narodowej",
                normalized_name="Ministerstwo Obrony Narodowej",
                organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
            ),
        ],
        mentions=[
            Mention(
                text="Marcin Horyń",
                normalized_text="Marcin Horyń",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Rewita Hoteli",
                normalized_text="Rewita Hoteli",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
            Mention(
                text="Ministerstwu Obrony Narodowej",
                normalized_text="Ministerstwo Obrony Narodowej",
                mention_type="PublicInstitution",
                sentence_index=0,
                entity_id=EntityID("org-2"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]
    entity_names = {entity.entity_id: entity.canonical_name for entity in extracted.entities}

    assert appointments
    assert appointments[0].object_entity_id is not None
    assert entity_names[appointments[0].object_entity_id] == "Rewita Hoteli"
    owner_id = appointments[0].owner_context_entity_id
    assert isinstance(owner_id, str)
    assert entity_names[owner_id] == "Ministerstwo Obrony Narodowej"


def test_candidacy_requires_explicit_election_context() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Tadeusz Rydzyk dostał 300 tys. zł dotacji na projekt fundacji."
    document = ArticleDocument(
        document_id=DocumentID("doc-13"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Tadeusz Rydzyk",
                normalized_name="Tadeusz Rydzyk",
            ),
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Fundacja Lux Veritatis",
                normalized_name="Fundacja Lux Veritatis",
            ),
        ],
        mentions=[
            Mention(
                text="Tadeusz Rydzyk",
                normalized_text="Tadeusz Rydzyk",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="fundacji",
                normalized_text="Fundacja Lux Veritatis",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    assert not any(fact.fact_type == FactType.ELECTION_CANDIDACY for fact in extracted.facts)


def test_party_membership_does_not_cross_attach_between_multiple_people() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = "Stanisław Mazur z Lewicy i Andrzej Kloc z PSL będą kierować funduszem."
    document = ArticleDocument(
        document_id=DocumentID("doc-14"),
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
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Stanisław Mazur",
                normalized_name="Stanisław Mazur",
            ),
            Entity(
                entity_id=EntityID("person-2"),
                entity_type=EntityType.PERSON,
                canonical_name="Andrzej Kloc",
                normalized_name="Andrzej Kloc",
            ),
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Lewicy",
                normalized_name="Lewica",
            ),
            Entity(
                entity_id=EntityID("party-2"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="PSL",
                normalized_name="PSL",
            ),
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="funduszem",
                normalized_name="fundusz",
            ),
        ],
        mentions=[
            Mention(
                text="Stanisław Mazur",
                normalized_text="Stanisław Mazur",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-1"),
            ),
            Mention(
                text="Andrzej Kloc",
                normalized_text="Andrzej Kloc",
                mention_type="Person",
                sentence_index=0,
                entity_id=EntityID("person-2"),
            ),
            Mention(
                text="Lewicy",
                normalized_text="Lewica",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("party-1"),
            ),
            Mention(
                text="PSL",
                normalized_text="PSL",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("party-2"),
            ),
            Mention(
                text="funduszem",
                normalized_text="fundusz",
                mention_type="Organization",
                sentence_index=0,
                entity_id=EntityID("org-1"),
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(resolved_mentions=[]),
    )

    party_facts = {
        (fact.subject_entity_id, fact.object_entity_id)
        for fact in extracted.facts
        if fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
    }
    names = {entity.entity_id: entity.canonical_name for entity in extracted.entities}
    mazur_id = next(key for key, value in names.items() if value == "Stanisław Mazur")
    kloc_id = next(key for key, value in names.items() if value == "Andrzej Kloc")
    psl_id = next(key for key, value in names.items() if value == "Polskie Stronnictwo Ludowe")
    mazur_party_names = {
        names[object_id]
        for subject_id, object_id in party_facts
        if subject_id == mazur_id and object_id is not None
    }

    assert any("Lewic" in party_name for party_name in mazur_party_names)
    assert (kloc_id, psl_id) in party_facts
    assert (mazur_id, psl_id) not in party_facts


def test_named_person_referral_to_cba_emits_anti_corruption_fact() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Radny Jan Kowalski złożył zawiadomienie do CBA."
    document = prepared_single_clause_document(
        document_id="doc-cba-person",
        text=text,
        entities=[
            ("Jan Kowalski", EntityType.PERSON, "Jan Kowalski"),
            ("CBA", EntityType.PUBLIC_INSTITUTION, "Centralne Biuro Antykorupcyjne"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    referrals = [
        fact for fact in extracted.facts if fact.fact_type == FactType.ANTI_CORRUPTION_REFERRAL
    ]
    assert referrals
    assert referrals[0].subject_entity_id == EntityID("entity-0")
    assert referrals[0].object_entity_id == EntityID("entity-1")


def test_party_referral_to_cba_uses_party_actor_when_no_person_present() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Radni reprezentujący PiS zapowiedzieli zawiadomienie do CBA."
    document = prepared_single_clause_document(
        document_id="doc-cba-party",
        text=text,
        entities=[
            ("PiS", EntityType.POLITICAL_PARTY, "Prawo i Sprawiedliwość"),
            ("CBA", EntityType.PUBLIC_INSTITUTION, "Centralne Biuro Antykorupcyjne"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    referrals = [
        fact for fact in extracted.facts if fact.fact_type == FactType.ANTI_CORRUPTION_REFERRAL
    ]
    assert referrals
    assert referrals[0].subject_entity_id == EntityID("entity-0")
    assert referrals[0].object_entity_id == EntityID("entity-1")


def test_referral_context_uses_stanza_lemmas_for_inflected_trigger() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Radny Jan Kowalski skierował skargę do CBA."
    document = prepared_single_clause_document(
        document_id="doc-cba-person-skarga",
        text=text,
        entities=[
            ("Jan Kowalski", EntityType.PERSON, "Jan Kowalski"),
            ("CBA", EntityType.PUBLIC_INSTITUTION, "Centralne Biuro Antykorupcyjne"),
        ],
        parsed_words=[
            word(1, "Radny", "radny", 0, head=3, deprel="nsubj"),
            word(2, "Jan", "Jan", 6, head=1, deprel="flat", upos="PROPN"),
            word(3, "skierował", "skierować", 19, upos="VERB"),
            word(4, "skargę", "skarga", 29, head=3, deprel="obj"),
            word(5, "CBA", "cba", 39, head=3, deprel="obl", upos="PROPN"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    referrals = [
        fact for fact in extracted.facts if fact.fact_type == FactType.ANTI_CORRUPTION_REFERRAL
    ]
    assert referrals
    assert referrals[0].subject_entity_id == EntityID("entity-0")
    assert referrals[0].object_entity_id == EntityID("entity-1")


def test_cross_sentence_party_context_uses_profile_lemma() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text_1 = "Kandydatka PSL pracowała wcześniej w urzędzie."
    text_2 = "Anna Nowak została dyrektorem spółki."
    document = ArticleDocument(
        document_id=DocumentID("doc-cross-party-lemma"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=f"{text_1} {text_2}",
        paragraphs=[text_1, text_2],
        sentences=[
            SentenceFragment(
                text=text_1,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(text_1),
            ),
            SentenceFragment(
                text=text_2,
                paragraph_index=0,
                sentence_index=1,
                start_char=len(text_1) + 1,
                end_char=len(text_1) + 1 + len(text_2),
            ),
        ],
        entities=[
            Entity(
                entity_id=EntityID("party-1"),
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name="Polskie Stronnictwo Ludowe",
                normalized_name="Polskie Stronnictwo Ludowe",
            ),
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Anna Nowak",
                normalized_name="Anna Nowak",
            ),
        ],
        mentions=[
            Mention(
                text="PSL",
                normalized_text="Polskie Stronnictwo Ludowe",
                mention_type="PoliticalParty",
                sentence_index=0,
                paragraph_index=0,
                entity_id=EntityID("party-1"),
            ),
            Mention(
                text="Anna Nowak",
                normalized_text="Anna Nowak",
                mention_type="Person",
                sentence_index=1,
                paragraph_index=0,
                entity_id=EntityID("person-1"),
            ),
        ],
    )
    document.parsed_sentences = {
        0: [
            word(1, "Kandydatka", "działaczka", 0),
            word(2, "PSL", "psl", 11, head=1, deprel="nmod", upos="PROPN"),
        ],
        1: [word(1, "Anna", "Anna", 0, upos="PROPN")],
    }
    candidate_graph = CandidateGraphBuilder(config).build(
        document=document,
        coreference=CoreferenceResult(resolved_mentions=[]),
        parsed_sentences=document.parsed_sentences,
    )

    facts = PolishFactExtractor._cross_sentence_party_facts(document, candidate_graph)

    assert facts
    assert facts[0].subject_entity_id == EntityID("person-1")
    assert facts[0].object_entity_id == EntityID("party-1")


def test_public_employment_entry_wording_emits_appointment_with_job_label() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Jan Kowalski został koordynatorem projektu w Powiatowym Centrum Pomocy Rodzinie."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-entry",
        text=text,
        entities=[
            ("Jan Kowalski", EntityType.PERSON, "Jan Kowalski"),
            (
                "Powiatowym Centrum Pomocy Rodzinie",
                EntityType.PUBLIC_INSTITUTION,
                "Powiatowe Centrum Pomocy Rodzinie",
            ),
        ],
        parsed_words=[
            word(1, "Jan", "Jan", 0, head=3, deprel="nsubj", upos="PROPN"),
            word(2, "Kowalski", "Kowalski", 4, head=1, deprel="flat", upos="PROPN"),
            word(3, "został", "zostać", 13, head=4, deprel="aux", upos="AUX"),
            word(4, "koordynatorem", "koordynator", 20, upos="NOUN"),
            word(5, "projektu", "projekt", 34, head=4, deprel="nmod"),
            word(6, "w", "w", 43, head=9, deprel="case", upos="ADP"),
            word(7, "Powiatowym", "powiatowy", 45, head=9, deprel="amod"),
            word(8, "Centrum", "centrum", 56, head=9, deprel="flat"),
            word(9, "Pomocy", "pomoc", 64, head=4, deprel="obl"),
            word(10, "Rodzinie", "rodzina", 71, head=9, deprel="nmod"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]
    assert appointments
    assert appointments[0].subject_entity_id == EntityID("entity-0")
    assert appointments[0].object_entity_id == EntityID("entity-1")
    assert appointments[0].role == "Koordynator Projektu"
    assert appointments[0].value_text == "Koordynator Projektu"


def test_public_employment_status_wording_emits_role_held() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Anna Nowak pracuje jako główny specjalista w Powiatowym Urzędzie Pracy."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-status",
        text=text,
        entities=[
            ("Anna Nowak", EntityType.PERSON, "Anna Nowak"),
            (
                "Powiatowym Urzędzie Pracy",
                EntityType.PUBLIC_INSTITUTION,
                "Powiatowy Urząd Pracy",
            ),
        ],
        parsed_words=[
            word(1, "Anna", "Anna", 0, head=3, deprel="nsubj", upos="PROPN"),
            word(2, "Nowak", "Nowak", 5, head=1, deprel="flat", upos="PROPN"),
            word(3, "pracuje", "pracować", 11, upos="VERB"),
            word(4, "jako", "jako", 19, head=6, deprel="case", upos="SCONJ"),
            word(5, "główny", "główny", 24, head=6, deprel="amod"),
            word(6, "specjalista", "specjalista", 31, head=3, deprel="xcomp"),
            word(7, "w", "w", 43, head=9, deprel="case", upos="ADP"),
            word(8, "Powiatowym", "powiatowy", 45, head=9, deprel="amod"),
            word(9, "Urzędzie", "urząd", 56, head=3, deprel="obl"),
            word(10, "Pracy", "praca", 64, head=9, deprel="nmod"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    role_facts = [fact for fact in extracted.facts if fact.fact_type == FactType.ROLE_HELD]
    assert role_facts
    assert role_facts[0].subject_entity_id == EntityID("entity-0")
    assert role_facts[0].object_entity_id == EntityID("entity-1")
    assert role_facts[0].role == "Główny Specjalista"
    assert role_facts[0].time_scope == TimeScope.CURRENT


def test_public_contract_emits_one_fact_per_public_counterparty_with_same_amount() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Firma X podpisała umowy z miastem Y oraz spółką Z na kwotę 397 496,95 zł."
    document = prepared_single_clause_document(
        document_id="doc-contract",
        text=text,
        entities=[
            ("Firma X", EntityType.ORGANIZATION, "Firma X"),
            ("miastem Y", EntityType.PUBLIC_INSTITUTION, "Miasto Y"),
            ("spółką Z", EntityType.ORGANIZATION, "Spółka Z"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    contracts = [fact for fact in extracted.facts if fact.fact_type == FactType.PUBLIC_CONTRACT]
    assert len(contracts) == 2
    assert {fact.object_entity_id for fact in contracts} == {
        EntityID("entity-1"),
        EntityID("entity-2"),
    }
    assert {fact.amount_text for fact in contracts} == {"397 496,95 Zł"}


def test_generic_contract_sentence_without_parties_does_not_emit_public_contract() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Wszystkie umowy zawierane są zgodnie z prawem."
    document = prepared_single_clause_document(
        document_id="doc-contract-negative",
        text=text,
        entities=[],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    assert not any(fact.fact_type == FactType.PUBLIC_CONTRACT for fact in extracted.facts)


def test_owner_context_collaborator_tie_skips_quote_attribution_person() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Firma Bartłomieja Wnuka zatrudniała wieloletniego kolegę i współpracownika "
        "prezydenta Mariusza Wołosza, powiedział Maciej Bartków."
    )
    document = prepared_single_clause_document(
        document_id="doc-owner-tie",
        text=text,
        entities=[
            ("Bartłomieja Wnuka", EntityType.PERSON, "Bartłomiej Wnuk"),
            ("Mariusza Wołosza", EntityType.PERSON, "Mariusz Wołosz"),
            ("Maciej Bartków", EntityType.PERSON, "Maciej Bartków"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document, CoreferenceResult(resolved_mentions=[]))

    ties = [
        fact for fact in extracted.facts if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
    ]
    assert len(ties) == 1
    assert ties[0].subject_entity_id == EntityID("entity-1")
    assert ties[0].object_entity_id == EntityID("entity-0")
    assert ties[0].subject_entity_id != ties[0].object_entity_id
    assert EntityID("entity-2") not in {
        ties[0].subject_entity_id,
        ties[0].object_entity_id,
    }
