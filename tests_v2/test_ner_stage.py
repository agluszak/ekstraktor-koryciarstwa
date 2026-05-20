from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.retrieval import EntityCandidateRetriever
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import NerLabel


@dataclass(frozen=True, slots=True)
class StaticEntityProvider:
    entities: tuple[NamedEntitySpan, ...]

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def test_named_entity_stage_emits_resolution_proposal_for_inflected_full_person_mentions() -> None:
    cleaned_text = "Krzysztof Staruch wygrał wybory. Krzysztofa Starucha poparł komitet."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=("Krzysztof Staruch wygrał wybory. Krzysztofa Starucha poparł komitet.",),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    first_start = cleaned_text.index("Krzysztof Staruch")
    second_start = cleaned_text.index("Krzysztofa Starucha")
    stage = NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Krzysztof Staruch",
                    label=NerLabel.PERSON,
                    span=Span(first_start, first_start + len("Krzysztof Staruch")),
                ),
                NamedEntitySpan(
                    text="Krzysztofa Starucha",
                    label=NerLabel.PERSON,
                    span=Span(second_start, second_start + len("Krzysztofa Starucha")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    )

    stage.run(document)
    mention_ids = tuple(document.store.mentions)

    assert len(mention_ids) == 2
    first_ids = document.store.entity_ids_for_mention(mention_ids[0])
    second_ids = document.store.entity_ids_for_mention(mention_ids[1])

    assert first_ids != second_ids
    second_entity = document.store.entity_candidates[next(iter(second_ids))]
    proposals = EntityCandidateRetriever(document.store).proposals_for_entity(second_entity)
    assert len(proposals) == 1


def test_named_entity_stage_records_organization_evidence_in_sentence_context() -> None:
    cleaned_text = "Fundacja podpisała umowę z urzędem."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=("Fundacja podpisała umowę z urzędem.",),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Fundacja")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Fundacja",
                    label=NerLabel.ORGANIZATION,
                    span=Span(start, start + len("Fundacja")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    entity = next(iter(document.store.entity_candidates.values()))
    evidence = next(iter(document.store.evidence.values()))

    assert entity.canonical_hint == "Fundacja"
    assert evidence.text == "Fundacja"
    assert evidence.paragraph_index == 0
