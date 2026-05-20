from __future__ import annotations

from pipeline_v2.nlp import NerLabel, Span
from pipeline_v2.types import FactKind
from tests_v2.test_governance import (
    NamedEntitySpan,
    entity_argument_id,
    run_governance_stage,
)


def test_governance_stage_uses_discourse_fallback_organization() -> None:
    # Organization in paragraph 0, person and dismissal in paragraph 1
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

    records = [c.to_fact_record() for c in document.store.fact_candidates.values()]
    dismissals = [r for r in records if r.kind == FactKind.GOVERNANCE_DISMISSAL]

    assert len(dismissals) >= 1
    record = dismissals[0]

    person = document.store.entity_candidates[entity_argument_id(record, "person")]
    org = document.store.entity_candidates[entity_argument_id(record, "organization")]

    assert person.canonical_hint == "Marcin Kubica"
    assert org.canonical_hint == "PZU"


def test_governance_stage_uses_paragraph_lead_for_cross_paragraph_fallback() -> None:
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

    records = [c.to_fact_record() for c in document.store.fact_candidates.values()]
    dismissals = [r for r in records if r.kind == FactKind.GOVERNANCE_DISMISSAL]

    assert len(dismissals) >= 1
    record = dismissals[0]

    person = document.store.entity_candidates[entity_argument_id(record, "person")]
    org = document.store.entity_candidates[entity_argument_id(record, "organization")]

    assert "Leśn" in (person.canonical_hint or "")
    assert org.canonical_hint == "Komunalnik"
