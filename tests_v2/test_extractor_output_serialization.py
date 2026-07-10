import json

from wrapped_pipeline_v2 import ExtractorOutput, PoliticalFact


def test_extractor_output_json_serializable():
    """Test that ExtractorOutput can be serialized using standard json.dumps"""

    # Create some mock facts
    fact1 = PoliticalFact(
        kind="public_employment",
        confidence=0.85,
        person="Jan Kowalski",
        organization="Urząd Miasta",
        role="Dyrektor",
    )

    fact2 = PoliticalFact(
        kind="public_contract", confidence=0.92, organization="Firma ABC", amount="100000 PLN"
    )

    # Create an ExtractorOutput instance
    output = ExtractorOutput(
        url="https://example.com",
        relevant=True,
        relevance_score=0.99,
        facts=[fact1, fact2],
        title="Test Article",
    )

    # This should not raise a TypeError
    serialized = json.dumps(output)

    # Verify the serialized string can be loaded back into a dict and has correct fields
    loaded = json.loads(serialized)

    assert loaded["url"] == "https://example.com"
    assert loaded["relevant"] is True
    assert loaded["relevance_score"] == 0.99
    assert loaded["title"] == "Test Article"

    assert len(loaded["facts"]) == 2
    assert loaded["facts"][0]["kind"] == "public_employment"
    assert loaded["facts"][0]["person"] == "Jan Kowalski"

    assert loaded["facts"][1]["kind"] == "public_contract"
    assert loaded["facts"][1]["amount"] == "100000 PLN"

    # Also verify dot access still works (dataclass behavior)
    assert output.url == "https://example.com"
    assert output.facts[0].person == "Jan Kowalski"
