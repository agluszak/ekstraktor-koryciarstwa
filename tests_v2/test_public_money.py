from __future__ import annotations

from pipeline_v2.candidates import EntityFactArgument
from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import LexicalEntityContextStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import (
    ContractCounterpartySignal,
    ContractDocumentSignal,
    ContractorSignal,
    DirectPrepositionalAttachmentSignal,
    EventRole,
    FactArgumentRole,
    FactKind,
    FundingLemmaSignal,
    GrantTransactionSignal,
    LocalPhraseRecipientSignal,
    MicroAmountSignal,
    MoneyAmountSignal,
    NerLabel,
    PublicContractLemmaSignal,
    ServiceTransactionSignal,
)
from tests_v2.materialized import (
    entity_argument,
    entity_hint_for_role,
    fact_records,
    first_fact_record,
    text_argument,
)


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def entity_filler_hint(document: ArticleDocument, filler) -> str | None:
    match filler:
        case EntityFactArgument(entity_id=entity_id):
            return document.store.entity_candidates[entity_id].canonical_hint
        case _:
            return None


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
    LexicalEntityContextStage().run(document)
    PublicMoneyCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
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
    LexicalEntityContextStage().run(document)
    PublicMoneyCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
    return document


def run_public_money_producer_stage_with_entities(
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
    PublicMoneyCandidateStage().run(document)
    return document


def test_public_money_stage_distinguishes_contract_grant_and_compensation() -> None:
    document = run_public_money_stage(
        "Urząd podpisał umowy za 49 tys. zł. "
        "Fundacja otrzymała 100 tys. zł dotacji. "
        "Prezes pobrał 250 tys. zł wynagrodzenia."
    )

    records = fact_records(document)

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

    assert fact_records(document) == ()


def test_public_money_facts_are_scored_from_evidence_signals() -> None:
    document = run_public_money_stage("Fundacja otrzymała 100 tys. zł dotacji.")

    ProbabilisticInferenceStage().run(document)

    assert len(document.fact_assessments) == 1
    assessment = document.fact_assessments[0].assessment
    assert assessment.score >= 0.7
    assert set(assessment.positive_signals) == {
        MoneyAmountSignal(amount="100 tys. zł"),
        FundingLemmaSignal(lemma="dotacja"),
        LocalPhraseRecipientSignal(),
        GrantTransactionSignal(),
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

    record = first_fact_record(document)

    assert record.kind is FactKind.PUBLIC_CONTRACT
    assert entity_hint_for_role(document, record, "counterparty") == "Urząd Miasta"
    assert entity_hint_for_role(document, record, "contractor") == "Alfa"
    assert text_argument(record, "amount") == "49 tys. zł"
    assert set(record.signals) == {
        MoneyAmountSignal(amount="49 tys. zł"),
        PublicContractLemmaSignal(lemma="podpisać"),
        ContractCounterpartySignal(),
        ContractorSignal(),
        # Both parties now carry syntactic-position evidence:
        # Urząd Miasta is subject (no prep) → counterparty boost;
        # Alfa follows "z" → contractor boost.
        DirectPrepositionalAttachmentSignal(),
        ContractDocumentSignal(),
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

    record = first_fact_record(document)

    assert record.kind is FactKind.FUNDING
    assert entity_hint_for_role(document, record, "recipient") == "Fundacja Alfa"
    assert text_argument(record, "amount") == "100 tys. zł"


def test_public_money_stage_emits_partial_ownership_event_before_inference() -> None:
    text = "Jan Kowalski posiada udziały warte 10 tys. zł."
    document = run_public_money_producer_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
        ),
    )

    ownership_events = tuple(
        event
        for event in document.store.event_candidates.values()
        if event.kind is FactKind.CORPORATE_OWNERSHIP
    )
    assert ownership_events
    bindings = document.store.argument_bindings_for_event(ownership_events[0].id)
    assert any(binding.role is EventRole.SUBJECT for binding in bindings)
    assert any(binding.role is EventRole.AMOUNT for binding in bindings)
    assert not any(binding.role is EventRole.OBJECT for binding in bindings)


def test_public_money_stage_infers_local_organization_phrases_when_ner_misses_parties() -> None:
    text = (
        "Fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego "
        "Karola Bielskiego otrzymała 100 tysięcy złotych z urzędu marszałkowskiego "
        "za promowanie imprezy."
    )
    document = run_public_money_stage(text)

    record = first_fact_record(document)

    assert record.kind is FactKind.FUNDING
    assert entity_hint_for_role(document, record, "funder") == "urzędu marszałkowskiego"
    assert entity_hint_for_role(document, record, "recipient") == (
        "Fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola Bielskiego"
    )
    assert text_argument(record, "amount") == "100 tysięcy złotych"
    funder = document.store.entity_candidates[entity_argument(record, "funder")]
    assert funder.grounding.value == "inferred"
    recipient = document.store.entity_candidates[entity_argument(record, "recipient")]
    assert recipient.grounding.value == "inferred"


def test_public_money_stage_overproduces_mixed_service_and_grant_shapes() -> None:
    document = run_public_money_stage(
        "Fundacja otrzymała 100 tys. zł dotacji za usługę promocyjną."
    )

    kinds = {record.kind for record in fact_records(document)}

    assert FactKind.FUNDING in kinds
    assert FactKind.PUBLIC_CONTRACT in kinds
    contract = next(
        record for record in fact_records(document) if record.kind is FactKind.PUBLIC_CONTRACT
    )
    assert ServiceTransactionSignal() in contract.signals


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
    ProbabilisticInferenceStage().run(document)

    scores_by_funder_hint = {}
    for record in fact_records(document):
        funder_hint = entity_hint_for_role(document, record, "funder")
        assessment = next(
            item.assessment
            for item in document.fact_assessments
            if item.materialized_fact_id == record.id
        )
        scores_by_funder_hint[funder_hint] = assessment.score

    assert scores_by_funder_hint["AMW Rewita"] >= 0.6
    alternatives = document.materialized_role_alternatives[first_fact_record(document).id]
    mon_funder_alternative = next(
        alternative
        for alternative in alternatives
        if alternative.role is FactArgumentRole.FUNDER
        and entity_filler_hint(document, alternative.filler) == "Ministerstwu Obrony Narodowej"
    )
    assert mon_funder_alternative.posterior < 0.1


def test_public_money_stage_emits_compensation_for_perfective_salary_verb() -> None:
    text = (
        "W Totalizatorze Sportowym są dyrektorskie stanowiska. "
        "Osoby na tych stanowiskach mogą zarobić nawet ponad 20 tys. zł miesięcznie."
    )
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Totalizatorze Sportowym",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Totalizatorze Sportowym"),
                    text.index("Totalizatorze Sportowym") + len("Totalizatorze Sportowym"),
                ),
            ),
        ),
    )

    compensation_records = [
        record for record in fact_records(document) if record.kind is FactKind.COMPENSATION
    ]
    assert len(compensation_records) == 1
    record = compensation_records[0]
    assert entity_hint_for_role(document, record, "funder") == "Totalizatorze Sportowym"
    assert text_argument(record, "amount") == "20 tys. zł"


def test_public_money_stage_emits_compensation_for_textual_amount_phrase() -> None:
    text = (
        "Kierowanie WFOŚiGW wiąże się również z wysokimi zarobkami rzędu "
        "kilkudziesięciu tysięcy złotych miesięcznie."
    )
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="WFOŚiGW",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("WFOŚiGW"), text.index("WFOŚiGW") + len("WFOŚiGW")),
            ),
        ),
    )

    compensation_records = [
        record for record in fact_records(document) if record.kind is FactKind.COMPENSATION
    ]
    assert len(compensation_records) == 1
    record = compensation_records[0]
    assert entity_hint_for_role(document, record, "funder") == "WFOŚiGW"
    assert text_argument(record, "amount") == "kilkudziesięciu tysięcy złotych"


def test_public_contract_stage_does_not_materialize_same_surface_on_both_sides() -> None:
    text = "Wnuk Consulting zawarł umowę z miastem na 397 496,95 zł."
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Wnuk Consulting",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wnuk Consulting"), text.index("Wnuk Consulting") + 15),
            ),
            NamedEntitySpan(
                text="Wnuk Consulting",
                label=NerLabel.PERSON,
                span=Span(text.index("Wnuk Consulting"), text.index("Wnuk Consulting") + 15),
            ),
            NamedEntitySpan(
                text="miastem",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("miastem"), text.index("miastem") + 7),
            ),
        ),
    )

    for record in fact_records(document):
        if record.kind is not FactKind.PUBLIC_CONTRACT:
            continue
        roles = {argument.to_json()["role"] for argument in record.arguments}
        if {"counterparty", "contractor"} <= roles:
            assert entity_hint_for_role(document, record, "counterparty") != entity_hint_for_role(
                document, record, "contractor"
            )


def test_public_money_stage_materializes_amount_backed_delivery_with_person_contractor() -> None:
    text = "Dominik Herberholz dostarczył program komputerowy za 180 tys. zł."
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Dominik Herberholz",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Dominik Herberholz"),
                    text.index("Dominik Herberholz") + 18,
                ),
            ),
        ),
    )

    record = first_fact_record(document)

    assert record.kind is FactKind.PUBLIC_CONTRACT
    assert entity_hint_for_role(document, record, "contractor") == "Dominik Herberholz"
    assert text_argument(record, "amount") == "180 tys. zł"


def test_compensation_without_funder_or_recipient_does_not_materialize() -> None:
    document = run_public_money_stage("Premia wyniosła 100 tys. zł.")

    assert fact_records(document) == ()


def test_funding_stage_does_not_materialize_same_surface_for_funder_and_recipient() -> None:
    text = "Fundacja Lux Veritatis otrzymała od Fundacji Lux Veritatis 100 tys. zł dotacji."
    document = run_public_money_stage_with_entities(
        text,
        (
            NamedEntitySpan(
                text="Fundacja Lux Veritatis",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Fundacja Lux Veritatis"),
                    text.index("Fundacja Lux Veritatis") + 22,
                ),
            ),
            NamedEntitySpan(
                text="Fundacji Lux Veritatis",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Fundacji Lux Veritatis"),
                    text.index("Fundacji Lux Veritatis") + 22,
                ),
            ),
        ),
    )

    for record in fact_records(document):
        if record.kind is not FactKind.FUNDING:
            continue
        roles = {argument.to_json()["role"] for argument in record.arguments}
        if {"funder", "recipient"} <= roles:
            assert entity_hint_for_role(document, record, "funder") != entity_hint_for_role(
                document, record, "recipient"
            )


def test_public_money_stage_does_not_flag_thousands_amount_as_micro() -> None:
    text = "Urząd Miasta podpisał umowę z firmą Alfa za 253 tys. zł."
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

    record = first_fact_record(document)

    assert record.kind is FactKind.PUBLIC_CONTRACT
    assert text_argument(record, "amount") == "253 tys. zł"
    assert not any(isinstance(s, MicroAmountSignal) for s in record.signals)
