from __future__ import annotations

from pipeline.base import FactExtractor
from pipeline.compensation import CompensationFactBuilder
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    CandidateType,
    EntityID,
    EntityType,
    FactID,
    FactType,
    RelationshipType,
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

        # Map person names to entity IDs for quick lookup if coref fails
        person_name_to_id: dict[str, EntityID] = {}
        for entity in document.entities:
            if entity.entity_type == EntityType.PERSON:
                for alias in [entity.canonical_name, entity.normalized_name, *entity.aliases]:
                    person_name_to_id[alias.lower()] = entity.entity_id

        for sentence in document.sentences:
            lowered = sentence.text.lower()
            trigger = next((word for word in kinship_triggers if word in lowered), None)
            if trigger is None:
                continue

            sentence_candidates = candidates_by_sentence.get(sentence.sentence_index, [])
            # Target common phrasing where a new person is introduced with a kinship term
            # relating them to someone mentioned earlier.
            persons_in_sent = [
                c for c in sentence_candidates if c.candidate_type == CandidateType.PERSON
            ]

            target_subjects: list[EntityCandidate] = []
            if persons_in_sent:
                target_subjects = persons_in_sent
            else:
                # Search FORWARD (e.g. "Narzeczona... [new sentence] Marta...")
                for next_sent_idx in range(
                    sentence.sentence_index + 1,
                    sentence.sentence_index + 3,
                ):
                    if next_sent_idx >= len(document.sentences):
                        break
                    next_sent = document.sentences[next_sent_idx]
                    if next_sent.paragraph_index != sentence.paragraph_index:
                        break

                    next_sent_persons = [
                        c
                        for c in candidates_by_sentence.get(next_sent_idx, [])
                        if c.candidate_type == CandidateType.PERSON
                    ]
                    if next_sent_persons:
                        target_subjects = [next_sent_persons[0]]
                        break

            if not target_subjects:
                continue

            # For each subject (curr_person), try to find their relation target
            for curr_person in target_subjects:
                target_person: EntityCandidate | None = None

                # Search BACKWARDS in recent discourse
                for prev_sent_idx in range(sentence.sentence_index - 1, -1, -1):
                    prev_persons = [
                        c
                        for c in candidates_by_sentence.get(prev_sent_idx, [])
                        if c.candidate_type == CandidateType.PERSON
                        and (c.entity_id or c.candidate_id)
                        != (curr_person.entity_id or curr_person.candidate_id)
                    ]
                    if prev_persons:
                        target_person = prev_persons[0]
                        break

                # If still nothing, search FORWARDS (excluding curr_person themselves)
                if not target_person:
                    for next_sent_idx in range(
                        sentence.sentence_index + 1, sentence.sentence_index + 4
                    ):
                        if next_sent_idx >= len(document.sentences):
                            break
                        next_sent = document.sentences[next_sent_idx]
                        if sentence.paragraph_index - next_sent.paragraph_index > 1:
                            break
                        next_persons = [
                            c
                            for c in candidates_by_sentence.get(next_sent_idx, [])
                            if c.candidate_type == CandidateType.PERSON
                            and (c.entity_id or c.candidate_id)
                            != (curr_person.entity_id or curr_person.candidate_id)
                        ]
                        if next_persons:
                            target_person = next_persons[0]
                            break

                if target_person:
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
                            subject_entity_id=EntityID(
                                curr_person.entity_id or curr_person.candidate_id
                            ),
                            object_entity_id=EntityID(
                                target_person.entity_id or target_person.candidate_id
                            ),
                            value_text=rel_type.value,
                            value_normalized=rel_type.value,
                            confidence=0.6,
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
