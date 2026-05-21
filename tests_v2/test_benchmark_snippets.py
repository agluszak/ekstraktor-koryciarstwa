from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.coreference import CoreferenceReferenceStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    FactCandidateId,
    ProducerId,
    SentenceId,
)
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import (
    CoreferenceSpanLink,
    EvidenceSpan,
    Morfeusz2MorphologyAdapter,
    NamedEntitySpan,
    Sentence,
    Span,
)
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.producers import EvidenceSignalProducer
from pipeline_v2.proxy import FamilyProxyCandidateStage
from pipeline_v2.public_employment import PublicEmploymentCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.ties import PersonalTieCandidateStage
from pipeline_v2.types import (
    AntiCorruptionInvestigationLemmaSignal,
    AppointmentLemmaSignal,
    ConflictingPartyAffiliationSignal,
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocalTargetSignal,
    MentionKind,
    NerLabel,
    OversightInstitutionSignal,
    PublicEmploymentLemmaSignal,
    ReferenceKind,
    RelationshipDetail,
    SameNameContrastContextSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)
from tests_v2.materialized import add_event, bind_entity, fact_records, first_fact_record


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


def build_document(
    text: str,
    entities: tuple[NamedEntitySpan, ...] = (),
) -> tuple[ArticleDocument, Morfeusz2MorphologyAdapter]:
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
    if entities:
        NamedEntityCandidateStage(
            provider=StaticEntityProvider(entities),
            morphology=morphology,
        ).run(document)
    return document, morphology


def person_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.PERSON,
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def organization_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def build_manual_sentence_document(text: str) -> tuple[ArticleDocument, EvidenceId]:
    document = ArticleDocument(
        document_id=DocumentId("doc-manual"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=(text,),
    )
    sentence_id = document.store.add_sentence(
        Sentence(
            id=SentenceId("sentence-0"),
            sentence_index=0,
            paragraph_index=0,
            text=text,
            span=Span(0, len(text)),
        )
    )
    evidence_id = document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("evidence-0"),
            text=text,
            span=Span(0, len(text)),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    return document, evidence_id


def test_benchmark_split_sentence_governance_scenario() -> None:
    text = "Jan Kowalski jest prezesem spółki Wodkan. Został powołany bez konkursu."
    document, morphology = build_document(
        text,
        (
            person_span(text, "Jan Kowalski"),
            organization_span(text, "Wodkan"),
        ),
    )

    RoleCandidateStage(morphology).run(document)
    GovernanceCandidateStage().run(document)
    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.GOVERNANCE_APPOINTMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-0"},
        {"role": "organization", "entity_id": "entity-1"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert set(record.signals) == {
        AppointmentLemmaSignal(lemma="powołać"),
        WindowPersonSignal(),
        WindowOrganizationSignal(),
        WindowRoleSignal(),
    }
    assert assessment.score >= 0.8


def test_benchmark_public_employment_scenario() -> None:
    text = "Urząd miasta zatrudnił Marka Nowaka jako doradcę burmistrza."
    document, morphology = build_document(
        text,
        (
            organization_span(text, "Urząd miasta"),
            person_span(text, "Marka Nowaka"),
        ),
    )

    RoleCandidateStage(morphology).run(document)
    GovernanceCandidateStage().run(document)
    PublicEmploymentCandidateStage().run(document)
    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-1"},
        {"role": "organization", "entity_id": "entity-0"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert set(record.signals) == {
        PublicEmploymentLemmaSignal(lemma="zatrudnić"),
        LocalPersonSignal(),
        LocalOrganizationSignal(),
        LocalRoleSignal(),
    }
    assert assessment.score >= 0.8


def test_benchmark_public_contract_scenario() -> None:
    text = "Urząd podpisał umowę z firmą Alfa za 49 tys. zł."
    document, _morphology = build_document(
        text,
        (
            organization_span(text, "Urząd"),
            organization_span(text, "Alfa"),
        ),
    )

    PublicMoneyCandidateStage().run(document)
    PublicEmploymentCandidateStage().run(document)
    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert fact_records(document) != ()
    assert record.kind is FactKind.PUBLIC_CONTRACT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "counterparty", "entity_id": "entity-0"},
        {"role": "contractor", "entity_id": "entity-1"},
        {"role": "amount", "value": "49 tys. zł"},
    )
    assert assessment.score >= 0.8


def test_benchmark_anti_corruption_mixed_party_context_scenario() -> None:
    text = "Radni PiS zapowiedzieli zawiadomienie do CBA w sprawie zatrudnienia Jana Nowaka."
    document, morphology = build_document(
        text,
        (
            organization_span(text, "CBA"),
            person_span(text, "Jana Nowaka"),
        ),
    )

    PartyCandidateStage(morphology).run(document)
    RoleCandidateStage(morphology).run(document)
    GovernanceCandidateStage().run(document)
    AntiCorruptionCandidateStage().run(document)
    FactScoringStage().run(document)

    records = fact_records(document)
    assert tuple(record.kind for record in records) == (FactKind.ANTI_CORRUPTION_REFERRAL,)

    referral_record = records[0]

    assert tuple(argument.to_json() for argument in referral_record.arguments) == (
        {"role": "complainant", "entity_id": "entity-2"},
        {"role": "target", "entity_id": "entity-1"},
        {"role": "institution", "entity_id": "entity-0"},
        {"role": "context", "value": "w sprawie zatrudnienia Jana Nowaka"},
    )


def test_benchmark_proxy_family_tie_scenario() -> None:
    text = "Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie."
    document, morphology = build_document(text, (person_span(text, "Jan Kowalski"),))
    antecedent_start = text.index("Jan Kowalski")
    reference_start = text.index("Jego żona")

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
    PersonalTieCandidateStage().run(document)
    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "subject", "entity_id": "proxy-1"},
        {"role": "object", "entity_id": "entity-0"},
        {"role": "relationship_detail", "value": "spouse"},
    )
    assert assessment.score >= 0.7


def test_benchmark_party_true_negative_scenario() -> None:
    text = "Radni PiS skrytykowali projekt budżetu miasta."
    document, morphology = build_document(text)

    PartyCandidateStage(morphology).run(document)
    FactScoringStage().run(document)

    assert tuple(record.kind for record in fact_records(document)) == ()


def test_benchmark_anti_corruption_investigation_scenario() -> None:
    text = "Prokuratura wszczęła śledztwo w sprawie Jana Nowaka."
    document, _morphology = build_document(text, (person_span(text, "Jana Nowaka"),))

    AntiCorruptionCandidateStage().run(document)
    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "target", "entity_id": "entity-0"},
        {"role": "institution", "value": "Prokuratura"},
        {"role": "context", "value": "w sprawie Jana Nowaka"},
    )
    assert set(record.signals) == {
        AntiCorruptionInvestigationLemmaSignal(lemma="wszcząć"),
        OversightInstitutionSignal(),
        LocalTargetSignal(),
    }
    assert assessment.score >= 0.7


def test_benchmark_same_name_party_contrast_scenario() -> None:
    text = "Jan Kowalski z PO, nie mylić z Janem Kowalskim z PiS."
    document, evidence_id = build_manual_sentence_document(text)
    assert SameNameContrastContextSignal() in EvidenceSignalProducer().signals_for_evidence_ids(
        document.store,
        (evidence_id,),
    )


def test_benchmark_family_name_overlap_tie_scenario() -> None:
    text = "Marek Kowalski, syn Jana Kowalskiego, pracuje w urzędzie."
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Marek Kowalski"),
            person_span(text, "Jana Kowalskiego"),
        ),
    )

    PersonalTieCandidateStage().run(document)
    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "subject", "entity_id": "entity-0"},
        {"role": "object", "entity_id": "entity-1"},
        {"role": "relationship_detail", "value": "child"},
    )
    assert assessment.score >= 0.7


def test_benchmark_party_and_oversight_true_negative_scenario() -> None:
    text = "NIK opublikowała raport o kontroli urzędu. PiS skrytykował jego wnioski."
    document, morphology = build_document(text)

    PartyCandidateStage(morphology).run(document)
    AntiCorruptionCandidateStage().run(document)
    FactScoringStage().run(document)

    assert fact_records(document) == ()


def test_benchmark_multiparagraph_surname_only_resolution() -> None:
    paragraphs = (
        "Jan Kowalski został prezesem spółki.",
        "Kowalski ma spore doświadczenie.",
    )
    text = "\n\n".join(paragraphs)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=paragraphs,
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)

    entities = (
        NamedEntitySpan(
            text="Jan Kowalski",
            label=NerLabel.PERSON,
            span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + len("Jan Kowalski")),
        ),
        NamedEntitySpan(
            text="Kowalski",
            label=NerLabel.PERSON,
            span=Span(text.index("Kowalski"), text.index("Kowalski") + len("Kowalski")),
        ),
    )
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)

    FactScoringStage().run(document)

    entity_candidates = list(document.store.entity_candidates.values())
    assert len(entity_candidates) == 2

    full_person = next(c for c in entity_candidates if c.canonical_hint == "Jan Kowalski")
    surname_person = next(c for c in entity_candidates if c.canonical_hint == "Kowalski")

    full_mention = document.store.mentions[full_person.mention_ids[0]]
    surname_mention = document.store.mentions[surname_person.mention_ids[0]]
    assert full_mention.kind == MentionKind.NER
    assert surname_mention.kind == MentionKind.SURNAME_ONLY

    claims = list(document.store.resolution_claims.values())
    assert len(claims) == 1
    claim = claims[0]
    assert {claim.left_entity_id, claim.right_entity_id} == {full_person.id, surname_person.id}
    assert claim.assessment.score >= 0.5


def test_benchmark_multiparagraph_same_name_party_contrast() -> None:
    paragraphs = (
        "Jan Kowalski z PO został powołany.",
        "Tymczasem Jan Kowalski z PiS złożył dymisję.",
    )
    text = "\n\n".join(paragraphs)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=paragraphs,
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)

    first_name_index = text.index("Jan Kowalski")
    second_name_index = text.index("Jan Kowalski", first_name_index + 1)

    entities = (
        NamedEntitySpan(
            text="Jan Kowalski",
            label=NerLabel.PERSON,
            span=Span(first_name_index, first_name_index + len("Jan Kowalski")),
        ),
        NamedEntitySpan(
            text="Jan Kowalski",
            label=NerLabel.PERSON,
            span=Span(second_name_index, second_name_index + len("Jan Kowalski")),
        ),
    )
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)

    entity_candidates = list(document.store.entity_candidates.values())
    assert len(entity_candidates) == 2
    left_person = entity_candidates[0]
    right_person = entity_candidates[1]

    po_party_id = document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-po"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(),
            canonical_hint="Platforma Obywatelska",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("benchmark_manual"),
        )
    )
    pis_party_id = document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-pis"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(),
            canonical_hint="Prawo i Sprawiedliwość",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("benchmark_manual"),
        )
    )

    add_event(
        document,
        event_id=EventCandidateId("event-po"),
        fact_id=FactCandidateId("fact-po"),
        kind=FactKind.PARTY_AFFILIATION,
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("binding-po-subject"),
        event_id=EventCandidateId("event-po"),
        role=EventRole.SUBJECT,
        entity_id=left_person.id,
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("binding-po-object"),
        event_id=EventCandidateId("event-po"),
        role=EventRole.OBJECT,
        entity_id=po_party_id,
    )
    add_event(
        document,
        event_id=EventCandidateId("event-pis"),
        fact_id=FactCandidateId("fact-pis"),
        kind=FactKind.PARTY_AFFILIATION,
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("binding-pis-subject"),
        event_id=EventCandidateId("event-pis"),
        role=EventRole.SUBJECT,
        entity_id=right_person.id,
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("binding-pis-object"),
        event_id=EventCandidateId("event-pis"),
        role=EventRole.OBJECT,
        entity_id=pis_party_id,
    )

    FactScoringStage().run(document)

    claims = list(document.store.resolution_claims.values())
    assert len(claims) == 1
    claim = claims[0]
    assert claim.assessment.score < 0.5
    assert any(
        signal
        == ConflictingPartyAffiliationSignal(
            left_party_hint="platforma obywatelska",
            right_party_hint="prawo i sprawiedliwość",
        )
        for signal in claim.assessment.negative_signals
    )
