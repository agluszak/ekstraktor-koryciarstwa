from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    ClauseID,
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FactType,
    FrameID,
    GovernanceSignal,
    NERLabel,
    OrganizationKind,
)
from pipeline.domains.compensation import CompensationFactBuilder, PolishCompensationFrameExtractor
from pipeline.domains.funding import FundingFactBuilder, PolishFundingFrameExtractor
from pipeline.domains.governance import GovernanceFactBuilder, GovernanceTargetResolver
from pipeline.domains.governance_frames import PolishGovernanceFrameExtractor
from pipeline.extraction_context import ExtractionContext
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    CompensationFrame,
    Entity,
    EntityCluster,
    EvidenceSpan,
    FundingFrame,
    GovernanceFrame,
    Mention,
    ParsedWord,
    SentenceFragment,
    TemporalExpression,
)


def cluster(
    cluster_id: str,
    name: str,
    entity_type: EntityType = EntityType.ORGANIZATION,
    *,
    sentence_index: int = 0,
    start_char: int = 0,
    end_char: int | None = None,
    entity_id: str | None = None,
    organization_kind: OrganizationKind | None = None,
) -> EntityCluster:
    return EntityCluster(
        cluster_id=ClusterID(cluster_id),
        entity_type=entity_type,
        canonical_name=name,
        normalized_name=name,
        mentions=[
            ClusterMention(
                text=name,
                entity_type=entity_type,
                sentence_index=sentence_index,
                paragraph_index=0,
                start_char=start_char,
                end_char=end_char if end_char is not None else start_char + len(name),
                entity_id=EntityID(entity_id)
                if entity_id
                else EntityID(cluster_id.replace("cluster-", "entity-")),
            )
        ],
        aliases=[name],
        organization_kind=organization_kind,
    )


def clause(text: str = "Jan został prezesem spółki.") -> ClauseUnit:
    return ClauseUnit(
        clause_id=ClauseID("clause-1"),
        text=text,
        trigger_head_text="został",
        trigger_head_lemma="zostać",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=len(text),
    )


def parsed_word(
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


def document(clusters: list[EntityCluster]) -> ArticleDocument:
    return ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-15",
        cleaned_text="",
        paragraphs=[],
        clusters=clusters,
    )


def test_target_resolver_prefers_stadnina_over_skarb_panstwa() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    target = cluster("cluster-target", "Stadnina Koni Iwno", start_char=20)
    owner = cluster("cluster-owner", "Skarbu Państwa", start_char=50)

    result = resolver.resolve(
        document=document([target, owner]),
        clause=clause("A. Góralczyk została prezeską Stadniny Koni Iwno, spółki Skarbu Państwa."),
        org_clusters=[target, owner],
        role_cluster=None,
    )

    assert result.target_org == target
    assert result.owner_context == owner


def test_target_resolver_rejects_city_context_when_company_target_is_present() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    target = cluster(
        "cluster-target",
        "Polski Holding Nieruchomości",
        start_char=42,
        organization_kind=OrganizationKind.COMPANY,
    )
    city = cluster("cluster-city", "Warszawy", start_char=18)

    result = resolver.resolve(
        document=document([target, city]),
        clause=clause(
            "Marcin Kopania z Warszawy został wicedyrektorem w Polskim Holdingu Nieruchomości."
        ),
        org_clusters=[city, target],
        role_cluster=None,
    )

    assert result.target_org == target


def test_target_resolver_rejects_ner_location_targets() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    location = cluster("cluster-location", "Poznań", EntityType.LOCATION, start_char=30)

    result = resolver.resolve(
        document=document([location]),
        clause=clause("Jan Kowalski z Poznania został dyrektorem."),
        org_clusters=[location],
        role_cluster=None,
    )

    assert result.target_org is None


def test_governance_fact_builder_expands_list_appointments_with_exception() -> None:
    text = (
        "Do rady nadzorczej spółki Alfa powołano Annę Nowak, Piotra Lisa i Ewę "
        "Zielińską. Z wyjątkiem Marka Kota wszyscy kandydaci zostali powołani."
    )
    target = cluster(
        "cluster-target",
        "Spółka Alfa",
        start_char=text.index("spółki Alfa"),
        organization_kind=OrganizationKind.COMPANY,
    )
    anna = cluster(
        "cluster-anna",
        "Anna Nowak",
        EntityType.PERSON,
        start_char=text.index("Annę Nowak"),
        entity_id="entity-anna",
    )
    piotr = cluster(
        "cluster-piotr",
        "Piotr Lis",
        EntityType.PERSON,
        start_char=text.index("Piotra Lisa"),
        entity_id="entity-piotr",
    )
    ewa = cluster(
        "cluster-ewa",
        "Ewa Zielińska",
        EntityType.PERSON,
        start_char=text.index("Ewę Zielińską"),
        entity_id="entity-ewa",
    )
    marek = cluster(
        "cluster-marek",
        "Marek Kot",
        EntityType.PERSON,
        start_char=text.index("Marka Kota"),
        entity_id="entity-marek",
    )
    doc = ArticleDocument(
        document_id=DocumentID("doc-list-governance"),
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
        clusters=[target, anna, piotr, ewa, marek],
    )

    facts = GovernanceFactBuilder().build(doc, ExtractionContext.build(doc))

    assert {fact.subject_entity_id for fact in facts} == {
        EntityID("entity-anna"),
        EntityID("entity-piotr"),
        EntityID("entity-ewa"),
    }
    assert all(fact.fact_type == FactType.APPOINTMENT for fact in facts)
    assert all(fact.object_entity_id == EntityID("entity-target") for fact in facts)
    assert all(fact.role == "rada nadzorcza" for fact in facts)


def test_governance_event_detection_handles_stanza_copular_role_root() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    text = "Anna została prezeską spółki."
    parsed_words = [
        ParsedWord(
            index=1,
            text="Anna",
            lemma="Anna",
            upos="PROPN",
            head=3,
            deprel="nsubj",
            start=0,
            end=4,
        ),
        ParsedWord(
            index=2,
            text="została",
            lemma="zostać",
            upos="AUX",
            head=3,
            deprel="aux",
            start=5,
            end=12,
        ),
        ParsedWord(
            index=3,
            text="prezeską",
            lemma="prezeska",
            upos="NOUN",
            head=0,
            deprel="root",
            start=13,
            end=21,
        ),
    ]

    detected = extractor._detect_signal(
        ClauseUnit(
            clause_id=ClauseID("clause-copular-role"),
            text=text,
            trigger_head_text="prezeską",
            trigger_head_lemma="prezeska",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
        ),
        parsed_words,
    )

    assert detected == GovernanceSignal.APPOINTMENT


def test_governance_event_detection_uses_lemma_for_objac_stanowisko() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    text = "Anna stanowisko objęła w poniedziałek."

    detected = extractor._detect_signal(
        ClauseUnit(
            clause_id=ClauseID("clause-objac-role"),
            text=text,
            trigger_head_text="stanowisko",
            trigger_head_lemma="stanowisko",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
        ),
        [
            parsed_word(1, "Anna", "Anna", 0, head=3, deprel="nsubj", upos="PROPN"),
            parsed_word(2, "stanowisko", "stanowisko", 5),
            parsed_word(3, "objęła", "objąć", 16, head=2, deprel="acl", upos="VERB"),
        ],
    )

    assert detected == GovernanceSignal.APPOINTMENT


def test_governance_event_detection_uses_lemma_for_rezygnacja() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    text = "Anna rezygnację złożyła w poniedziałek."

    detected = extractor._detect_signal(
        ClauseUnit(
            clause_id=ClauseID("clause-resignation"),
            text=text,
            trigger_head_text="rezygnację",
            trigger_head_lemma="rezygnacja",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
        ),
        [
            parsed_word(1, "Anna", "Anna", 0, head=3, deprel="nsubj", upos="PROPN"),
            parsed_word(2, "rezygnację", "rezygnacja", 5),
            parsed_word(3, "złożyła", "złożyć", 16, head=2, deprel="acl", upos="VERB"),
        ],
    )

    assert detected == GovernanceSignal.DISMISSAL


def test_resolve_people_recovers_previous_sentence_appointing_authority() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    previous_text = "Piotr Grzymowicz wybrał kandydata."
    clause_text = "To Jarosław Słoma."
    sentence_break = len(previous_text) + 1
    authority = cluster(
        "cluster-authority",
        "Piotr Grzymowicz",
        EntityType.PERSON,
        sentence_index=0,
        start_char=0,
        end_char=16,
    )
    appointee = cluster(
        "cluster-appointee",
        "Jarosław Słoma",
        EntityType.PERSON,
        sentence_index=1,
        start_char=sentence_break + 3,
        end_char=sentence_break + 17,
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-appointing-authority"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text=f"{previous_text} {clause_text}",
        paragraphs=[f"{previous_text} {clause_text}"],
        sentences=[
            SentenceFragment(
                text=previous_text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(previous_text),
            ),
            SentenceFragment(
                text=clause_text,
                paragraph_index=0,
                sentence_index=1,
                start_char=sentence_break,
                end_char=sentence_break + len(clause_text),
            ),
        ],
        clusters=[authority, appointee],
        parsed_sentences={
            0: [
                parsed_word(1, "Piotr", "Piotr", 0, head=3, deprel="nsubj", upos="PROPN"),
                parsed_word(2, "Grzymowicz", "Grzymowicz", 6, head=1, deprel="flat", upos="PROPN"),
                parsed_word(3, "wybrał", "wybrać", 17, upos="VERB"),
                parsed_word(4, "kandydata", "kandydat", 24, head=3, deprel="obj"),
            ],
            1: [
                parsed_word(1, "To", "to", 0, head=2, deprel="expl"),
                parsed_word(2, "Jarosław", "Jarosław", 3, head=0, deprel="root", upos="PROPN"),
                parsed_word(3, "Słoma", "Słoma", 12, head=2, deprel="flat", upos="PROPN"),
            ],
        },
    )
    clause = ClauseUnit(
        clause_id=ClauseID("clause-appointing-authority"),
        text=clause_text,
        trigger_head_text="Jarosław",
        trigger_head_lemma="objąć",
        sentence_index=1,
        paragraph_index=0,
        start_char=sentence_break,
        end_char=sentence_break + len(clause_text),
        cluster_mentions=[appointee.mentions[0]],
    )

    person_cluster_id, appointing_authority_id = extractor._resolve_people(
        clause,
        document,
        [appointee],
        GovernanceSignal.APPOINTMENT,
    )

    assert person_cluster_id == appointee.cluster_id
    assert appointing_authority_id == authority.cluster_id


def test_resolve_people_binds_title_only_authority_to_recent_named_holder() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    previous_text = "Prezydent Piotr Grzymowicz mówi o kompetencjach."
    chooser_text = "Prezydent stworzył nowe stanowisko, a kandydata wybrał sam."
    clause_text = "To Jarosław Słoma."
    first_break = len(previous_text) + 1
    second_break = first_break + len(chooser_text) + 1
    authority = cluster(
        "cluster-authority",
        "Piotr Grzymowicz",
        EntityType.PERSON,
        sentence_index=0,
        start_char=10,
        end_char=26,
    )
    appointee = cluster(
        "cluster-appointee",
        "Jarosław Słoma",
        EntityType.PERSON,
        sentence_index=2,
        start_char=second_break + 3,
        end_char=second_break + 17,
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-titled-appointing-authority"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text=f"{previous_text} {chooser_text} {clause_text}",
        paragraphs=[f"{previous_text} {chooser_text} {clause_text}"],
        sentences=[
            SentenceFragment(
                text=previous_text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(previous_text),
            ),
            SentenceFragment(
                text=chooser_text,
                paragraph_index=0,
                sentence_index=1,
                start_char=first_break,
                end_char=first_break + len(chooser_text),
            ),
            SentenceFragment(
                text=clause_text,
                paragraph_index=0,
                sentence_index=2,
                start_char=second_break,
                end_char=second_break + len(clause_text),
            ),
        ],
        clusters=[authority, appointee],
        parsed_sentences={
            0: [
                parsed_word(1, "Prezydent", "prezydent", 0, head=4, deprel="nsubj"),
                parsed_word(2, "Piotr", "Piotr", 10, head=1, deprel="appos", upos="PROPN"),
                parsed_word(3, "Grzymowicz", "Grzymowicz", 16, head=2, deprel="flat", upos="PROPN"),
                parsed_word(4, "mówi", "mówić", 27, upos="VERB"),
            ],
            1: [
                parsed_word(1, "Prezydent", "prezydent", 0, head=2, deprel="nsubj"),
                parsed_word(2, "stworzył", "stworzyć", 10, upos="VERB"),
                parsed_word(3, "stanowisko", "stanowisko", 24, head=2, deprel="obj"),
                parsed_word(4, "kandydata", "kandydat", 38, head=5, deprel="obj"),
                parsed_word(5, "wybrał", "wybrać", 48, head=2, deprel="conj", upos="VERB"),
                parsed_word(6, "sam", "sam", 55, head=5, deprel="obl"),
            ],
            2: [
                parsed_word(1, "To", "to", 0, head=2, deprel="expl"),
                parsed_word(2, "Jarosław", "Jarosław", 3, head=0, deprel="root", upos="PROPN"),
                parsed_word(3, "Słoma", "Słoma", 12, head=2, deprel="flat", upos="PROPN"),
            ],
        },
    )
    clause = ClauseUnit(
        clause_id=ClauseID("clause-titled-appointing-authority"),
        text=clause_text,
        trigger_head_text="Jarosław",
        trigger_head_lemma="objąć",
        sentence_index=2,
        paragraph_index=0,
        start_char=second_break,
        end_char=second_break + len(clause_text),
        cluster_mentions=[appointee.mentions[0]],
    )

    person_cluster_id, appointing_authority_id = extractor._resolve_people(
        clause,
        document,
        [appointee],
        GovernanceSignal.APPOINTMENT,
    )

    assert person_cluster_id == appointee.cluster_id
    assert appointing_authority_id == authority.cluster_id


def test_target_resolver_prefers_company_over_ministry_owner() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    target = cluster("cluster-target", "Rewita Hoteli", start_char=30)
    owner = cluster("cluster-owner", "Ministerstwo Obrony Narodowej", start_char=60)

    result = resolver.resolve(
        document=document([target, owner]),
        clause=clause("Marcin Horyń został dyrektorem Rewita Hoteli, spółki podległej MON."),
        org_clusters=[target, owner],
        role_cluster=None,
    )

    assert result.target_org == target
    assert result.owner_context == owner


def test_target_resolver_rejects_generic_polska_for_totalizator() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    totalizator = cluster("cluster-target", "Totalizator Sportowy", start_char=20)
    polska = cluster("cluster-polska", "Polska", start_char=45)

    result = resolver.resolve(
        document=document([totalizator, polska]),
        clause=clause("Adam Sekuła został dyrektorem Totalizatora Sportowego w Polsce."),
        org_clusters=[polska, totalizator],
        role_cluster=None,
    )

    assert result.target_org == totalizator


def test_target_resolver_does_not_use_party_as_target() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    party = cluster("cluster-party", "Polskie Stronnictwo Ludowe", start_char=20)

    result = resolver.resolve(
        document=document([party]),
        clause=clause("Jan Kowalski z PSL został powołany."),
        org_clusters=[party],
        role_cluster=None,
    )

    assert result.target_org is None


def test_target_resolver_prefers_lubelskie_koleje_over_wojewodztwo_context() -> None:
    config = PipelineConfig.from_file("config.yaml")
    resolver = GovernanceTargetResolver(config)
    text = (
        "Marszałek województwa lubelskiego z PiS do rady nadzorczej spółki "
        "Lubelskie Koleje powołał Sylwię Sobolewską."
    )
    owner_start = text.index("województwa lubelskiego")
    owner = cluster(
        "cluster-owner",
        "Województwo Lubelskie",
        EntityType.PUBLIC_INSTITUTION,
        start_char=owner_start,
        end_char=owner_start + len("województwa lubelskiego"),
        organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
    )
    target_start = text.index("Lubelskie Koleje")
    target = cluster(
        "cluster-target",
        "Lubelskie Koleje",
        start_char=target_start,
        end_char=target_start + len("Lubelskie Koleje"),
        organization_kind=OrganizationKind.COMPANY,
    )
    body_start = text.index("rady nadzorczej")
    body = cluster(
        "cluster-body",
        "Rada Nadzorcza",
        start_char=body_start,
        end_char=body_start + len("rady nadzorczej"),
        organization_kind=OrganizationKind.GOVERNING_BODY,
    )
    doc = document([owner, target, body])
    doc.cleaned_text = text

    result = resolver.resolve(
        document=doc,
        clause=clause(text),
        org_clusters=[owner, body, target],
        role_cluster=None,
    )

    assert result.target_org == target
    assert result.owner_context == owner
    assert result.governing_body == body


def test_governance_frame_assembler_joins_split_sentence_appointment() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie. "
        "Teraz awansowała na stanowisko prezesa zarządu. "
        "Chodzi o Stadninę Koni Iwno, spółkę Skarbu Państwa."
    )
    person = cluster("cluster-person", "A. Góralczyk", EntityType.PERSON, sentence_index=0)
    target_start = text.index("Stadninę Koni Iwno")
    target = cluster(
        "cluster-target",
        "Stadnina Koni Iwno",
        sentence_index=2,
        start_char=target_start,
        end_char=target_start + len("Stadninę Koni Iwno"),
    )
    owner_start = text.index("Skarbu Państwa")
    owner = cluster(
        "cluster-owner",
        "Skarbu Państwa",
        sentence_index=2,
        start_char=owner_start,
    )
    doc = document([person, target, owner])
    doc.cleaned_text = text
    doc.paragraphs = [text]
    sentence_texts = [
        "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie.",
        "Teraz awansowała na stanowisko prezesa zarządu.",
        "Chodzi o Stadninę Koni Iwno, spółkę Skarbu Państwa.",
    ]
    doc.sentences = [
        SentenceFragment(
            text=sentence_text,
            paragraph_index=0,
            sentence_index=sentence_index,
            start_char=text.index(sentence_text),
            end_char=text.index(sentence_text) + len(sentence_text),
        )
        for sentence_index, sentence_text in enumerate(sentence_texts)
    ]
    role_start = doc.sentences[1].text.index("prezesa")
    doc.parsed_sentences = {
        1: [
            ParsedWord(
                1,
                "prezesa",
                "prezes",
                "NOUN",
                0,
                "root",
                role_start,
                role_start + len("prezesa"),
            )
        ]
    }
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-appointment"),
            text=doc.sentences[1].text,
            trigger_head_text="awansowała",
            trigger_head_lemma="awansować",
            sentence_index=1,
            paragraph_index=0,
            start_char=doc.sentences[1].start_char,
            end_char=doc.sentences[1].end_char,
            cluster_mentions=[],
        )
    ]

    extracted = PolishGovernanceFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert len(extracted.governance_frames) == 1
    frame = extracted.governance_frames[0]
    assert frame.person_cluster_id == "cluster-person"
    assert frame.target_org_cluster_id == "cluster-target"
    assert frame.owner_context_cluster_id == "cluster-owner"
    assert frame.found_role == "Prezes"
    assert frame.evidence_scope == "discourse_window"
    assert {evidence.sentence_index for evidence in frame.evidence} == {0, 1, 2}


def test_governance_frame_assembler_joins_split_sentence_dismissal() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Odwołano poprzedniego prezesa. Był nim Przemysław Pacia. Chodzi o Stadninę Koni Iwno."
    person_start = text.index("Przemysław Pacia")
    person = cluster(
        "cluster-person",
        "Przemysław Pacia",
        EntityType.PERSON,
        sentence_index=1,
        start_char=person_start,
    )
    target_start = text.index("Stadninę Koni Iwno")
    target = cluster(
        "cluster-target",
        "Stadnina Koni Iwno",
        sentence_index=2,
        start_char=target_start,
        end_char=target_start + len("Stadninę Koni Iwno"),
    )
    doc = document([person, target])
    doc.cleaned_text = text
    doc.paragraphs = [text]
    sentence_texts = [
        "Odwołano poprzedniego prezesa.",
        "Był nim Przemysław Pacia.",
        "Chodzi o Stadninę Koni Iwno.",
    ]
    doc.sentences = [
        SentenceFragment(
            text=sentence_text,
            paragraph_index=0,
            sentence_index=sentence_index,
            start_char=text.index(sentence_text),
            end_char=text.index(sentence_text) + len(sentence_text),
        )
        for sentence_index, sentence_text in enumerate(sentence_texts)
    ]
    role_start = doc.sentences[0].text.index("prezesa")
    doc.parsed_sentences = {
        0: [
            ParsedWord(
                1,
                "prezesa",
                "prezes",
                "NOUN",
                0,
                "root",
                role_start,
                role_start + len("prezesa"),
            )
        ]
    }
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-dismissal"),
            text=doc.sentences[0].text,
            trigger_head_text="Odwołano",
            trigger_head_lemma="odwołać",
            sentence_index=0,
            paragraph_index=0,
            start_char=doc.sentences[0].start_char,
            end_char=doc.sentences[0].end_char,
            cluster_mentions=[],
        )
    ]

    extracted = PolishGovernanceFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert len(extracted.governance_frames) == 1
    frame = extracted.governance_frames[0]
    assert frame.signal == GovernanceSignal.DISMISSAL
    assert frame.person_cluster_id == "cluster-person"
    assert frame.target_org_cluster_id == "cluster-target"
    assert frame.found_role == "Prezes"


def test_clusterer_preserves_mention_span_and_paragraph_provenance() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Pierwszy akapit.\n\nDrugi akapit wymienia Stadninę Koni Iwno."
    start = text.index("Stadninę Koni Iwno")
    doc = ArticleDocument(
        document_id=DocumentID("doc-provenance"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=["Pierwszy akapit.", "Drugi akapit wymienia Stadninę Koni Iwno."],
        sentences=[
            SentenceFragment(
                text="Pierwszy akapit.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=15,
            ),
            SentenceFragment(
                text="Drugi akapit wymienia Stadninę Koni Iwno.",
                paragraph_index=1,
                sentence_index=1,
                start_char=17,
                end_char=len(text),
            ),
        ],
        entities=[
            Entity(
                entity_id=EntityID("org-1"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Stadnina Koni Iwno",
                normalized_name="Stadnina Koni Iwno",
            )
        ],
        mentions=[
            Mention(
                text="Stadninę Koni Iwno",
                normalized_text="Stadnina Koni Iwno",
                mention_type="Organization",
                sentence_index=1,
                paragraph_index=1,
                start_char=start,
                end_char=start + len("Stadninę Koni Iwno"),
                entity_id=EntityID("org-1"),
                ner_label=NERLabel.ORGANIZATION,
            )
        ],
    )

    from pipeline.clustering import PolishEntityClusterer

    clustered = PolishEntityClusterer(config).run(doc)

    mention = clustered.clusters[0].mentions[0]
    assert mention.paragraph_index == 1
    assert mention.start_char == start
    assert mention.end_char == start + len("Stadninę Koni Iwno")
    assert mention.ner_label == NERLabel.ORGANIZATION


def test_governance_fact_builder_merges_duplicate_roleless_fact() -> None:
    person = cluster(
        "cluster-person",
        "Jan Kowalski",
        EntityType.PERSON,
        entity_id=EntityID("person-1"),
    )
    organization = cluster("cluster-org", "AMW Rewita", entity_id=EntityID("org-1"))
    role = cluster(
        "cluster-role",
        "Wiceprezes",
        EntityType.POSITION,
        entity_id=EntityID("position-1"),
    )
    doc = document([person, organization, role])
    doc.governance_frames = [
        GovernanceFrame(
            frame_id=FrameID("frame-roleless"),
            signal=GovernanceSignal.APPOINTMENT,
            person_cluster_id=person.cluster_id,
            target_org_cluster_id=organization.cluster_id,
            confidence=0.7,
            evidence=[EvidenceSpan(text="Jan trafił do AMW Rewita.", paragraph_index=0)],
        ),
        GovernanceFrame(
            frame_id=FrameID("frame-role"),
            signal=GovernanceSignal.APPOINTMENT,
            person_cluster_id=person.cluster_id,
            role_cluster_id=role.cluster_id,
            target_org_cluster_id=organization.cluster_id,
            confidence=0.8,
            evidence=[
                EvidenceSpan(
                    text="Jan został wiceprezesem AMW Rewita.",
                    paragraph_index=0,
                )
            ],
        ),
    ]

    facts = GovernanceFactBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].value_text == "Wiceprezes"
    assert facts[0].position_entity_id == "position-1"
    assert facts[0].confidence == 0.8


def test_governance_fact_builder_prefers_local_event_date_from_evidence() -> None:
    person = cluster(
        "cluster-person",
        "Jarosław Słoma",
        EntityType.PERSON,
        entity_id=EntityID("person-1"),
    )
    organization = cluster("cluster-org", "PWiK Olsztyn", entity_id=EntityID("org-1"))
    role = cluster(
        "cluster-role",
        "Wiceprezes",
        EntityType.POSITION,
        entity_id=EntityID("position-1"),
    )
    doc = document([person, organization, role])
    doc.publication_date = "2019-03-22"
    doc.governance_frames = [
        GovernanceFrame(
            frame_id=FrameID("frame-date"),
            signal=GovernanceSignal.APPOINTMENT,
            person_cluster_id=person.cluster_id,
            role_cluster_id=role.cluster_id,
            target_org_cluster_id=organization.cluster_id,
            confidence=0.9,
            evidence=[
                EvidenceSpan(
                    text="Jarosław Słoma od 25 lutego zajął funkcję wiceprezesa PWiK Olsztyn.",
                    paragraph_index=0,
                )
            ],
        )
    ]

    facts = GovernanceFactBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].event_date == "2019-02-25"


def test_governance_fact_builder_recovers_titled_appointing_authority_from_evidence() -> None:
    person = cluster(
        "cluster-person",
        "Jarosław Słoma",
        EntityType.PERSON,
        sentence_index=0,
        entity_id=EntityID("person-1"),
    )
    authority = cluster(
        "cluster-authority",
        "Piotr Grzymowicz",
        EntityType.PERSON,
        sentence_index=1,
        start_char=114,
        end_char=130,
        entity_id=EntityID("person-2"),
    )
    organization = cluster(
        "cluster-org",
        "PWiK Olsztyn",
        sentence_index=0,
        start_char=90,
        entity_id=EntityID("org-1"),
    )
    role = cluster(
        "cluster-role",
        "Wiceprezes",
        EntityType.POSITION,
        sentence_index=0,
        start_char=60,
        entity_id=EntityID("position-1"),
    )
    doc = document([person, authority, organization, role])
    doc.sentences = [
        SentenceFragment(
            text="Jarosław Słoma od 25 lutego zajął funkcję wiceprezesa PWiK Olsztyn.",
            paragraph_index=0,
            sentence_index=0,
            start_char=0,
            end_char=66,
        ),
        SentenceFragment(
            text=(
                "WodKan mówi o ciągłości zarządzania, prezydent Piotr Grzymowicz "
                "o wysokich kompetencjach nowego wiceprezesa."
            ),
            paragraph_index=0,
            sentence_index=1,
            start_char=67,
            end_char=180,
        ),
    ]
    doc.parsed_sentences = {
        1: [
            parsed_word(1, "WodKan", "WodKan", 0, head=2, deprel="nsubj", upos="PROPN"),
            parsed_word(2, "mówi", "mówić", 7, upos="VERB"),
            parsed_word(3, "prezydent", "prezydent", 37, head=2, deprel="conj"),
            parsed_word(4, "Piotr", "Piotr", 47, head=3, deprel="appos", upos="PROPN"),
            parsed_word(5, "Grzymowicz", "Grzymowicz", 53, head=4, deprel="flat", upos="PROPN"),
        ]
    }
    doc.governance_frames = [
        GovernanceFrame(
            frame_id=FrameID("frame-authority"),
            signal=GovernanceSignal.APPOINTMENT,
            person_cluster_id=person.cluster_id,
            role_cluster_id=role.cluster_id,
            target_org_cluster_id=organization.cluster_id,
            confidence=0.9,
            evidence=[
                EvidenceSpan(
                    text="Jarosław Słoma od 25 lutego zajął funkcję wiceprezesa PWiK Olsztyn.",
                    paragraph_index=0,
                    sentence_index=0,
                    start_char=0,
                    end_char=66,
                ),
                EvidenceSpan(
                    text=(
                        "WodKan mówi o ciągłości zarządzania, prezydent Piotr Grzymowicz "
                        "o wysokich kompetencjach nowego wiceprezesa."
                    ),
                    paragraph_index=0,
                    sentence_index=1,
                    start_char=67,
                    end_char=180,
                ),
            ],
        )
    ]

    facts = GovernanceFactBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].appointing_authority_entity_id == EntityID("person-2")


def test_compensation_fact_builder_emits_person_org_salary_fact() -> None:
    person = cluster(
        "cluster-person",
        "Łukasz Bałajewicz",
        EntityType.PERSON,
        entity_id=EntityID("person-1"),
    )
    organization = cluster("cluster-org", "KZN", entity_id=EntityID("org-1"))
    role = cluster("cluster-role", "Prezes", EntityType.POSITION, entity_id=EntityID("position-1"))
    doc = document([person, organization, role])
    doc.compensation_frames = [
        CompensationFrame(
            frame_id=FrameID("comp-frame-1"),
            amount_text="31 tys. zł brutto",
            amount_normalized="31 Tys. Zł Brutto",
            period="Miesięcznie",
            person_cluster_id=person.cluster_id,
            role_cluster_id=role.cluster_id,
            organization_cluster_id=organization.cluster_id,
            confidence=0.85,
            evidence=[
                EvidenceSpan(
                    text="Łukasz Bałajewicz zarabia miesięcznie ponad 31 tys. zł brutto.",
                    paragraph_index=0,
                )
            ],
            extraction_signal="syntactic_direct",
            evidence_scope="same_clause",
            score_reason="person_amount_role_org_same_clause",
        )
    ]

    facts = CompensationFactBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].fact_type == "COMPENSATION"
    assert facts[0].subject_entity_id == "person-1"
    assert facts[0].object_entity_id == "org-1"
    assert facts[0].position_entity_id == "position-1"
    assert facts[0].source_extractor == "compensation_frame"


def test_compensation_fact_builder_prefers_preserved_temporal_expression() -> None:
    person = cluster(
        "cluster-person",
        "Łukasz Bałajewicz",
        EntityType.PERSON,
        entity_id=EntityID("person-1"),
    )
    organization = cluster("cluster-org", "KZN", entity_id=EntityID("org-1"))
    doc = document([person, organization])
    doc.publication_date = "2019-03-22"
    doc.temporal_expressions = [
        TemporalExpression(
            text="25 lut.",
            label=NERLabel.DATE,
            normalized_value="2019-02-25",
            sentence_index=0,
            paragraph_index=0,
            start_char=24,
            end_char=31,
        )
    ]
    doc.compensation_frames = [
        CompensationFrame(
            frame_id=FrameID("comp-frame-date"),
            amount_text="31 tys. zł brutto",
            amount_normalized="31 Tys. Zł Brutto",
            period="Miesięcznie",
            person_cluster_id=person.cluster_id,
            organization_cluster_id=organization.cluster_id,
            confidence=0.85,
            evidence=[
                EvidenceSpan(
                    text="Łukasz Bałajewicz od 25 lut. zarabia 31 tys. zł brutto.",
                    sentence_index=0,
                    paragraph_index=0,
                    start_char=0,
                    end_char=58,
                )
            ],
            extraction_signal="syntactic_direct",
            evidence_scope="same_clause",
            score_reason="person_amount_org_same_clause",
        )
    ]

    facts = CompensationFactBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].event_date == "2019-02-25"


def test_compensation_frame_extractor_ignores_funding_amounts() -> None:
    config = PipelineConfig.from_file("config.yaml")
    fundacja = cluster("cluster-org", "Fundacja Lux Veritatis", entity_id=EntityID("org-1"))
    doc = document([fundacja])
    text = "Fundacja dostała 300 tys. zł dotacji na projekt."
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-comp-1"),
            text=text,
            trigger_head_text="dostała",
            trigger_head_lemma="dostać",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=fundacja.mentions,
        )
    ]

    extracted = PolishCompensationFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert extracted.compensation_frames == []


def test_compensation_frame_extractor_emits_role_only_salary_frame() -> None:
    config = PipelineConfig.from_file("config.yaml")
    role = cluster(
        "cluster-role", "Dyrektor", EntityType.POSITION, entity_id=EntityID("position-1")
    )
    org = cluster("cluster-org", "Totalizator Sportowy", entity_id=EntityID("org-1"), start_char=40)
    doc = document([role, org])
    text = "Dyrektorzy Totalizatora Sportowego mogą zarobić ponad 20 tys. zł miesięcznie."
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-comp-2"),
            text=text,
            trigger_head_text="zarobić",
            trigger_head_lemma="zarobić",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=[*role.mentions, *org.mentions],
        )
    ]

    extracted = PolishCompensationFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert len(extracted.compensation_frames) == 1
    assert extracted.compensation_frames[0].role_cluster_id == "cluster-role"
    assert extracted.compensation_frames[0].organization_cluster_id == "cluster-org"
    assert extracted.compensation_frames[0].confidence == 0.66


def test_funding_frame_extractor_emits_grant_frame_without_compensation_frame() -> None:
    config = PipelineConfig.from_file("config.yaml")
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id=EntityID("org-funder"),
    )
    recipient = cluster(
        "cluster-recipient", "Fundacja Lux Veritatis", entity_id=EntityID("org-recipient")
    )
    text = "WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji."
    doc = document([funder, recipient])
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-funding-1"),
            text=text,
            trigger_head_text="przekazał",
            trigger_head_lemma="przekazać",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=[*funder.mentions, *recipient.mentions],
        )
    ]

    doc = PolishCompensationFrameExtractor(config).run(doc, ExtractionContext.build(doc))
    doc = PolishFundingFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert doc.compensation_frames == []
    assert len(doc.funding_frames) == 1
    assert doc.funding_frames[0].funder_cluster_id == "cluster-funder"
    assert doc.funding_frames[0].recipient_cluster_id == "cluster-recipient"
    assert doc.funding_frames[0].amount_normalized == "300 Tys. Zł"


def test_funding_frame_extractor_rejects_reporting_przekazac_with_amount() -> None:
    config = PipelineConfig.from_file("config.yaml")
    source = cluster(
        "cluster-source",
        "Biuro Prasowe",
        EntityType.PUBLIC_INSTITUTION,
        entity_id=EntityID("org-source"),
    )
    recipient = cluster("cluster-recipient", "Redakcja", entity_id=EntityID("org-recipient"))
    text = "Biuro Prasowe przekazało redakcji 300 tys. zł informacji."
    doc = document([source, recipient])
    doc.parsed_sentences = {
        0: [
            parsed_word(1, "Biuro", "biuro", 0, head=3, deprel="nsubj"),
            parsed_word(2, "Prasowe", "prasowy", 6, head=1, deprel="amod", upos="ADJ"),
            parsed_word(3, "przekazało", "przekazać", 14, upos="VERB"),
            parsed_word(4, "redakcji", "redakcja", 25, head=3, deprel="iobj"),
            parsed_word(5, "informacji", "informacja", 46, head=3, deprel="obj"),
        ]
    }
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-funding-reporting"),
            text=text,
            trigger_head_text="przekazało",
            trigger_head_lemma="przekazać",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=[*source.mentions, *recipient.mentions],
        )
    ]

    doc = PolishFundingFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert doc.funding_frames == []


def test_funding_frame_extractor_handles_postposed_funder_with_relative_token_offsets() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "* Po publikacji otrzymaliśmy potwierdzenie z Fundacji Lux Veritatis, "
        "że 100 tys. zł na Park Pamięci wyłożyły także Jastrzębskie Zakłady Remontowe."
    )
    sentence_start = 8000
    recipient_start = sentence_start + text.index("Fundacji Lux Veritatis")
    funder_start = sentence_start + text.index("Jastrzębskie Zakłady Remontowe")
    recipient = cluster(
        "cluster-recipient",
        "Fundacja Lux Veritatis",
        sentence_index=3,
        start_char=recipient_start,
        end_char=recipient_start + len("Fundacji Lux Veritatis"),
        entity_id=EntityID("org-recipient"),
    )
    funder = cluster(
        "cluster-funder",
        "Jastrzębskie Zakłady Remontowe",
        sentence_index=3,
        start_char=funder_start,
        entity_id=EntityID("org-funder"),
    )
    doc = document([recipient, funder])
    doc.parsed_sentences = {
        3: [
            ParsedWord(
                index=1,
                text="wyłożyły",
                lemma="wyłożyć",
                upos="VERB",
                head=0,
                deprel="root",
                start=text.index("wyłożyły"),
                end=text.index("wyłożyły") + len("wyłożyły"),
            )
        ]
    }
    doc.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-funding-2"),
            text=text,
            trigger_head_text="wyłożyły",
            trigger_head_lemma="wyłożyć",
            sentence_index=3,
            paragraph_index=0,
            start_char=sentence_start,
            end_char=sentence_start + len(text),
            cluster_mentions=[*recipient.mentions, *funder.mentions],
        )
    ]

    doc = PolishFundingFrameExtractor(config).run(doc, ExtractionContext.build(doc))

    assert len(doc.funding_frames) == 1
    assert doc.funding_frames[0].funder_cluster_id == "cluster-funder"
    assert doc.funding_frames[0].recipient_cluster_id == "cluster-recipient"


def test_funding_fact_builder_emits_recipient_funded_by_funder_fact() -> None:
    funder = cluster(
        "cluster-funder",
        "WFOŚiGW",
        EntityType.PUBLIC_INSTITUTION,
        entity_id=EntityID("org-funder"),
    )
    recipient = cluster(
        "cluster-recipient", "Fundacja Lux Veritatis", entity_id=EntityID("org-recipient")
    )
    doc = document([funder, recipient])
    doc.funding_frames = [
        FundingFrame(
            frame_id=FrameID("funding-frame-1"),
            amount_text="300 tys. zł",
            amount_normalized="300 Tys. Zł",
            funder_cluster_id=funder.cluster_id,
            recipient_cluster_id=recipient.cluster_id,
            confidence=0.82,
            evidence=[
                EvidenceSpan(
                    text="WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji.",
                    paragraph_index=0,
                )
            ],
            extraction_signal="syntactic_direct",
            evidence_scope="same_clause",
            score_reason="funder_recipient_amount_same_clause",
        )
    ]

    facts = FundingFactBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].fact_type == "FUNDING"
    assert facts[0].subject_entity_id == "org-recipient"
    assert facts[0].object_entity_id == "org-funder"
    assert facts[0].source_extractor == "funding_frame"


def test_resolve_people_treats_passive_subject_as_appointee_not_authority() -> None:
    """In passive appointment sentences ("Jan Kowalski został powołany") the person
    with deprel nsubj:pass is the recipient of the appointment (appointee), not the
    appointing authority.  Before the fix this was mis-classified as an authority
    because the code only checked role.startswith("nsubj")."""
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    text = "Jan Kowalski został powołany na prezesa."
    appointee = cluster(
        "cluster-appointee",
        "Jan Kowalski",
        EntityType.PERSON,
        sentence_index=0,
        start_char=0,
        end_char=12,
    )
    clause_unit = ClauseUnit(
        clause_id=ClauseID("clause-passive"),
        text=text,
        trigger_head_text="powołany",
        trigger_head_lemma="powołać",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=len(text),
        cluster_mentions=[appointee.mentions[0]],
        mention_roles={"Jan Kowalski": "nsubj:pass"},
    )
    doc = ArticleDocument(
        document_id=DocumentID("doc-passive"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        clusters=[appointee],
    )

    person_cluster_id, appointing_authority_id = extractor._resolve_people(
        clause_unit,
        doc,
        [appointee],
        GovernanceSignal.APPOINTMENT,
    )

    assert person_cluster_id == appointee.cluster_id
    assert appointing_authority_id is None


def test_imperfective_strong_trigger_requires_noun_support() -> None:
    """A strong appointment trigger verb with Aspect=Imp should be treated like a weak
    trigger and require an appointment noun in the sentence.  Without the noun it must
    return no signal, because imperfective ('powoływać') describes habitual/background
    processes rather than single completed appointment events."""
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishGovernanceFrameExtractor(config)
    # 'powoływać' is a strong trigger lemma but with Aspect=Imp
    parsed_words_no_noun = [
        ParsedWord(
            index=1,
            text="powoływać",
            lemma="powołać",
            upos="VERB",
            head=0,
            deprel="root",
            start=0,
            end=9,
            feats={"Aspect": "Imp"},
        ),
    ]
    clause_no_noun = ClauseUnit(
        clause_id=ClauseID("clause-imp-no-noun"),
        text="powoływać",
        trigger_head_text="powoływać",
        trigger_head_lemma="powołać",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=9,
    )

    signal_no_noun = extractor._detect_signal(clause_no_noun, parsed_words_no_noun)
    assert signal_no_noun is None, "Imp trigger without noun support should yield no signal"

    # With an appointment noun ('prezes') the imperfective trigger should still fire
    parsed_words_with_noun = [
        ParsedWord(
            index=1,
            text="powoływać",
            lemma="powołać",
            upos="VERB",
            head=0,
            deprel="root",
            start=0,
            end=9,
            feats={"Aspect": "Imp"},
        ),
        ParsedWord(
            index=2,
            text="prezesów",
            lemma="prezes",
            upos="NOUN",
            head=1,
            deprel="obj",
            start=10,
            end=18,
        ),
    ]
    clause_with_noun = ClauseUnit(
        clause_id=ClauseID("clause-imp-noun"),
        text="powoływać prezesów",
        trigger_head_text="powoływać",
        trigger_head_lemma="powołać",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=18,
    )

    signal_with_noun = extractor._detect_signal(clause_with_noun, parsed_words_with_noun)
    assert signal_with_noun == GovernanceSignal.APPOINTMENT, (
        "Imp trigger with appointment noun should still yield APPOINTMENT signal"
    )


def test_przekazac_numeric_dep_object_detects_money_transfer() -> None:
    """_przekazac_has_numeric_dep_object should return True when 'przekazać' has
    a NUM token in its direct dep subtree, and False for a communication context."""
    from pipeline.domains.public_money import _przekazac_has_numeric_dep_object

    # 'przekazał 300 tys. zł' – NUM directly attached to przekazać
    transfer_words = [
        parsed_word(1, "przekazał", "przekazać", 0, upos="VERB"),
        ParsedWord(
            index=2, text="300", lemma="300", upos="NUM", head=1, deprel="obj", start=10, end=13
        ),
        parsed_word(3, "tys", "tysiąc", 14, head=2, deprel="nummod"),
    ]
    assert _przekazac_has_numeric_dep_object(transfer_words) is True

    # 'przekazał nam informacje' – no NUM child of przekazać
    communication_words = [
        parsed_word(1, "przekazał", "przekazać", 0, upos="VERB"),
        parsed_word(2, "nam", "my", 10, head=1, deprel="iobj"),
        parsed_word(3, "informacje", "informacja", 14, head=1, deprel="obj"),
    ]
    assert _przekazac_has_numeric_dep_object(communication_words) is False

    # 'przekazał fundacji 300 tys.' – NUM attached to obj child of przekazać
    grant_words = [
        parsed_word(1, "przekazał", "przekazać", 0, upos="VERB"),
        parsed_word(2, "fundacji", "fundacja", 10, head=1, deprel="iobj"),
        ParsedWord(
            index=3, text="300", lemma="300", upos="NUM", head=2, deprel="nummod", start=19, end=22
        ),
    ]
    assert _przekazac_has_numeric_dep_object(grant_words) is True
