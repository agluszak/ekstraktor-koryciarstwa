from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.ids import DocumentId, EntityCandidateId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import (
    ContractCounterpartySignal,
    ContractorSignal,
    FactArgumentRole,
    FactKind,
    FundingLemmaSignal,
    LocalPhraseRecipientSignal,
    MoneyAmountSignal,
    NerLabel,
    PublicContractLemmaSignal,
)


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_public_money_stage(text: str) -> ArticleDocument:
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
    PublicMoneyCandidateStage().run(document)
    return document


def run_public_money_stage_with_entities(
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
    PublicMoneyCandidateStage().run(document)
    return document


def test_public_money_stage_distinguishes_contract_grant_and_compensation() -> None:
    document = run_public_money_stage(
        "Urząd podpisał umowy za 49 tys. zł. "
        "Fundacja otrzymała 100 tys. zł dotacji. "
        "Prezes pobrał 250 tys. zł wynagrodzenia."
    )

    records = tuple(
        candidate.to_fact_record() for candidate in document.store.fact_candidates.values()
    )

    assert tuple(record.kind for record in records) == (
        FactKind.PUBLIC_CONTRACT,
        FactKind.FUNDING,
        FactKind.COMPENSATION,
    )
    assert tuple(
        argument.to_json()
        for record in records
        for argument in record.arguments
        if argument.role == FactArgumentRole.AMOUNT
    ) == (
        {"role": "amount", "value": "49 tys. zł"},
        {"role": "amount", "value": "100 tys. zł"},
        {"role": "amount", "value": "250 tys. zł"},
    )


def test_public_money_stage_does_not_emit_transfer_fact_without_amount() -> None:
    document = run_public_money_stage("Rzeczniczka przekazała nam komentarz urzędu.")

    assert tuple(document.store.fact_candidates.values()) == ()


def test_public_money_facts_are_scored_from_evidence_signals() -> None:
    document = run_public_money_stage("Fundacja otrzymała 100 tys. zł dotacji.")

    FactScoringStage().run(document)

    assert len(document.fact_assessments) == 1
    assessment = document.fact_assessments[0].assessment
    assert assessment.score >= 0.7
    assert set(assessment.positive_signals) == {
        MoneyAmountSignal(amount="100 tys. zł"),
        FundingLemmaSignal(lemma="dotacja"),
        LocalPhraseRecipientSignal(),
    }


def test_public_money_stage_attaches_sentence_local_parties_as_uncertain_arguments() -> None:
    text = "Urząd Miasta podpisał umowę z firmą Alfa za 49 tys. zł."
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Urząd Miasta",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Urząd Miasta"), text.index("Urząd Miasta") + 12),
            ),
            NamedEntitySpan(
                text="Alfa",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Alfa"), text.index("Alfa") + 4),
            ),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.PUBLIC_CONTRACT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "counterparty", "entity_id": "entity-0"},
        {"role": "contractor", "entity_id": "entity-1"},
        {"role": "amount", "value": "49 tys. zł"},
    )
    assert set(record.signals) == {
        MoneyAmountSignal(amount="49 tys. zł"),
        PublicContractLemmaSignal(lemma="podpisać"),
        ContractCounterpartySignal(),
        ContractorSignal(),
    }


def test_public_money_stage_marks_single_receiving_organization_as_recipient() -> None:
    text = "Fundacja Alfa otrzymała 100 tys. zł dotacji."
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Fundacja Alfa",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Fundacja Alfa"), text.index("Fundacja Alfa") + 13),
            ),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.FUNDING
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "recipient", "entity_id": "entity-0"},
        {"role": "amount", "value": "100 tys. zł"},
    )


def test_public_money_stage_infers_local_organization_phrases_when_ner_misses_parties() -> None:
    text = (
        "Fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego "
        "Karola Bielskiego otrzymała 100 tysięcy złotych z urzędu marszałkowskiego "
        "za promowanie imprezy."
    )
    document = run_public_money_stage(text)

    candidate = next(iter(document.store.fact_candidates.values()))
    record = candidate.to_fact_record()

    assert record.kind is FactKind.FUNDING
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "funder", "entity_id": "entity-0"},
        {"role": "recipient", "entity_id": "entity-1"},
        {"role": "amount", "value": "100 tysięcy złotych"},
    )
    assert (
        document.store.entity_candidates[EntityCandidateId("entity-0")].canonical_hint
        == "urzędu marszałkowskiego"
    )
    assert document.store.entity_candidates[EntityCandidateId("entity-1")].canonical_hint == (
        "Fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola Bielskiego"
    )
    assert (
        document.store.entity_candidates[EntityCandidateId("entity-0")].grounding.value
        == "inferred"
    )
    assert (
        document.store.entity_candidates[EntityCandidateId("entity-1")].grounding.value
        == "inferred"
    )


def test_compensation_scores_controller_organization_below_direct_employer() -> None:
    text = (
        "AMW Rewita podległa Ministerstwu Obrony Narodowej zatrudniła Rząsowskiego. "
        "Poprzednik Rząsowskiego zarabiał 24 tys. zł wynagrodzenia."
    )
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="AMW Rewita",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("AMW Rewita"), text.index("AMW Rewita") + 10),
            ),
            NamedEntitySpan(
                text="Ministerstwu Obrony Narodowej",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Ministerstwu Obrony Narodowej"),
                    text.index("Ministerstwu Obrony Narodowej")
                    + len("Ministerstwu Obrony Narodowej"),
                ),
            ),
            NamedEntitySpan(
                text="Rząsowskiego",
                label=NerLabel.PERSON,
                span=Span(text.index("Rząsowskiego"), text.index("Rząsowskiego") + 11),
            ),
        ),
    )
    FactScoringStage().run(document)

    scores_by_funder_id = {}
    for candidate in document.store.fact_candidates.values():
        record = candidate.to_fact_record()
        funder = next(
            argument.to_json()["entity_id"]
            for argument in record.arguments
            if argument.to_json()["role"] == "funder"
        )
        assessment = next(
            item.assessment
            for item in document.fact_assessments
            if item.fact_candidate_id == candidate.id
        )
        scores_by_funder_id[funder] = assessment.score

    assert scores_by_funder_id["entity-0"] >= 0.7
    assert scores_by_funder_id["entity-1"] < 0.5
