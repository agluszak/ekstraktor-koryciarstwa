from __future__ import annotations

import pytest

from pipeline_v2.embeddings import EvidenceVectorIndex
from pipeline_v2.ids import EvidenceId


def test_evidence_vector_index_returns_ranked_semantic_matches() -> None:
    index = EvidenceVectorIndex()
    index.add(EvidenceId("public-contract"), (1.0, 0.0))
    index.add(EvidenceId("party-membership"), (0.0, 1.0))
    index.add(EvidenceId("near-contract"), (0.8, 0.2))

    matches = index.search((1.0, 0.0), limit=2, min_score=0.7)

    assert tuple(match.evidence_id for match in matches) == (
        EvidenceId("public-contract"),
        EvidenceId("near-contract"),
    )
    assert matches[0].score == 1.0


def test_evidence_vector_index_rejects_mismatched_dimensions() -> None:
    index = EvidenceVectorIndex()
    index.add(EvidenceId("evidence"), (1.0, 0.0))

    with pytest.raises(ValueError, match="embedding dimensions must match"):
        index.search((1.0,), limit=1)
