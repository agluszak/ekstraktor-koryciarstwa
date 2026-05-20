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
from pipeline_v2.fact_resolution import FactResolutionStage
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage, SpacyNamedEntityProvider
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter
from pipeline_v2.nominal_coreference import NominalKinshipCandidateStage
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


class V2StagePhase(StrEnum):
    RELEVANCE = "relevance"
    LINGUISTIC_ANALYSIS = "linguistic_analysis"
    ENTITY_CANDIDATES = "entity_candidates"
    DOMAIN_CANDIDATES = "domain_candidates"
    REFERENCES = "references"
    TIE_CANDIDATES = "tie_candidates"
    SEMANTIC_ENRICHMENT = "semantic_enrichment"
    SCORING = "scoring"


@dataclass(frozen=True, slots=True)
class OrderedStage:
    phase: V2StagePhase
    stage: DocumentStage


@dataclass(frozen=True, slots=True)
class V2PipelineConfig:
    spacy_model: str = "pl_core_news_lg"
    sentence_transformer_model: str | None = None
    coreference_mode: CoreferenceMode = CoreferenceMode.OFF
    coreference_provider: CoreferenceProvider | None = None
    enable_syntax: bool = False


def _coreference_stage(
    config: V2PipelineConfig,
    morphology: Morfeusz2MorphologyAdapter,
) -> DocumentStage:
    if config.coreference_mode == CoreferenceMode.OFF:
        return DiagnosticStage(
            stage_name="coreference_stage_v2",
            status=StageDiagnosticStatus.SKIPPED,
            reason="disabled by config",
        )
    if config.coreference_mode == CoreferenceMode.LIGHT:
        return LightReferenceStage()
    if config.coreference_provider is not None:
        return CoreferenceReferenceStage(
            provider=config.coreference_provider,
            morphology=morphology,
        )
    return DiagnosticStage(
        stage_name="coreference_stage_v2",
        status=StageDiagnosticStatus.UNAVAILABLE,
        reason="provider not configured",
    )


def _ordered_stages(
    config: V2PipelineConfig,
    morphology: Morfeusz2MorphologyAdapter,
) -> tuple[OrderedStage, ...]:
    plan: list[OrderedStage] = [
        OrderedStage(V2StagePhase.RELEVANCE, ProfileRelevanceFilter()),
        OrderedStage(V2StagePhase.LINGUISTIC_ANALYSIS, ParagraphSentenceSegmenter()),
        OrderedStage(V2StagePhase.LINGUISTIC_ANALYSIS, MorfeuszMorphologyStage(morphology)),
    ]
    if config.enable_syntax:
        plan.append(
            OrderedStage(
                V2StagePhase.LINGUISTIC_ANALYSIS,
                DependencyParseStage(StanzaDependencyProvider()),
            )
        )
    plan.extend(
        (
            OrderedStage(
                V2StagePhase.ENTITY_CANDIDATES,
                NamedEntityCandidateStage(
                    provider=SpacyNamedEntityProvider(config.spacy_model),
                    morphology=morphology,
                ),
            ),
        )
    )
    plan.extend(
        (
            OrderedStage(V2StagePhase.DOMAIN_CANDIDATES, PartyCandidateStage(morphology)),
            OrderedStage(V2StagePhase.DOMAIN_CANDIDATES, RoleCandidateStage(morphology)),
            OrderedStage(V2StagePhase.REFERENCES, _coreference_stage(config, morphology)),
            OrderedStage(V2StagePhase.REFERENCES, NominalKinshipCandidateStage()),
            OrderedStage(V2StagePhase.REFERENCES, FamilyProxyCandidateStage()),
            OrderedStage(V2StagePhase.DOMAIN_CANDIDATES, GovernanceCandidateStage()),
            OrderedStage(V2StagePhase.DOMAIN_CANDIDATES, PublicEmploymentCandidateStage()),
            OrderedStage(V2StagePhase.DOMAIN_CANDIDATES, PublicMoneyCandidateStage()),
            OrderedStage(V2StagePhase.DOMAIN_CANDIDATES, AntiCorruptionCandidateStage()),
            OrderedStage(V2StagePhase.TIE_CANDIDATES, PersonalTieCandidateStage()),
        )
    )
    if config.sentence_transformer_model is not None:
        plan.append(
            OrderedStage(
                V2StagePhase.SEMANTIC_ENRICHMENT,
                EvidenceEmbeddingStage(
                    SentenceTransformerEmbeddingProvider(config.sentence_transformer_model)
                ),
            )
        )
    plan.extend(
        (
            OrderedStage(V2StagePhase.SCORING, ResolutionScoringStage()),
            OrderedStage(V2StagePhase.SCORING, FactResolutionStage()),
            OrderedStage(V2StagePhase.SCORING, FactScoringStage()),
        )
    )
    return tuple(plan)


def build_v2_pipeline(config: V2PipelineConfig = V2PipelineConfig()) -> V2Pipeline:
    morphology = Morfeusz2MorphologyAdapter()
    stages = tuple(ordered.stage for ordered in _ordered_stages(config, morphology))
    return V2Pipeline(
        preprocessor=HtmlArticlePreprocessor(),
        stages=stages,
    )
