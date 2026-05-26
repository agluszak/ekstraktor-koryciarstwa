from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityFactArgument,
    EntityFiller,
    FactCandidateRecord,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import LexicalEntityContextStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId, EntityCandidateId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import (
    Morfeusz2MorphologyAdapter,
    NamedEntitySpan,
    ParsedDependencySentence,
    ParsedDependencyToken,
    Span,
)
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.syntax import DependencyParseStage
from pipeline_v2.types import (
    AppointmentLemmaSignal,
    DependencyRelation,
    EntityKind,
    EntityTag,
    EventRole,
    FactKind,
    ImplausiblePersonBindingSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    NerLabel,
    PartyOrganizationSignal,
    WindowOrganizationSignal,
)
from tests_v2.materialized import (
    argument_roles,
    entity_hint_for_role,
    fact_records,
    first_fact_record,
    text_argument,
)


@dataclass(frozen=True, slots=True)
class StaticDependencyProvider:
    parsed: tuple[ParsedDependencySentence, ...]

    def parse(self, text: str) -> tuple[ParsedDependencySentence, ...]:
        _ = text
        return self.parsed


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_governance_stage(
    text: str,
    entities: tuple[NamedEntitySpan, ...],
    paragraphs: tuple[str, ...] | None = None,
) -> ArticleDocument:
    actual_paragraphs = paragraphs or (text,)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=actual_paragraphs,
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)
    LexicalEntityContextStage().run(document)
    RoleCandidateStage(morphology).run(document)
    GovernanceCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
    return document


def test_governance_stage_emits_appointment_candidate_with_sentence_local_entities() -> None:
    text = "Jan Kowalski został powołany do zarządu spółki Wodkan."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    record = first_fact_record(document)

    assert record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    assert entity_hint_for_role(document, record, "person") == "Jan Kowalski"
    assert entity_hint_for_role(document, record, "organization") == "Wodkan"
    assert entity_hint_for_role(document, record, "role") == "zarządu"
    assert {
        AppointmentLemmaSignal(lemma="powołać"),
        LocalPersonSignal(),
        LocalOrganizationSignal(),
        LocalRoleSignal(),
    } <= set(record.signals)


def test_governance_stage_emits_dismissal_candidate_and_fact_score() -> None:
    text = "Anna Nowak została odwołana z rady nadzorczej spółki Komunalnik."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Anna Nowak",
                label=NerLabel.PERSON,
                span=Span(text.index("Anna Nowak"), text.index("Anna Nowak") + 10),
            ),
            NamedEntitySpan(
                text="Komunalnik",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Komunalnik"), text.index("Komunalnik") + 9),
            ),
        ),
    )

    ProbabilisticInferenceStage().run(document)
    # Both PUBLIC_ROLE_APPOINTMENT (from 'zostać') and PUBLIC_ROLE_END
    # (from 'odwołać') are emitted; find the dismissal specifically.
    dismissal_record = next(
        record for record in fact_records(document) if record.kind is FactKind.PUBLIC_ROLE_END
    )

    assert dismissal_record.kind is FactKind.PUBLIC_ROLE_END
    dismissal_assessment = next(
        a.assessment
        for a in document.fact_assessments
        if a.materialized_fact_id == dismissal_record.id
    )
    assert dismissal_assessment.score >= 0.6


def test_governance_stage_keeps_generic_appointment_in_separate_dismissal_clause() -> None:
    text = "Jan Kowalski został prezesem spółki Wodkan po tym, jak odwołano Annę Nowak."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
            NamedEntitySpan(
                text="Annę Nowak",
                label=NerLabel.PERSON,
                span=Span(text.index("Annę Nowak"), text.index("Annę Nowak") + 10),
            ),
        ),
    )

    appointments = [
        record
        for record in fact_records(document)
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    ]
    assert any(
        entity_hint_for_role(document, record, "person") == "Jan Kowalski"
        and entity_hint_for_role(document, record, "organization") == "Wodkan"
        for record in appointments
    )


def test_governance_stage_does_not_emit_candidate_without_person_entity() -> None:
    text = "Zarząd spółki Wodkan został powołany w maju."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    assert fact_records(document) == ()


def test_governance_stage_does_not_emit_person_only_appointment() -> None:
    text = "Stanisław Mazur został powołany w maju."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Stanisław Mazur",
                label=NerLabel.PERSON,
                span=Span(text.index("Stanisław Mazur"), text.index("Stanisław Mazur") + 15),
            ),
        ),
    )

    assert fact_records(document) == ()


def test_governance_stage_uses_adjacent_sentence_context_for_split_appointment() -> None:
    first = "Jan Kowalski jest prezesem spółki Wodkan."
    second = "Został powołany bez konkursu."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    record = next(
        record
        for record in fact_records(document)
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    )

    # The copular "jest prezesem" in sentence 1 produces the primary fact.  The
    # "Został powołany" in sentence 2 provides corroborating evidence via window
    # entities and is merged into the same fact by inference.  Both triggers must
    # result in a single governance appointment about Jan Kowalski.
    assert record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    assert entity_hint_for_role(document, record, "person") == "Jan Kowalski"
    assert entity_hint_for_role(document, record, "organization") == "Wodkan"
    assert entity_hint_for_role(document, record, "role") == "prezesem"


def test_governance_stage_does_not_use_previous_paragraph_for_missing_person() -> None:
    first = "Jan Kowalski jest prezesem spółki Wodkan."
    second = "Został powołany bez konkursu."
    text = f"{first}\n{second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
        paragraphs=(first, second),
    )

    # The copular "jest prezesem" in para 1 produces a local fact.  The second
    # paragraph's "powołany" must NOT use cross-paragraph window entities.
    records = fact_records(document)
    assert not any(AppointmentLemmaSignal(lemma="powołać") in r.signals for r in records), (
        "cross-paragraph window appointment should not be produced"
    )


def test_governance_stage_emits_holding_for_role_first_persistence_clause() -> None:
    first = "Krzysztof Michalski będzie prezesem spółki Aqua."
    second = "Wiceprezesem firmy pozostaje Henryk Wysogląd."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Krzysztof Michalski",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Krzysztof Michalski"),
                    text.index("Krzysztof Michalski") + 19,
                ),
            ),
            NamedEntitySpan(
                text="Henryk Wysogląd",
                label=NerLabel.PERSON,
                span=Span(text.index("Henryk Wysogląd"), text.index("Henryk Wysogląd") + len("Henryk Wysogląd")),
            ),
            NamedEntitySpan(
                text="Aqua",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Aqua"), text.index("Aqua") + 4),
            ),
        ),
    )

    holdings = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert any(
        entity_hint_for_role(document, record, "person") == "Henryk Wysogląd"
        and entity_hint_for_role(document, record, "organization") == "Aqua"
        and (entity_hint_for_role(document, record, "role") or "").startswith("Wiceprezes")
        for record in holdings
    )


def test_governance_stage_prefers_board_role_in_zasiadac_clause() -> None:
    text = (
        "Krzysztof Michalski zasiada także w radzie nadzorczej spółki GPW Inżynieria, "
        "na co zgodę wyraziła rada nadzorcza spółki Aqua."
    )
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Krzysztof Michalski",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Krzysztof Michalski"),
                    text.index("Krzysztof Michalski") + 19,
                ),
            ),
            NamedEntitySpan(
                text="GPW Inżynieria",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("GPW Inżynieria"), text.index("GPW Inżynieria") + 14),
            ),
            NamedEntitySpan(
                text="Aqua",
                label=NerLabel.ORGANIZATION,
                span=Span(text.rindex("Aqua"), text.rindex("Aqua") + 4),
            ),
        ),
    )

    holdings = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert any(
        entity_hint_for_role(document, record, "person") == "Krzysztof Michalski"
        and entity_hint_for_role(document, record, "organization") == "GPW Inżynieria"
        and "nadzorc" in (entity_hint_for_role(document, record, "role") or "").casefold()
        for record in holdings
    )


def test_governance_stage_prefers_pretrigger_board_role_in_zasiadac_clause() -> None:
    text = (
        "W radzie nadzorczej spółki Aqua zasiada Maria Wasiak, "
        "wiceprezydent Bydgoszczy i była minister."
    )
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Maria Wasiak",
                label=NerLabel.PERSON,
                span=Span(text.index("Maria Wasiak"), text.index("Maria Wasiak") + 12),
            ),
            NamedEntitySpan(
                text="Aqua",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Aqua"), text.index("Aqua") + 4),
            ),
            NamedEntitySpan(
                text="Bydgoszczy",
                label=NerLabel.LOCATION,
                span=Span(text.index("Bydgoszczy"), text.index("Bydgoszczy") + 10),
            ),
        ),
    )

    holdings = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert any(
        entity_hint_for_role(document, record, "person") == "Maria Wasiak"
        and entity_hint_for_role(document, record, "organization") == "Aqua"
        and "nadzorc" in (entity_hint_for_role(document, record, "role") or "").casefold()
        and text_argument(record, "role_domain") == "supervisory_board"
        for record in holdings
    )


def test_governance_stage_prefers_predicate_role_over_former_political_apposition() -> None:
    text = "W samorządowej spółce Aqua wiceszefem rady nadzorczej jest były minister Jan Kowalski."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Aqua",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Aqua"), text.index("Aqua") + 4),
            ),
        ),
    )

    holdings = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert any(
        entity_hint_for_role(document, record, "person") == "Jan Kowalski"
        and entity_hint_for_role(document, record, "organization") == "Aqua"
        and (role := (entity_hint_for_role(document, record, "role") or "").casefold())
        and "minister" not in role
        and ("wiceszef" in role or "nadzorc" in role)
        for record in holdings
    )


def test_governance_stage_prefers_post_trigger_person_over_historical_name_in_holding_clause() -> (
    None
):
    text = "Jej prezesem jest Konrad Mikołajski, wcześniej prezes Zachemu i członek zarządu KPEC."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Konrad Mikołajski",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Konrad Mikołajski"),
                    text.index("Konrad Mikołajski") + 17,
                ),
            ),
            NamedEntitySpan(
                text="Zachemu",
                label=NerLabel.PERSON,
                span=Span(text.index("Zachemu"), text.index("Zachemu") + 7),
            ),
            NamedEntitySpan(
                text="KPEC",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("KPEC"), text.index("KPEC") + 4),
            ),
        ),
    )

    holdings = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert any(
        entity_hint_for_role(document, record, "person") == "Konrad Mikołajski"
        and "prezes" in (entity_hint_for_role(document, record, "role") or "").casefold()
        for record in holdings
    )
    assert not any(
        entity_hint_for_role(document, record, "person") == "Konrad Mikołajski"
        and "organization" in argument_roles(record)
        and entity_hint_for_role(document, record, "organization") == "KPEC"
        and "prezes" in (entity_hint_for_role(document, record, "role") or "").casefold()
        for record in holdings
    )
    assert not any(
        entity_hint_for_role(document, record, "person") == "Zachemu"
        and "prezes" in (entity_hint_for_role(document, record, "role") or "").casefold()
        for record in holdings
    )


def test_governance_stage_skips_former_political_title_background_holding() -> None:
    text = "W ProNaturze pracuje Jan Kowalski, były radny PiS."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="ProNaturze",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("ProNaturze"), text.index("ProNaturze") + 10),
            ),
        ),
    )

    assert not any(
        record.kind is FactKind.PUBLIC_ROLE_HOLDING
        and entity_hint_for_role(document, record, "person") == "Jan Kowalski"
        and "radn" in (entity_hint_for_role(document, record, "role") or "").casefold()
        for record in fact_records(document)
    )


def test_governance_stage_ignores_following_sentence_background_organization() -> None:
    first = "Z funkcji odwołany został dotychczasowy prezes Olgierd Cieślik."
    second = "Wcześniej pełnił kierownicze stanowiska w Poczcie Polskiej."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Olgierd Cieślik",
                label=NerLabel.PERSON,
                span=Span(text.index("Olgierd Cieślik"), text.index("Olgierd Cieślik") + 15),
            ),
            NamedEntitySpan(
                text="Poczcie Polskiej",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Poczcie Polskiej"), text.index("Poczcie Polskiej") + 16),
            ),
        ),
    )

    # 'odwołany został' fires both a dismissal ('odwołać') and an appointment
    # ('zostać').  The test verifies the dismissal specifically, and that the
    # following-sentence organisation is NOT used as an org argument.
    dismissal_candidate = next(
        record for record in fact_records(document) if record.kind is FactKind.PUBLIC_ROLE_END
    )
    record = dismissal_candidate

    assert record.kind is FactKind.PUBLIC_ROLE_END
    assert {"person", "role"} <= argument_roles(record)
    assert entity_hint_for_role(document, record, "person") == "Olgierd Cieślik"
    assert entity_hint_for_role(document, record, "role") == "prezes"


def test_governance_stage_keeps_party_organization_out_of_primary_facts() -> None:
    text = "Sławomir Czwal, działacz Koalicji Obywatelskiej, został powołany na dyrektora."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Sławomir Czwal",
                label=NerLabel.PERSON,
                span=Span(text.index("Sławomir Czwal"), text.index("Sławomir Czwal") + 15),
            ),
            NamedEntitySpan(
                text="Koalicji Obywatelskiej",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Koalicji Obywatelskiej"),
                    text.index("Koalicji Obywatelskiej") + 22,
                ),
            ),
        ),
    )

    for record in fact_records(document):
        roles = argument_roles(record)
        if "organization" in roles:
            assert (
                entity_hint_for_role(document, record, "organization") != "Koalicji Obywatelskiej"
            )
    assert any(
        binding.event_id in document.store.event_candidates
        and document.store.event_candidates[binding.event_id].kind
        is FactKind.PUBLIC_ROLE_APPOINTMENT
        and PartyOrganizationSignal() in binding.signals
        for bindings in document.store.argument_bindings_by_event_id.values()
        for binding in bindings
    )


def test_governance_stage_treats_inflected_ministry_as_context_not_organization() -> None:
    text = (
        "Jan Kowalski został powołany na prezesa Orlenu decyzją Ministerstwa Aktywów Państwowych."
    )
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Orlenu",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Orlenu"), text.index("Orlenu") + 6),
            ),
            NamedEntitySpan(
                text="Ministerstwa Aktywów Państwowych",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Ministerstwa Aktywów Państwowych"),
                    text.index("Ministerstwa Aktywów Państwowych") + 33,
                ),
            ),
        ),
    )

    record = first_fact_record(document)
    ministry_entity = next(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.canonical_hint == "Ministerstwa Aktywów Państwowych"
    )

    assert record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    assert entity_hint_for_role(document, record, "organization") == "Orlenu"
    proposed_tags = frozenset(
        proposal.context_kind
        for proposal in document.entity_context_proposals
        if proposal.entity_id == ministry_entity.id
    )
    assert proposed_tags == frozenset({EntityTag.PUBLIC_INSTITUTION, EntityTag.GENERIC_OWNER})


def test_governance_stage_keeps_generic_owner_on_org_role_for_inference_competition() -> None:
    text = (
        "Jan Kowalski został powołany na prezesa Orlenu decyzją Ministerstwa Aktywów Państwowych."
    )
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Orlenu",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Orlenu"), text.index("Orlenu") + 6),
            ),
            NamedEntitySpan(
                text="Ministerstwa Aktywów Państwowych",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Ministerstwa Aktywów Państwowych"),
                    text.index("Ministerstwa Aktywów Państwowych") + 33,
                ),
            ),
        ),
    )

    ministry_entity = next(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.canonical_hint == "Ministerstwa Aktywów Państwowych"
    )
    appointment_event = next(
        event
        for event in document.store.event_candidates.values()
        if event.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    )

    ministry_roles = {
        binding.role
        for binding in document.store.argument_bindings_for_event(appointment_event.id)
        if _binding_targets_entity(binding, ministry_entity.id)
    }

    assert ministry_roles == {EventRole.ORGANIZATION, EventRole.CONTEXT}


def _binding_targets_entity(
    binding: ArgumentBindingCandidate,
    entity_id: EntityCandidateId,
) -> bool:
    match binding.filler:
        case EntityFiller(entity_id=binding_entity_id):
            return binding_entity_id == entity_id
        case _:
            return False


def test_governance_stage_prefers_one_window_organization_candidate() -> None:
    first = "WFOŚiGW w Lublinie ma kłopoty."
    second = "Poczta Polska ogłasza wyniki."
    third = "Jan Kowalski został powołany na prezesa."
    text = f"{first} {second} {third}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="WFOŚiGW w Lublinie",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("WFOŚiGW w Lublinie"), text.index("WFOŚiGW w Lublinie") + 18),
            ),
            NamedEntitySpan(
                text="Poczta Polska",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Poczta Polska"), text.index("Poczta Polska") + 13),
            ),
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
        ),
    )

    facts = list(fact_records(document))
    assert len(facts) == 1
    record = facts[0]
    assert WindowOrganizationSignal() in record.signals


def test_governance_window_only_org_and_role_near_public_office_actor_scores_low() -> None:
    first = "Dyrektorem Gminnego Ośrodka Kultury był Szymon Kubit."
    second = "Tomasz Kościelniak, wójt, został wybrany w drugiej turze."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Gminnego Ośrodka Kultury",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Gminnego Ośrodka Kultury"),
                    text.index("Gminnego Ośrodka Kultury") + len("Gminnego Ośrodka Kultury"),
                ),
            ),
            NamedEntitySpan(
                text="Szymon Kubit",
                label=NerLabel.PERSON,
                span=Span(text.index("Szymon Kubit"), text.index("Szymon Kubit") + 12),
            ),
            NamedEntitySpan(
                text="Tomasz Kościelniak",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Tomasz Kościelniak"),
                    text.index("Tomasz Kościelniak") + len("Tomasz Kościelniak"),
                ),
            ),
        ),
    )
    ProbabilisticInferenceStage().run(document)

    bad_candidate = next(
        (
            candidate
            for candidate in fact_records(document)
            if _has_entity_hint(document, candidate, "person", "Tomasz Kościelniak")
            and _has_entity_hint(document, candidate, "organization", "Gminnego Ośrodka Kultury")
        ),
        None,
    )
    if bad_candidate is None:
        return
    bad_assessment = next(
        assessment.assessment
        for assessment in document.fact_assessments
        if assessment.materialized_fact_id == bad_candidate.id
    )

    assert bad_assessment.score < 0.5


def test_governance_stage_rejects_org_like_person_noise() -> None:
    text = "Do rady nadzorczej PZU powołano przedstawicieli Allianza OFE."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Allianza OFE",
                label=NerLabel.PERSON,
                span=Span(text.index("Allianza OFE"), text.index("Allianza OFE") + 12),
            ),
            NamedEntitySpan(
                text="PZU",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("PZU"), text.index("PZU") + 3),
            ),
        ),
    )

    governance_people = {
        entity_hint_for_role(document, record, "person")
        for record in fact_records(document)
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    }
    assert "Allianza OFE" not in governance_people
    allianz_entity = next(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.canonical_hint == "Allianza OFE"
    )
    assert allianz_entity.kind is EntityKind.ORGANIZATION


def test_governance_stage_keeps_implausible_person_candidate_as_suppressed_alternative() -> None:
    text = "PAP Kowalski został powołany do rady nadzorczej PZU."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="PAP Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("PAP Kowalski"), text.index("PAP Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="PZU",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("PZU"), text.index("PZU") + 3),
            ),
        ),
    )

    governance_people = {
        entity_hint_for_role(document, record, "person")
        for record in fact_records(document)
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    }
    assert "PAP Kowalski" not in governance_people
    implausible_entity = next(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.canonical_hint == "PAP Kowalski"
    )
    assert any(
        _binding_targets_entity(binding, implausible_entity.id)
        and ImplausiblePersonBindingSignal() in binding.signals
        for bindings in document.store.argument_bindings_by_event_id.values()
        for binding in bindings
    )


def _has_entity_hint(
    document: ArticleDocument,
    record: FactCandidateRecord,
    role: str,
    canonical_hint: str,
) -> bool:
    for argument in record.arguments:
        match argument:
            case EntityFactArgument(role=argument_role, entity_id=entity_id) if (
                argument_role.value == role
            ):
                return document.store.entity_candidates[entity_id].canonical_hint == canonical_hint
            case _:
                continue
    return False


# --- Bug 1: imperfective dismissal lemmas ---


def test_governance_stage_emits_dismissal_for_imperfective_odchodzic() -> None:
    """'odchodzi ze stanowiska' should produce PUBLIC_ROLE_END (Bug 1)."""
    text = "Katarzyna Zapał odchodzi ze stanowiska prezesa spółki Komunalnik."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Katarzyna Zapał",
                label=NerLabel.PERSON,
                span=Span(text.index("Katarzyna Zapał"), text.index("Katarzyna Zapał") + 15),
            ),
            NamedEntitySpan(
                text="Komunalnik",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Komunalnik"), text.index("Komunalnik") + 10),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    assert dismissals, "expected at least one PUBLIC_ROLE_END"
    assert any(entity_hint_for_role(document, r, "person") == "Katarzyna Zapał" for r in dismissals)


def test_governance_stage_emits_dismissal_for_imperfective_rezygnowac() -> None:
    """'rezygnuje ze stanowiska' should produce PUBLIC_ROLE_END (Bug 1)."""
    text = "Anna Nowak rezygnuje ze stanowiska dyrektora spółki Wodkan."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Anna Nowak",
                label=NerLabel.PERSON,
                span=Span(text.index("Anna Nowak"), text.index("Anna Nowak") + 10),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    assert dismissals, "expected at least one PUBLIC_ROLE_END"


def test_governance_stage_prefers_person_attached_roles_in_multi_person_dismissal() -> None:
    text = (
        "Rada nadzorcza odwołała prezes Agnieszkę Kruk i wiceprezes Annę Pokwapisz "
        "z zarządu WFOŚiGW w Lublinie."
    )
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Agnieszkę Kruk",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Agnieszkę Kruk"),
                    text.index("Agnieszkę Kruk") + len("Agnieszkę Kruk"),
                ),
            ),
            NamedEntitySpan(
                text="Annę Pokwapisz",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Annę Pokwapisz"),
                    text.index("Annę Pokwapisz") + len("Annę Pokwapisz"),
                ),
            ),
            NamedEntitySpan(
                text="WFOŚiGW w Lublinie",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("WFOŚiGW w Lublinie"),
                    text.index("WFOŚiGW w Lublinie") + len("WFOŚiGW w Lublinie"),
                ),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    roles_by_person = {
        entity_hint_for_role(document, record, "person"): entity_hint_for_role(
            document, record, "role"
        )
        for record in dismissals
    }

    assert roles_by_person["Agnieszkę Kruk"] == "prezes"
    assert roles_by_person["Annę Pokwapisz"] == "wiceprezes"


def test_governance_stage_ignores_alternative_role_in_resignation_clause() -> None:
    text = (
        "Nie wykluczam rezygnacji z bycia prezesem WFOŚiGW na rzecz mandatu radnego "
        "— podkreśla Stanisław Mazur."
    )
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="WFOŚiGW",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("WFOŚiGW"), text.index("WFOŚiGW") + len("WFOŚiGW")),
            ),
            NamedEntitySpan(
                text="Stanisław Mazur",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Stanisław Mazur"),
                    text.index("Stanisław Mazur") + len("Stanisław Mazur"),
                ),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    assert dismissals
    assert any(
        entity_hint_for_role(document, record, "person") == "Stanisław Mazur"
        and (entity_hint_for_role(document, record, "role") or "").startswith("prezes")
        for record in dismissals
    )
    assert not any(
        (entity_hint_for_role(document, record, "person") or "").startswith("prezes")
        or entity_hint_for_role(document, record, "role") == "radnego"
        for record in dismissals
    )


def test_governance_stage_does_not_materialize_first_person_departure_without_speaker() -> None:
    text = "Nie wykluczam rezygnacji z bycia prezesem WFOŚiGW na rzecz mandatu radnego."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="WFOŚiGW",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("WFOŚiGW"), text.index("WFOŚiGW") + len("WFOŚiGW")),
            ),
        ),
    )

    assert not any(record.kind is FactKind.PUBLIC_ROLE_END for record in fact_records(document))


# --- Bug 2: temporal objąć/objęcie suppression ---


def test_governance_stage_does_not_produce_appointment_from_temporal_objecia() -> None:
    """'od objęcia stanowiska' is a temporal clause, not an appointment event (Bug 2)."""
    text = "Katarzyna Zapał od objęcia stanowiska w spółce Komunalnik pełni obowiązki."
    morphology = Morfeusz2MorphologyAdapter()
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=(text,),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Katarzyna Zapał",
                    label=NerLabel.PERSON,
                    span=Span(
                        text.index("Katarzyna Zapał"),
                        text.index("Katarzyna Zapał") + 15,
                    ),
                ),
                NamedEntitySpan(
                    text="Komunalnik",
                    label=NerLabel.ORGANIZATION,
                    span=Span(
                        text.index("Komunalnik"),
                        text.index("Komunalnik") + 10,
                    ),
                ),
            )
        ),
        morphology=morphology,
    ).run(document)
    LexicalEntityContextStage().run(document)
    RoleCandidateStage(morphology).run(document)

    # Identify 1-based token positions for "od" and the objąć/objęcie token.
    sentence = next(iter(document.store.sentences.values()))
    tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
    od_index = next(i + 1 for i, t in enumerate(tokens) if t.text.lower() == "od")
    objecia_index = next(
        i + 1
        for i, t in enumerate(tokens)
        if {"objąć", "objęcie"} & {analysis.lemma for analysis in t.morph}
    )

    # "od" is a CASE marker governing "objęcia" — supply just this arc.
    DependencyParseStage(
        StaticDependencyProvider(
            (
                ParsedDependencySentence(
                    sentence_index=0,
                    tokens=(
                        ParsedDependencyToken(
                            token_index=od_index,
                            text="od",
                            lemma="od",
                            upos="ADP",
                            head_index=objecia_index,
                            relation=DependencyRelation.CASE,
                        ),
                    ),
                ),
            )
        )
    ).run(document)

    GovernanceCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    appointments = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_APPOINTMENT]
    assert not appointments, "spurious PUBLIC_ROLE_APPOINTMENT from temporal 'od objęcia'"


# --- Bug 3: successor pattern ---


def test_governance_stage_assigns_successor_not_predecessor_in_nastepca_pattern() -> None:
    """'Jej następcą zostanie Agnieszka Paradyż' — appointee is Paradyż, not Zapał (Bug 3)."""
    first = "Katarzyna Zapał odchodzi ze stanowiska prezesa spółki Komunalnik."
    second = "Jej następcą zostanie Agnieszka Paradyż."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Katarzyna Zapał",
                label=NerLabel.PERSON,
                span=Span(text.index("Katarzyna Zapał"), text.index("Katarzyna Zapał") + 15),
            ),
            NamedEntitySpan(
                text="Komunalnik",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Komunalnik"), text.index("Komunalnik") + 10),
            ),
            NamedEntitySpan(
                text="Agnieszka Paradyż",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Agnieszka Paradyż"),
                    text.index("Agnieszka Paradyż") + len("Agnieszka Paradyż"),
                ),
            ),
        ),
    )

    appointments = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_APPOINTMENT]
    assert appointments, "expected at least one PUBLIC_ROLE_APPOINTMENT"
    appointment_people = {entity_hint_for_role(document, r, "person") for r in appointments}
    assert "Agnieszka Paradyż" in appointment_people, "successor should be appointed"
    assert "Katarzyna Zapał" not in appointment_people, (
        "predecessor should not appear in appointment person slot"
    )


# --- Bug 4: dash-apposition current-role pattern ---


def test_governance_stage_produces_appointment_from_dash_apposition_current_role() -> None:
    """'Jan Kowalski — obecny prezes Spółki ABC' implies a governance appointment (Bug 4)."""
    text = "Jan Kowalski — obecny prezes Spółki ABC wygrał konkurs."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Spółki ABC",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Spółki ABC"), text.index("Spółki ABC") + 10),
            ),
        ),
    )

    appointments = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert appointments, "expected PUBLIC_ROLE_HOLDING from dash-apposition pattern"
    assert any(entity_hint_for_role(document, r, "person") == "Jan Kowalski" for r in appointments)


def test_governance_stage_does_not_dismiss_person_in_exception_clause() -> None:
    text = "Odwołano wszystkich dyrektorów z wyjątkiem Jana Kowalskiego."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jana Kowalskiego",
                label=NerLabel.PERSON,
                span=Span(text.index("Jana Kowalskiego"), text.index("Jana Kowalskiego") + 16),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    dismissed_people = {entity_hint_for_role(document, r, "person") for r in dismissals}
    assert "Jana Kowalskiego" not in dismissed_people, (
        "person in exception clause should not be marked as dismissed"
    )


def test_governance_stage_dismisses_person_not_in_exception_clause() -> None:
    text = "Piotr Wiśniewski został odwołany z wyjątkiem Jana Kowalskiego."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Piotr Wiśniewski",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Piotr Wiśniewski"),
                    text.index("Piotr Wiśniewski") + len("Piotr Wiśniewski"),
                ),
            ),
            NamedEntitySpan(
                text="Jana Kowalskiego",
                label=NerLabel.PERSON,
                span=Span(text.index("Jana Kowalskiego"), text.index("Jana Kowalskiego") + 16),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    dismissed_people = {entity_hint_for_role(document, r, "person") for r in dismissals}
    assert "Jana Kowalskiego" not in dismissed_people, (
        "person in exception clause should not be dismissed"
    )
    assert "Piotr Wiśniewski" in dismissed_people, (
        "person before exception clause should still be dismissed"
    )


def test_governance_stage_dismisses_person_after_closed_exception_clause() -> None:
    text = "Z wyjątkiem Jana Kowalskiego, odwołano Piotra Wiśniewskiego."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jana Kowalskiego",
                label=NerLabel.PERSON,
                span=Span(text.index("Jana Kowalskiego"), text.index("Jana Kowalskiego") + 16),
            ),
            NamedEntitySpan(
                text="Piotra Wiśniewskiego",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Piotra Wiśniewskiego"),
                    text.index("Piotra Wiśniewskiego") + len("Piotra Wiśniewskiego"),
                ),
            ),
        ),
    )

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    dismissed_people = {entity_hint_for_role(document, r, "person") for r in dismissals}
    assert "Jana Kowalskiego" not in dismissed_people
    assert "Piotra Wiśniewskiego" in dismissed_people


def test_governance_stage_does_not_bind_role_title_person_ner_span_as_governance_person() -> None:
    text = "Prezes podpisał umowę z firmą Wodkan."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Prezes",
                label=NerLabel.PERSON,
                span=Span(text.index("Prezes"), text.index("Prezes") + 6),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    person_entities = {
        e.canonical_hint
        for e in document.store.entity_candidates.values()
        if e.kind == EntityKind.PERSON
    }
    governance_people = {
        entity_hint_for_role(document, record, "person")
        for record in fact_records(document)
        if record.kind in {FactKind.PUBLIC_ROLE_APPOINTMENT, FactKind.PUBLIC_ROLE_END}
    }

    assert "Prezes" not in person_entities
    assert "Prezes" not in governance_people


def test_governance_stage_still_binds_named_person_with_role_title() -> None:
    text = "Prezes Jan Kowalski został powołany do zarządu spółki Wodkan."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Prezes Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(
                    text.index("Prezes Jan Kowalski"),
                    text.index("Prezes Jan Kowalski") + len("Prezes Jan Kowalski"),
                ),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    governance_people = [
        entity_hint_for_role(document, record, "person")
        for record in fact_records(document)
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    ]
    assert "Jan Kowalski" in governance_people


def test_governance_stage_does_not_materialize_bare_role_descriptor_as_holder() -> None:
    text = "Prezes jest przy tym bardzo pewny siebie."
    document = run_governance_stage(text, ())

    records = [
        record for record in fact_records(document) if record.kind is FactKind.PUBLIC_ROLE_HOLDING
    ]

    assert records == []


def test_governance_stage_list_appointments_via_conj() -> None:
    text = "Do zarządu powołano Jana Kowalskiego, Tomasza Nowaka i Adama Cisza."
    entities = (
        NamedEntitySpan(
            text="Jana Kowalskiego",
            label=NerLabel.PERSON,
            span=Span(20, 36),
        ),
        NamedEntitySpan(
            text="Tomasza Nowaka",
            label=NerLabel.PERSON,
            span=Span(38, 52),
        ),
        NamedEntitySpan(
            text="Adama Cisza",
            label=NerLabel.PERSON,
            span=Span(55, 66),
        ),
    )

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
    RoleCandidateStage(morphology).run(document)

    sentence = next(iter(document.store.sentences.values()))
    tokens = [document.store.tokens[tid] for tid in sentence.token_ids]

    kowalskiego_idx = next(i + 1 for i, t in enumerate(tokens) if t.text.lower() == "kowalskiego")
    nowaka_idx = next(i + 1 for i, t in enumerate(tokens) if t.text.lower() == "nowaka")
    cisza_idx = next(i + 1 for i, t in enumerate(tokens) if t.text.lower() == "cisza")

    DependencyParseStage(
        StaticDependencyProvider(
            (
                ParsedDependencySentence(
                    sentence_index=0,
                    tokens=(
                        ParsedDependencyToken(
                            token_index=nowaka_idx,
                            text="Nowaka",
                            lemma="Nowak",
                            upos="PROPN",
                            head_index=kowalskiego_idx,
                            relation=DependencyRelation.CONJ,
                        ),
                        ParsedDependencyToken(
                            token_index=cisza_idx,
                            text="Cisza",
                            lemma="Cisz",
                            upos="PROPN",
                            head_index=nowaka_idx,
                            relation=DependencyRelation.CONJ,
                        ),
                    ),
                ),
            )
        )
    ).run(document)

    GovernanceCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    appointments = [
        entity_hint_for_role(document, r, "person")
        for r in fact_records(document)
        if r.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    ]
    assert "Jana Kowalskiego" in appointments
    assert "Tomasza Nowaka" in appointments
    assert "Adama Cisza" in appointments


def test_governance_stage_reflexive_dismissal_guard() -> None:
    text = "Marta Kowalska odwołała się od decyzji."
    entities = (
        NamedEntitySpan(
            text="Marta Kowalska",
            label=NerLabel.PERSON,
            span=Span(0, 14),
        ),
    )

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
    RoleCandidateStage(morphology).run(document)

    sentence = next(iter(document.store.sentences.values()))
    tokens = [document.store.tokens[tid] for tid in sentence.token_ids]

    odwolala_idx = next(i + 1 for i, t in enumerate(tokens) if t.text.lower() == "odwołała")
    sie_idx = next(i + 1 for i, t in enumerate(tokens) if t.text.lower() == "się")

    DependencyParseStage(
        StaticDependencyProvider(
            (
                ParsedDependencySentence(
                    sentence_index=0,
                    tokens=(
                        ParsedDependencyToken(
                            token_index=sie_idx,
                            text="się",
                            lemma="się",
                            upos="PRON",
                            head_index=odwolala_idx,
                            relation=DependencyRelation.UNKNOWN,
                        ),
                    ),
                ),
            )
        )
    ).run(document)

    GovernanceCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    dismissals = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_END]
    assert not dismissals, "should suppress dismissal when odwołać is reflexive (odwołać się)"


# --- Succession pattern and copular role-holder pattern ---


def test_governance_stage_succession_pattern_binds_new_person_to_vacated_role() -> None:
    """'Jej miejsce zajęła X' — X should get the role from the previous sentence
    where someone departed, not be silently dropped because that sentence had a
    different person."""
    first = "Po roku pracy ze stanowiskiem Sekretarza Miasta pożegnała się Barbara Chamiga."
    second = "Jej miejsce zajęła Marta Tartanus-Oryszczak."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Barbara Chamiga",
                label=NerLabel.PERSON,
                span=Span(text.index("Barbara Chamiga"), text.index("Barbara Chamiga") + 15),
            ),
            NamedEntitySpan(
                text="Marta Tartanus-Oryszczak",
                label=NerLabel.PERSON,
                span=Span(
                    text.rindex("Marta Tartanus-Oryszczak"),
                    text.rindex("Marta Tartanus-Oryszczak") + len("Marta Tartanus-Oryszczak"),
                ),
            ),
        ),
    )

    appointments = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_APPOINTMENT]
    marta_appointments = [
        r
        for r in appointments
        if _has_entity_hint(document, r, "person", "Marta Tartanus-Oryszczak")
    ]
    assert marta_appointments, (
        "Marta Tartanus-Oryszczak should be bound to a governance appointment"
    )
    record = marta_appointments[0]
    assert entity_hint_for_role(document, record, "role") == "Sekretarza"


def test_governance_stage_succession_does_not_bind_unrelated_window_organization() -> None:
    first = "Marta Tartanus-Oryszczak kierowała Biurem Finansowym."
    second = "Ze stanowiskiem Sekretarza Miasta pożegnała się Barbara Chamiga."
    third = "Jej miejsce zajęła Marta Tartanus-Oryszczak."
    text = f"{first} {second} {third}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Marta Tartanus-Oryszczak",
                label=NerLabel.PERSON,
                span=Span(
                    text.rindex("Marta Tartanus-Oryszczak"),
                    text.rindex("Marta Tartanus-Oryszczak") + len("Marta Tartanus-Oryszczak"),
                ),
            ),
            NamedEntitySpan(
                text="Biurem Finansowym",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("Biurem Finansowym"),
                    text.index("Biurem Finansowym") + len("Biurem Finansowym"),
                ),
            ),
            NamedEntitySpan(
                text="Barbara Chamiga",
                label=NerLabel.PERSON,
                span=Span(text.index("Barbara Chamiga"), text.index("Barbara Chamiga") + 15),
            ),
        ),
    )

    record = next(
        record
        for record in fact_records(document)
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
        and _has_entity_hint(document, record, "person", "Marta Tartanus-Oryszczak")
    )
    assert entity_hint_for_role(document, record, "role") == "Sekretarza"
    assert "organization" not in argument_roles(record)


def test_governance_stage_copular_role_holder_produces_holding() -> None:
    """'X jest przewodniczącą rady nadzorczej Y' — copular construction with a
    governance role entity should produce a PUBLIC_ROLE_HOLDING."""
    text = "Anna Nowak jest przewodniczącą rady nadzorczej spółki Komunalnik."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Anna Nowak",
                label=NerLabel.PERSON,
                span=Span(text.index("Anna Nowak"), text.index("Anna Nowak") + 10),
            ),
            NamedEntitySpan(
                text="Komunalnik",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Komunalnik"), text.index("Komunalnik") + 10),
            ),
        ),
    )

    holdings = [r for r in fact_records(document) if r.kind is FactKind.PUBLIC_ROLE_HOLDING]
    assert holdings, "copular governance role should produce a PUBLIC_ROLE_HOLDING"
    record = holdings[0]
    assert entity_hint_for_role(document, record, "person") == "Anna Nowak"
    assert entity_hint_for_role(document, record, "organization") == "Komunalnik"
