from pipeline.dependency_frames import DependencyArgumentRole
from pipeline.domain_types import ClauseID, ClusterID, DocumentID, EntityID, EntityType
from pipeline.extraction_context import ExtractionContext
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    ParsedWord,
    ResolvedEntity,
)


def cluster(
    cluster_id: str,
    name: str,
    entity_type: EntityType,
    start_char: int,
) -> ResolvedEntity:
    return ResolvedEntity(
        entity_id=EntityID(cluster_id),
        entity_type=entity_type,
        canonical_name=name,
        normalized_name=name.casefold(),
        mentions=[
            ClusterMention(
                text=name,
                entity_type=entity_type,
                sentence_index=0,
                paragraph_index=0,
                start_char=start_char,
                end_char=start_char + len(name),
                entity_id=EntityID(cluster_id.replace("entity-", "entity-")),
            )
        ],
    )


def document(text: str, clusters: list[ResolvedEntity]) -> ArticleDocument:
    return ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        resolved_entities=clusters,
    )


def clause(text: str, trigger: str, lemma: str) -> ClauseUnit:
    return ClauseUnit(
        clause_id=ClauseID("clause-1"),
        text=text,
        trigger_head_text=trigger,
        trigger_head_lemma=lemma,
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=len(text),
    )


def test_dependency_frame_extracts_active_appointment_arguments() -> None:
    text = "Starosta powołał Annę Nowak na prezeskę spółki."
    authority = cluster("entity-authority", "Starosta", EntityType.PERSON, 0)
    appointee = cluster("entity-person", "Annę Nowak", EntityType.PERSON, 17)
    company = cluster("entity-org", "spółki", EntityType.ORGANIZATION, 39)
    doc = document(text, [authority, appointee, company])
    doc.parsed_sentences = {
        0: [
            ParsedWord(1, "Starosta", "starosta", "NOUN", 2, "nsubj", 0, 8),
            ParsedWord(2, "powołał", "powołać", "VERB", 0, "root", 9, 16),
            ParsedWord(3, "Annę", "Anna", "PROPN", 2, "obj", 17, 21),
            ParsedWord(4, "Nowak", "Nowak", "PROPN", 3, "flat", 22, 27),
            ParsedWord(5, "prezeskę", "prezes", "NOUN", 2, "obl", 31, 39),
            ParsedWord(6, "spółki", "spółka", "NOUN", 5, "nmod", 39, 45),
        ]
    }
    doc.clause_units = [clause(text, "powołał", "powołać")]
    doc.clause_units[0].cluster_mentions = [
        *authority.mentions,
        *appointee.mentions,
        *company.mentions,
    ]

    frame = ExtractionContext.build(doc).dependency_frame_for_clause(doc.clause_units[0])

    assert frame is not None
    object_cluster = frame.first_cluster(
        ExtractionContext.build(doc),
        (DependencyArgumentRole.OBJECT,),
        {EntityType.PERSON},
    )
    assert object_cluster is not None
    assert object_cluster.entity_id == ClusterID("entity-person")


def test_dependency_frame_marks_passive_subject() -> None:
    text = "Anna Nowak została powołana na prezeskę spółki."
    person = cluster("entity-person", "Anna Nowak", EntityType.PERSON, 0)
    doc = document(text, [person])
    doc.parsed_sentences = {
        0: [
            ParsedWord(1, "Anna", "Anna", "PROPN", 4, "nsubj:pass", 0, 4),
            ParsedWord(2, "Nowak", "Nowak", "PROPN", 1, "flat", 5, 10),
            ParsedWord(3, "została", "zostać", "AUX", 4, "aux:pass", 11, 18),
            ParsedWord(4, "powołana", "powołać", "VERB", 0, "root", 19, 27),
        ]
    }
    doc.clause_units = [clause(text, "powołana", "powołać")]
    doc.clause_units[0].cluster_mentions = [*person.mentions]

    frame = ExtractionContext.build(doc).dependency_frame_for_clause(doc.clause_units[0])

    assert frame is not None
    passive_subject = frame.first_cluster(
        ExtractionContext.build(doc),
        (DependencyArgumentRole.PASSIVE_SUBJECT,),
        {EntityType.PERSON},
    )
    assert passive_subject is not None
    assert passive_subject.entity_id == ClusterID("entity-person")


def test_dependency_frame_extracts_funding_transfer_arguments_and_money() -> None:
    text = "WFOŚiGW przekazał Fundacji Lux Veritatis 300 tys. zł dotacji."
    funder = cluster("entity-funder", "WFOŚiGW", EntityType.PUBLIC_INSTITUTION, 0)
    recipient = cluster("entity-recipient", "Fundacji Lux Veritatis", EntityType.ORGANIZATION, 17)
    doc = document(text, [funder, recipient])
    doc.parsed_sentences = {
        0: [
            ParsedWord(1, "WFOŚiGW", "WFOŚiGW", "PROPN", 2, "nsubj", 0, 7),
            ParsedWord(2, "przekazał", "przekazać", "VERB", 0, "root", 8, 17),
            ParsedWord(3, "Fundacji", "fundacja", "NOUN", 2, "iobj", 18, 26),
            ParsedWord(4, "Lux", "Lux", "PROPN", 3, "flat", 27, 30),
            ParsedWord(5, "Veritatis", "Veritatis", "PROPN", 3, "flat", 31, 40),
            ParsedWord(6, "dotacji", "dotacja", "NOUN", 2, "obj", 53, 60),
        ]
    }
    doc.clause_units = [clause(text, "przekazał", "przekazać")]
    doc.clause_units[0].cluster_mentions = [*funder.mentions, *recipient.mentions]

    frame = ExtractionContext.build(doc).dependency_frame_for_clause(doc.clause_units[0])

    assert frame is not None
    assert frame.money_transfer_evidence
    assert frame.money_spans[0].text == "300 tys. zł"
    subject = frame.first_cluster(
        ExtractionContext.build(doc),
        (DependencyArgumentRole.SUBJECT,),
        {EntityType.PUBLIC_INSTITUTION},
    )
    assert subject is not None
    assert subject.entity_id == ClusterID("entity-funder")


def test_dependency_frame_marks_reporting_przekazac() -> None:
    text = "Biuro Prasowe przekazało redakcji 300 tys. zł informacji."
    source = cluster("entity-source", "Biuro Prasowe", EntityType.PUBLIC_INSTITUTION, 0)
    doc = document(text, [source])
    doc.parsed_sentences = {
        0: [
            ParsedWord(1, "Biuro", "biuro", "NOUN", 3, "nsubj", 0, 5),
            ParsedWord(2, "Prasowe", "prasowy", "ADJ", 1, "amod", 6, 13),
            ParsedWord(3, "przekazało", "przekazać", "VERB", 0, "root", 14, 24),
            ParsedWord(4, "redakcji", "redakcja", "NOUN", 3, "iobj", 25, 33),
            ParsedWord(5, "informacji", "informacja", "NOUN", 3, "obj", 46, 56),
        ]
    }
    doc.clause_units = [clause(text, "przekazało", "przekazać")]
    doc.clause_units[0].cluster_mentions = [*source.mentions]

    frame = ExtractionContext.build(doc).dependency_frame_for_clause(doc.clause_units[0])

    assert frame is not None
    assert frame.reporting_transfer


def test_dependency_frame_preserves_imperfective_aspect_hint() -> None:
    text = "Rada powoływała prezesa spółki."
    doc = document(text, [])
    doc.parsed_sentences = {
        0: [
            ParsedWord(
                1,
                "powoływała",
                "powoływać",
                "VERB",
                0,
                "root",
                5,
                15,
                feats={"Aspect": "Imp"},
            )
        ]
    }
    doc.clause_units = [clause(text, "powoływała", "powoływać")]

    frame = ExtractionContext.build(doc).dependency_frame_for_clause(doc.clause_units[0])

    assert frame is not None
    assert frame.trigger_aspect == "Imp"
