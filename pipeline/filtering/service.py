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
        lowered_full = document.cleaned_text.lower()
        keyword_hits = [
            keyword for keyword in self.config.keywords if keyword.lower() in lowered_full
        ]

        # Sentence-level co-occurrence check
        co_occurrence_count = 0
        for sentence in document.sentences:
            lowered_sent = sentence.text.lower()
            
            # Check for multiple categories in the same sentence
            has_person = bool(self.person_like_re.search(sentence.text))
            has_org = any(
                marker in lowered_sent for marker in self.config.patterns.state_company_markers
            )
            has_board = any(marker in lowered_sent for marker in self.config.patterns.board_terms)
            has_event = any(
                verb in lowered_sent
                for verb in (
                    self.config.patterns.appointment_verbs + self.config.patterns.dismissal_verbs
                )
            )
            
            categories_hit = sum([has_person, has_org, has_board, has_event])
            if categories_hit >= 2:
                co_occurrence_count += 1
                if categories_hit >= 3:
                    co_occurrence_count += 1 # Extra weight for dense sentences

        has_person_like = bool(self.person_like_re.search(document.cleaned_text))
        has_org_marker = any(
            marker in lowered_full for marker in self.config.patterns.state_company_markers
        )
        has_board_marker = any(marker in lowered_full for marker in self.config.patterns.board_terms)
        event_markers = (
            self.config.patterns.appointment_verbs + self.config.patterns.dismissal_verbs
        )
        has_governance_event = any(verb in lowered_full for verb in event_markers)

        score = 0.0
        reasons: list[str] = []
        
        # Base keyword score
        if keyword_hits:
            score += min(0.4, len(keyword_hits) * 0.1)
            reasons.append(f"keyword hits: {', '.join(keyword_hits[:5])}")
            
        # Co-occurrence bonus (structural relevance)
        if co_occurrence_count > 0:
            bonus = min(0.5, co_occurrence_count * 0.15)
            score += bonus
            reasons.append(f"structural co-occurrence hits: {co_occurrence_count}")

        # Global features
        if has_person_like:
            score += 0.1
            reasons.append("contains person-like full name")
        if has_org_marker:
            score += 0.1
            reasons.append("contains company or board marker")
        if has_board_marker:
            score += 0.1
            reasons.append("contains board or management marker")
        if has_governance_event:
            score += 0.1
            reasons.append("contains appointment or dismissal language")

        return RelevanceDecision(
            is_relevant=score >= 0.45,
            score=round(min(score, 1.0), 3),
            reasons=reasons or ["no relevance indicators found"],
        )
