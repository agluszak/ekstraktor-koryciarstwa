from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.coreference import CoreferenceReferenceStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import CoreferenceSpanLink, Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.proxy import FamilyProxyCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import FactKind, GroundingKind, NerLabel, ReferenceKind, RelationshipDetail
from tests_v2.materialized import entity_hint_for_role, first_fact_record, text_argument


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


def test_family_reference_materializes_proxy_person_linked_to_anchor() -> None:
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
    reference_start = cleaned_text.index("Jego żona")
    CoreferenceReferenceStage(
        provider=StaticCoreferenceProvider(
            (
                CoreferenceSpanLink(
                    antecedent_text="Jan Kowalski",
                    antecedent_span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                    reference_text="Jego żona",
                    reference_span=Span(reference_start, reference_start + len("Jego żona")),
                    reference_kind=ReferenceKind.PROXY_FAMILY_PHRASE,
                    relationship_detail=RelationshipDetail.SPOUSE,
                ),
            )
        ),
        morphology=morphology,
    ).run(document)

    FamilyProxyCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
    proxy_candidates = tuple(
        candidate
        for candidate in document.store.entity_candidates.values()
        if candidate.grounding == GroundingKind.PROXY
    )

    assert tuple(candidate.canonical_hint for candidate in proxy_candidates) == (
        "spouse of Jan Kowalski",
    )
    assert document.store.entity_ids_for_reference(
        proxy_candidates[0].reference_ids[0]
    ) == frozenset({proxy_candidates[0].id})
    tie_record = first_fact_record(document)
    assert tie_record.kind is FactKind.EXTENDED_KINSHIP
    assert entity_hint_for_role(document, tie_record, "subject") == "spouse of Jan Kowalski"
    assert entity_hint_for_role(document, tie_record, "object") == "Jan Kowalski"
    assert text_argument(tie_record, "relationship_detail") == "spouse"
