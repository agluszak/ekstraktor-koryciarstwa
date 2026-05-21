from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import FactKind, NerLabel
from tests_v2.materialized import fact_records


@dataclass(frozen=True, slots=True)
class StaticEntityProvider:
    entities: tuple[NamedEntitySpan, ...]

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def person_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.PERSON,
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def build_article_excerpt(
    paragraphs: tuple[str, ...],
    entities: tuple[NamedEntitySpan, ...],
) -> ArticleDocument:
    text = "\n\n".join(paragraphs)
    document = ArticleDocument(
        document_id=DocumentId("article-doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=paragraphs,
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)
    PartyCandidateStage(morphology).run(document)
    PublicMoneyCandidateStage().run(document)
    FactScoringStage().run(document)
    return document


def test_article_excerpt_recovers_funding_and_party_context() -> None:
    paragraphs = (
        "Nasz dziennikarz ujawnił, że fundacja założona przez dyrektora warszawskiego "
        "pogotowia ratunkowego Karola Bielskiego otrzymała 100 tysięcy złotych z urzędu "
        "marszałkowskiego za promowanie imprezy, którą organizowało pogotowie.",
        "Marszałkiem województwa od 25 lat jest Adam Struzik z Polskiego Stronnictwa Ludowego.",
        "Marcelina Zawisza, posłanka partii Razem, zapowiedziała kontrolę wszystkich umów "
        "dotyczących działań promocyjnych.",
    )
    text = "\n\n".join(paragraphs)
    document = build_article_excerpt(
        paragraphs,
        (
            person_span(text, "Karola Bielskiego"),
            person_span(text, "Adam Struzik"),
            person_span(text, "Marcelina Zawisza"),
        ),
    )

    records = fact_records(document)
    funding_record = next(record for record in records if record.kind is FactKind.FUNDING)
    party_records = tuple(record for record in records if record.kind is FactKind.PARTY_AFFILIATION)

    assert tuple(argument.to_json() for argument in funding_record.arguments) == (
        {"role": "funder", "entity_id": "entity-5"},
        {"role": "recipient", "entity_id": "entity-6"},
        {"role": "amount", "value": "100 tysięcy złotych"},
    )

    assert any(
        tuple(argument.to_json() for argument in record.arguments)
        == (
            {"role": "subject", "entity_id": "entity-1"},
            {"role": "object", "entity_id": "entity-3"},
        )
        for record in party_records
    )
    assert any(
        tuple(argument.to_json() for argument in record.arguments)
        == (
            {"role": "subject", "entity_id": "entity-2"},
            {"role": "object", "entity_id": "entity-4"},
        )
        for record in party_records
    )
