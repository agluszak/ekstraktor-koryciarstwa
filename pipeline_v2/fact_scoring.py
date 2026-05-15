from __future__ import annotations

from pipeline_v2.document import ArticleDocument, FactAssessment
from pipeline_v2.scoring import FactRecordScorer


class FactScoringStage:
    def name(self) -> str:
        return "fact_scoring_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        scorer = FactRecordScorer(document.store)
        assessed_ids = {assessment.fact_candidate_id for assessment in document.fact_assessments}
        for candidate in document.store.fact_candidates.values():
            if candidate.id in assessed_ids:
                continue
            record = candidate.to_fact_record()
            document.fact_assessments.append(
                FactAssessment(
                    fact_candidate_id=candidate.id,
                    assessment=scorer.score(record),
                )
            )
        return document
