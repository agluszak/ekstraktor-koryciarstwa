from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.coreference import CoreferenceReferenceStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    ProducerId,
    SentenceId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
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
)
from tests_v2.materialized import (
    add_event,
    bind_entity,
    entity_hint_for_role,
    fact_records,
    first_fact_record,
    span_of,
    text_argument,
)


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
        span=span_of(text, name),
    )


def organization_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=span_of(text, name),
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
    ProbabilisticInferenceStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    # The copular "jest prezesem" states current role holding; the later
    # "powołany" sentence may corroborate the same role but should not turn the
    # holding statement into an appointment.
    assert record.kind is FactKind.PUBLIC_ROLE_HOLDING
    assert entity_hint_for_role(document, record, "person") == "Jan Kowalski"
    assert entity_hint_for_role(document, record, "organization") == "Wodkan"
    assert entity_hint_for_role(document, record, "role") == "prezesem"
    assert assessment.score >= 0.6


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
    ProbabilisticInferenceStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert entity_hint_for_role(document, record, "person") == "Marka Nowaka"
    assert entity_hint_for_role(document, record, "organization") == "Urząd miasta"
    assert entity_hint_for_role(document, record, "role") == "doradcę"
    assert set(record.signals) == {
        PublicEmploymentLemmaSignal(lemma="zatrudnić"),
        LocalPersonSignal(),
        LocalOrganizationSignal(),
        LocalRoleSignal(),
    }
    assert assessment.score >= 0.6


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
    ProbabilisticInferenceStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert fact_records(document) != ()
    assert record.kind is FactKind.PUBLIC_CONTRACT
    assert entity_hint_for_role(document, record, "counterparty") == "Urząd"
    assert entity_hint_for_role(document, record, "contractor") == "Alfa"
    assert text_argument(record, "amount") == "49 tys. zł"
    assert assessment.score >= 0.6


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
    ProbabilisticInferenceStage().run(document)

    records = fact_records(document)
    referral_records = [r for r in records if r.kind == FactKind.ANTI_CORRUPTION_REFERRAL]
    assert len(referral_records) == 1
    referral_record = referral_records[0]

    assert entity_hint_for_role(document, referral_record, "complainant") == (
        "Prawo i Sprawiedliwość"
    )
    assert entity_hint_for_role(document, referral_record, "target") == "Jana Nowaka"
    assert entity_hint_for_role(document, referral_record, "institution") == "CBA"
    assert text_argument(referral_record, "context") == "w sprawie zatrudnienia Jana Nowaka"


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
                    antecedent_span=Span(
                        antecedent_start,
                        antecedent_start + len("Jan Kowalski"),
                    ),
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
    ProbabilisticInferenceStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.KINSHIP_TIE
    assert entity_hint_for_role(document, record, "subject") == "spouse of Jan Kowalski"
    assert entity_hint_for_role(document, record, "object") == "Jan Kowalski"
    assert text_argument(record, "relationship_detail") == "spouse"
    assert assessment.score >= 0.3


def test_benchmark_party_true_negative_scenario() -> None:
    text = "Radni PiS skrytykowali projekt budżetu miasta."
    document, morphology = build_document(text)

    PartyCandidateStage(morphology).run(document)
    ProbabilisticInferenceStage().run(document)

    assert tuple(record.kind for record in fact_records(document)) == ()


def test_benchmark_anti_corruption_investigation_scenario() -> None:
    text = "Prokuratura wszczęła śledztwo w sprawie Jana Nowaka."
    document, _morphology = build_document(text, (person_span(text, "Jana Nowaka"),))

    AntiCorruptionCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert entity_hint_for_role(document, record, "target") == "Jana Nowaka"
    assert text_argument(record, "institution") == "Prokuratura"
    assert text_argument(record, "context") == "w sprawie Jana Nowaka"
    assert set(record.signals) == {
        AntiCorruptionInvestigationLemmaSignal(lemma="wszcząć"),
        OversightInstitutionSignal(),
        LocalTargetSignal(),
    }
    assert assessment.score >= 0.6


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
    ProbabilisticInferenceStage().run(document)

    records = fact_records(document)
    kinship_records = [r for r in records if r.kind == FactKind.KINSHIP_TIE]
    assert len(kinship_records) >= 1
    record = kinship_records[0]
    assessment_record = next(
        a for a in document.fact_assessments if a.materialized_fact_id == record.id
    )
    assessment = assessment_record.assessment

    assert record.kind is FactKind.KINSHIP_TIE
    assert entity_hint_for_role(document, record, "subject") == "Marek Kowalski"
    assert entity_hint_for_role(document, record, "object") == "Jana Kowalskiego"
    assert text_argument(record, "relationship_detail") == "child"
    assert assessment.score >= 0.6


def test_benchmark_party_and_oversight_true_negative_scenario() -> None:
    text = "NIK opublikowała raport o kontroli urzędu. PiS skrytykował jego wnioski."
    document, morphology = build_document(text)

    PartyCandidateStage(morphology).run(document)
    AntiCorruptionCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

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
            span=span_of(text, "Jan Kowalski"),
        ),
        NamedEntitySpan(
            text="Kowalski",
            label=NerLabel.PERSON,
            span=span_of(text, "Kowalski"),
        ),
    )
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)

    ProbabilisticInferenceStage().run(document)

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
        kind=FactKind.PARTY_MEMBERSHIP,
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
        kind=FactKind.PARTY_MEMBERSHIP,
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

    ProbabilisticInferenceStage().run(document)

    # Party-contradicted same-name pairs produce no resolution claim: the same-entity
    # posterior falls below the 0.5 gate, so the pair is not merged.
    claims = list(document.store.resolution_claims.values())
    assert len(claims) == 0
