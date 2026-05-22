from __future__ import annotations

from pipeline_v2.candidates import EntityFactArgument, FactCandidateRecord
from pipeline_v2.document import ArticleDocument
from pipeline_v2.entity_classification import EntityClassificationStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import (
    AppointmentLemmaSignal,
    EntityTag,
    FactKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    NerLabel,
    PartyOrganizationSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)
from tests_v2.materialized import (
    argument_roles,
    entity_hint_for_role,
    fact_records,
    first_fact_record,
)


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
    EntityClassificationStage().run(document)
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

    assert record.kind is FactKind.GOVERNANCE_APPOINTMENT
    assert entity_hint_for_role(document, record, "person") == "Jan Kowalski"
    assert entity_hint_for_role(document, record, "organization") == "Wodkan"
    assert entity_hint_for_role(document, record, "role") == "zarządu"
    assert set(record.signals) == {
        AppointmentLemmaSignal(lemma="powołać"),
        LocalPersonSignal(),
        LocalOrganizationSignal(),
        LocalRoleSignal(),
    }


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
    # Both GOVERNANCE_APPOINTMENT (from 'zostać') and GOVERNANCE_DISMISSAL
    # (from 'odwołać') are emitted; find the dismissal specifically.
    dismissal_record = next(
        record for record in fact_records(document) if record.kind is FactKind.GOVERNANCE_DISMISSAL
    )

    assert dismissal_record.kind is FactKind.GOVERNANCE_DISMISSAL
    dismissal_assessment = next(
        a.assessment
        for a in document.fact_assessments
        if a.materialized_fact_id == dismissal_record.id
    )
    assert dismissal_assessment.score >= 0.6


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

    record = first_fact_record(document)

    assert record.kind is FactKind.GOVERNANCE_APPOINTMENT
    assert entity_hint_for_role(document, record, "person") == "Jan Kowalski"
    assert entity_hint_for_role(document, record, "organization") == "Wodkan"
    assert entity_hint_for_role(document, record, "role") == "prezesem"
    assert set(record.signals) == {
        AppointmentLemmaSignal(lemma="powołać"),
        WindowPersonSignal(),
        WindowOrganizationSignal(),
        WindowRoleSignal(),
    }


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

    assert fact_records(document) == ()


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
        record for record in fact_records(document) if record.kind is FactKind.GOVERNANCE_DISMISSAL
    )
    record = dismissal_candidate

    assert record.kind is FactKind.GOVERNANCE_DISMISSAL
    assert argument_roles(record) == frozenset({"person", "role"})
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
        is FactKind.GOVERNANCE_APPOINTMENT
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

    assert record.kind is FactKind.GOVERNANCE_APPOINTMENT
    assert entity_hint_for_role(document, record, "organization") == "Orlenu"
    assert document.store.entity_tags[ministry_entity.id] == frozenset(
        {EntityTag.PUBLIC_INSTITUTION, EntityTag.GENERIC_OWNER}
    )


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
        if record.kind is FactKind.GOVERNANCE_APPOINTMENT
    }
    assert "Allianza OFE" not in governance_people


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
