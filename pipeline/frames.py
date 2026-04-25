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


class PolishFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.governance = PolishGovernanceFrameExtractor(config)
        self.compensation = PolishCompensationFrameExtractor(config)
        self.funding = PolishFundingFrameExtractor(config)
        self.public_contracts = PolishPublicContractFrameExtractor(config)
        self.public_employment = PolishPublicEmploymentFrameExtractor(config)
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
