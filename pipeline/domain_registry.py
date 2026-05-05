from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pipeline.config import PipelineConfig
from pipeline.extraction_context import ExtractionContext, FactExtractionContext, SentenceContext
from pipeline.models import ArticleDocument, Fact
from pipeline.runtime import PipelineRuntime


class FrameDomain(Protocol):
    def name(self) -> str: ...

    def run(self, document: ArticleDocument, context: ExtractionContext) -> ArticleDocument: ...


class SentenceFactDomain(Protocol):
    def extract(self, context: SentenceContext) -> list[Fact]: ...


class DocumentFactDomain(Protocol):
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]: ...


class GraphFactDomain(Protocol):
    def build(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
        fact_context: FactExtractionContext,
    ) -> list[Fact]: ...


@dataclass(frozen=True, slots=True)
class DomainRegistry:
    frame_extractors: tuple[FrameDomain, ...]
    sentence_fact_extractors: tuple[SentenceFactDomain, ...]
    document_fact_builders: tuple[DocumentFactDomain, ...]
    graph_fact_builders: tuple[GraphFactDomain, ...]


def build_default_domain_registry(
    config: PipelineConfig,
    runtime: PipelineRuntime | None = None,
) -> DomainRegistry:
    from pipeline.domains.anti_corruption import (
        AntiCorruptionInvestigationFactBuilder,
        AntiCorruptionReferralFactBuilder,
        PolishAntiCorruptionAbuseFrameExtractor,
        PolishAntiCorruptionReferralFrameExtractor,
        PublicProcurementAbuseFactBuilder,
    )
    from pipeline.domains.compensation import (
        CompensationFactBuilder,
        PolishCompensationFrameExtractor,
    )
    from pipeline.domains.funding import FundingFactBuilder, PolishFundingFrameExtractor
    from pipeline.domains.governance import GovernanceFactBuilder
    from pipeline.domains.governance_frames import PolishGovernanceFrameExtractor
    from pipeline.domains.kinship import KinshipTieBuilder
    from pipeline.domains.political_profile import (
        CrossSentencePartyFactBuilder,
        PoliticalProfileFactExtractor,
    )
    from pipeline.domains.public_employment import (
        PolishPublicEmploymentFrameExtractor,
        PublicEmploymentFactBuilder,
    )
    from pipeline.domains.public_money import (
        PolishPublicContractFrameExtractor,
        PublicContractFactBuilder,
    )
    from pipeline.domains.secondary_facts import TieFactExtractor

    return DomainRegistry(
        frame_extractors=(
            PolishGovernanceFrameExtractor(config),
            PolishCompensationFrameExtractor(config),
            PolishFundingFrameExtractor(config, runtime=runtime),
            PolishPublicContractFrameExtractor(config, runtime=runtime),
            PolishPublicEmploymentFrameExtractor(config, runtime=runtime),
            PolishAntiCorruptionReferralFrameExtractor(config),
            PolishAntiCorruptionAbuseFrameExtractor(config),
        ),
        sentence_fact_extractors=(
            PoliticalProfileFactExtractor(),
            TieFactExtractor(),
        ),
        document_fact_builders=(
            GovernanceFactBuilder(),
            CompensationFactBuilder(),
            FundingFactBuilder(),
            PublicContractFactBuilder(),
            PublicEmploymentFactBuilder(),
            AntiCorruptionReferralFactBuilder(),
            AntiCorruptionInvestigationFactBuilder(),
            PublicProcurementAbuseFactBuilder(),
        ),
        graph_fact_builders=(
            CrossSentencePartyFactBuilder(),
            KinshipTieBuilder(),
        ),
    )
