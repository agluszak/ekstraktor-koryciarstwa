from __future__ import annotations

from collections import defaultdict
from typing import cast

from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import LexicalEntityContextStage
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
    LexicalEntityContextStage().run(document)
    return document


def organization_span(text: str, organization: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=organization,
        label=NerLabel.ORGANIZATION,
        span=Span(text.index(organization), text.index(organization) + len(organization)),
    )


def _proposals_by_hint(document: ArticleDocument) -> dict[str, frozenset[EntityTag]]:
    by_entity: dict[str, set[EntityTag]] = defaultdict(set)
    for entity in document.store.entity_candidates.values():
        by_entity[entity.canonical_hint or ""] = set()
    for proposal in document.entity_context_proposals:
        entity = document.store.entity_candidates.get(proposal.entity_id)
        if entity is None:
            continue
        by_entity[entity.canonical_hint or ""].add(proposal.context_kind)
    return {hint: frozenset(tags) for hint, tags in by_entity.items()}


def test_entity_classification_proposes_inflected_ministry_and_media_outlet() -> None:
    text = "Ministerstwa Aktywów Państwowych i TVN Warszawa komentowały sytuację Orlenu."
    document = run_entity_classification(
        text,
        (
            organization_span(text, "Ministerstwa Aktywów Państwowych"),
            organization_span(text, "TVN Warszawa"),
            organization_span(text, "Orlenu"),
        ),
    )

    tags_by_hint = _proposals_by_hint(document)

    assert tags_by_hint["Ministerstwa Aktywów Państwowych"] == frozenset(
        {EntityTag.PUBLIC_INSTITUTION, EntityTag.GENERIC_OWNER}
    )
    assert tags_by_hint["TVN Warszawa"] == frozenset({EntityTag.MEDIA_OUTLET})
    assert tags_by_hint["Orlenu"] == frozenset()

    # Each proposal carries at least one trigger evidence id and one retrieval signal
    for proposal in document.entity_context_proposals:
        assert len(proposal.evidence_ids) >= 1
        assert len(proposal.retrieval_signals) >= 1

    # JSON output exposes the proposals with `context_kind`
    json_document = document_to_json(document)
    json_proposals = cast(list[dict[str, object]], json_document["entity_context_proposals"])
    media_proposals = [
        proposal
        for proposal in json_proposals
        if proposal["context_kind"] == EntityTag.MEDIA_OUTLET.value
    ]
    assert len(media_proposals) == 1


def test_entity_classification_does_not_use_wp_substring_as_media_match() -> None:
    text = "Spółka Wspólna Produkcja podpisała umowę z urzędem."
    document = run_entity_classification(
        text,
        (organization_span(text, "Spółka Wspólna Produkcja"),),
    )

    candidate = next(iter(document.store.entity_candidates.values()))
    proposals_for_candidate = [
        proposal
        for proposal in document.entity_context_proposals
        if proposal.entity_id == candidate.id
    ]
    assert proposals_for_candidate == []


def test_entity_classification_recognizes_shared_media_outlet_aliases() -> None:
    text = "Onet, WP, Wirtualna Polska, Gazeta Wyborcza, TVP i Niezależna opisały sprawę."
    document = run_entity_classification(
        text,
        (
            organization_span(text, "Onet"),
            organization_span(text, "WP"),
            organization_span(text, "Wirtualna Polska"),
            organization_span(text, "Gazeta Wyborcza"),
            organization_span(text, "TVP"),
            organization_span(text, "Niezależna"),
        ),
    )

    tags_by_hint = _proposals_by_hint(document)

    for outlet in (
        "Onet",
        "WP",
        "Wirtualna Polska",
        "Gazeta Wyborcza",
        "TVP",
        "Niezależna",
    ):
        assert tags_by_hint[outlet] == frozenset({EntityTag.MEDIA_OUTLET})


def test_entity_classification_keeps_case_sensitive_media_aliases_from_generic_words() -> None:
    text = "Niezależna opisała sprawę. niezależna organizacja złożyła wniosek."
    document = run_entity_classification(
        text,
        (
            organization_span(text, "Niezależna"),
            organization_span(text, "niezależna organizacja"),
        ),
    )

    tags_by_hint = _proposals_by_hint(document)

    assert tags_by_hint["Niezależna"] == frozenset({EntityTag.MEDIA_OUTLET})
    assert tags_by_hint["niezależna organizacja"] == frozenset()
