from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.embeddings import EmbeddingVector
from pipeline_v2.ids import DocumentId, EvidenceId
from pipeline_v2.nlp import EvidenceSpan, Span
from pipeline_v2.semantic import EvidenceEmbeddingStage


@dataclass(frozen=True, slots=True)
class StaticEmbeddingProvider:
    vectors_by_text: dict[str, EmbeddingVector]

    def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return tuple(self.vectors_by_text[text] for text in texts)


def test_evidence_embedding_stage_indexes_evidence_for_semantic_search() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("contract"),
            text="umowa publiczna",
            span=Span(0, 14),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("party"),
            text="członek partii",
            span=Span(15, 28),
        )
    )

    EvidenceEmbeddingStage(
        StaticEmbeddingProvider(
            {
                "umowa publiczna": (1.0, 0.0),
                "członek partii": (0.0, 1.0),
            }
        )
    ).run(document)
    matches = document.evidence_index.search((1.0, 0.0), limit=1)

    assert tuple(match.evidence_id for match in matches) == (EvidenceId("contract"),)
