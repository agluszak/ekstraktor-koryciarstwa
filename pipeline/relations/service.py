from __future__ import annotations

from pipeline.base import FactExtractor
from pipeline.compensation import CompensationFactBuilder
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    CandidateType,
    FactID,
    FactType,
    TimeScope,
)
from pipeline.funding import FundingFactBuilder
from pipeline.governance import GovernanceFactBuilder
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    CoreferenceResult,
    EntityCandidate,
    EvidenceSpan,
    Fact,
)
from pipeline.nlp_rules import PARTY_PROFILE_CONTEXT_LEMMAS
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.public_facts import (
    AntiCorruptionReferralFactBuilder,
    PublicContractFactBuilder,
)
from pipeline.utils import stable_id

from .candidate_graph import CandidateGraphBuilder
from .fact_extractors import (
    PoliticalProfileFactExtractor,
    SentenceContext,
    TieFactExtractor,
)


class PolishFactExtractor(FactExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.graph_builder = CandidateGraphBuilder(config)
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self.governance_fact_builder = GovernanceFactBuilder()
        self.compensation_fact_builder = CompensationFactBuilder()
        self.funding_fact_builder = FundingFactBuilder()
        self.public_contract_fact_builder = PublicContractFactBuilder()
        self.anti_corruption_referral_fact_builder = AntiCorruptionReferralFactBuilder()
        self.fact_extractors = [
            PoliticalProfileFactExtractor(),
            TieFactExtractor(),
        ]

    def name(self) -> str:
        return "polish_fact_extractor"

    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        candidate_graph = self.graph_builder.build(
            document=document,
            coreference=coreference,
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
        facts.extend(self.anti_corruption_referral_fact_builder.build(document))
        facts.extend(self._cross_sentence_party_facts(document, candidate_graph))
        facts.extend(self._cross_sentence_kinship_ties(document, candidate_graph))

        document.facts = self._deduplicate_facts(facts)
        return self.canonicalizer.run(document)

    @staticmethod
    def _cross_sentence_party_facts(
        document: ArticleDocument,
        candidate_graph: CandidateGraph,
    ) -> list[Fact]:
        candidates_by_sentence: dict[int, list[EntityCandidate]] = {}
        for candidate in candidate_graph.candidates:
            candidates_by_sentence.setdefault(candidate.sentence_index, []).append(candidate)

        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_candidates = candidates_by_sentence.get(sentence.sentence_index, [])
            parties = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == CandidateType.POLITICAL_PARTY
                and candidate.entity_id is not None
            ]
            if not parties:
                continue
            lowered = sentence.text.lower()
            parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
            if parsed_words:
                has_party_context = any(
                    word.lemma.casefold() in PARTY_PROFILE_CONTEXT_LEMMAS for word in parsed_words
                )
            else:
                has_party_context = any(
                    marker in lowered
                    for marker in ("działacz", "polityk", "radn", "lider", "członk")
                )
            if not has_party_context:
                continue
            if any(
                candidate.candidate_type == CandidateType.PERSON
                for candidate in sentence_candidates
            ):
                continue
            next_sentence = next(
                (
                    candidate_sentence
                    for candidate_sentence in document.sentences
                    if candidate_sentence.sentence_index == sentence.sentence_index + 1
                ),
                None,
            )
            if (
                next_sentence is None
                or next_sentence.paragraph_index - sentence.paragraph_index > 1
            ):
                continue
            persons = [
                candidate
                for candidate in candidates_by_sentence.get(next_sentence.sentence_index, [])
                if candidate.candidate_type == CandidateType.PERSON
                and candidate.entity_id is not None
                and candidate.start_char <= 20
            ]
            if not persons:
                continue
            person = min(persons, key=lambda candidate: candidate.start_char)
            for party in parties:
                assert person.entity_id is not None
                assert party.entity_id is not None
                fact_id = FactID(
                    stable_id(
                        "fact",
                        document.document_id,
                        FactType.PARTY_MEMBERSHIP,
                        person.entity_id,
                        party.entity_id,
                        str(sentence.sentence_index),
                    )
                )
                facts.append(
                    Fact(
                        fact_id=fact_id,
                        fact_type=FactType.PARTY_MEMBERSHIP,
                        subject_entity_id=person.entity_id,
                        object_entity_id=party.entity_id,
                        value_text=party.canonical_name,
                        value_normalized=party.normalized_name,
                        confidence=0.92,
                        time_scope=TimeScope.CURRENT,
                        event_date=document.publication_date,
                        evidence=EvidenceSpan(
                            text=f"{person.canonical_name} ({party.canonical_name})",
                            sentence_index=sentence.sentence_index,
                            paragraph_index=sentence.paragraph_index,
                            start_char=min(person.start_char, party.start_char),
                            end_char=max(person.end_char, party.end_char),
                        ),
                        source_extractor="party_membership_relation_extractor",
                        extraction_signal="discourse_window",
                        evidence_scope="adjacent_sentence",
                        party=party.canonical_name,
                    )
                )
        return facts

    @staticmethod
    def _cross_sentence_kinship_ties(
        document: ArticleDocument,
        candidate_graph: CandidateGraph,
    ) -> list[Fact]:
        from pipeline.nlp_rules import KINSHIP_LEMMAS, TIE_WORDS

        candidates_by_sentence: dict[int, list[EntityCandidate]] = {}
        for candidate in candidate_graph.candidates:
            candidates_by_sentence.setdefault(candidate.sentence_index, []).append(candidate)

        facts: list[Fact] = []
        kinship_triggers = set(KINSHIP_LEMMAS).union(set(TIE_WORDS.keys()))

        for sentence in document.sentences:
            lowered = sentence.text.lower()
            trigger = next((word for word in kinship_triggers if word in lowered), None)
            if trigger is None:
                continue

            sentence_candidates = candidates_by_sentence.get(sentence.sentence_index, [])
            # If a person is mentioned in the same sentence as the trigger, the standard extractor should handle it.
            # But if there's ONLY one person here, and they are mentioned near the trigger, 
            # maybe the relationship refers to someone in the PREVIOUS sentence.
            if len(sentence_candidates) != 1:
                continue
            
            curr_person = sentence_candidates[0]
            if curr_person.candidate_type != CandidateType.PERSON:
                continue

            prev_sentence_idx = sentence.sentence_index - 1
            if prev_sentence_idx < 0:
                continue
            
            prev_candidates = candidates_by_sentence.get(prev_sentence_idx, [])
            prev_persons = [c for c in prev_candidates if c.candidate_type == CandidateType.PERSON]
            if not prev_persons:
                continue
            
            # Use the last person from the previous sentence as the potential target
            target_person = prev_persons[-1]
            
            if curr_person.entity_id == target_person.entity_id:
                continue

            rel_type = TIE_WORDS.get(trigger, RelationshipType.FAMILY)
            
            fact_id = FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.PERSONAL_OR_POLITICAL_TIE,
                    curr_person.entity_id or curr_person.candidate_id,
                    target_person.entity_id or target_person.candidate_id,
                    str(sentence.sentence_index),
                    "cross-sentence",
                )
            )
            facts.append(
                Fact(
                    fact_id=fact_id,
                    fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                    subject_entity_id=EntityID(curr_person.entity_id or curr_person.candidate_id),
                    object_entity_id=EntityID(target_person.entity_id or target_person.candidate_id),
                    value_text=rel_type.value,
                    value_normalized=rel_type.value,
                    confidence=0.65,
                    time_scope=TimeScope.CURRENT,
                    event_date=document.publication_date,
                    evidence=EvidenceSpan(
                        text=f"{target_person.canonical_name} ... {sentence.text}",
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=target_person.start_char,
                        end_char=sentence.end_char,
                    ),
                    source_extractor="cross_sentence_kinship_extractor",
                    relationship_type=rel_type,
                )
            )
        return facts

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
