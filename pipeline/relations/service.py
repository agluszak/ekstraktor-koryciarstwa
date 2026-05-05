from __future__ import annotations

from pipeline.base import FactExtractor
from pipeline.compensation import CompensationFactBuilder
from pipeline.config import PipelineConfig
from pipeline.domains.kinship import KinshipTieBuilder
from pipeline.domains.political_profile import (
    CrossSentencePartyFactBuilder,
    PoliticalProfileFactExtractor,
)
from pipeline.domains.secondary_facts import TieFactExtractor
from pipeline.extraction_context import SentenceContext
from pipeline.funding import FundingFactBuilder
from pipeline.governance import GovernanceFactBuilder
from pipeline.models import ArticleDocument, Fact
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.public_facts import (
    AntiCorruptionInvestigationFactBuilder,
    AntiCorruptionReferralFactBuilder,
    PublicContractFactBuilder,
    PublicEmploymentFactBuilder,
    PublicProcurementAbuseFactBuilder,
)

from .candidate_graph import CandidateGraphBuilder


class PolishFactExtractor(FactExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.graph_builder = CandidateGraphBuilder(config)
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self.governance_fact_builder = GovernanceFactBuilder()
        self.compensation_fact_builder = CompensationFactBuilder()
        self.funding_fact_builder = FundingFactBuilder()
        self.public_contract_fact_builder = PublicContractFactBuilder()
        self.public_employment_fact_builder = PublicEmploymentFactBuilder()
        self.anti_corruption_referral_fact_builder = AntiCorruptionReferralFactBuilder()
        self.anti_corruption_investigation_fact_builder = AntiCorruptionInvestigationFactBuilder()
        self.public_procurement_abuse_fact_builder = PublicProcurementAbuseFactBuilder()
        self.cross_sentence_party_fact_builder = CrossSentencePartyFactBuilder()
        self.kinship_tie_builder = KinshipTieBuilder()
        self.fact_extractors = [
            PoliticalProfileFactExtractor(),
            TieFactExtractor(),
        ]

    def name(self) -> str:
        return "polish_fact_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        candidate_graph = self.graph_builder.build(
            document=document,
            parsed_sentences=document.parsed_sentences,
        )
        facts: list[Fact] = list(document.facts)
        for sentence in document.sentences:
            sentence_candidates = [
                candidate
                for candidate in candidate_graph.candidates
                if candidate.sentence_index == sentence.sentence_index
            ]
            if not sentence_candidates:
                continue
            paragraph_candidates = [
                candidate
                for candidate in candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
            ]
            previous_candidates = [
                candidate
                for candidate in candidate_graph.candidates
                if candidate.paragraph_index == sentence.paragraph_index
                and candidate.sentence_index == sentence.sentence_index - 1
            ]
            context = SentenceContext(
                document=document,
                sentence=sentence,
                parsed_words=document.parsed_sentences.get(sentence.sentence_index, []),
                graph=candidate_graph,
                candidates=sentence_candidates,
                paragraph_candidates=paragraph_candidates,
                previous_candidates=previous_candidates,
            )
            for extractor in self.fact_extractors:
                facts.extend(extractor.extract(context))

        facts.extend(self.governance_fact_builder.build(document))
        facts.extend(self.compensation_fact_builder.build(document))
        facts.extend(self.funding_fact_builder.build(document))
        facts.extend(self.public_contract_fact_builder.build(document))
        facts.extend(self.public_employment_fact_builder.build(document))
        facts.extend(self.anti_corruption_referral_fact_builder.build(document))
        facts.extend(self.anti_corruption_investigation_fact_builder.build(document))
        facts.extend(self.public_procurement_abuse_fact_builder.build(document))
        facts.extend(
            self.cross_sentence_party_fact_builder.build_cross_sentence_party_facts(
                document,
                candidate_graph,
            )
        )
        facts.extend(self.kinship_tie_builder.build(document, candidate_graph))

        document.facts = self._deduplicate_facts(facts)
        return self.canonicalizer.run(document)

    @staticmethod
    def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str, str | None, str | None, str], Fact] = {}
        for fact in facts:
            key = (
                fact.fact_type,
                fact.subject_entity_id,
                fact.object_entity_id,
                fact.value_normalized,
                fact.evidence.text,
            )
            if key not in deduplicated or deduplicated[key].confidence < fact.confidence:
                deduplicated[key] = fact
        return list(deduplicated.values())
