from __future__ import annotations

import re

from pipeline.base import RelevanceFilter
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, RelevanceDecision


class KeywordRelevanceFilter(RelevanceFilter):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.person_like_re = re.compile(
            r"\b[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+ [A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+\b"
        )

    def name(self) -> str:
        return "keyword_relevance_filter"

    def run(self, document: ArticleDocument) -> RelevanceDecision:
        lowered = document.cleaned_text.lower()
        keyword_hits = [keyword for keyword in self.config.keywords if keyword.lower() in lowered]
        has_person_like = bool(self.person_like_re.search(document.cleaned_text))
        has_org_marker = any(
            marker in lowered for marker in self.config.patterns.state_company_markers
        )
        has_board_marker = any(marker in lowered for marker in self.config.patterns.board_terms)
        event_markers = (
            self.config.patterns.appointment_verbs + self.config.patterns.dismissal_verbs
        )
        has_governance_event = any(verb in lowered for verb in event_markers)

        score = 0.0
        reasons: list[str] = []
        if keyword_hits:
            score += min(0.6, len(keyword_hits) * 0.15)
            reasons.append(f"keyword hits: {', '.join(keyword_hits[:5])}")
        if has_person_like:
            score += 0.2
            reasons.append("contains person-like full name")
        if has_org_marker:
            score += 0.2
            reasons.append("contains company or board marker")
        if has_board_marker:
            score += 0.15
            reasons.append("contains board or management marker")
        if has_governance_event:
            score += 0.2
            reasons.append("contains appointment or dismissal language")

        return RelevanceDecision(
            is_relevant=score >= 0.4,
            score=round(min(score, 1.0), 3),
            reasons=reasons or ["no relevance indicators found"],
        )
