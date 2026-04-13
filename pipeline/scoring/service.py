from __future__ import annotations

from pipeline.base import Scorer
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, ScoreResult


class RuleBasedNepotismScorer(Scorer):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "rule_based_nepotism_scorer"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        score = 0.0
        reasons: list[str] = []
        relation_types = [relation.relation_type for relation in document.relations]
        event_types = [event.event_type for event in document.events]
        lowered = document.cleaned_text.lower()

        if "AFFILIATED_WITH_PARTY" in relation_types:
            score += self.config.score_weights.political_tie
            reasons.append("detected party affiliation")
        if "RELATED_TO" in relation_types:
            score += self.config.score_weights.family_tie
            reasons.append("detected family or acquaintance tie")
        if "MEMBER_OF_BOARD" in relation_types:
            score += self.config.score_weights.board_position
            reasons.append("detected board appointment")
        if "RECEIVES_COMPENSATION" in relation_types:
            score += 0.15
            reasons.append("detected public-money compensation signal")
        if "FUNDED_BY" in relation_types:
            score += 0.2
            reasons.append("detected public funding relation")
        if any(marker in lowered for marker in self.config.patterns.state_company_markers):
            score += self.config.score_weights.state_company
            reasons.append("organization looks state-owned or municipal")
        if any(marker in lowered for marker in self.config.patterns.qualification_markers):
            score += self.config.score_weights.qualification_gap
            reasons.append("qualification-gap language detected")
        if "dismissal" in event_types:
            score += self.config.score_weights.dismissal_signal
            reasons.append("dismissal is a governance event signal")

        document.score = ScoreResult(value=round(max(0.0, min(score, 1.0)), 3), reasons=reasons)
        return document
