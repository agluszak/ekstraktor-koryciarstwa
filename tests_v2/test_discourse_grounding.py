from __future__ import annotations

from pipeline_v2.candidates import EntityFactArgument, FactCandidateRecord
from pipeline_v2.nlp import NerLabel, Span
from pipeline_v2.types import FactArgumentRole, FactKind
from tests_v2.materialized import fact_records
from tests_v2.test_governance import (
    NamedEntitySpan,
    entity_argument_id,
    run_governance_stage,
)


def test_governance_stage_does_not_use_distant_cross_paragraph_fallback_organization() -> None:
    para0 = "Zarząd PZU podjął ważne decyzje."
    para1 = (
        "Spółka odnotowała wzrost przychodów. "
        "Udziałowcy pozytywnie ocenili wyniki. "
        "Rada nadzorcza zatwierdziła sprawozdanie. "
        "Z funkcji odwołany został Marcin Kubica."
    )
    text = f"{para0} {para1}"

    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="PZU",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("PZU"), text.index("PZU") + 3),
            ),
            NamedEntitySpan(
                text="Marcin Kubica",
                label=NerLabel.PERSON,
                span=Span(text.index("Marcin Kubica"), text.index("Marcin Kubica") + 13),
            ),
        ),
        paragraphs=(para0, para1),
    )

    records = list(fact_records(document))
    dismissals = [r for r in records if r.kind == FactKind.GOVERNANCE_DISMISSAL]

    assert len(dismissals) >= 1
    record = dismissals[0]

    person = document.store.entity_candidates[entity_argument_id(record, "person")]

    assert person.canonical_hint == "Marcin Kubica"
    assert not _has_entity_argument(record, FactArgumentRole.ORGANIZATION)


def test_governance_stage_does_not_use_paragraph_lead_for_cross_paragraph_fallback() -> None:
    para0 = (
        "W Komunalniku trwa konflikt. "
        "Rada nadzorcza wodociągów miejskich przedstawiła harmonogram zmian."
    )
    para1 = "W kolejnych tygodniach trwały rozmowy o restrukturyzacji."
    para2 = "Ze stanowiska odwołano Annę Leśną."
    text = f"{para0} {para1} {para2}"

    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Komunalnik",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Komunalnik"), text.index("Komunalnik") + 10),
            ),
            NamedEntitySpan(
                text="wodociągów miejskich",
                label=NerLabel.ORGANIZATION,
                span=Span(
                    text.index("wodociągów miejskich"),
                    text.index("wodociągów miejskich") + len("wodociągów miejskich"),
                ),
            ),
            NamedEntitySpan(
                text="Annę Leśną",
                label=NerLabel.PERSON,
                span=Span(text.index("Annę Leśną"), text.index("Annę Leśną") + 10),
            ),
        ),
        paragraphs=(para0, para1, para2),
    )

    records = list(fact_records(document))
    dismissals = [r for r in records if r.kind == FactKind.GOVERNANCE_DISMISSAL]

    assert len(dismissals) >= 1
    record = dismissals[0]

    person = document.store.entity_candidates[entity_argument_id(record, "person")]

    assert "Leśn" in (person.canonical_hint or "")
    assert not _has_entity_argument(record, FactArgumentRole.ORGANIZATION)


def _has_entity_argument(record: FactCandidateRecord, role: FactArgumentRole) -> bool:
    for argument in record.arguments:
        match argument:
            case EntityFactArgument(role=argument_role) if argument_role is role:
                return True
    return False
