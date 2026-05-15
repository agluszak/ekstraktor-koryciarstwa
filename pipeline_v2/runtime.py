from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.coreference import (
    CoreferenceProvider,
    CoreferenceReferenceStage,
    LightReferenceStage,
)
from pipeline_v2.document import StageDiagnosticStatus
from pipeline_v2.embeddings import SentenceTransformerEmbeddingProvider
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage, SpacyNamedEntityProvider
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.preprocessing import HtmlArticlePreprocessor
from pipeline_v2.proxy import FamilyProxyCandidateStage
from pipeline_v2.public_employment import PublicEmploymentCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.relevance import ProfileRelevanceFilter
from pipeline_v2.resolution_scoring import ResolutionScoringStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.semantic import EvidenceEmbeddingStage
from pipeline_v2.stages import DiagnosticStage, DocumentStage, V2Pipeline
from pipeline_v2.syntax import DependencyParseStage, StanzaDependencyProvider
from pipeline_v2.ties import PersonalTieCandidateStage


class CoreferenceMode(StrEnum):
    OFF = "off"
    LIGHT = "light"
    STANZA = "stanza"


@dataclass(frozen=True, slots=True)
class V2PipelineConfig:
    spacy_model: str = "pl_core_news_lg"
    sentence_transformer_model: str | None = None
    coreference_mode: CoreferenceMode = CoreferenceMode.OFF
    coreference_provider: CoreferenceProvider | None = None
    enable_syntax: bool = False


def build_v2_pipeline(config: V2PipelineConfig = V2PipelineConfig()) -> V2Pipeline:
    morphology = Morfeusz2MorphologyAdapter()
    stages: list[DocumentStage] = [
        ProfileRelevanceFilter(),
        ParagraphSentenceSegmenter(),
        MorfeuszMorphologyStage(morphology),
    ]
    if config.enable_syntax:
        stages.append(DependencyParseStage(StanzaDependencyProvider()))
    stages.append(
        NamedEntityCandidateStage(
            provider=SpacyNamedEntityProvider(config.spacy_model),
            morphology=morphology,
        )
    )
    stages.append(PartyCandidateStage(morphology))
    stages.append(RoleCandidateStage(morphology))
    stages.append(GovernanceCandidateStage())
    stages.append(PublicEmploymentCandidateStage())
    stages.append(PublicMoneyCandidateStage())
    stages.append(AntiCorruptionCandidateStage())
    if config.coreference_mode == CoreferenceMode.OFF:
        stages.append(
            DiagnosticStage(
                stage_name="coreference_stage_v2",
                status=StageDiagnosticStatus.SKIPPED,
                reason="disabled by config",
            )
        )
    elif config.coreference_mode == CoreferenceMode.LIGHT:
        stages.append(LightReferenceStage())
    elif config.coreference_provider is not None:
        stages.append(
            CoreferenceReferenceStage(
                provider=config.coreference_provider,
                morphology=morphology,
            )
        )
    else:
        stages.append(
            DiagnosticStage(
                stage_name="coreference_stage_v2",
                status=StageDiagnosticStatus.UNAVAILABLE,
                reason="provider not configured",
            )
        )
    stages.append(FamilyProxyCandidateStage())
    stages.append(PersonalTieCandidateStage())
    if config.sentence_transformer_model is not None:
        stages.append(
            EvidenceEmbeddingStage(
                SentenceTransformerEmbeddingProvider(config.sentence_transformer_model)
            )
        )
    stages.append(ResolutionScoringStage())
    stages.append(FactScoringStage())
    return V2Pipeline(
        preprocessor=HtmlArticlePreprocessor(),
        stages=tuple(stages),
    )
