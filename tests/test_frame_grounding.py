from __future__ import annotations

from pipeline.config import PipelineConfig
from pipeline.domain_types import ClauseID, ClusterID, DocumentID, EntityID, EntityType
from pipeline.enrichment import SharedEntityEnricher
from pipeline.frame_grounding import FrameSlotGrounder
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


def _word(
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


def _document(
    text: str,
    *,
    entities: list[tuple[str, EntityType, str]],
    parsed_words: list[ParsedWord],
) -> ArticleDocument:
    sentence = SentenceFragment(
        text=text,
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len(text),
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-frame-grounding"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[sentence],
        parsed_sentences={0: parsed_words},
    )
    cluster_mentions: list[ClusterMention] = []
    for index, (surface, entity_type, canonical_name) in enumerate(entities):
        start = text.index(surface)
        end = start + len(surface)
        entity_id = EntityID(f"entity-{index}")
        document.entities.append(
            Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                canonical_name=canonical_name,
                normalized_name=canonical_name,
            )
        )
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
    document.clause_units = [
        ClauseUnit(
            clause_id=ClauseID("clause-1"),
            text=text,
            trigger_head_text=parsed_words[0].text if parsed_words else "",
            trigger_head_lemma=parsed_words[0].lemma if parsed_words else "",
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(text),
            cluster_mentions=cluster_mentions,
        )
    ]
    return document


def test_shared_grounding_recovers_person_grounded_foundation_from_money_context() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Fundacja dyrektora warszawskiego pogotowia Karola Bielskiego otrzymała "
        "100 tysięcy złotych z urzędu marszałkowskiego za promowanie wydarzenia."
    )
    document = _document(
        text,
        entities=[("Karola Bielskiego", EntityType.PERSON, "Karol Bielski")],
        parsed_words=[
            _word(1, "Fundacja", "fundacja", 0, head=7, deprel="nsubj"),
            _word(2, "dyrektora", "dyrektor", 9, head=1, deprel="nmod"),
            _word(3, "warszawskiego", "warszawski", 19, head=4, deprel="amod", upos="ADJ"),
            _word(4, "pogotowia", "pogotowie", 32, head=2, deprel="nmod"),
            _word(5, "Karola", "Karol", 42, head=1, deprel="nmod", upos="PROPN"),
            _word(6, "Bielskiego", "Bielski", 49, head=5, deprel="flat", upos="PROPN"),
            _word(7, "otrzymała", "otrzymać", 60, upos="VERB"),
            _word(8, "urzędu", "urząd", text.index("urzędu"), head=7, deprel="obl"),
            _word(
                9,
                "marszałkowskiego",
                "marszałkowski",
                text.index("marszałkowskiego"),
                head=8,
                deprel="amod",
                upos="ADJ",
            ),
        ],
    )

    SharedEntityEnricher(config).run(document)

    assert any(
        cluster.canonical_name == "Fundacja Karola Bielskiego" for cluster in document.clusters
    )
    assert any(cluster.canonical_name == "Urząd Marszałkowski" for cluster in document.clusters)


def test_shared_grounding_normalizes_wojewodzki_office_name() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = (
        "Agnieszka Królikowska została powołana na funkcję Dyrektora Generalnego "
        "Opolskiego Urzędu Wojewódzkiego."
    )
    document = _document(
        text,
        entities=[("Agnieszka Królikowska", EntityType.PERSON, "Agnieszka Królikowska")],
        parsed_words=[
            _word(1, "Agnieszka", "Agnieszka", 0, head=3, deprel="nsubj", upos="PROPN"),
            _word(2, "Królikowska", "Królikowska", 10, head=1, deprel="flat", upos="PROPN"),
            _word(3, "została", "zostać", 22, upos="AUX"),
            _word(4, "powołana", "powołać", 30, head=3, deprel="xcomp", upos="VERB"),
            _word(5, "Dyrektora", "dyrektor", text.index("Dyrektora"), upos="NOUN"),
            _word(6, "Generalnego", "generalny", text.index("Generalnego"), head=5, deprel="amod"),
            _word(7, "Opolskiego", "opolski", text.index("Opolskiego"), head=8, deprel="amod"),
            _word(8, "Urzędu", "urząd", text.index("Urzędu"), head=4, deprel="obl"),
            _word(
                9,
                "Wojewódzkiego",
                "wojewódzki",
                text.index("Wojewódzkiego"),
                head=8,
                deprel="amod",
            ),
        ],
    )

    SharedEntityEnricher(config).run(document)

    assert any(
        cluster.canonical_name == "Opolski Urząd Wojewódzki" for cluster in document.clusters
    )


def test_role_grounder_rejects_person_name_role_phrase() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Anna Nowak pracuje jako Agnieszka Królikowska w urzędzie."
    document = _document(
        text,
        entities=[
            ("Anna Nowak", EntityType.PERSON, "Anna Nowak"),
            ("Agnieszka Królikowska", EntityType.PERSON, "Agnieszka Królikowska"),
        ],
        parsed_words=[
            _word(1, "Anna", "Anna", 0, head=3, deprel="nsubj", upos="PROPN"),
            _word(2, "Nowak", "Nowak", 5, head=1, deprel="flat", upos="PROPN"),
            _word(3, "pracuje", "pracować", 11, upos="VERB"),
            _word(4, "jako", "jako", 19, head=5, deprel="case", upos="SCONJ"),
            _word(5, "Agnieszka", "Agnieszka", 24, head=3, deprel="xcomp", upos="PROPN"),
            _word(6, "Królikowska", "Królikowska", 34, head=5, deprel="flat", upos="PROPN"),
            _word(7, "urzędzie", "urząd", text.index("urzędzie"), head=3, deprel="obl"),
        ],
    )
    grounder = FrameSlotGrounder(config)

    grounded = grounder.ground_public_employment_role(
        document,
        document.clause_units[0],
        employee=document.clusters[0],
        role_cluster=None,
    )

    assert grounded is None


def test_role_grounder_rejects_generic_date_dominated_phrase() -> None:
    config = PipelineConfig.from_file("config.yaml")
    text = "Partnerka wójta dostała pracę jako potrzebna 1 lutego 2024 w urzędzie."
    document = _document(
        text,
        entities=[("Partnerka", EntityType.PERSON, "partnerka wójta")],
        parsed_words=[
            _word(1, "Partnerka", "partnerka", 0, head=3, deprel="nsubj"),
            _word(2, "wójta", "wójt", 10, head=1, deprel="nmod"),
            _word(3, "dostała", "dostać", 16, upos="VERB"),
            _word(4, "pracę", "praca", 24, head=3, deprel="obj"),
            _word(5, "jako", "jako", 30, head=6, deprel="case", upos="SCONJ"),
            _word(6, "potrzebna", "potrzebny", 35, head=3, deprel="xcomp", upos="ADJ"),
            _word(7, "1", "1", 45, head=6, deprel="nummod"),
            _word(8, "lutego", "luty", 47, head=6, deprel="obl"),
            _word(9, "2024", "2024", 54, head=8, deprel="nummod"),
            _word(10, "urzędzie", "urząd", text.index("urzędzie"), head=3, deprel="obl"),
        ],
    )
    grounder = FrameSlotGrounder(config)

    grounded = grounder.ground_public_employment_role(
        document,
        document.clause_units[0],
        employee=document.clusters[0],
        role_cluster=None,
    )

    assert grounded is None
