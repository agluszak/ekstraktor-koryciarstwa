from __future__ import annotations

import re

from pipeline.base import RelevanceFilter
from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument, RelevanceDecision
from pipeline.semantic_signals import (
    ANTI_CORRUPTION_CONTEXT_MARKERS,
    PATRONAGE_LANGUAGE_MARKERS,
    PUBLIC_FUND_CONTEXT_MARKERS,
    PUBLIC_OFFICE_ACTOR_MARKERS,
    SOFT_GOVERNANCE_CONTEXT_MARKERS,
    matching_markers,
)


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
        focus_segments = [document.title, document.lead_text, *document.paragraphs[:3]]
        lowered_focus = " ".join(
            segment.lower() for segment in focus_segments if isinstance(segment, str) and segment
        )
        keyword_hits = [
            keyword for keyword in self.config.keywords if keyword.lower() in lowered_full
        ]
        focus_keyword_hits = [
            keyword for keyword in self.config.keywords if keyword.lower() in lowered_focus
        ]

        # Sentence-level co-occurrence check
        co_occurrence_count = 0
        text_units = [sentence.text for sentence in document.sentences] or document.paragraphs
        for text_unit in text_units:
            lowered_sent = text_unit.lower()

            # Check for multiple categories in the same sentence
            has_person = bool(self.person_like_re.search(text_unit))
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
                    co_occurrence_count += 1  # Extra weight for dense sentences

        has_person_like = bool(self.person_like_re.search(document.cleaned_text))
        has_org_marker = any(
            marker in lowered_full for marker in self.config.patterns.state_company_markers
        )
        has_board_marker = any(
            marker in lowered_full for marker in self.config.patterns.board_terms
        )
        event_markers = (
            self.config.patterns.appointment_verbs + self.config.patterns.dismissal_verbs
        )
        has_governance_event = any(verb in lowered_full for verb in event_markers)
        public_fund_hits = matching_markers(lowered_full, PUBLIC_FUND_CONTEXT_MARKERS)
        soft_governance_hits = matching_markers(lowered_full, SOFT_GOVERNANCE_CONTEXT_MARKERS)
        focus_public_fund_hits = matching_markers(lowered_focus, PUBLIC_FUND_CONTEXT_MARKERS)
        focus_soft_governance_hits = matching_markers(
            lowered_focus, SOFT_GOVERNANCE_CONTEXT_MARKERS
        )

        score = 0.0
        reasons: list[str] = []

        # Base keyword score
        if keyword_hits:
            score += min(0.4, len(keyword_hits) * 0.1)
            reasons.append(f"keyword hits: {', '.join(keyword_hits[:5])}")

        patronage_hits = matching_markers(lowered_full, PATRONAGE_LANGUAGE_MARKERS)
        if patronage_hits:
            score += 0.25
            reasons.append(f"patronage language: {', '.join(patronage_hits)}")

        anti_corruption_hits = matching_markers(lowered_full, ANTI_CORRUPTION_CONTEXT_MARKERS)
        public_actor_hits = matching_markers(lowered_full, PUBLIC_OFFICE_ACTOR_MARKERS)
        if anti_corruption_hits:
            score += min(0.35, 0.12 * len(anti_corruption_hits))
            reasons.append(f"anti-corruption context: {', '.join(anti_corruption_hits[:4])}")
        if anti_corruption_hits and public_actor_hits:
            score += 0.18
            reasons.append(f"public-office actor context: {', '.join(public_actor_hits[:3])}")
        if public_fund_hits:
            score += min(0.25, 0.08 * len(public_fund_hits))
            reasons.append(f"public-fund context: {', '.join(public_fund_hits[:4])}")
        if soft_governance_hits:
            score += min(0.18, 0.06 * len(soft_governance_hits))
            reasons.append(f"soft governance language: {', '.join(soft_governance_hits[:4])}")
        if focus_public_fund_hits and (
            focus_soft_governance_hits or focus_keyword_hits or has_person_like
        ):
            score += 0.18
            reasons.append("headline/lead public-fund governance signal")

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
            reasons.append("contains public institution or board marker")
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
