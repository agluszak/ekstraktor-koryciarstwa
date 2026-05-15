from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.embeddings import EmbeddingProvider


class EvidenceEmbeddingStage:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def name(self) -> str:
        return "evidence_embedding_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        evidence_items = tuple(
            sorted(document.store.evidence.values(), key=lambda evidence: str(evidence.id))
        )
        vectors = self.provider.embed(tuple(evidence.text for evidence in evidence_items))
        for evidence, vector in zip(evidence_items, vectors):
            document.evidence_index.add(evidence.id, vector)
        return document
