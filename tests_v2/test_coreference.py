from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.coreference import CoreferenceReferenceStage, LightReferenceStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import CoreferenceSpanLink, Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.orchestrator import V2Orchestrator
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import NerLabel, ReferenceKind


@dataclass(frozen=True, slots=True)
class StaticEntityProvider:
    entities: tuple[NamedEntitySpan, ...]

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


@dataclass(frozen=True, slots=True)
class StaticCoreferenceProvider:
    coreference_links: tuple[CoreferenceSpanLink, ...]

    def links(self, text: str) -> tuple[CoreferenceSpanLink, ...]:
        _ = text
        return self.coreference_links


def test_coreference_stage_proposes_reference_resolution_without_merging_entities() -> None:
    cleaned_text = "Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=("Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie.",),
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    antecedent_start = cleaned_text.index("Jan Kowalski")
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Jan Kowalski",
                    label=NerLabel.PERSON,
                    span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                ),
            )
        ),
        morphology=morphology,
    ).run(document)
    reference_start = cleaned_text.index("Jego")

    CoreferenceReferenceStage(
        provider=StaticCoreferenceProvider(
            (
                CoreferenceSpanLink(
                    antecedent_text="Jan Kowalski",
                    antecedent_span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                    reference_text="Jego",
                    reference_span=Span(reference_start, reference_start + len("Jego")),
                    reference_kind=ReferenceKind.POSSESSIVE_PRONOUN,
                ),
            )
        ),
        morphology=morphology,
    ).run(document)
    result = V2Orchestrator(document.store).assess(
        reference_resolutions=tuple(document.reference_resolution_proposals)
    )

    assert tuple(
        candidate.canonical_hint for candidate in document.store.entity_candidates.values()
    ) == ("Jan Kowalski",)
    assert tuple(reference.kind for reference in document.store.references.values()) == (
        ReferenceKind.POSSESSIVE_PRONOUN,
    )
    assert len(result.reference_resolution_assessments) == 1
    assert result.reference_resolution_assessments[0].assessment.score >= 0.7


def test_light_reference_stage_emits_pronoun_reference_candidates_without_merging() -> None:
    cleaned_text = "Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=("Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie.",),
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    antecedent_start = cleaned_text.index("Jan Kowalski")
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Jan Kowalski",
                    label=NerLabel.PERSON,
                    span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                ),
            )
        ),
        morphology=morphology,
    ).run(document)

    LightReferenceStage().run(document)
    result = V2Orchestrator(document.store).assess(
        reference_resolutions=tuple(document.reference_resolution_proposals)
    )

    assert tuple(reference.text for reference in document.store.references.values()) == ("Jego",)
    assert tuple(
        candidate.canonical_hint for candidate in document.store.entity_candidates.values()
    ) == ("Jan Kowalski",)
    assert len(result.reference_resolution_assessments) == 1
    assert result.reference_resolution_assessments[0].assessment.score >= 0.5
