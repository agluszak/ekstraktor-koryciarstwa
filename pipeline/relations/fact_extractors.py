from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet

from pipeline.domain_types import (
    CandidateType,
    EntityID,
    FactID,
    FactType,
    OrganizationKind,
    RoleKind,
    TimeScope,
)
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    EntityCandidate,
    EvidenceSpan,
    Fact,
    ParsedWord,
    SentenceFragment,
)
from pipeline.nlp_rules import (
    APPOINTMENT_TRIGGER_LEMMAS,
    APPOINTMENT_TRIGGER_TEXTS,
    BOARD_ROLE_KINDS,
    BODY_CONTEXT_TERMS,
    COMPENSATION_PATTERN,
    DISMISSAL_TRIGGER_LEMMAS,
    DISMISSAL_TRIGGER_TEXTS,
    FORMER_MARKERS,
    FUNDING_HINTS,
    OFFICE_CANDIDACY_LEMMAS,
    OWNER_CONTEXT_TERMS,
    PARTY_CONTEXT_LEMMAS,
    TARGET_CONTEXT_TERMS,
    TIE_WORDS,
)
from pipeline.utils import find_dates, normalize_entity_name, stable_id


@dataclass(frozen=True, slots=True)
class SecondaryFactScore:
    confidence: float
    extraction_signal: str
    evidence_scope: str
    reason: str


class SecondaryFactScorer:
    SYNTACTIC_DIRECT = 0.85
    APPOSITIVE_CONTEXT = 0.78
    DEPENDENCY_EDGE = 0.72
    SAME_CLAUSE = 0.64
    SAME_SENTENCE = 0.55
    SAME_PARAGRAPH = 0.42
    BROAD_CONTEXT = 0.30

    @classmethod
    def party_membership(
        cls,
        context: SentenceContext,
        person: EntityCandidate,
        party: EntityCandidate,
        *,
        governance_signal: bool,
    ) -> SecondaryFactScore | None:
        edge_confidence = context.edge_confidence(
            "person-affiliated-party",
            person.candidate_id,
            party.candidate_id,
        )
        syntactic_signal = _party_syntactic_signal(context, person, party)
        distance = abs(person.start_char - party.start_char)

        if syntactic_signal == "syntactic_direct":
            confidence = max(cls.SYNTACTIC_DIRECT, edge_confidence or 0.0)
            return cls._score(confidence, syntactic_signal, "same_sentence", "direct_party_edge")
        if syntactic_signal == "appositive_context":
            confidence = max(cls.APPOSITIVE_CONTEXT, edge_confidence or 0.0)
            return cls._score(confidence, syntactic_signal, "same_sentence", "party_apposition")
        if edge_confidence is not None:
            confidence = max(cls.DEPENDENCY_EDGE, edge_confidence)
            if governance_signal:
                confidence -= 0.12
            return cls._score(
                confidence,
                "dependency_edge",
                "same_sentence",
                "candidate_graph_party_edge",
            )
        if distance <= 40 and _party_context_window_supports(context, person, party):
            confidence = cls.SAME_SENTENCE - (0.1 if governance_signal else 0.0)
            return cls._score(confidence, "same_sentence", "same_sentence", "near_party_context")
        return None

    @classmethod
    def political_office(
        cls,
        context: SentenceContext,
        person: EntityCandidate,
        role: EntityCandidate,
        *,
        governance_signal: bool,
    ) -> SecondaryFactScore | None:
        edge_confidence = context.edge_confidence(
            "person-has-role",
            person.candidate_id,
            role.candidate_id,
        )
        distance = abs(person.start_char - role.start_char)
        if edge_confidence is not None and edge_confidence >= 0.72:
            confidence = max(cls.DEPENDENCY_EDGE, edge_confidence)
            if governance_signal:
                confidence -= 0.1
            return cls._score(
                confidence,
                "dependency_edge",
                "same_sentence",
                "person_role_edge",
            )
        if distance <= 28:
            confidence = cls.SAME_SENTENCE - (0.08 if governance_signal else 0.0)
            return cls._score(confidence, "same_sentence", "same_sentence", "near_office_role")
        if distance <= 48 and not governance_signal:
            return cls._score(cls.SAME_PARAGRAPH, "same_paragraph", "same_sentence", "loose_role")
        return None

    @classmethod
    def candidacy(
        cls,
        context: SentenceContext,
        person: EntityCandidate,
    ) -> SecondaryFactScore | None:
        lemmas = {word.lemma for word in context.parsed_words}
        if not (
            OFFICE_CANDIDACY_LEMMAS.intersection(lemmas)
            or "kandydat" in context.lowered_text
            or "wybory" in context.lowered_text
        ):
            return None
        governing_words = [
            word
            for word in context.parsed_words
            if word.lemma in OFFICE_CANDIDACY_LEMMAS or word.lemma == "kandydat"
        ]
        if "wybory" not in context.lowered_text and "kandydat" not in context.lowered_text:
            return None
        if any(abs(person.start_char - word.start) <= 28 for word in governing_words):
            return cls._score(cls.DEPENDENCY_EDGE, "dependency_edge", "same_sentence", "candidacy")
        return cls._score(cls.SAME_SENTENCE, "same_sentence", "same_sentence", "election_context")

    @classmethod
    def compensation(
        cls,
        *,
        person: EntityCandidate | None,
        organization: EntityCandidate | None,
        role: EntityCandidate | None,
    ) -> SecondaryFactScore:
        if person is not None and organization is not None and role is not None:
            return cls._score(
                cls.SYNTACTIC_DIRECT,
                "syntactic_direct",
                "same_sentence",
                "amount_person_role_org",
            )
        if person is not None and organization is not None:
            return cls._score(
                cls.DEPENDENCY_EDGE,
                "dependency_edge",
                "same_sentence",
                "amount_person_org",
            )
        if person is not None:
            return cls._score(
                cls.SAME_SENTENCE,
                "same_sentence",
                "same_sentence",
                "amount_person",
            )
        return cls._score(
            cls.SAME_PARAGRAPH,
            "same_paragraph",
            "same_sentence",
            "amount_public_org",
        )

    @classmethod
    def funding(cls, *, has_amount: bool) -> SecondaryFactScore:
        return cls._score(
            cls.DEPENDENCY_EDGE if has_amount else cls.SAME_SENTENCE,
            "dependency_edge" if has_amount else "same_sentence",
            "same_sentence",
            "funding_amount" if has_amount else "funding_verb",
        )

    @classmethod
    def tie(
        cls,
        context: SentenceContext,
        source: EntityCandidate,
        target: EntityCandidate,
        trigger: str,
        edge_confidence: float,
    ) -> SecondaryFactScore:
        strong_triggers = {"przyjaciel", "doradca", "rekomendować", "rekomendacja"}
        distance = abs(source.start_char - target.start_char)
        confidence = max(cls.SAME_SENTENCE, edge_confidence)
        signal = "dependency_edge"
        reason = f"tie_trigger:{trigger}"
        if trigger in strong_triggers:
            confidence += 0.08
            signal = "syntactic_direct"
        if distance > 120:
            confidence -= 0.12
            reason += ":long_distance"
        if _is_quote_speaker_risk(context, source) or _is_quote_speaker_risk(context, target):
            confidence -= 0.12
            reason += ":quote_speaker_risk"
        return cls._score(confidence, signal, "same_sentence", reason)

    @staticmethod
    def _score(
        confidence: float,
        extraction_signal: str,
        evidence_scope: str,
        reason: str,
    ) -> SecondaryFactScore:
        return SecondaryFactScore(
            confidence=max(0.05, min(confidence, 0.95)),
            extraction_signal=extraction_signal,
            evidence_scope=evidence_scope,
            reason=reason,
        )


@dataclass(slots=True)
class SentenceContext:
    document: ArticleDocument
    sentence: SentenceFragment
    parsed_words: list[ParsedWord]
    graph: CandidateGraph
    candidates: list[EntityCandidate]
    paragraph_candidates: list[EntityCandidate]
    previous_candidates: list[EntityCandidate]

    @property
    def persons(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.PERSON
        ]

    @property
    def positions(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.POSITION
        ]

    @property
    def organizations(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type
            in {CandidateType.ORGANIZATION, CandidateType.PUBLIC_INSTITUTION}
        ]

    @property
    def parties(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.candidate_type == CandidateType.POLITICAL_PARTY
        ]

    @property
    def paragraph_persons(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.paragraph_candidates
            if candidate.candidate_type == CandidateType.PERSON
        ]

    @property
    def paragraph_organizations(self) -> list[EntityCandidate]:
        return [
            candidate
            for candidate in self.paragraph_candidates
            if candidate.candidate_type
            in {CandidateType.ORGANIZATION, CandidateType.PUBLIC_INSTITUTION}
        ]

    @property
    def lowered_text(self) -> str:
        return self.sentence.text.lower()

    @property
    def event_date(self) -> str | None:
        return next(iter(find_dates(self.sentence.text)), self.document.publication_date)

    @property
    def time_scope(self) -> TimeScope:
        lowered = self.lowered_text
        if any(marker in lowered for marker in FORMER_MARKERS):
            return TimeScope.FORMER
        if "ma zostać" in lowered:
            return TimeScope.FUTURE
        return TimeScope.CURRENT

    @property
    def evidence(self) -> EvidenceSpan:
        return EvidenceSpan(
            text=self.sentence.text,
            sentence_index=self.sentence.sentence_index,
            paragraph_index=self.sentence.paragraph_index,
            start_char=self.sentence.start_char,
            end_char=self.sentence.end_char,
        )

    def edge_confidence(self, edge_type: str, source_id: str, target_id: str) -> float | None:
        candidates = [
            edge.confidence
            for edge in self.graph.edges
            if edge.edge_type == edge_type
            and edge.sentence_index == self.sentence.sentence_index
            and edge.source_candidate_id == source_id
            and edge.target_candidate_id == target_id
        ]
        return max(candidates) if candidates else None

    def outgoing(self, edge_type: str, source_id: str) -> list[EntityCandidate]:
        target_ids = [
            edge.target_candidate_id
            for edge in self.graph.edges
            if edge.edge_type == edge_type
            and edge.sentence_index == self.sentence.sentence_index
            and edge.source_candidate_id == source_id
        ]
        return [candidate for candidate in self.candidates if candidate.candidate_id in target_ids]

    @property
    def overlaps_governance(self) -> bool:
        return any(
            evidence.sentence_index == self.sentence.sentence_index
            for frame in self.document.governance_frames
            for evidence in frame.evidence
        )


def _fact(
    *,
    document: ArticleDocument,
    sentence_context: SentenceContext,
    fact_type: FactType,
    subject: EntityCandidate,
    object_candidate: EntityCandidate | None,
    value_text: str | None,
    value_normalized: str | None,
    confidence: float,
    score: SecondaryFactScore,
    source_extractor: str,
    **extra_fields,
) -> Fact:
    f = Fact(
        fact_id=FactID(
            stable_id(
                "fact",
                document.document_id,
                fact_type,
                subject.entity_id or subject.candidate_id,
                object_candidate.entity_id or object_candidate.candidate_id
                if object_candidate
                else "",
                value_normalized or value_text or "",
                sentence_context.evidence.text,
            )
        ),
        fact_type=fact_type,
        subject_entity_id=EntityID(subject.entity_id or subject.candidate_id),
        object_entity_id=EntityID(object_candidate.entity_id or object_candidate.candidate_id)
        if object_candidate
        else None,
        value_text=value_text,
        value_normalized=value_normalized,
        time_scope=sentence_context.time_scope,
        event_date=sentence_context.event_date,
        confidence=round(confidence, 3),
        evidence=sentence_context.evidence,
        extraction_signal=score.extraction_signal,
        evidence_scope=score.evidence_scope,
        overlaps_governance=sentence_context.overlaps_governance,
        source_extractor=source_extractor,
        score_reason=score.reason,
    )
    for k, v in extra_fields.items():
        setattr(f, k, v)
    return f


class PoliticalProfileFactExtractor:
    POLITICAL_ROLE_NAMES = {
        RoleKind.RADNY.value,
        RoleKind.POSEL.value,
        RoleKind.SENATOR.value,
        RoleKind.WICEMINISTER.value,
        RoleKind.MINISTER.value,
        RoleKind.PREZYDENT_MIASTA.value,
        RoleKind.WICEPREZYDENT.value,
        RoleKind.WICEWOJEWODA.value,
    }

    def extract(self, context: SentenceContext) -> list[Fact]:
        facts: list[Fact] = []
        governance_signal = _has_signal(
            context.parsed_words,
            context.lowered_text,
            APPOINTMENT_TRIGGER_LEMMAS | DISMISSAL_TRIGGER_LEMMAS,
            APPOINTMENT_TRIGGER_TEXTS | DISMISSAL_TRIGGER_TEXTS,
        )
        for person in context.persons:
            for party in context.outgoing("person-affiliated-party", person.candidate_id):
                score = SecondaryFactScorer.party_membership(
                    context,
                    person,
                    party,
                    governance_signal=governance_signal,
                )
                if score is None:
                    continue
                fact_type = (
                    FactType.FORMER_PARTY_MEMBERSHIP
                    if context.time_scope == TimeScope.FORMER
                    else FactType.PARTY_MEMBERSHIP
                )
                facts.append(
                    _fact(
                        document=context.document,
                        sentence_context=context,
                        fact_type=fact_type,
                        subject=person,
                        object_candidate=party,
                        value_text=party.canonical_name,
                        value_normalized=party.normalized_name,
                        confidence=score.confidence,
                        score=score,
                        source_extractor="political_profile",
                        party=party.canonical_name,
                    )
                )

            for role in context.outgoing("person-has-role", person.candidate_id):
                role_name = role.normalized_name.lower()
                if role_name not in self.POLITICAL_ROLE_NAMES:
                    continue
                score = SecondaryFactScorer.political_office(
                    context,
                    person,
                    role,
                    governance_signal=governance_signal,
                )
                if score is None:
                    continue
                facts.append(
                    _fact(
                        document=context.document,
                        sentence_context=context,
                        fact_type=FactType.POLITICAL_OFFICE,
                        subject=person,
                        object_candidate=role,
                        value_text=role.canonical_name,
                        value_normalized=role.normalized_name,
                        confidence=score.confidence,
                        score=score,
                        source_extractor="political_profile",
                        office_type=role.canonical_name,
                    )
                )

            candidacy_score = SecondaryFactScorer.candidacy(context, person)
            if candidacy_score is not None:
                facts.append(
                    _fact(
                        document=context.document,
                        sentence_context=context,
                        fact_type=FactType.ELECTION_CANDIDACY,
                        subject=person,
                        object_candidate=None,
                        value_text=None,
                        value_normalized=None,
                        confidence=candidacy_score.confidence,
                        score=candidacy_score,
                        source_extractor="political_profile",
                        candidacy_scope="mentioned",
                    )
                )
        return facts


class CompensationFactExtractor:
    def extract(self, context: SentenceContext) -> list[Fact]:
        match = COMPENSATION_PATTERN.search(context.sentence.text)
        if match is None:
            return []
        person = _nearest_candidate(context.persons, match.start()) if context.persons else None
        organization_for_context = _nearest_candidate(context.organizations, match.start())
        if person is None and organization_for_context is None:
            return []
        role = _best_role_candidate(context, person) if person is not None else None
        organization = (
            _best_org_candidate(context, person, role)
            if person is not None
            else organization_for_context
        )
        object_candidate = organization or role
        subject = person or organization_for_context
        if subject is None:
            return []
        score = SecondaryFactScorer.compensation(
            person=person,
            organization=organization,
            role=role,
        )
        return [
            _fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.COMPENSATION,
                subject=subject,
                object_candidate=object_candidate,
                value_text=match.group("amount"),
                value_normalized=normalize_entity_name(match.group("amount").lower()),
                confidence=score.confidence,
                score=score,
                source_extractor="compensation",
                amount_text=normalize_entity_name(match.group("amount").lower()),
                period=normalize_entity_name(match.group("period").lower())
                if match.group("period")
                else None,
                position_entity_id=role.entity_id or EntityID(role.candidate_id) if role else None,
                organization_kind=organization.organization_kind if organization else None,
            )
        ]


class FundingFactExtractor:
    def extract(self, context: SentenceContext) -> list[Fact]:
        lemmas = {word.lemma for word in context.parsed_words}
        if not any(hint in lemmas or hint in context.lowered_text for hint in FUNDING_HINTS):
            return []
        if len(context.organizations) < 2:
            return []

        source = context.organizations[0]
        target = context.organizations[-1]
        if source.entity_id == target.entity_id:
            return []

        amount = COMPENSATION_PATTERN.search(context.sentence.text)
        score = SecondaryFactScorer.funding(has_amount=amount is not None)
        return [
            _fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.FUNDING,
                subject=target,
                object_candidate=source,
                value_text=amount.group("amount") if amount else None,
                value_normalized=normalize_entity_name(amount.group("amount").lower())
                if amount
                else None,
                confidence=score.confidence,
                score=score,
                source_extractor="funding",
                amount_text=normalize_entity_name(amount.group("amount").lower())
                if amount
                else None,
                organization_kind=source.organization_kind,
            )
        ]


class TieFactExtractor:
    def extract(self, context: SentenceContext) -> list[Fact]:
        lowered = context.lowered_text
        trigger = next((word for word in TIE_WORDS if word in lowered), None)
        if trigger is None:
            return []
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
                _fact(
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
        return facts


def _has_signal(
    parsed_words: list[ParsedWord],
    lowered_text: str,
    lemmas: AbstractSet[str],
    surface_triggers: AbstractSet[str],
) -> bool:
    parsed_lemmas = {word.lemma for word in parsed_words}
    return bool(
        parsed_lemmas.intersection(lemmas)
        or any(trigger in lowered_text for trigger in surface_triggers)
    )


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
        kinship_markers = {
            "żona",
            "mąż",
            "syn",
            "córka",
            "brat",
            "siostra",
            "szwagier",
            "szwagierka",
            "kuzyn",
            "partnerka",
            "partner",
        }
        if word.upos == "NOUN" or word.text.lower() in kinship_markers:
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


def _best_role_candidate(
    context: SentenceContext,
    person: EntityCandidate,
) -> EntityCandidate | None:
    roles = context.outgoing("person-has-role", person.candidate_id)
    if not roles:
        if context.positions:
            return max(
                context.positions,
                key=lambda role: (
                    _role_priority(role),
                    -abs(person.start_char - role.start_char)
                    if role.sentence_index == person.sentence_index
                    else 0,
                ),
            )
        return None
    return max(
        roles,
        key=lambda role: (
            _role_priority(role),
            context.edge_confidence(
                "person-has-role",
                person.candidate_id,
                role.candidate_id,
            )
            or 0.0,
            -abs(person.start_char - role.start_char),
        ),
    )


def _appointment_object_candidate(
    context: SentenceContext,
    subject: EntityCandidate,
) -> EntityCandidate | None:
    root = next((word for word in context.parsed_words if word.deprel == "root"), None)
    if root is None or root.lemma not in {"powoływać", "powołać", "mianować", "wybrać"}:
        return None

    object_words = [
        word
        for word in context.parsed_words
        if word.head == root.index and word.deprel in {"obj", "iobj"}
    ]
    if not object_words:
        return None

    for word in object_words:
        candidate = next(
            (
                person
                for person in context.persons
                if person.entity_id != subject.entity_id
                and person.start_char <= word.start < person.end_char
            ),
            None,
        )
        if candidate is not None:
            return candidate

    if any(word.upos == "PRON" for word in object_words):
        previous_persons = [
            candidate
            for candidate in context.previous_candidates
            if candidate.candidate_type == CandidateType.PERSON
            and candidate.entity_id != subject.entity_id
        ]
        if previous_persons:
            return min(previous_persons, key=lambda candidate: candidate.start_char)
    return None


def _best_org_candidate(
    context: SentenceContext,
    person: EntityCandidate,
    role: EntityCandidate | None,
) -> EntityCandidate | None:
    organization_pool = _candidate_organization_pool(context, person, role)
    if organization_pool:
        return max(
            organization_pool,
            key=lambda org: _organization_resolution_score(
                context=context,
                candidate=org,
                role=role,
                person=person,
            ),
        )
    return None


def _candidate_organization_pool(
    context: SentenceContext,
    person: EntityCandidate,
    role: EntityCandidate | None,
) -> list[EntityCandidate]:
    pooled: dict[str, EntityCandidate] = {}
    if role is not None:
        for candidate in context.outgoing("role-at-organization", role.candidate_id):
            if candidate.candidate_type != CandidateType.POLITICAL_PARTY:
                pooled[candidate.candidate_id] = candidate
    for candidate in context.outgoing("person-org-context", person.candidate_id):
        if candidate.candidate_type != CandidateType.POLITICAL_PARTY:
            pooled[candidate.candidate_id] = candidate
    for candidate in context.paragraph_organizations:
        if candidate.candidate_type != CandidateType.POLITICAL_PARTY:
            pooled[candidate.candidate_id] = candidate
    return list(pooled.values())


def _organization_priority(candidate: EntityCandidate) -> float:
    normalized = candidate.normalized_name.lower()
    kind = candidate.organization_kind
    if kind == OrganizationKind.PUBLIC_INSTITUTION:
        base = 0.9
    elif kind == OrganizationKind.COMPANY:
        base = 1.0
    elif kind == OrganizationKind.GOVERNING_BODY:
        base = 0.25
    else:
        base = 0.5
    if normalized.startswith("zarząd") or normalized.startswith("rada"):
        base -= 0.35
    if "skarbu państwa" in normalized:
        base -= 0.65
    if any(term in normalized for term in OWNER_CONTEXT_TERMS):
        base -= 0.25
    if normalized.isupper() and len(normalized) <= 6:
        base -= 0.2
    if len(normalized.split()) == 1 and normalized.isalpha() and normalized.isupper():
        base -= 0.1
    return base + min(len(candidate.canonical_name), 40) / 200


def _organization_resolution_score(
    *,
    context: SentenceContext,
    candidate: EntityCandidate,
    role: EntityCandidate | None,
    person: EntityCandidate,
) -> tuple[float, float, int]:
    reference_start = role.start_char if role is not None else person.start_char
    role_edge = (
        context.edge_confidence("role-at-organization", role.candidate_id, candidate.candidate_id)
        if role is not None
        else None
    )
    person_edge = context.edge_confidence(
        "person-org-context",
        person.candidate_id,
        candidate.candidate_id,
    )
    confidence = max(role_edge or 0.0, person_edge or 0.0)
    priority = _organization_priority(candidate)
    distance = abs(reference_start - candidate.start_char)
    clause_bonus = _organization_clause_bonus(context, candidate, role, person)
    if _is_target_like_org(candidate):
        priority += 0.14
    if _is_owner_like_org(candidate):
        priority -= 0.2
    if role is not None and candidate.start_char >= role.start_char:
        priority += 0.06
    if candidate.sentence_index != person.sentence_index:
        priority -= 0.08
    priority += clause_bonus
    return (
        confidence * 0.65 + priority * 0.35,
        priority,
        -distance,
    )


def _role_priority(candidate: EntityCandidate) -> float:
    role_name = candidate.normalized_name.lower()
    if role_name in PoliticalProfileFactExtractor.POLITICAL_ROLE_NAMES:
        return 0.2
    if role_name in {role.value for role in BOARD_ROLE_KINDS}:
        return 1.0 + min(len(role_name), 32) / 200
    return 0.8 + min(len(role_name), 32) / 300


def _party_syntactic_signal(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
) -> str | None:
    party_word = _candidate_head_word(context.parsed_words, party)
    person_words = _candidate_words(context.parsed_words, person)
    if party_word is None or not person_words:
        return None

    head = next((word for word in context.parsed_words if word.index == party_word.head), None)
    if head is not None and head.lemma in PARTY_CONTEXT_LEMMAS:
        if any(person_word.index == head.head for person_word in person_words):
            return "syntactic_direct"
        if any(person_word.head == head.index for person_word in person_words):
            return "appositive_context"
        between_text = _between_candidates(context, person, party)
        if any(marker in between_text for marker in (" z ", ",", "(", ")")):
            return "appositive_context"

    preceding_text = context.sentence.text[max(0, party.start_char - 3) : party.start_char].lower()
    if preceding_text.endswith(" z "):
        return "syntactic_direct"
    return None


def _party_context_window_supports(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
) -> bool:
    window_start = max(0, min(person.start_char, party.start_char) - 8)
    window_end = max(person.end_char, party.end_char) + 16
    party_window = context.lowered_text[window_start:window_end]
    between_text = _between_candidates(context, person, party)
    strong_context = ("polityk", "działacz", "radny", "radna", "lider", "prezes")
    return any(marker in party_window for marker in strong_context) or any(
        marker in between_text for marker in (" z ", " z ")
    )


def _candidate_head_word(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> ParsedWord | None:
    words = _candidate_words(parsed_words, candidate)
    if not words:
        return None
    word_indices = {word.index for word in words}
    return next((word for word in words if word.head not in word_indices), words[-1])


def _candidate_words(
    parsed_words: list[ParsedWord],
    candidate: EntityCandidate,
) -> list[ParsedWord]:
    return [
        word
        for word in parsed_words
        if candidate.start_char <= word.start < candidate.end_char
        or word.start <= candidate.start_char < word.end
    ]


def _between_candidates(
    context: SentenceContext,
    left: EntityCandidate,
    right: EntityCandidate,
) -> str:
    between_start = min(left.end_char, right.end_char)
    between_end = max(left.start_char, right.start_char)
    return context.lowered_text[between_start:between_end]


def _is_quote_speaker_risk(
    context: SentenceContext,
    candidate: EntityCandidate,
) -> bool:
    candidate_words = _candidate_words(context.parsed_words, candidate)
    if not candidate_words:
        return False
    speech_roots = {
        word.index
        for word in context.parsed_words
        if word.deprel == "root"
        and any(
            child.deprel.startswith("parataxis")
            for child in context.parsed_words
            if child.head == word.index
        )
    }
    return any(
        word.head in speech_roots and word.deprel.startswith("nsubj") for word in candidate_words
    )


def _supports_party_fact(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
    governance_signal: bool,
) -> bool:
    distance = abs(person.start_char - party.start_char)
    max_distance = 24 if governance_signal else 40
    if distance > max_distance:
        return False
    window_start = max(0, min(person.start_char, party.start_char) - 8)
    window_end = max(person.end_char, party.end_char) + 16
    party_window = context.lowered_text[window_start:window_end]
    between_start = min(person.end_char, party.end_char)
    between_end = max(person.start_char, party.start_char)
    between_text = context.lowered_text[between_start:between_end]
    if any(
        marker in party_window
        for marker in ("polityk", "działacz", "radny", "radna", "lider", "prezes")
    ):
        return governance_signal or any(
            marker in between_text for marker in ("polityk", "działacz", "radny", "radna", "lider")
        )
    party_word = next(
        (
            word
            for word in context.parsed_words
            if word.start <= party.start_char < word.end
            or party.start_char <= word.start < party.end_char
        ),
        None,
    )
    if party_word is None:
        return False
    person_words = [
        word
        for word in context.parsed_words
        if person.start_char <= word.start < person.end_char
        or word.start <= person.start_char < word.end
    ]
    if not person_words:
        return False
    if party_word.head:
        head = next((word for word in context.parsed_words if word.index == party_word.head), None)
        if head is not None and head.lemma in PARTY_CONTEXT_LEMMAS:
            if any(person_word.index == head.head for person_word in person_words):
                return True
            if any(person_word.head == head.index for person_word in person_words):
                return True
            return not governance_signal and abs(person.start_char - party.start_char) <= 24
    preceding_text = context.sentence.text[max(0, party.start_char - 3) : party.start_char].lower()
    return preceding_text.endswith(" z ")


def _supports_office_fact(
    context: SentenceContext,
    person: EntityCandidate,
    role: EntityCandidate,
    governance_signal: bool,
) -> bool:
    distance = abs(person.start_char - role.start_char)
    edge_confidence = (
        context.edge_confidence(
            "person-has-role",
            person.candidate_id,
            role.candidate_id,
        )
        or 0.0
    )
    if governance_signal:
        return distance <= 28 or edge_confidence >= 0.72
    return distance <= 48 or edge_confidence >= 0.6


def _supports_candidacy(context: SentenceContext, person: EntityCandidate) -> bool:
    lemmas = {word.lemma for word in context.parsed_words}
    if not (
        OFFICE_CANDIDACY_LEMMAS.intersection(lemmas)
        or "kandydat" in context.lowered_text
        or "wybory" in context.lowered_text
    ):
        return False
    governing_words = [
        word
        for word in context.parsed_words
        if word.lemma in OFFICE_CANDIDACY_LEMMAS or word.lemma == "kandydat"
    ]
    if "wybory" not in context.lowered_text and "kandydat" not in context.lowered_text:
        return False
    return any(abs(person.start_char - word.start) <= 28 for word in governing_words)


def _is_target_like_org(candidate: EntityCandidate) -> bool:
    normalized = candidate.normalized_name.lower()
    if _is_body_like_org(candidate) or _is_owner_like_org(candidate):
        return False
    if candidate.organization_kind == OrganizationKind.COMPANY:
        return True
    return any(
        term in normalized
        for term in ("stadnin", "rewita", "tour", "wodociąg", "hotel", "port", "centrum", "spółk")
    )


def _is_owner_like_org(candidate: EntityCandidate) -> bool:
    normalized = candidate.normalized_name.lower()
    if "skarbu państwa" in normalized:
        return True
    if candidate.organization_kind == OrganizationKind.PUBLIC_INSTITUTION and any(
        term in normalized for term in OWNER_CONTEXT_TERMS
    ):
        return True
    return False


def _is_body_like_org(candidate: EntityCandidate) -> bool:
    normalized = candidate.normalized_name.lower()
    kind = candidate.organization_kind
    return kind == OrganizationKind.GOVERNING_BODY or any(
        normalized.startswith(term) for term in BODY_CONTEXT_TERMS
    )


def _nearest_candidate(
    candidates: list[EntityCandidate],
    index: int,
) -> EntityCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs(candidate.start_char - index))


def _organization_clause_bonus(
    context: SentenceContext,
    candidate: EntityCandidate,
    role: EntityCandidate | None,
    person: EntityCandidate,
) -> float:
    reference = role or person
    if candidate.sentence_index != reference.sentence_index:
        return -0.06

    local_start = min(reference.end_char, candidate.end_char)
    local_end = max(reference.start_char, candidate.start_char)
    between_text = context.lowered_text[local_start:local_end]
    bonus = 0.0

    if role is not None and candidate.start_char >= role.end_char:
        bonus += 0.08
    if between_text and "," not in between_text and len(between_text) <= 24:
        bonus += 0.08
    if any(term in candidate.normalized_name.lower() for term in TARGET_CONTEXT_TERMS):
        bonus += 0.08
    if any(term in between_text for term in OWNER_CONTEXT_TERMS):
        bonus -= 0.14
    if any(term in between_text for term in BODY_CONTEXT_TERMS):
        bonus -= 0.1
    return bonus
