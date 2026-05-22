from __future__ import annotations

from typing import cast

from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import EntityClassificationStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.output import document_to_json
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import EntityTag, NerLabel


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_entity_classification(
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
    EntityClassificationStage().run(document)
    return document


def organization_span(text: str, organization: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=organization,
        label=NerLabel.ORGANIZATION,
        span=Span(text.index(organization), text.index(organization) + len(organization)),
    )


def test_entity_classification_tags_inflected_ministry_and_media_outlet() -> None:
    text = "Ministerstwa Aktywów Państwowych i TVN Warszawa komentowały sytuację Orlenu."
    document = run_entity_classification(
        text,
        (
            organization_span(text, "Ministerstwa Aktywów Państwowych"),
            organization_span(text, "TVN Warszawa"),
            organization_span(text, "Orlenu"),
        ),
    )

    tags_by_hint = {
        entity.canonical_hint: document.store.entity_tags.get(entity.id, frozenset())
        for entity in document.store.entity_candidates.values()
    }

    assert tags_by_hint["Ministerstwa Aktywów Państwowych"] == frozenset(
        {EntityTag.PUBLIC_INSTITUTION, EntityTag.GENERIC_OWNER}
    )
    assert tags_by_hint["TVN Warszawa"] == frozenset({EntityTag.MEDIA_OUTLET})
    assert tags_by_hint["Orlenu"] == frozenset()

    json_document = document_to_json(document)
    json_entities = {
        cast(str, entity["canonical_hint"]): entity
        for entity in cast(list[dict[str, object]], json_document["entities"])
    }
    assert json_entities["TVN Warszawa"]["tags"] == ["media_outlet"]


def test_entity_classification_does_not_use_wp_substring_as_media_match() -> None:
    text = "Spółka Wspólna Produkcja podpisała umowę z urzędem."
    document = run_entity_classification(
        text,
        (organization_span(text, "Spółka Wspólna Produkcja"),),
    )

    candidate = next(iter(document.store.entity_candidates.values()))
    assert document.store.entity_tags.get(candidate.id, frozenset()) == frozenset()
