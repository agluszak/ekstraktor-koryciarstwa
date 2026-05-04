from __future__ import annotations

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domains.anti_corruption import (
    PolishAntiCorruptionAbuseFrameExtractor,
    PolishAntiCorruptionReferralFrameExtractor,
)
from pipeline.domains.compensation import PolishCompensationFrameExtractor
from pipeline.domains.funding import PolishFundingFrameExtractor
from pipeline.domains.governance_frames import PolishGovernanceFrameExtractor
from pipeline.domains.public_employment import PolishPublicEmploymentFrameExtractor
from pipeline.domains.public_money import PolishPublicContractFrameExtractor
from pipeline.models import ArticleDocument
from pipeline.runtime import PipelineRuntime


class PolishFrameExtractor(FrameExtractor):
    def __init__(
        self,
        config: PipelineConfig,
        runtime: PipelineRuntime | None = None,
    ) -> None:
        self.governance = PolishGovernanceFrameExtractor(config)
        self.compensation = PolishCompensationFrameExtractor(config)
        self.funding = PolishFundingFrameExtractor(config, runtime=runtime)
        self.public_contracts = PolishPublicContractFrameExtractor(config, runtime=runtime)
        self.public_employment = PolishPublicEmploymentFrameExtractor(config, runtime=runtime)
        self.anti_corruption_referrals = PolishAntiCorruptionReferralFrameExtractor(config)
        self.anti_corruption_abuse = PolishAntiCorruptionAbuseFrameExtractor(config)

    def name(self) -> str:
        return "polish_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document = self.governance.run(document)
        document = self.compensation.run(document)
        document = self.funding.run(document)
        document = self.public_contracts.run(document)
        document = self.public_employment.run(document)
        document = self.anti_corruption_referrals.run(document)
        return self.anti_corruption_abuse.run(document)
