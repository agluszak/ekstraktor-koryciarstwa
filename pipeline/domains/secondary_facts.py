from __future__ import annotations

import re

from pipeline.complaint_classifier import (
    detect_patronage_complaint,
    has_complaint_recipient_markers,
    has_power_holder_markers,
    has_speaker_markers,
    has_whistleblower_markers,
)
from pipeline.domain_lexicons import KINSHIP_LEMMAS
from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    EntityType,
    FactType,
    RelationshipType,
)
from pipeline.extraction_context import SentenceContext
from pipeline.models import EntityCandidate, Fact
from pipeline.nlp_rules import TIE_WORDS
from pipeline.secondary_fact_helpers import (
    SecondaryFactScore,
    SecondaryFactScorer,
    _is_quote_speaker_risk,
    build_secondary_fact,
)
from pipeline.utils import stable_id


class TieFactExtractor:
    def extract(self, context: SentenceContext) -> list[Fact]:
        trigger = self._tie_trigger(context)
        if trigger is None:
            return self._complaint_context_ties(context)
        person_edges = [
            edge
            for edge in context.graph.edges
            if edge.edge_type == "person-related-to-person"
            and edge.sentence_index == context.sentence.sentence_index
        ]
        facts: list[Fact] = []
        for edge in person_edges:
            source = next(
                candidate
                for candidate in context.candidates
                if candidate.candidate_id == edge.source_candidate_id
            )
            target = next(
                candidate
                for candidate in context.candidates
                if candidate.candidate_id == edge.target_candidate_id
            )
            score = SecondaryFactScorer.tie(
                context,
                source,
                target,
                trigger,
                edge.confidence,
            )
            facts.append(
                build_secondary_fact(
                    document=context.document,
                    sentence_context=context,
                    fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                    subject=source,
                    object_candidate=target,
                    value_text=TIE_WORDS[trigger].value,
                    value_normalized=TIE_WORDS[trigger].value,
                    confidence=score.confidence,
                    score=score,
                    source_extractor="tie",
                    relationship_type=TIE_WORDS[trigger],
                )
            )
        if not facts:
            facts.extend(self._owner_context_ties(context, trigger))
        if not facts:
            facts.extend(self._complaint_context_ties(context))
        return facts

    @staticmethod
    def _tie_trigger(context: SentenceContext) -> str | None:
        lemma_tokens = {(word.lemma or word.text).casefold() for word in context.parsed_words}
        text = context.lowered_text
        for trigger in TIE_WORDS:
            if " " not in trigger and trigger in lemma_tokens:
                return trigger
            if " " not in trigger and any(
                token.startswith(trigger[: max(5, len(trigger) - 2)]) for token in lemma_tokens
            ):
                return trigger
            pattern = rf"(?<!\w){re.escape(trigger)}(?!\w)"
            if re.search(pattern, text):
                return trigger
            if " " not in trigger and re.search(
                rf"(?<!\w){re.escape(trigger[: max(5, len(trigger) - 2)])}\w*",
                text,
            ):
                return trigger
        return None

    @staticmethod
    def _owner_context_ties(context: SentenceContext, trigger: str) -> list[Fact]:
        lowered = context.lowered_text
        anchor = lowered.find(trigger)
        if anchor < 0:
            anchor = min(
                (
                    lowered.find(marker)
                    for marker in ("współpracownik", "koleg", "znajom", "przyjaciel")
                    if lowered.find(marker) >= 0
                ),
                default=-1,
            )
        if anchor < 0:
            return []
        public_role_markers = ("prezydent", "burmistrz", "wójt", "minister", "poseł", "radny")
        public_actors = [
            person
            for person in context.persons
            if person.start_char >= anchor
            and any(
                marker in lowered[max(0, person.start_char - 40) : person.end_char + 8]
                for marker in public_role_markers
            )
            and not _is_quote_speaker_risk(context, person)
        ]
        if not public_actors:
            return []
        source = min(public_actors, key=lambda person: person.start_char)

        org_names = " ".join(org.normalized_name.lower() for org in context.organizations)
        document_org_names = " ".join(
            entity.normalized_name.lower()
            for entity in context.document.entities
            if entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        )
        owner_candidates = [
            person
            for person in context.paragraph_persons
            if person.entity_id != source.entity_id
            and person.canonical_name.split()
            and not _person_name_looks_like_company(person.canonical_name)
            and person.canonical_name.split()[-1].lower() in f"{org_names} {document_org_names}"
            and not _is_quote_speaker_risk(context, person)
        ]
        owner_candidates.extend(
            _document_owner_person_candidates(
                context,
                source=source,
                document_org_names=document_org_names,
            )
        )
        if not owner_candidates:
            return []
        target = min(owner_candidates, key=lambda person: abs(person.start_char - anchor))
        score = SecondaryFactScore(
            confidence=0.78,
            extraction_signal="dependency_edge",
            evidence_scope="same_paragraph",
            reason=f"tie_trigger:{trigger}:owner_context",
        )
        return [
            build_secondary_fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                subject=source,
                object_candidate=target,
                value_text=TIE_WORDS[trigger].value,
                value_normalized=TIE_WORDS[trigger].value,
                confidence=score.confidence,
                score=score,
                source_extractor="tie",
                relationship_type=TIE_WORDS[trigger],
            )
        ]

    def _complaint_context_ties(self, context: SentenceContext) -> list[Fact]:
        paragraph_text = self._paragraph_text(context)
        complaint_signal = detect_patronage_complaint(paragraph_text)
        if complaint_signal is None:
            return []

        paragraph_people = self._unique_people(context.paragraph_persons)
        if len(paragraph_people) < 2:
            return []

        source = self._complaint_source(context)
        if source is None:
            return []
        target_candidates = [
            candidate
            for candidate in paragraph_people
            if candidate.entity_id != source.entity_id
            and self._has_complaint_power_context(context, candidate)
            and not self._looks_like_complaint_recipient(context, candidate)
            and not _is_quote_speaker_risk(context, candidate)
        ]
        if not target_candidates:
            return []
        anchor = paragraph_text.find("kolesi")
        if anchor < 0:
            anchor = min(
                (paragraph_text.find(marker) for marker in complaint_signal.patronage_markers),
                default=-1,
            )
        if anchor < 0:
            anchor = source.start_char
        target = min(
            target_candidates,
            key=lambda candidate: (abs(candidate.start_char - anchor), candidate.start_char),
        )
        score = SecondaryFactScore(
            confidence=0.76,
            extraction_signal="same_paragraph",
            evidence_scope="same_paragraph",
            reason="complaint_patronage_context",
        )
        return [
            build_secondary_fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                subject=source,
                object_candidate=target,
                value_text=RelationshipType.ASSOCIATE.value,
                value_normalized=RelationshipType.ASSOCIATE.value,
                confidence=score.confidence,
                score=score,
                source_extractor="tie",
                relationship_type=RelationshipType.ASSOCIATE,
            )
        ]

    @staticmethod
    def _paragraph_text(context: SentenceContext) -> str:
        return " ".join(
            sentence.text.lower()
            for sentence in context.document.sentences
            if sentence.paragraph_index == context.sentence.paragraph_index
        )

    @staticmethod
    def _unique_people(candidates: list[EntityCandidate]) -> list[EntityCandidate]:
        unique: dict[str, EntityCandidate] = {}
        for candidate in candidates:
            if candidate.entity_id is None:
                continue
            unique.setdefault(str(candidate.entity_id), candidate)
        return list(unique.values())

    def _complaint_source(self, context: SentenceContext) -> EntityCandidate | None:
        sentence_people = [
            candidate
            for candidate in self._unique_people(context.persons)
            if not _is_quote_speaker_risk(context, candidate)
        ]
        if not sentence_people:
            sentence_people = [
                candidate
                for candidate in self._unique_people(context.paragraph_persons)
                if not _is_quote_speaker_risk(context, candidate)
            ]
        if not sentence_people:
            return None
        speaker_candidates = [
            candidate
            for candidate in sentence_people
            if self._has_speaker_context(context, candidate)
            and not self._looks_like_complaint_recipient(context, candidate)
        ]
        if speaker_candidates:
            return max(
                speaker_candidates,
                key=lambda candidate: (
                    self._has_whistleblower_context(context, candidate),
                    -candidate.start_char,
                ),
            )
        return min(
            (
                candidate
                for candidate in sentence_people
                if not self._has_complaint_power_context(context, candidate)
                and not self._looks_like_complaint_recipient(context, candidate)
            ),
            key=lambda candidate: candidate.start_char,
            default=None,
        )

    def _has_speaker_context(self, context: SentenceContext, candidate: EntityCandidate) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_speaker_markers(window)

    def _has_complaint_power_context(
        self,
        context: SentenceContext,
        candidate: EntityCandidate,
    ) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_power_holder_markers(window)

    def _has_whistleblower_context(
        self,
        context: SentenceContext,
        candidate: EntityCandidate,
    ) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_whistleblower_markers(window)

    def _looks_like_complaint_recipient(
        self,
        context: SentenceContext,
        candidate: EntityCandidate,
    ) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_complaint_recipient_markers(window)

    @staticmethod
    def _candidate_context_window(context: SentenceContext, candidate: EntityCandidate) -> str:
        paragraph_text = TieFactExtractor._paragraph_text(context)
        names = [
            candidate.canonical_name.lower(),
            candidate.normalized_name.lower(),
        ]
        if candidate.canonical_name.split():
            names.append(candidate.canonical_name.split()[0].lower())
        if candidate.canonical_name.split():
            names.append(candidate.canonical_name.split()[-1].lower())
        for name in names:
            anchor = paragraph_text.find(name)
            if anchor >= 0:
                return paragraph_text[max(0, anchor - 64) : anchor + len(name) + 64]
        return paragraph_text[:128]


def _document_owner_person_candidates(
    context: SentenceContext,
    *,
    source: EntityCandidate,
    document_org_names: str,
) -> list[EntityCandidate]:
    candidates: list[EntityCandidate] = []
    if not any(marker in context.lowered_text for marker in ("firmą prowadzon", "firma prowadzon")):
        return candidates
    for entity in context.document.entities:
        if entity.entity_type != EntityType.PERSON or entity.entity_id == source.entity_id:
            continue
        if _person_name_looks_like_company(entity.canonical_name):
            continue
        tokens = entity.canonical_name.split()
        if len(tokens) < 2 or tokens[-1].lower() not in document_org_names:
            continue
        candidates.append(
            EntityCandidate(
                candidate_id=CandidateID(
                    stable_id(
                        "candidate",
                        context.document.document_id,
                        entity.entity_id,
                        str(context.sentence.sentence_index),
                        "owner-context",
                    )
                ),
                entity_id=entity.entity_id,
                candidate_type=CandidateType.PERSON,
                canonical_name=entity.canonical_name,
                normalized_name=entity.normalized_name,
                sentence_index=context.sentence.sentence_index,
                paragraph_index=context.sentence.paragraph_index,
                start_char=0,
                end_char=0,
                source="document_owner_context",
            )
        )
    return candidates


def _person_name_looks_like_company(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in ("consulting", "group", "spół", "firma"))


def _subject_candidate(context: SentenceContext) -> EntityCandidate | None:
    """Resolve the subject of a governance event using POS tags and dependency
    structure from the NLP parse, rather than hardcoded word lists.

    Strategy:
    1. Partition nsubj words into governance-attached vs quote-attribution.
       Quote-verb subjects (nsubj of root speech verbs like ``mówi``) are
       deprioritized because they identify the speaker, not the actor.
    2. If a subject word directly overlaps a PERSON candidate, return it.
    3. Traverse the syntactic subtree of each subject word looking for PERSON
       candidates attached via nmod/appos/flat etc.
    4. If the subject word is a **common noun** (UPOS=NOUN) — indicating a
       referential proxy like "żona", "szwagierka" — and no person was found
       in the subtree, look backward in the paragraph for the most recent person.
    5. Fall back to proximity and paragraph-level heuristics.
    """
    speaker_names: set[str] = set()

    all_nsubj = [word for word in context.parsed_words if word.deprel.startswith("nsubj")]
    if not all_nsubj:
        all_nsubj = [word for word in context.parsed_words if word.deprel == "root"]

    # Speech/quote verbs are recognized by deprel: the governance clause is
    # usually attached as ``parataxis`` to the speech verb which is the root.
    # So an nsubj whose head verb has deprel == "root" AND whose head verb has
    # a parataxis child with its own nsubj is likely a quote attribution.
    # a parataxis child with its own nsubj is likely a quote attribution.
    speech_verb_indices: set[int] = set()
    for w in context.parsed_words:
        if w.deprel == "root":
            # Check if this root verb has a parataxis child with its own nsubj
            has_parataxis_with_nsubj = any(
                child.deprel.startswith("parataxis")
                and any(
                    gc.head == child.index and gc.deprel.startswith("nsubj")
                    for gc in context.parsed_words
                )
                for child in context.parsed_words
                if child.head == w.index
            )
            if has_parataxis_with_nsubj:
                speech_verb_indices.add(w.index)

    # Partition: governance subjects first, then quote-attribution subjects
    governance_subjects = [w for w in all_nsubj if w.head not in speech_verb_indices]
    attribution_subjects = [w for w in all_nsubj if w.head in speech_verb_indices]
    ordered_subjects = governance_subjects + attribution_subjects

    # --- Steps 1-3: Resolution per subject word (Prioritizing early subjects) ---
    def _find_entity_in_subtree(head_index: int, depth: int = 0) -> EntityCandidate | None:
        if depth > 4:
            return None
        children = [w for w in context.parsed_words if w.head == head_index]
        for child in children:
            for candidate in context.persons:
                if candidate.start_char <= child.start < candidate.end_char:
                    return candidate
            found = _find_entity_in_subtree(child.index, depth + 1)
            if found:
                return found
        return None

    for word in ordered_subjects:
        # A: Direct overlap (Named Entity)
        for candidate in context.persons:
            if candidate.start_char <= word.start < candidate.end_char:
                # If it's a PROPN or the word matches a Person, we accept it as a direct mention
                if word.upos == "PROPN" or any(
                    t.upos == "PROPN"
                    for t in context.parsed_words
                    if word.start <= t.start < word.end
                ):
                    return candidate

        # B: Subtree resolution (Nested Name)
        subtree_found = _find_entity_in_subtree(word.index)
        if subtree_found:
            return subtree_found

        # C: Referential proxy (Noun looking backwards)
        # We also check the word text for kinship markers in case POS is noisy.
        if word.upos == "NOUN" or word.text.lower() in KINSHIP_LEMMAS:
            # Identify the speaker(s) in this sentence by name to avoid self-attribution
            speaker_names = {
                c.canonical_name
                for c in context.persons
                if any(aw.start <= c.start_char < aw.end for aw in attribution_subjects)
            }

            # Look backward: previous sentence, then paragraph
            # We prefer candidates NOT in the speaker list.
            previous_persons = [
                c
                for c in context.previous_candidates
                if c.candidate_type == CandidateType.PERSON
                and c.canonical_name not in speaker_names
            ]
            if previous_persons:
                return previous_persons[-1]

            # Fallback to paragraph persons, skipping current speaker and their identity
            for p in context.paragraph_persons:
                if p.canonical_name not in speaker_names:
                    return p

    # --- Step 4: Proximity fallback (bounded) ---------------------------------
    for word in ordered_subjects:
        candidate = _nearest_candidate(context.persons, word.start)
        if (
            candidate is not None
            and abs(candidate.start_char - word.start) <= 45
            and candidate.canonical_name not in speaker_names
        ):
            return candidate

    # --- Step 5: Paragraph and Context fallbacks ------------------------------
    filtered_persons = [p for p in context.persons if p.canonical_name not in speaker_names]
    if filtered_persons:
        return filtered_persons[0]

    previous_persons = [
        candidate
        for candidate in context.previous_candidates
        if candidate.candidate_type == CandidateType.PERSON
        and candidate.canonical_name not in speaker_names
    ]
    if previous_persons:
        return previous_persons[-1]

    for p in context.paragraph_persons:
        if p.canonical_name not in speaker_names:
            return p

    return None


def _nearest_candidate(
    candidates: list[EntityCandidate],
    index: int,
) -> EntityCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs(candidate.start_char - index))
