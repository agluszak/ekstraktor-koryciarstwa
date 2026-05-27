from __future__ import annotations

from pipeline_v2.candidates import FactCandidateRecord
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId, EntityCandidateId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan
from pipeline_v2.nominal_coreference import NominalKinshipCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import FactKind, GroundingKind, NerLabel
from tests_v2.materialized import entity_hint_for_role, fact_records, span_of, text_argument


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_nominal_kinship_stage(
    text: str,
    entities: tuple[NamedEntitySpan, ...],
) -> ArticleDocument:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=(text,),
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)
    NominalKinshipCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
    return document


def person_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.PERSON,
        span=span_of(text, name),
    )


def organization_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=span_of(text, name),
    )


def entity_argument_id(record: FactCandidateRecord, role: str) -> EntityCandidateId:
    argument = next(
        argument.to_json() for argument in record.arguments if argument.to_json()["role"] == role
    )
    return EntityCandidateId(argument["entity_id"])


def test_nominal_kinship_within_40_chars_links_named_referent() -> None:
    text = "Marek Kowalski zatrudnił swoją żonę Annę Nowak w urzędzie."
    document = run_nominal_kinship_stage(
        text,
        (
            person_span(text, "Marek Kowalski"),
            person_span(text, "Annę Nowak"),
        ),
    )
    records = fact_records(document)
    assert len(records) == 1
    record = records[0]
    assert record.kind is FactKind.KINSHIP_TIE
    assert entity_hint_for_role(document, record, "subject") == "Annę Nowak"
    assert entity_hint_for_role(document, record, "object") == "Marek Kowalski"
    assert text_argument(record, "relationship_detail") == "spouse"
    assert text_argument(record, "context") == "żona"


def test_nominal_kinship_beyond_40_chars_creates_proxy_instead() -> None:
    # Janusz Wiśniewski is too far from "żonę", so this should create a proxy.
    text = (
        "Marek Kowalski zatrudnił swoją żonę w firmie, o czym z ogromnym "
        "zadowoleniem poinformował nas Janusz Wiśniewski."
    )
    document = run_nominal_kinship_stage(
        text,
        (
            person_span(text, "Marek Kowalski"),
            person_span(text, "Janusz Wiśniewski"),
        ),
    )
    records = fact_records(document)
    assert len(records) == 1
    record = records[0]
    assert record.kind is FactKind.KINSHIP_TIE

    # Subject should be the spouse proxy entity (grounding = PROXY)
    subject_id = entity_argument_id(record, "subject")
    assert subject_id is not None
    subject_entity = document.store.entity_candidates[subject_id]
    assert subject_entity.grounding == GroundingKind.PROXY
    assert subject_entity.canonical_hint == "żona of Marek Kowalski"


def test_nominal_kinship_copular_clause_uses_discourse_subject() -> None:
    first = "Marta Tartanus-Oryszczak została sekretarzem miasta."
    second = "Prywatnie jest żoną Łukasza Oryszczaka."
    text = f"{first} {second}"
    document = run_nominal_kinship_stage(
        text,
        (
            person_span(text, "Marta Tartanus-Oryszczak"),
            person_span(text, "Łukasza Oryszczaka"),
        ),
    )

    records = fact_records(document)
    record = next(record for record in records if record.kind is FactKind.KINSHIP_TIE)
    assert entity_hint_for_role(document, record, "subject") == "Marta Tartanus-Oryszczak"
    assert entity_hint_for_role(document, record, "object") == "Łukasza Oryszczaka"
    assert text_argument(record, "relationship_detail") == "spouse"


def test_nominal_kinship_unnamed_creates_proxy() -> None:
    text = "Tomasz Kościelniak zatrudnił swoją partnerkę."
    document = run_nominal_kinship_stage(
        text,
        (person_span(text, "Tomasz Kościelniak"),),
    )
    records = fact_records(document)
    assert len(records) == 1
    record = records[0]
    assert record.kind is FactKind.KINSHIP_TIE

    # Check subject role points to proxy
    subject_id = entity_argument_id(record, "subject")
    subject_entity = document.store.entity_candidates[subject_id]
    assert subject_entity.grounding == GroundingKind.PROXY
    assert subject_entity.canonical_hint == "partnerka of Tomasz Kościelniak"


def test_nominal_kinship_ignores_person_homograph_for_known_organization() -> None:
    text = "Jego partnerka starała się o pracę u Karlika i dlatego zacieśniał relacje z tą firmą."
    document = run_nominal_kinship_stage(
        text,
        (
            person_span(text, "Karlika"),
            organization_span(text, "Karlika"),
        ),
    )

    assert fact_records(document) == ()
