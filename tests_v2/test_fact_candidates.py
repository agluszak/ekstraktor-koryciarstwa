from __future__ import annotations

from pipeline_v2.candidates import EntityFactArgument, FactCandidateRecord, TextFactArgument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, FactCandidateId, ProducerId
from pipeline_v2.types import FactArgumentRole, FactKind


def test_fact_candidate_record_serializes_entity_and_text_arguments() -> None:
    record = FactCandidateRecord(
        id=FactCandidateId("funding"),
        kind=FactKind.FUNDING,
        arguments=(
            EntityFactArgument(FactArgumentRole.FUNDER, EntityCandidateId("funder")),
            EntityFactArgument(FactArgumentRole.RECIPIENT, EntityCandidateId("recipient")),
            TextFactArgument(FactArgumentRole.AMOUNT, "100 tys. zl"),
        ),
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
    )

    assert record.to_json() == {
        "id": "funding",
        "kind": "funding",
        "arguments": [
            {"role": "funder", "entity_id": "funder"},
            {"role": "recipient", "entity_id": "recipient"},
            {"role": "amount", "value": "100 tys. zl"},
        ],
        "evidence_ids": ["evidence"],
        "source": "test",
        "signals": [],
    }


def test_entity_fact_argument_to_json_preserves_role_and_id() -> None:
    argument = EntityFactArgument(FactArgumentRole.PERSON, EntityCandidateId("person"))

    assert argument.to_json() == {"role": "person", "entity_id": "person"}


def test_text_fact_argument_to_json_preserves_role_and_value() -> None:
    argument = TextFactArgument(FactArgumentRole.CONTEXT, "umowa-zlecenie")

    assert argument.to_json() == {"role": "context", "value": "umowa-zlecenie"}
