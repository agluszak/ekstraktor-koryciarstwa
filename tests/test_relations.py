from dataclasses import dataclass

from pipeline.attribution import (
    resolve_party_attributions,
    resolve_political_role_attributions,
    resolve_public_employment_attribution,
)
from pipeline.clustering import PolishEntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    ClauseID,
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FactType,
    KinshipDetail,
    OrganizationKind,
    RelationshipType,
    RoleKind,
    RoleModifier,
    TimeScope,
)
from pipeline.domains.political_profile import CrossSentencePartyFactBuilder
from pipeline.enrichment import SharedEntityEnricher
from pipeline.extraction_context import (
    ALL_ENTITY_TYPES,
    ExtractionContext,
)
from pipeline.fact_extractor import PolishFactExtractor
from pipeline.frames import PolishFrameExtractor
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    Entity,
    EntityCluster,
    Mention,
    ParsedWord,
    SentenceFragment,
)
from pipeline.role_matching import match_role_mentions
from pipeline.runtime import PipelineRuntime
from pipeline.segmentation import ParagraphSentenceSegmenter
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
    feats: dict[str, str] | None = None,
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
        feats=feats or {},
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


def build_extraction_context(
    document: ArticleDocument,
) -> tuple[ExtractionContext, SentenceFragment]:
    config = PipelineConfig.from_file("config.yaml")
    SharedEntityEnricher(config).run(document)
    context = ExtractionContext.build(document)
    sentence = document.sentences[0]
    return context, sentence


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


def test_shared_enrichment_adds_public_office_positions_idempotently() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Sekretarz Powiatu Joanna Pszczółkowska wydała decyzję."
    document = prepared_single_clause_document(
        document_id="doc-enrichment-position",
        text=text,
        entities=[("Joanna Pszczółkowska", EntityType.PERSON, "Joanna Pszczółkowska")],
        parsed_words=[
            word(1, "Sekretarz", "sekretarz", 0, head=3, deprel="nsubj"),
            word(2, "Powiatu", "powiat", 10, head=1, deprel="nmod"),
            word(3, "Joanna", "Joanna", 18, head=5, deprel="nsubj", upos="PROPN"),
            word(4, "Pszczółkowska", "Pszczółkowska", 25, head=3, deprel="flat", upos="PROPN"),
            word(5, "wydała", "wydać", 39, upos="VERB"),
        ],
    )

    from pipeline.clustering import PolishEntityClusterer
    from pipeline.roles import PolishPositionExtractor

    extractor = PolishPositionExtractor(config)
    clusterer = PolishEntityClusterer(config)

    extractor.run(document)
    clusterer.run(document)

    # Enrichment is still needed for grounding refreshes
    enricher = SharedEntityEnricher(config)
    enricher.run(document)

    position_clusters = [
        cluster for cluster in document.clusters if cluster.entity_type == EntityType.POSITION
    ]
    assert len(position_clusters) == 1
    assert position_clusters[0].role_kind == RoleKind.SEKRETARZ_POWIATU
    assert any(
        mention.entity_type == EntityType.POSITION
        for clause in document.clause_units
        for mention in clause.cluster_mentions
    )


def test_resolve_party_attributions_uses_shared_candidate_support() -> None:
    document = prepared_single_clause_document(
        document_id="doc-attribution-party",
        text="Jan Kowalski z PSL zabrał głos.",
        entities=[
            ("Jan Kowalski", EntityType.PERSON, "Jan Kowalski"),
            ("PSL", EntityType.ORGANIZATION, "PSL"),
        ],
        parsed_words=[
            word(1, "Jan", "Jan", 0, head=4, deprel="nsubj", upos="PROPN"),
            word(2, "Kowalski", "Kowalski", 4, head=1, deprel="flat", upos="PROPN"),
            word(3, "z", "z", 13, head=4, deprel="case", upos="ADP"),
            word(4, "PSL", "PSL", 15, head=1, deprel="nmod", upos="PROPN"),
            word(5, "zabrał", "zabrać", 19, upos="VERB"),
            word(6, "głos", "głos", 26, head=5, deprel="obj"),
        ],
    )

    context, sentence = build_extraction_context(document)
    views = context.mention_views_in_sentence(
        sentence.sentence_index, sentence.paragraph_index, ALL_ENTITY_TYPES
    )
    person = next(v for v in views if v.canonical_name == "Jan Kowalski")

    attributions = resolve_party_attributions(context, sentence, person, governance_signal=False)

    assert len(attributions) == 1
    assert attributions[0].party.canonical_name == "Polskie Stronnictwo Ludowe"


def test_resolve_political_role_attributions_uses_shared_role_support() -> None:
    document = prepared_single_clause_document(
        document_id="doc-attribution-role",
        text="Sekretarz Powiatu Joanna Pszczółkowska wydała decyzję.",
        entities=[("Joanna Pszczółkowska", EntityType.PERSON, "Joanna Pszczółkowska")],
        parsed_words=[
            word(1, "Sekretarz", "sekretarz", 0, head=4, deprel="nsubj"),
            word(2, "Powiatu", "powiat", 10, head=1, deprel="nmod"),
            word(3, "Joanna", "Joanna", 18, head=1, deprel="appos", upos="PROPN"),
            word(4, "Pszczółkowska", "Pszczółkowska", 25, head=3, deprel="flat", upos="PROPN"),
            word(5, "wydała", "wydać", 39, upos="VERB"),
            word(6, "decyzję", "decyzja", 46, head=5, deprel="obj"),
        ],
    )

    context, sentence = build_extraction_context(document)
    views = context.mention_views_in_sentence(
        sentence.sentence_index, sentence.paragraph_index, ALL_ENTITY_TYPES
    )
    person = next(v for v in views if "Joanna" in v.canonical_name)

    attributions = resolve_political_role_attributions(
        context,
        sentence,
        person,
        governance_signal=False,
    )

    assert len(attributions) == 1
    assert attributions[0].role.canonical_name == "Sekretarz Powiatu"


def test_proxy_person_does_not_emit_office_or_candidacy_facts() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Partnerka wójta kandyduje w wyborach."
    document = prepared_single_clause_document(
        document_id="doc-proxy-no-office",
        text=text,
        entities=[("Partnerka wójta", EntityType.PERSON, "Partnerka Wójta")],
        parsed_words=[
            word(1, "Partnerka", "partnerka", 0, head=3, deprel="nsubj"),
            word(2, "wójta", "wójt", 10, head=1, deprel="nmod"),
            word(3, "kandyduje", "kandydować", 16, upos="VERB"),
            word(4, "w", "w", 26, head=5, deprel="case", upos="ADP"),
            word(5, "wyborach", "wybory", 28, head=3, deprel="obl"),
        ],
    )
    document.entities[0].is_proxy_person = True
    document.entities[0].kinship_detail = KinshipDetail.PARTNER

    extracted = PolishFactExtractor(config).run(document)

    assert not any(fact.fact_type == FactType.POLITICAL_OFFICE for fact in extracted.facts)
    assert not any(fact.fact_type == FactType.ELECTION_CANDIDACY for fact in extracted.facts)


def test_kinship_phrase_does_not_attach_office_to_relative_name() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Agnieszka Królikowska, partnerka marszałka województwa Szymona Ogłazy, pracuje w urzędzie."
    )
    document = prepared_single_clause_document(
        document_id="doc-kinship-office-guard",
        text=text,
        entities=[
            ("Agnieszka Królikowska", EntityType.PERSON, "Agnieszka Królikowska"),
            ("Szymona Ogłazy", EntityType.PERSON, "Szymon Ogłaza"),
        ],
        parsed_words=[
            word(1, "Agnieszka", "Agnieszka", 0, head=8, deprel="nsubj", upos="PROPN"),
            word(2, "Królikowska", "Królikowska", 10, head=1, deprel="flat", upos="PROPN"),
            word(3, "partnerka", "partnerka", 24, head=1, deprel="appos"),
            word(4, "marszałka", "marszałek", 34, head=3, deprel="nmod"),
            word(5, "województwa", "województwo", 45, head=4, deprel="nmod"),
            word(6, "Szymona", "Szymon", 57, head=4, deprel="nmod", upos="PROPN"),
            word(7, "Ogłazy", "Ogłaza", 65, head=6, deprel="flat", upos="PROPN"),
            word(8, "pracuje", "pracować", 73, upos="VERB"),
            word(9, "w", "w", 81, head=10, deprel="case", upos="ADP"),
            word(10, "urzędzie", "urząd", 83, head=8, deprel="obl"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document)

    offices = [fact for fact in extracted.facts if fact.fact_type == FactType.POLITICAL_OFFICE]
    assert not any(fact.subject_entity_id == EntityID("entity-0") for fact in offices)


def test_shared_enrichment_marks_public_institution_clusters() -> None:
    config = PipelineConfig.from_file("config.yaml")
    document = prepared_single_clause_document(
        document_id="doc-enrichment-public-institution",
        text="Urząd Gminy Poczesna zatrudnił pracownika.",
        entities=[("Urząd Gminy Poczesna", EntityType.ORGANIZATION, "Urząd Gminy Poczesna")],
        parsed_words=[word(1, "Urząd", "urząd", 0)],
    )

    SharedEntityEnricher(config).run(document)

    assert document.clusters[0].entity_type == EntityType.PUBLIC_INSTITUTION
    assert document.clusters[0].organization_kind == OrganizationKind.PUBLIC_INSTITUTION
    assert document.entities[0].entity_type == EntityType.PUBLIC_INSTITUTION


def test_shared_enrichment_adds_grounded_foundation_and_marshal_office() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Fundacja założona przez Karola Bielskiego otrzymała 100 tysięcy złotych "
        "z urzędu marszałkowskiego za promowanie wydarzenia."
    )
    document = prepared_single_clause_document(
        document_id="doc-derived-orgs",
        text=text,
        entities=[("Karola Bielskiego", EntityType.PERSON, "Karol Bielski")],
        parsed_words=[
            word(1, "Fundacja", "fundacja", 0, head=5, deprel="nsubj"),
            word(2, "założona", "założyć", 9, head=1, deprel="acl"),
            word(3, "przez", "przez", 18, head=4, deprel="case"),
            word(4, "Karola", "Karol", 24, head=2, deprel="obl", upos="PROPN"),
            word(5, "otrzymała", "otrzymać", text.index("otrzymała"), upos="VERB"),
            word(6, "urzędu", "urząd", text.index("urzędu"), head=5, deprel="obl"),
            word(7, "marszałkowskiego", "marszałkowski", text.index("marszałkowskiego")),
        ],
    )

    SharedEntityEnricher(config).run(document)

    assert any(
        cluster.canonical_name == "Fundacja Karola Bielskiego" for cluster in document.clusters
    )
    assert any(
        cluster.canonical_name == "Urząd Marszałkowski"
        and cluster.entity_type == EntityType.PUBLIC_INSTITUTION
        for cluster in document.clusters
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
    )
    party_names = sorted(
        entity.canonical_name
        for entity in extracted.entities
        if entity.entity_type == "PoliticalParty"
    )

    assert party_names == ["Prawo i Sprawiedliwość"]


def test_razem_party_alias_yields_membership_fact() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Marcelina Zawisza, posłanka partii Razem, zapowiedziała kontrolę."
    document = prepared_single_clause_document(
        document_id="doc-razem-party",
        text=text,
        entities=[("Marcelina Zawisza", EntityType.PERSON, "Marcelina Zawisza")],
        parsed_words=[
            word(1, "Marcelina", "Marcelina", 0, upos="PROPN"),
            word(2, "Zawisza", "Zawisza", 10, upos="PROPN"),
            word(3, "posłanka", "posłanka", text.index("posłanka")),
            word(4, "partii", "partia", text.index("partii")),
            word(5, "Razem", "Razem", text.index("Razem"), upos="PROPN"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document)

    assert any(
        fact.fact_type == FactType.PARTY_MEMBERSHIP and fact.value_normalized == "Razem"
        for fact in extracted.facts
    )


def test_omitted_subject_party_membership_attaches_to_previous_unique_person() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text_1 = "Karol Bielski kieruje pogotowiem."
    text_2 = "I również należy do PSL."
    first = SentenceFragment(
        text=text_1,
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len(text_1),
    )
    second = SentenceFragment(
        text=text_2,
        paragraph_index=0,
        sentence_index=1,
        start_char=len(text_1) + 1,
        end_char=len(text_1) + 1 + len(text_2),
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-omitted-party"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=f"{text_1} {text_2}",
        paragraphs=[f"{text_1} {text_2}"],
        sentences=[first, second],
    )
    person_id = EntityID("entity-person")
    document.entities.append(
        Entity(
            entity_id=person_id,
            entity_type=EntityType.PERSON,
            canonical_name="Karol Bielski",
            normalized_name="Karol Bielski",
        )
    )
    document.mentions.append(
        Mention(
            text="Karol Bielski",
            normalized_text="Karol Bielski",
            mention_type=EntityType.PERSON,
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len("Karol Bielski"),
            entity_id=person_id,
        )
    )
    document.clusters.append(
        EntityCluster(
            cluster_id=ClusterID("cluster-person"),
            entity_type=EntityType.PERSON,
            canonical_name="Karol Bielski",
            normalized_name="Karol Bielski",
            mentions=[
                ClusterMention(
                    text="Karol Bielski",
                    entity_type=EntityType.PERSON,
                    sentence_index=0,
                    paragraph_index=0,
                    start_char=0,
                    end_char=len("Karol Bielski"),
                    entity_id=person_id,
                )
            ],
        )
    )
    document.parsed_sentences = {
        0: [word(1, "Karol", "Karol", 0, upos="PROPN")],
        1: [
            word(1, "należy", "należeć", text_2.index("należy"), upos="VERB"),
            word(2, "PSL", "PSL", text_2.index("PSL"), upos="PROPN"),
        ],
    }

    extracted = PolishFactExtractor(config).run(document)

    assert any(
        fact.fact_type == FactType.PARTY_MEMBERSHIP
        and fact.subject_entity_id == person_id
        and fact.value_normalized == "Polskie Stronnictwo Ludowe"
        for fact in extracted.facts
    )


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


def test_appositive_profile_tail_links_leading_person_despite_intervening_name() -> None:
    text = (
        "Jarosław Słoma - ostatnio zastępca Piotra Grzymowicza, działacz PO w regionie, "
        "a po wyborach również radny wojewódzki."
    )
    document = prepared_single_clause_document(
        document_id="doc-appositive-profile-tail",
        text=text,
        entities=[
            ("Jarosław Słoma", EntityType.PERSON, "Jarosław Słoma"),
            ("Piotra Grzymowicza", EntityType.PERSON, "Piotr Grzymowicz"),
        ],
        parsed_words=[
            word(
                1,
                "Jarosław",
                "Jarosław",
                text.index("Jarosław"),
                head=2,
                deprel="flat",
                upos="PROPN",
            ),
            word(2, "Słoma", "Słoma", text.index("Słoma"), head=0, deprel="root", upos="PROPN"),
            word(3, "zastępca", "zastępca", text.index("zastępca"), head=2, deprel="appos"),
            word(4, "Piotra", "Piotr", text.index("Piotra"), head=3, deprel="nmod", upos="PROPN"),
            word(
                5,
                "Grzymowicza",
                "Grzymowicz",
                text.index("Grzymowicza"),
                head=4,
                deprel="flat",
                upos="PROPN",
            ),
            word(6, "działacz", "działacz", text.index("działacz"), head=2, deprel="appos"),
            word(7, "PO", "PO", text.index("PO"), head=6, deprel="nmod", upos="PROPN"),
            word(8, "radny", "radny", text.index("radny"), head=2, deprel="appos"),
            word(
                9,
                "wojewódzki",
                "wojewódzki",
                text.index("wojewódzki"),
                head=8,
                deprel="amod",
                upos="ADJ",
            ),
        ],
    )

    context, sentence = build_extraction_context(document)
    views = context.mention_views_in_sentence(
        sentence.sentence_index, sentence.paragraph_index, ALL_ENTITY_TYPES
    )
    person = next(v for v in views if v.canonical_name == "Jarosław Słoma")

    party_attributions = resolve_party_attributions(
        context, sentence, person, governance_signal=False
    )
    role_attributions = resolve_political_role_attributions(
        context,
        sentence,
        person,
        governance_signal=False,
    )

    assert any(
        attribution.party.canonical_name == "Platforma Obywatelska"
        for attribution in party_attributions
    )
    assert any(attribution.role.canonical_name == "Radny" for attribution in role_attributions)


def test_lowercase_po_preposition_does_not_create_party_membership() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishFactExtractor(config)
    text = (
        "Maciej Pach, konstytucjonalista z Poznańskiego Centrum Praw Człowieka INP PAN, "
        "opisuje po kolei możliwe ścieżki prawne."
    )
    document = prepared_single_clause_document(
        document_id="doc-lowercase-po-preposition",
        text=text,
        entities=[("Maciej Pach", EntityType.PERSON, "Maciej Pach")],
    )
    document = prepare_for_relation_extraction(config, document)
    extracted = extractor.run(document)

    assert not any(
        fact.fact_type in {FactType.PARTY_MEMBERSHIP, FactType.FORMER_PARTY_MEMBERSHIP}
        for fact in extracted.facts
    )


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
    )

    assert any(
        cluster.entity_type == EntityType.PUBLIC_INSTITUTION for cluster in extracted.clusters
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
    )

    assert any(
        cluster.entity_type == EntityType.POLITICAL_PARTY and "Koalicja" in cluster.canonical_name
        for cluster in extracted.clusters
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
    )

    public_institutions = {
        cluster.canonical_name
        for cluster in extracted.clusters
        if cluster.entity_type == EntityType.PUBLIC_INSTITUTION
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
    extracted = PolishFactExtractor(config).run(document)

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
    extracted = PolishFactExtractor(config).run(document)

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
    extracted = PolishFactExtractor(config).run(document)

    referrals = [
        fact for fact in extracted.facts if fact.fact_type == FactType.ANTI_CORRUPTION_REFERRAL
    ]
    assert referrals
    assert referrals[0].subject_entity_id == EntityID("entity-0")
    assert referrals[0].object_entity_id == EntityID("entity-1")


def test_cba_investigation_and_procurement_abuse_emit_public_abuse_facts() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "CBA zatrzymało wójta gminy Ostrów za łapówki przy zlecaniu remontów."
    document = prepared_single_clause_document(
        document_id="doc-cba-investigation",
        text=text,
        entities=[
            ("CBA", EntityType.PUBLIC_INSTITUTION, "Centralne Biuro Antykorupcyjne"),
            ("wójta", EntityType.POSITION, "Wójt"),
            ("gminy Ostrów", EntityType.PUBLIC_INSTITUTION, "Gmina Ostrów"),
        ],
        parsed_words=[
            word(1, "CBA", "cba", 0, head=2, deprel="nsubj", upos="PROPN"),
            word(2, "zatrzymało", "zatrzymać", text.index("zatrzymało"), upos="VERB"),
            word(3, "wójta", "wójt", text.index("wójta"), head=2, deprel="obj"),
            word(4, "gminy", "gmina", text.index("gminy"), head=3, deprel="nmod"),
            word(5, "Ostrów", "Ostrów", text.index("Ostrów"), head=4, deprel="flat"),
            word(6, "łapówki", "łapówka", text.index("łapówki"), head=2, deprel="obl"),
            word(7, "zlecaniu", "zlecać", text.index("zlecaniu"), head=6, deprel="acl"),
            word(8, "remontów", "remont", text.index("remontów"), head=7, deprel="obj"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document)

    investigations = [
        fact for fact in extracted.facts if fact.fact_type == FactType.ANTI_CORRUPTION_INVESTIGATION
    ]
    procurement_abuse = [
        fact for fact in extracted.facts if fact.fact_type == FactType.PUBLIC_PROCUREMENT_ABUSE
    ]
    assert investigations
    assert investigations[0].subject_entity_id == EntityID("entity-0")
    assert investigations[0].object_entity_id == EntityID("entity-1")
    assert procurement_abuse
    assert procurement_abuse[0].subject_entity_id == EntityID("entity-1")


def test_cross_sentence_party_context_uses_profile_lemma() -> None:
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

    facts = CrossSentencePartyFactBuilder().build(
        document,
        ExtractionContext.build(document),
    )

    assert facts
    assert facts[0].subject_entity_id == EntityID("person-1")
    assert facts[0].object_entity_id == EntityID("party-1")


def test_public_employment_uses_adjacent_public_employer_context() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text_1 = "Rafał Dobosz został zatrudniony jako ekodoradca."
    text_2 = "Urząd Gminy Poczesna potwierdził etat."
    cleaned_text = f"{text_1} {text_2}"
    person_id = EntityID("person-1")
    org_id = EntityID("org-1")
    document = ArticleDocument(
        document_id=DocumentID("doc-public-employment-adjacent"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=[cleaned_text],
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
                end_char=len(cleaned_text),
            ),
        ],
        entities=[
            Entity(
                entity_id=person_id,
                entity_type=EntityType.PERSON,
                canonical_name="Rafał Dobosz",
                normalized_name="Rafał Dobosz",
            ),
            Entity(
                entity_id=org_id,
                entity_type=EntityType.PUBLIC_INSTITUTION,
                canonical_name="Urząd Gminy Poczesna",
                normalized_name="Urząd Gminy Poczesna",
                organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
            ),
        ],
        mentions=[
            Mention(
                text="Rafał Dobosz",
                normalized_text="Rafał Dobosz",
                mention_type=EntityType.PERSON,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=len("Rafał Dobosz"),
                entity_id=person_id,
            ),
            Mention(
                text="Urząd Gminy Poczesna",
                normalized_text="Urząd Gminy Poczesna",
                mention_type=EntityType.PUBLIC_INSTITUTION,
                sentence_index=1,
                paragraph_index=0,
                start_char=0,
                end_char=len("Urząd Gminy Poczesna"),
                entity_id=org_id,
            ),
        ],
    )
    document.parsed_sentences = {
        0: [
            word(1, "Rafał", "Rafał", 0, head=2, deprel="flat", upos="PROPN"),
            word(2, "Dobosz", "Dobosz", 6, head=4, deprel="nsubj", upos="PROPN"),
            word(3, "został", "zostać", text_1.index("został"), head=4, deprel="aux"),
            word(
                4,
                "zatrudniony",
                "zatrudnić",
                text_1.index("zatrudniony"),
                upos="VERB",
            ),
            word(5, "jako", "jako", text_1.index("jako"), head=6, deprel="case", upos="SCONJ"),
            word(6, "ekodoradca", "ekodoradca", text_1.index("ekodoradca"), head=4, deprel="xcomp"),
        ],
        1: [word(1, "Urząd", "urząd", 0)],
    }
    person_mention = ClusterMention(
        text="Rafał Dobosz",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=len("Rafał Dobosz"),
        entity_id=person_id,
    )
    org_start = len(text_1) + 1
    org_mention = ClusterMention(
        text="Urząd Gminy Poczesna",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        sentence_index=1,
        paragraph_index=0,
        start_char=org_start,
        end_char=org_start + len("Urząd Gminy Poczesna"),
        entity_id=org_id,
    )
    document.clusters = [
        EntityCluster(
            cluster_id=ClusterID("cluster-person"),
            entity_type=EntityType.PERSON,
            canonical_name="Rafał Dobosz",
            normalized_name="Rafał Dobosz",
            mentions=[person_mention],
        ),
        EntityCluster(
            cluster_id=ClusterID("cluster-org"),
            entity_type=EntityType.PUBLIC_INSTITUTION,
            canonical_name="Urząd Gminy Poczesna",
            normalized_name="Urząd Gminy Poczesna",
            mentions=[org_mention],
            organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
        ),
    ]
    document.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-public-employment-adjacent"),
            text=text_1,
            trigger_head_text="zatrudniony",
            trigger_head_lemma="zatrudnić",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text_1),
            cluster_mentions=[person_mention],
        )
    ]
    document = PolishFrameExtractor(config).run(document)

    extracted = PolishFactExtractor(config).run(document)

    appointments = [fact for fact in extracted.facts if fact.fact_type == FactType.APPOINTMENT]
    assert appointments
    assert appointments[0].subject_entity_id == person_id
    assert appointments[0].object_entity_id == org_id
    assert appointments[0].role is not None
    assert "ekodoradca" in appointments[0].role.casefold()


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

    document = PolishFrameExtractor(config).run(document)

    extracted = PolishFactExtractor(config).run(document)

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

    document = PolishFrameExtractor(config).run(document)

    extracted = PolishFactExtractor(config).run(document)

    role_facts = [fact for fact in extracted.facts if fact.fact_type == FactType.ROLE_HELD]
    assert role_facts
    assert role_facts[0].subject_entity_id == EntityID("entity-0")
    assert role_facts[0].object_entity_id == EntityID("entity-1")
    assert role_facts[0].role == "Główny Specjalista"
    assert role_facts[0].time_scope == TimeScope.CURRENT


def test_public_employment_past_status_emits_former_scope_and_period() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Anna Nowak pracowała jako główny specjalista od 2020 r. w Powiatowym Urzędzie Pracy."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-former-status",
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
            word(
                3,
                "pracowała",
                "pracować",
                11,
                upos="VERB",
                feats={"Tense": "Past"},
            ),
            word(4, "jako", "jako", 21, head=6, deprel="case", upos="SCONJ"),
            word(5, "główny", "główny", 26, head=6, deprel="amod"),
            word(6, "specjalista", "specjalista", 34, head=3, deprel="xcomp"),
            word(7, "od", "od", 46, head=8, deprel="case", upos="ADP"),
            word(8, "2020", "2020", 49, head=3, deprel="obl", upos="NUM"),
            word(9, "r.", "rok", 54, head=8, deprel="nmod"),
            word(10, "w", "w", 57, head=13, deprel="case", upos="ADP"),
            word(11, "Powiatowym", "powiatowy", 59, head=12, deprel="amod"),
            word(12, "Urzędzie", "urząd", 71, head=3, deprel="obl"),
            word(13, "Pracy", "praca", 79, head=12, deprel="nmod"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document)

    role_facts = [fact for fact in extracted.facts if fact.fact_type == FactType.ROLE_HELD]
    assert role_facts
    assert role_facts[0].time_scope == TimeScope.FORMER
    assert role_facts[0].period == "od 2020 r"


def test_public_employment_frame_extracts_passive_hiring_patient() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Zatrudniono Rafała Dobosza na stanowisko pomocy administracyjnej w Urzędzie Gminy."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-passive-patient",
        text=text,
        entities=[
            ("Rafała Dobosza", EntityType.PERSON, "Rafał Dobosz"),
            ("Urzędzie Gminy", EntityType.PUBLIC_INSTITUTION, "Urząd Gminy"),
        ],
        parsed_words=[
            word(1, "Zatrudniono", "zatrudnić", 0, upos="VERB"),
            word(2, "Rafała", "Rafał", 12, head=1, deprel="obj", upos="PROPN"),
            word(3, "Dobosza", "Dobosz", 19, head=2, deprel="flat", upos="PROPN"),
            word(4, "na", "na", 27, head=5, deprel="case", upos="ADP"),
            word(5, "stanowisko", "stanowisko", 30, head=1, deprel="obl"),
            word(6, "pomocy", "pomoc", 41, head=5, deprel="nmod"),
            word(7, "administracyjnej", "administracyjny", 48, head=6, deprel="amod"),
            word(8, "w", "w", 64, head=9, deprel="case", upos="ADP"),
            word(9, "Urzędzie", "urząd", 66, head=1, deprel="obl"),
            word(10, "Gminy", "gmina", 74, head=9, deprel="nmod"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)

    assert document.public_employment_frames
    assert document.public_employment_frames[0].employee_cluster_id == ClusterID("cluster-0")
    assert document.public_employment_frames[0].role_label == "Pomocy Administracyjnej"


def test_public_employment_frame_uses_proxy_employee_for_partner_job() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Partnerka wójta dostała pracę jako ekodoradca w Urzędzie Gminy."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-proxy-partner",
        text=text,
        entities=[
            ("Partnerka", EntityType.PERSON, "partnerka wójta"),
            ("Urzędzie Gminy", EntityType.PUBLIC_INSTITUTION, "Urząd Gminy"),
        ],
        parsed_words=[
            word(1, "Partnerka", "partnerka", 0, head=3, deprel="nsubj"),
            word(2, "wójta", "wójt", 10, head=1, deprel="nmod"),
            word(3, "dostała", "dostać", 16, upos="VERB"),
            word(4, "pracę", "praca", 24, head=3, deprel="obj"),
            word(5, "jako", "jako", 30, head=6, deprel="case", upos="SCONJ"),
            word(6, "ekodoradca", "ekodoradca", 35, head=3, deprel="xcomp"),
            word(7, "w", "w", 46, head=8, deprel="case", upos="ADP"),
            word(8, "Urzędzie", "urząd", 48, head=3, deprel="obl"),
            word(9, "Gminy", "gmina", 56, head=8, deprel="nmod"),
        ],
    )
    document.clusters[0].is_proxy_person = True

    document = PolishFrameExtractor(config).run(document)

    assert document.public_employment_frames
    assert document.public_employment_frames[0].employee_cluster_id == ClusterID("cluster-0")
    assert document.public_employment_frames[0].role_label == "Ekodoradca"


def test_public_employment_attribution_resolves_proxy_employee_and_role_cluster() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Partnerka wójta dostała pracę jako ekodoradca w Urzędzie Gminy."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-attribution-proxy",
        text=text,
        entities=[
            ("Partnerka", EntityType.PERSON, "partnerka wójta"),
            ("ekodoradca", EntityType.POSITION, "ekodoradca"),
            ("Urzędzie Gminy", EntityType.PUBLIC_INSTITUTION, "Urząd Gminy"),
        ],
        parsed_words=[
            word(1, "Partnerka", "partnerka", 0, head=3, deprel="nsubj"),
            word(2, "wójta", "wójt", 10, head=1, deprel="nmod"),
            word(3, "dostała", "dostać", 16, upos="VERB"),
            word(4, "pracę", "praca", 24, head=3, deprel="obj"),
            word(5, "jako", "jako", 30, head=6, deprel="case", upos="SCONJ"),
            word(6, "ekodoradca", "ekodoradca", 35, head=3, deprel="xcomp"),
            word(7, "w", "w", 46, head=8, deprel="case", upos="ADP"),
            word(8, "Urzędzie", "urząd", 48, head=3, deprel="obl"),
            word(9, "Gminy", "gmina", 56, head=8, deprel="nmod"),
        ],
    )
    document.clusters[0].is_proxy_person = True

    attribution = resolve_public_employment_attribution(
        document,
        document.clause_units[0],
        config=config,
    )

    assert attribution is not None
    assert attribution.employee.cluster_id == ClusterID("cluster-0")
    assert attribution.role_cluster is not None
    assert attribution.role_cluster.cluster_id == ClusterID("cluster-1")
    assert attribution.employer.cluster_id == ClusterID("cluster-2")


def test_public_employment_frame_extracts_copular_director_status() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Agnieszka Królikowska w OUW jest dyrektorem generalnym."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-director-status",
        text=text,
        entities=[
            ("Agnieszka Królikowska", EntityType.PERSON, "Agnieszka Królikowska"),
            ("OUW", EntityType.PUBLIC_INSTITUTION, "Opolski Urząd Wojewódzki"),
        ],
        parsed_words=[
            word(1, "Agnieszka", "Agnieszka", 0, head=4, deprel="nsubj", upos="PROPN"),
            word(2, "Królikowska", "Królikowska", 10, head=1, deprel="flat", upos="PROPN"),
            word(3, "OUW", "ouw", 25, head=4, deprel="obl", upos="PROPN"),
            word(4, "jest", "być", 29, upos="AUX"),
            word(5, "dyrektorem", "dyrektor", 34, head=4, deprel="xcomp"),
            word(6, "generalnym", "generalny", 45, head=5, deprel="amod"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)

    assert document.public_employment_frames
    assert document.public_employment_frames[0].role_label == "Dyrektor Generalny"


def test_public_employment_frame_extracts_stanowisko_specialist_status() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Dariusz Jurek pracuje na stanowisku głównego specjalisty w Urzędzie Marszałkowskim."
    document = prepared_single_clause_document(
        document_id="doc-public-employment-specialist-status",
        text=text,
        entities=[
            ("Dariusz Jurek", EntityType.PERSON, "Dariusz Jurek"),
            (
                "Urzędzie Marszałkowskim",
                EntityType.PUBLIC_INSTITUTION,
                "Urząd Marszałkowski",
            ),
        ],
        parsed_words=[
            word(1, "Dariusz", "Dariusz", 0, head=3, deprel="nsubj", upos="PROPN"),
            word(2, "Jurek", "Jurek", 8, head=1, deprel="flat", upos="PROPN"),
            word(3, "pracuje", "pracować", 14, upos="VERB"),
            word(4, "na", "na", 22, head=5, deprel="case", upos="ADP"),
            word(5, "stanowisku", "stanowisko", 25, head=3, deprel="obl"),
            word(6, "głównego", "główny", 37, head=7, deprel="amod"),
            word(7, "specjalisty", "specjalista", 45, head=5, deprel="nmod"),
            word(8, "w", "w", 57, head=9, deprel="case", upos="ADP"),
            word(9, "Urzędzie", "urząd", 59, head=3, deprel="obl"),
            word(10, "Marszałkowskim", "marszałkowski", 67, head=9, deprel="amod"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)

    assert document.public_employment_frames
    assert document.public_employment_frames[0].role_label == "Główny Specjalista"


def test_public_employment_frame_ignores_wojewoda_decision_as_role_label() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Anna Nowak pracuje w Urzędzie Wojewódzkim. To suwerenna decyzja wojewody."
    document = ArticleDocument(
        document_id=DocumentID("doc-public-employment-negative-role-label"),
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
    person = EntityID("person-anna")
    org = EntityID("org-urzad")
    person_mention = ClusterMention(
        text="Anna Nowak",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=10,
        entity_id=person,
    )
    org_start = text.index("Urzędzie")
    org_mention = ClusterMention(
        text="Urzędzie Wojewódzkim",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        sentence_index=0,
        paragraph_index=0,
        start_char=org_start,
        end_char=org_start + len("Urzędzie Wojewódzkim"),
        entity_id=org,
    )
    document.entities = [
        Entity(person, EntityType.PERSON, "Anna Nowak", "Anna Nowak"),
        Entity(
            org,
            EntityType.PUBLIC_INSTITUTION,
            "Urząd Wojewódzki",
            "Urząd Wojewódzki",
            organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
        ),
    ]
    document.clusters = [
        EntityCluster(
            ClusterID("cluster-person"),
            EntityType.PERSON,
            "Anna Nowak",
            "Anna Nowak",
            [person_mention],
        ),
        EntityCluster(
            ClusterID("cluster-org"),
            EntityType.PUBLIC_INSTITUTION,
            "Urząd Wojewódzki",
            "Urząd Wojewódzki",
            [org_mention],
            organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
        ),
    ]
    document.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-negative-role-label"),
            text=text,
            trigger_head_text="pracuje",
            trigger_head_lemma="pracować",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=[person_mention, org_mention],
        )
    ]
    document.parsed_sentences = {
        0: [
            word(1, "Anna", "Anna", 0, head=3, deprel="nsubj", upos="PROPN"),
            word(2, "Nowak", "Nowak", 5, head=1, deprel="flat", upos="PROPN"),
            word(3, "pracuje", "pracować", 11, upos="VERB"),
            word(4, "Urzędzie", "urząd", org_start, head=3, deprel="obl"),
            word(5, "Wojewódzkim", "wojewódzki", org_start + 8, head=4, deprel="amod"),
            word(6, "decyzja", "decyzja", text.index("decyzja"), head=3, deprel="parataxis"),
            word(7, "wojewody", "wojewoda", text.index("wojewody"), head=6, deprel="nmod"),
        ]
    }

    document = PolishFrameExtractor(config).run(document)

    assert document.public_employment_frames
    assert document.public_employment_frames[0].role_label is None


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
    extracted = PolishFactExtractor(config).run(document)

    contracts = [fact for fact in extracted.facts if fact.fact_type == FactType.PUBLIC_CONTRACT]
    assert len(contracts) == 2
    assert {fact.object_entity_id for fact in contracts} == {
        EntityID("entity-1"),
        EntityID("entity-2"),
    }
    assert {fact.amount_text for fact in contracts} == {"397 496,95 Zł"}


def test_paid_promotion_public_money_flow_emits_public_contract() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Fundacja założona przez Karola Bielskiego otrzymała 100 tysięcy złotych "
        "z urzędu marszałkowskiego za promowanie wydarzenia."
    )
    document = prepared_single_clause_document(
        document_id="doc-paid-promotion-contract",
        text=text,
        entities=[("Karola Bielskiego", EntityType.PERSON, "Karol Bielski")],
        parsed_words=[
            word(1, "Fundacja", "fundacja", 0, head=5, deprel="nsubj"),
            word(2, "założona", "założyć", 9, head=1, deprel="acl"),
            word(3, "przez", "przez", 18, head=4, deprel="case"),
            word(4, "Karola", "Karol", 24, head=2, deprel="obl", upos="PROPN"),
            word(5, "otrzymała", "otrzymać", text.index("otrzymała"), upos="VERB"),
            word(6, "urzędu", "urząd", text.index("urzędu"), head=5, deprel="obl"),
            word(7, "marszałkowskiego", "marszałkowski", text.index("marszałkowskiego")),
            word(8, "promowanie", "promowanie", text.index("promowanie")),
        ],
    )

    SharedEntityEnricher(config).run(document)
    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document)

    contracts = [fact for fact in extracted.facts if fact.fact_type == FactType.PUBLIC_CONTRACT]
    assert len(contracts) == 1
    assert contracts[0].value_normalized == "100 Tysięcy Złotych"
    assert "Fundacja" in next(
        entity.canonical_name
        for entity in extracted.entities
        if entity.entity_id == contracts[0].subject_entity_id
    )
    assert "Urząd Marszałkowski" in next(
        entity.canonical_name
        for entity in extracted.entities
        if entity.entity_id == contracts[0].object_entity_id
    )


def test_public_contract_detects_zlecenia_with_amount_from_public_company() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Firma Bartosza Kopani otrzymywała od miejskiej spółki Gamma zlecenia "
        "warte ponad 100 tys. zł."
    )
    document = prepared_single_clause_document(
        document_id="doc-zlecenia-contract",
        text=text,
        entities=[
            ("Firma Bartosza Kopani", EntityType.ORGANIZATION, "Firma Bartosza Kopani"),
            ("miejskiej spółki Gamma", EntityType.ORGANIZATION, "Miejska Spółka Gamma"),
        ],
        parsed_words=[
            word(1, "Firma", "firma", 0, head=3, deprel="nsubj"),
            word(2, "Kopani", "Kopania", text.index("Kopani"), head=1, deprel="nmod"),
            word(3, "otrzymywała", "otrzymywać", text.index("otrzymywała"), upos="VERB"),
            word(4, "spółki", "spółka", text.index("spółki"), head=3, deprel="obl"),
            word(5, "zlecenia", "zlecenie", text.index("zlecenia"), head=3, deprel="obj"),
        ],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document)

    contracts = [fact for fact in extracted.facts if fact.fact_type == FactType.PUBLIC_CONTRACT]
    assert len(contracts) == 1
    assert contracts[0].value_text == "ponad 100 tys. zł"
    assert contracts[0].subject_entity_id == EntityID("entity-0")
    assert contracts[0].object_entity_id == EntityID("entity-1")


def test_generic_contract_sentence_without_parties_does_not_emit_public_contract() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Wszystkie umowy zawierane są zgodnie z prawem."
    document = prepared_single_clause_document(
        document_id="doc-contract-negative",
        text=text,
        entities=[],
    )

    document = PolishFrameExtractor(config).run(document)
    extracted = PolishFactExtractor(config).run(document)

    assert not any(fact.fact_type == FactType.PUBLIC_CONTRACT for fact in extracted.facts)


def test_zalozona_does_not_trigger_family_tie() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Fundacja założona przez Karola Bielskiego otrzymała środki od Adama Struzika."
    document = prepared_single_clause_document(
        document_id="doc-zalozona-no-wife",
        text=text,
        entities=[
            ("Karola Bielskiego", EntityType.PERSON, "Karol Bielski"),
            ("Adama Struzika", EntityType.PERSON, "Adam Struzik"),
        ],
        parsed_words=[
            word(1, "Fundacja", "fundacja", 0, head=5, deprel="nsubj"),
            word(2, "założona", "założyć", 9, head=1, deprel="acl"),
            word(3, "Karola", "Karol", text.index("Karola"), upos="PROPN"),
            word(4, "Bielskiego", "Bielski", text.index("Bielskiego"), upos="PROPN"),
            word(5, "otrzymała", "otrzymać", text.index("otrzymała"), upos="VERB"),
            word(6, "Adama", "Adam", text.index("Adama"), upos="PROPN"),
            word(7, "Struzika", "Struzik", text.index("Struzika"), upos="PROPN"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document)

    assert not any(
        fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
        and fact.relationship_type == RelationshipType.FAMILY
        for fact in extracted.facts
    )


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

    extracted = PolishFactExtractor(config).run(document)

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


def test_patronage_complaint_context_emits_tie_without_article_specific_name_patch() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Radna Dorota Połedniok napisała, że w mieście trwa kolesiostwo i rozdawanie posad, "
        "a prezydent Jacek Guza buduje koalicję dla członków swojej ekipy."
    )
    document = prepared_single_clause_document(
        document_id="doc-patronage-complaint",
        text=text,
        entities=[
            ("Dorota Połedniok", EntityType.PERSON, "Dorota Połedniok"),
            ("Jacek Guza", EntityType.PERSON, "Jacek Guza"),
        ],
        parsed_words=[
            word(1, "Radna", "radna", text.index("Radna"), upos="NOUN"),
            word(2, "Dorota", "Dorota", text.index("Dorota"), upos="PROPN"),
            word(3, "Połedniok", "Połedniok", text.index("Połedniok"), upos="PROPN"),
            word(4, "napisała", "napisać", text.index("napisała"), upos="VERB"),
            word(5, "prezydent", "prezydent", text.index("prezydent"), upos="NOUN"),
            word(6, "Jacek", "Jacek", text.index("Jacek"), upos="PROPN"),
            word(7, "Guza", "Guza", text.index("Guza"), upos="PROPN"),
        ],
    )

    extracted = PolishFactExtractor(config).run(document)

    ties = [
        fact for fact in extracted.facts if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
    ]
    assert ties
    assert any(
        fact.subject_entity_id == EntityID("entity-0")
        and fact.object_entity_id == EntityID("entity-1")
        for fact in ties
    )
