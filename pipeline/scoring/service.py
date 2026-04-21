from __future__ import annotations

from pipeline.base import Scorer
from pipeline.config import PipelineConfig
from pipeline.domain_types import FactType
from pipeline.models import ArticleDocument, ScoreResult


class RuleBasedNepotismScorer(Scorer):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "rule_based_nepotism_scorer"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        score = 0.0
        reasons: list[str] = []
        fact_types = {fact.fact_type for fact in document.facts}
        lowered = document.cleaned_text.lower()

        if (
            FactType.PARTY_MEMBERSHIP in fact_types
            or FactType.FORMER_PARTY_MEMBERSHIP in fact_types
        ):
            score += self.config.score_weights.political_tie
            reasons.append("detected party affiliation")
        if FactType.PERSONAL_OR_POLITICAL_TIE in fact_types:
            score += self.config.score_weights.family_tie
            reasons.append("detected family or acquaintance tie")

        has_board = any(
            f.fact_type in {FactType.APPOINTMENT, FactType.DISMISSAL} and f.board_role
            for f in document.facts
        )
        if has_board:
            score += self.config.score_weights.board_position
            reasons.append("detected board appointment")

        if FactType.COMPENSATION in fact_types:
            score += 0.15
            reasons.append("detected public-money compensation signal")
        if FactType.FUNDING in fact_types:
            score += 0.2
            reasons.append("detected public funding relation")
        if FactType.PUBLIC_CONTRACT in fact_types:
            score += 0.2
            reasons.append("detected public contract relation")
        if FactType.ANTI_CORRUPTION_REFERRAL in fact_types:
            score += 0.2
            reasons.append("detected anti-corruption referral")

        if any(marker in lowered for marker in self.config.patterns.state_company_markers):
            score += self.config.score_weights.state_company
            reasons.append("organization looks state-owned or municipal")
        if any(marker in lowered for marker in self.config.patterns.qualification_markers):
            score += self.config.score_weights.qualification_gap
            reasons.append("qualification-gap language detected")
        if FactType.DISMISSAL in fact_types:
            score += self.config.score_weights.dismissal_signal
            reasons.append("dismissal is a governance event signal")

        document.score = ScoreResult(value=round(max(0.0, min(score, 1.0)), 3), reasons=reasons)
        return document
