from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.retrieval import EntityCandidateRetriever
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import EntityKind, NerLabel
from tests_v2.helpers import StaticEntityProvider


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


def test_named_entity_stage_strips_role_title_from_person_candidate() -> None:
    cleaned_text = "Minister Jan Kowalski zabrał głos."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Minister Jan Kowalski")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Minister Jan Kowalski",
                    label=NerLabel.PERSON,
                    span=Span(start, start + len("Minister Jan Kowalski")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    person_candidates = [
        candidate
        for candidate in document.store.entity_candidates.values()
        if candidate.kind is EntityKind.PERSON
    ]
    role_candidates = [
        candidate
        for candidate in document.store.entity_candidates.values()
        if candidate.kind is EntityKind.ROLE
    ]

    assert len(person_candidates) == 1
    assert len(role_candidates) >= 1
    assert person_candidates[0].canonical_hint == "Jan Kowalski"
    role_mention_texts = {
        document.store.mentions[mention_id].text
        for candidate in role_candidates
        for mention_id in candidate.mention_ids
    }
    assert "Minister" in role_mention_texts


def test_named_entity_stage_strips_multi_token_role_prefix_from_person_candidate() -> None:
    cleaned_text = "Wiceprezes zarządu Jan Kowalski zabrał głos."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Wiceprezes zarządu Jan Kowalski")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Wiceprezes zarządu Jan Kowalski",
                    label=NerLabel.PERSON,
                    span=Span(start, start + len("Wiceprezes zarządu Jan Kowalski")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    person_candidates = [
        candidate
        for candidate in document.store.entity_candidates.values()
        if candidate.kind is EntityKind.PERSON
    ]
    role_candidates = [
        candidate
        for candidate in document.store.entity_candidates.values()
        if candidate.kind is EntityKind.ROLE
    ]

    assert len(person_candidates) == 1
    assert len(role_candidates) >= 1
    assert person_candidates[0].canonical_hint == "Jan Kowalski"
    role_mention_texts = {
        document.store.mentions[mention_id].text
        for candidate in role_candidates
        for mention_id in candidate.mention_ids
    }
    assert "Wiceprezes zarządu" in role_mention_texts


def test_named_entity_stage_reclassifies_surname_like_company_after_org_descriptor() -> None:
    cleaned_text = "Firma Karlik dostarczyla samochody."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Karlik")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Karlik",
                    label=NerLabel.PERSON,
                    span=Span(start, start + len("Karlik")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    candidates = tuple(document.store.entity_candidates.values())
    assert len(candidates) == 1
    assert candidates[0].canonical_hint == "Karlik"
    assert candidates[0].kind is EntityKind.ORGANIZATION


def test_named_entity_stage_reclassifies_surname_like_company_after_descriptor_with_gap() -> None:
    cleaned_text = "O pracę u tego dealera Karlika starała się partnerka prezesa."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Karlika")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Karlika",
                    label=NerLabel.PERSON,
                    span=Span(start, start + len("Karlika")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    candidates = tuple(document.store.entity_candidates.values())
    assert len(candidates) == 1
    assert candidates[0].canonical_hint == "Karlika"
    assert candidates[0].kind is EntityKind.ORGANIZATION


def test_named_entity_stage_reclassifies_person_span_with_organization_suffix() -> None:
    cleaned_text = "Nominat Allianza OFE nie został poddany głosowaniu."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Allianza OFE")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Allianza OFE",
                    label=NerLabel.PERSON,
                    span=Span(start, start + len("Allianza OFE")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    candidates = tuple(document.store.entity_candidates.values())
    assert len(candidates) == 1
    assert candidates[0].canonical_hint == "Allianza OFE"
    assert candidates[0].kind is EntityKind.ORGANIZATION


def test_named_entity_stage_reclassifies_inflected_media_outlet_from_person_label() -> None:
    cleaned_text = "W rozmowie z Onetowi pracownicy opisali sytuację."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    start = cleaned_text.index("Onetowi")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Onetowi",
                    label=NerLabel.PERSON,
                    span=Span(start, start + len("Onetowi")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    candidates = tuple(document.store.entity_candidates.values())
    assert len(candidates) == 1
    assert candidates[0].canonical_hint == "Onetowi"
    assert candidates[0].kind is EntityKind.ORGANIZATION


def test_named_entity_stage_merges_adjacent_initial_and_surname_person_spans() -> None:
    """NER sometimes splits 'A. Góralczyk' into two 1-token PERSON spans.
    The stage should merge them into a single entity with a valid reuse_key."""
    cleaned_text = "A. Góralczyk awansowała na stanowisko prezesa."
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=(cleaned_text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    initial_start = cleaned_text.index("A.")
    surname_start = cleaned_text.index("Góralczyk")

    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="A.",
                    label=NerLabel.PERSON,
                    span=Span(initial_start, initial_start + len("A.")),
                ),
                NamedEntitySpan(
                    text="Góralczyk",
                    label=NerLabel.PERSON,
                    span=Span(surname_start, surname_start + len("Góralczyk")),
                ),
            )
        ),
        morphology=Morfeusz2MorphologyAdapter(),
    ).run(document)

    person_candidates = [
        c for c in document.store.entity_candidates.values() if c.kind is EntityKind.PERSON
    ]
    assert len(person_candidates) == 1, "split initial+surname spans should merge into one entity"
    assert person_candidates[0].reuse_key is not None, "merged entity should have a reuse_key"
    assert person_candidates[0].canonical_hint == "A. Góralczyk"
