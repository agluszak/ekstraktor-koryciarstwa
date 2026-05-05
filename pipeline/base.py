from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.domain_types import KBID
from pipeline.models import (
    ArticleDocument,
    EntityCluster,
    KBAliasRecord,
    KBEntityRecord,
    PipelineInput,
)


class PipelineStage(ABC):
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError


class Preprocessor(PipelineStage):
    @abstractmethod
    def run(self, data: PipelineInput) -> ArticleDocument:
        raise NotImplementedError


class DocumentStage(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class RelevanceFilter(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class Segmenter(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class NERExtractor(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class CoreferenceResolver(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class FactExtractor(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class EntityLinker(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class Scorer(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class EntityClusterer(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class ClauseParser(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class IdentityResolver(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class EntityEnricher(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class FrameExtractor(DocumentStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Knowledge-base interfaces
# ---------------------------------------------------------------------------


class EntityKnowledgeBase(ABC):
    """Persistent or in-memory store for canonical real-world entities."""

    @abstractmethod
    def get_candidates(self, cluster: EntityCluster) -> list[KBEntityRecord]:
        """Return KB records that could match *cluster* based on names/aliases."""
        raise NotImplementedError

    @abstractmethod
    def upsert_entity(self, record: KBEntityRecord) -> KBID:
        """Insert or update a KB entity record; return its kb_id."""
        raise NotImplementedError

    @abstractmethod
    def add_alias(self, record: KBAliasRecord) -> None:
        """Register an alias for a KB entity."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, kb_id: KBID) -> KBEntityRecord | None:
        """Retrieve a single KB record by its stable kb_id."""
        raise NotImplementedError


class CandidateGenerator(ABC):
    """Strategy for generating KB candidate records from a document cluster."""

    @abstractmethod
    def candidates_for_cluster(self, cluster: EntityCluster) -> list[KBEntityRecord]:
        raise NotImplementedError


class EntityDisambiguator(ABC):
    """Scores a KB candidate record against a document cluster."""

    @abstractmethod
    def score(
        self,
        cluster: EntityCluster,
        candidate: KBEntityRecord,
        document: ArticleDocument,
    ) -> float:
        raise NotImplementedError
