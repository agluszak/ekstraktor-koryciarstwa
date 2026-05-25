from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    ProducerId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.public_employment import PublicEmploymentCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.ties import PersonalTieCandidateStage
from pipeline_v2.types import EntityKind, EventRole, FactKind, GroundingKind, NerLabel
from tests_v2.materialized import entity_hint_for_role, fact_records, text_argument


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        return self.entities


def entity_span(text: str, name: str, label: NerLabel) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=label,
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def run_pipeline(text: str, entities: tuple[NamedEntitySpan, ...] = ()) -> ArticleDocument:
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

    PartyCandidateStage(morphology).run(document)
    RoleCandidateStage(morphology).run(document)
    GovernanceCandidateStage().run(document)
    PublicEmploymentCandidateStage().run(document)
    PublicMoneyCandidateStage().run(document)
    PersonalTieCandidateStage().run(document)

    ProbabilisticInferenceStage().run(document)
    return document


def test_party_membership() -> None:
    text = "Jan Kowalski był posłem z PO."
    document = run_pipeline(text, (entity_span(text, "Jan Kowalski", NerLabel.PERSON),))
    records = fact_records(document)
    former_records = [
        r
        for r in records
        if r.kind == FactKind.PARTY_MEMBERSHIP and text_argument(r, "status") == "former"
    ]
    assert len(former_records) >= 1
    rec = former_records[0]
    assert entity_hint_for_role(document, rec, "subject") == "Jan Kowalski"
    assert entity_hint_for_role(document, rec, "object") == "Platforma Obywatelska"


def test_party_membership_context_does_not_leak_to_unrelated_party() -> None:
    text = "Były minister Jan Kowalski z PO poparł Annę Nowak z PiS."
    document = run_pipeline(
        text,
        (
            entity_span(text, "Jan Kowalski", NerLabel.PERSON),
            entity_span(text, "Annę Nowak", NerLabel.PERSON),
        ),
    )
    records = fact_records(document)
    former_pairs = {
        (
            entity_hint_for_role(document, record, "subject"),
            entity_hint_for_role(document, record, "object"),
        )
        for record in records
        if record.kind == FactKind.PARTY_MEMBERSHIP and text_argument(record, "status") == "former"
    }
    current_pairs = {
        (
            entity_hint_for_role(document, record, "subject"),
            entity_hint_for_role(document, record, "object"),
        )
        for record in records
        if record.kind == FactKind.PARTY_MEMBERSHIP
        and text_argument(record, "status") in {"current", "unknown"}
    }

    assert ("Jan Kowalski", "Platforma Obywatelska") in former_pairs
    assert ("Annę Nowak", "Prawo i Sprawiedliwość") in current_pairs
    assert ("Annę Nowak", "Prawo i Sprawiedliwość") not in former_pairs


def test_election_candidacy() -> None:
    text = "Jan Kowalski kandydował w wyborach."
    document = run_pipeline(text, (entity_span(text, "Jan Kowalski", NerLabel.PERSON),))
    records = fact_records(document)
    candidacy_records = [r for r in records if r.kind == FactKind.ELECTION_CANDIDACY]
    assert len(candidacy_records) >= 1
    rec = candidacy_records[0]
    assert entity_hint_for_role(document, rec, "person") == "Jan Kowalski"


def test_election_context_word_alone_does_not_create_candidacy() -> None:
    text = "Jan Kowalski komentował wybory samorządowe."
    document = run_pipeline(text, (entity_span(text, "Jan Kowalski", NerLabel.PERSON),))

    assert not [r for r in fact_records(document) if r.kind == FactKind.ELECTION_CANDIDACY]


def test_public_role_holding() -> None:
    text = "Radny Jan Kowalski zabrał głos."
    document = run_pipeline(text, (entity_span(text, "Jan Kowalski", NerLabel.PERSON),))
    records = fact_records(document)
    office_records = [r for r in records if r.kind == FactKind.PUBLIC_ROLE_HOLDING]
    assert len(office_records) >= 1
    rec = office_records[0]
    assert entity_hint_for_role(document, rec, "person") == "Jan Kowalski"
    assert entity_hint_for_role(document, rec, "role") == "Radny"
    assert text_argument(rec, "role_domain") == "political_office"


def test_secretary_of_city_is_administrative_public_role_not_political_office() -> None:
    text = "Anna Nowak jest sekretarzem miasta."
    document = run_pipeline(text, (entity_span(text, "Anna Nowak", NerLabel.PERSON),))

    records = [r for r in fact_records(document) if r.kind == FactKind.PUBLIC_ROLE_HOLDING]
    assert records
    assert entity_hint_for_role(document, records[0], "person") == "Anna Nowak"
    assert text_argument(records[0], "role_domain") == "administrative_office"


def test_political_role_mention_does_not_attach_to_unrelated_person() -> None:
    text = "Minister skrytykował Jana Kowalskiego."
    document = run_pipeline(text, (entity_span(text, "Jana Kowalskiego", NerLabel.PERSON),))

    assert not [r for r in fact_records(document) if r.kind == FactKind.PUBLIC_ROLE_HOLDING]


def test_corporate_ownership() -> None:
    text = "Jan Kowalski posiada akcje o wartości 10 mln zł w spółce KGHM."
    document = run_pipeline(
        text,
        (
            entity_span(text, "Jan Kowalski", NerLabel.PERSON),
            entity_span(text, "KGHM", NerLabel.ORGANIZATION),
        ),
    )
    records = fact_records(document)
    ownership_records = [r for r in records if r.kind == FactKind.CORPORATE_OWNERSHIP]
    assert len(ownership_records) >= 1
    rec = ownership_records[0]
    assert entity_hint_for_role(document, rec, "subject") == "Jan Kowalski"
    assert entity_hint_for_role(document, rec, "object") == "KGHM"


def test_party_donation() -> None:
    text = "Jan Kowalski wpłacił 50 000 zł na rzecz partii PiS."
    document = run_pipeline(text, (entity_span(text, "Jan Kowalski", NerLabel.PERSON),))
    records = fact_records(document)
    donation_records = [r for r in records if r.kind == FactKind.PARTY_DONATION]
    assert len(donation_records) >= 1
    rec = donation_records[0]
    assert entity_hint_for_role(document, rec, "funder") == "Jan Kowalski"
    assert entity_hint_for_role(document, rec, "recipient") == "Prawo i Sprawiedliwość"
    assert text_argument(rec, "amount") == "50 000 zł"


def test_asset_declaration() -> None:
    text = "Jan Kowalski złożył oświadczenie majątkowe: zaoszczędził 100 tys. zł."
    document = run_pipeline(text, (entity_span(text, "Jan Kowalski", NerLabel.PERSON),))
    records = fact_records(document)
    asset_records = [r for r in records if r.kind == FactKind.ASSET_DECLARATION]
    assert len(asset_records) >= 1
    rec = asset_records[0]
    assert entity_hint_for_role(document, rec, "person") == "Jan Kowalski"
    assert text_argument(rec, "amount") == "100 tys. zł"


def test_kinship_tie() -> None:
    text = "Jan Kowalski to brat Adama Kowalskiego."
    document = run_pipeline(
        text,
        (
            entity_span(text, "Jan Kowalski", NerLabel.PERSON),
            entity_span(text, "Adama Kowalskiego", NerLabel.PERSON),
        ),
    )
    records = fact_records(document)
    kinship_records = [r for r in records if r.kind == FactKind.KINSHIP_TIE]
    assert len(kinship_records) >= 1
    rec = kinship_records[0]
    assert entity_hint_for_role(document, rec, "subject") == "Jan Kowalski"
    assert entity_hint_for_role(document, rec, "object") == "Adama Kowalskiego"
    assert text_argument(rec, "relationship_detail") == "sibling"
    assert not [r for r in records if r.kind == FactKind.PERSONAL_OR_POLITICAL_TIE]


def test_corporate_ownership_constraint_demotes_posterior() -> None:
    # 1. Subject != Object (should NOT be demoted, should materialize)
    document_valid = ArticleDocument(
        document_id=DocumentId("valid-doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    document_valid.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("person-1"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document_valid.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-1"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="KGHM",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    event_id_valid = EventCandidateId("event-valid")
    document_valid.store.add_event_candidate(
        EventCandidate(
            id=event_id_valid,
            kind=FactKind.CORPORATE_OWNERSHIP,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document_valid.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("b-sub-valid"),
            event_id=event_id_valid,
            role=EventRole.SUBJECT,
            filler=EntityFiller(EntityCandidateId("person-1")),
            evidence_ids=(),
        )
    )
    document_valid.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("b-obj-valid"),
            event_id=event_id_valid,
            role=EventRole.OBJECT,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(),
        )
    )
    document_valid.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("b-amt-valid"),
            event_id=event_id_valid,
            role=EventRole.AMOUNT,
            filler=TextFiller("10 mln zł"),
            evidence_ids=(),
        )
    )

    # 2. Subject == Object (should be demoted, should NOT materialize because penalty blocks it)
    document_invalid = ArticleDocument(
        document_id=DocumentId("invalid-doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    document_invalid.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-1"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="KGHM",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    event_id_invalid = EventCandidateId("event-invalid")
    document_invalid.store.add_event_candidate(
        EventCandidate(
            id=event_id_invalid,
            kind=FactKind.CORPORATE_OWNERSHIP,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document_invalid.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("b-sub-invalid"),
            event_id=event_id_invalid,
            role=EventRole.SUBJECT,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(),
        )
    )
    document_invalid.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("b-obj-invalid"),
            event_id=event_id_invalid,
            role=EventRole.OBJECT,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(),
        )
    )

    ProbabilisticInferenceStage().run(document_valid)
    ProbabilisticInferenceStage().run(document_invalid)

    valid_ownership = [
        r for r in fact_records(document_valid) if r.kind == FactKind.CORPORATE_OWNERSHIP
    ]
    assert len(valid_ownership) == 1

    # The invalid document should have corporate ownership demoted, and not materialized (blocked)
    invalid_ownership = [
        r for r in fact_records(document_invalid) if r.kind == FactKind.CORPORATE_OWNERSHIP
    ]
    assert len(invalid_ownership) == 0


def test_party_membership_person_after_party() -> None:
    text = "Do Platformy Obywatelskiej należał były poseł Jan Kowalski."
    document = run_pipeline(
        text,
        (entity_span(text, "Jan Kowalski", NerLabel.PERSON),),
    )
    records = fact_records(document)
    former_records = [
        r
        for r in records
        if r.kind == FactKind.PARTY_MEMBERSHIP and text_argument(r, "status") == "former"
    ]
    assert len(former_records) >= 1
    rec = former_records[0]
    assert entity_hint_for_role(document, rec, "subject") == "Jan Kowalski"
    assert entity_hint_for_role(document, rec, "object") == "Platforma Obywatelska"
