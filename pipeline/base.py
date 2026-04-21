from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.models import (
    ArticleDocument,
    CoreferenceResult,
    PipelineInput,
    RelevanceDecision,
)


class PipelineStage(ABC):
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError


class Preprocessor(PipelineStage):
    @abstractmethod
    def run(self, data: PipelineInput) -> ArticleDocument:
        raise NotImplementedError


class RelevanceFilter(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> RelevanceDecision:
        raise NotImplementedError


class Segmenter(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class NERExtractor(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class CoreferenceResolver(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> CoreferenceResult:
        raise NotImplementedError


class FactExtractor(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        raise NotImplementedError


class EntityLinker(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class Scorer(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class EntityClusterer(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class ClauseParser(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class IdentityResolver(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError


class FrameExtractor(PipelineStage):
    @abstractmethod
    def run(self, document: ArticleDocument) -> ArticleDocument:
        raise NotImplementedError
