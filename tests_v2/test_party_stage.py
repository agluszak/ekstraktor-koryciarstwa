from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.types import (
    DirectPrepositionalAttachmentSignal,
    EntityKind,
    FactKind,
    NerLabel,
    PartyAliasMatchSignal,
)
from tests_v2.helpers import StaticEntityProvider, setup_base_test_document
from tests_v2.materialized import entity_hint_for_role, fact_records, first_fact_record, span_of


def run_party_stage(text: str, entities: tuple[NamedEntitySpan, ...] = ()) -> ArticleDocument:
    document = setup_base_test_document(text)
    morphology = Morfeusz2MorphologyAdapter()
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)
    PartyCandidateStage(morphology).run(document)
    ProbabilisticInferenceStage().run(document)
    return document


def person_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.PERSON,
        span=span_of(text, name),
    )


def test_party_stage_emits_party_entity_and_direct_membership_from_z_party_phrase() -> None:
    text = "Jan Kowalski z PSL został powołany do rady."
    document = run_party_stage(text, (person_span(text, "Jan Kowalski"),))

    parties = tuple(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.kind == EntityKind.POLITICAL_PARTY
    )
    record = first_fact_record(document)

    assert tuple(party.canonical_hint for party in parties) == ("Polskie Stronnictwo Ludowe",)
    assert record.kind is FactKind.PARTY_MEMBERSHIP
    assert entity_hint_for_role(document, record, "subject") == "Jan Kowalski"
    assert entity_hint_for_role(document, record, "object") == "Polskie Stronnictwo Ludowe"
    assert {
        PartyAliasMatchSignal(),
        DirectPrepositionalAttachmentSignal(),
    } <= set(record.signals)


def test_party_stage_matches_inflected_full_party_name_in_direct_attachment() -> None:
    text = "Adam Struzik z Polskiego Stronnictwa Ludowego krytykował decyzję urzędu."
    document = run_party_stage(text, (person_span(text, "Adam Struzik"),))

    record = first_fact_record(document)

    assert record.kind is FactKind.PARTY_MEMBERSHIP
    assert entity_hint_for_role(document, record, "subject") == "Adam Struzik"
    assert entity_hint_for_role(document, record, "object") == "Polskie Stronnictwo Ludowe"


def test_party_stage_attaches_profile_phrases_to_nearest_correct_people() -> None:
    text = "Działacz Lewicy Stanisław Mazur i działacz PSL Andrzej Kloc będą kierować funduszem."
    document = run_party_stage(
        text,
        (
            person_span(text, "Stanisław Mazur"),
            person_span(text, "Andrzej Kloc"),
        ),
    )

    records = fact_records(document)

    assert tuple(record.kind for record in records) == (
        FactKind.PARTY_MEMBERSHIP,
        FactKind.PARTY_MEMBERSHIP,
    )
    attachments = {
        (
            entity_hint_for_role(document, record, "subject"),
            entity_hint_for_role(document, record, "object"),
        )
        for record in records
    }
    assert attachments == {
        ("Stanisław Mazur", "Lewica"),
        ("Andrzej Kloc", "Polskie Stronnictwo Ludowe"),
    }


def test_party_stage_attaches_reverse_profile_phrase_to_preceding_person() -> None:
    text = "Marcelina Zawisza, posłanka partii Razem, zwróciła uwagę na problem."
    document = run_party_stage(text, (person_span(text, "Marcelina Zawisza"),))

    record = first_fact_record(document)

    assert record.kind is FactKind.PARTY_MEMBERSHIP
    assert entity_hint_for_role(document, record, "subject") == "Marcelina Zawisza"
    assert entity_hint_for_role(document, record, "object") == "Razem"


def test_party_stage_does_not_turn_party_cooccurrence_into_membership() -> None:
    text = "Donald Tusk skrytykował PSL za decyzję w sprawie budżetu."
    document = run_party_stage(text, (person_span(text, "Donald Tusk"),))

    assert tuple(record.kind for record in fact_records(document)) == ()


def test_party_stage_ignores_lowercase_preposition_po() -> None:
    text = "Jan Kowalski poszedł po dokumenty do urzędu."
    document = run_party_stage(text, (person_span(text, "Jan Kowalski"),))

    assert (
        tuple(
            entity
            for entity in document.store.entity_candidates.values()
            if entity.kind == EntityKind.POLITICAL_PARTY
        )
        == ()
    )


def test_party_stage_ignores_lowercase_razem_as_adverb() -> None:
    text = "Jan Kowalski działał razem z innymi politykami."
    document = run_party_stage(text, (person_span(text, "Jan Kowalski"),))

    assert (
        tuple(
            entity
            for entity in document.store.entity_candidates.values()
            if entity.kind == EntityKind.POLITICAL_PARTY
        )
        == ()
    )


def test_party_stage_emits_weaker_political_support_for_candidacy_context() -> None:
    text = "Kandydatka PSL Anna Nowak wystartowała w wyborach."
    document = run_party_stage(text, (person_span(text, "Anna Nowak"),))

    ProbabilisticInferenceStage().run(document)
    record = first_fact_record(document)

    assert record.kind is FactKind.POLITICAL_SUPPORT
    assert entity_hint_for_role(document, record, "subject") == "Polskie Stronnictwo Ludowe"
    assert entity_hint_for_role(document, record, "object") == "Anna Nowak"
    assert document.fact_assessments[0].assessment.score < 0.7


def test_party_stage_does_not_attach_distant_previous_person_to_role_party_phrase() -> None:
    text = (
        "Dobre zdanie o Bykowskim mają prezydent Poznania z PO i wicemarszałek województwa z PSL."
    )
    document = run_party_stage(text, (person_span(text, "Bykowskim"),))

    assert tuple(record.kind for record in fact_records(document)) == ()


def test_party_stage_can_attach_following_person_after_prepositional_party_phrase() -> None:
    text = "Autorzy skargi odnoszą się do kojarzonego z PiS Mariusza Wiatrowskiego."
    document = run_party_stage(text, (person_span(text, "Mariusza Wiatrowskiego"),))

    record = first_fact_record(document)

    assert record.kind is FactKind.PARTY_MEMBERSHIP
    assert entity_hint_for_role(document, record, "subject") == "Mariusza Wiatrowskiego"
    assert entity_hint_for_role(document, record, "object") == "Prawo i Sprawiedliwość"


def test_party_stage_keeps_each_party_with_its_local_named_person() -> None:
    text = (
        "Poprosiliśmy prezydenta Poznania Jacka Jaśkowiaka z PO "
        "oraz wicemarszałka województwa Wojciecha Jankowiaka z PSL."
    )
    document = run_party_stage(
        text,
        (
            person_span(text, "Jacka Jaśkowiaka"),
            person_span(text, "Wojciecha Jankowiaka"),
        ),
    )

    attachments = {
        (
            entity_hint_for_role(document, record, "subject"),
            entity_hint_for_role(document, record, "object"),
        )
        for record in fact_records(document)
    }
    assert attachments == {
        ("Jacka Jaśkowiaka", "Platforma Obywatelska"),
        ("Wojciecha Jankowiaka", "Polskie Stronnictwo Ludowe"),
    }
