from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.models import (
    ArticleDocument,
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
