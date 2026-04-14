from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, cast

from pipeline.domain_types import (
    CandidateType,
    FactAttributes,
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
    SentenceFragment,
)
from pipeline.utils import find_dates, normalize_entity_name, stable_id

from .nlp_rules import (
    APPOINTMENT_TRIGGER_LEMMAS,
    APPOINTMENT_TRIGGER_TEXTS,
    BOARD_ROLE_KINDS,
    COMPENSATION_PATTERN,
    DISMISSAL_TRIGGER_LEMMAS,
    DISMISSAL_TRIGGER_TEXTS,
    FORMER_MARKERS,
    FUNDING_HINTS,
    OFFICE_CANDIDACY_LEMMAS,
    TIE_WORDS,
)
from .types import ParsedWord


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
    attributes: FactAttributes | None = None,
) -> Fact:
    return Fact(
        fact_id=stable_id(
            "fact",
            document.document_id,
            fact_type,
            subject.entity_id or subject.candidate_id,
            object_candidate.entity_id or object_candidate.candidate_id if object_candidate else "",
            value_normalized or value_text or "",
            sentence_context.evidence.text,
        ),
        fact_type=fact_type,
        subject_entity_id=subject.entity_id or subject.candidate_id,
        object_entity_id=object_candidate.entity_id if object_candidate else None,
        value_text=value_text,
        value_normalized=value_normalized,
        time_scope=sentence_context.time_scope,
        event_date=sentence_context.event_date,
        confidence=round(confidence, 3),
        evidence=sentence_context.evidence,
        attributes=cast(FactAttributes, attributes or {}),
    )


class GovernanceFactExtractor:
    def extract(self, context: SentenceContext) -> list[Fact]:
        has_appointment_signal = _has_signal(
            context.parsed_words,
            context.lowered_text,
            APPOINTMENT_TRIGGER_LEMMAS,
            APPOINTMENT_TRIGGER_TEXTS,
        )
        has_dismissal_signal = _has_signal(
            context.parsed_words,
            context.lowered_text,
            DISMISSAL_TRIGGER_LEMMAS,
            DISMISSAL_TRIGGER_TEXTS,
        )
        if not has_appointment_signal and not has_dismissal_signal:
            return []

        subject = _subject_candidate(context)
        if subject is None:
            return []

        role = _best_role_candidate(context, subject)
        if role is None and not has_dismissal_signal:
            return []
        organization = _best_org_candidate(context, subject, role)
        if organization is None:
            return []
        
        # Skip media organizations (news sources) as governance targets
        name_lower = organization.canonical_name.lower()
        media_markers = {
            "onet", "pap", "wp", "wirtualna polska", "rzzeczypospolita", 
            "fakt", "tvn", "tvp", "interia"
        }
        if (organization.attributes.get("is_media") or 
            any(m in name_lower for m in media_markers)):
            return []


        if organization.candidate_type == CandidateType.POLITICAL_PARTY:
            return []


        is_dismissal = has_dismissal_signal
        role_name = role.canonical_name if role else None
        return [
            _fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.DISMISSAL if is_dismissal else FactType.APPOINTMENT,
                subject=subject,
                object_candidate=organization,
                value_text=role_name,
                value_normalized=role.normalized_name if role else None,
                confidence=_governance_confidence(
                    context,
                    subject,
                    role,
                    organization,
                    is_dismissal,
                ),
                attributes={
                    "position_entity_id": role.entity_id if role else None,
                    "role": role_name,
                    "role_kind": role.normalized_name.lower() if role else None,
                    "board_role": bool(
                        role
                        and role.normalized_name.lower()
                        in {kind.value for kind in BOARD_ROLE_KINDS}
                    ),
                    "organization_kind": organization.attributes.get("organization_kind"),
                    "confidence_breakdown": {
                        "person_role": context.edge_confidence(
                            "person-has-role",
                            subject.candidate_id,
                            role.candidate_id,
                        )
                        if role
                        else None,
                        "role_org": context.edge_confidence(
                            "role-at-organization",
                            role.candidate_id,
                            organization.candidate_id,
                        )
                        if role
                        else None,
                    },
                },
            )
        ]


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
                if not _supports_party_fact(context, person, party, governance_signal):
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
                        confidence=0.77,
                        attributes={"party": party.canonical_name},
                    )
                )

            for role in context.outgoing("person-has-role", person.candidate_id):
                role_name = role.normalized_name.lower()
                if role_name in self.POLITICAL_ROLE_NAMES and _supports_office_fact(
                    context,
                    person,
                    role,
                    governance_signal,
                ):
                    facts.append(
                        _fact(
                            document=context.document,
                            sentence_context=context,
                            fact_type=FactType.POLITICAL_OFFICE,
                            subject=person,
                            object_candidate=role,
                            value_text=role.canonical_name,
                            value_normalized=role.normalized_name,
                            confidence=0.69,
                            attributes={"office_type": role.canonical_name},
                        )
                    )

            if _supports_candidacy(context, person):
                facts.append(
                    _fact(
                        document=context.document,
                        sentence_context=context,
                        fact_type=FactType.ELECTION_CANDIDACY,
                        subject=person,
                        object_candidate=None,
                        value_text=None,
                        value_normalized=None,
                        confidence=0.66,
                        attributes={"candidacy_scope": "mentioned"},
                    )
                )
        return facts


class CompensationFactExtractor:
    def extract(self, context: SentenceContext) -> list[Fact]:
        match = COMPENSATION_PATTERN.search(context.sentence.text)
        if match is None or not context.persons:
            return []
        person = _nearest_candidate(context.persons, match.start())
        if person is None:
            return []
        role = _best_role_candidate(context, person)
        organization = _best_org_candidate(context, person, role)
        object_candidate = organization or role
        if object_candidate is None:
            return []
        return [
            _fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.COMPENSATION,
                subject=person,
                object_candidate=object_candidate,
                value_text=match.group("amount"),
                value_normalized=normalize_entity_name(match.group("amount").lower()),
                confidence=0.74,
                attributes={
                    "amount_text": normalize_entity_name(match.group("amount").lower()),
                    "period": normalize_entity_name(match.group("period").lower())
                    if match.group("period")
                    else None,
                    "position_entity_id": role.entity_id if role else None,
                    "organization_kind": organization.attributes.get("organization_kind")
                    if organization
                    else None,
                },
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
                confidence=0.68,
                attributes={
                    "amount_text": normalize_entity_name(amount.group("amount").lower())
                    if amount
                    else None,
                    "organization_kind": source.attributes.get("organization_kind"),
                },
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
            facts.append(
                _fact(
                    document=context.document,
                    sentence_context=context,
                    fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                    subject=source,
                    object_candidate=target,
                    value_text=TIE_WORDS[trigger].value,
                    value_normalized=TIE_WORDS[trigger].value,
                    confidence=edge.confidence,
                    attributes={"relationship_type": TIE_WORDS[trigger]},
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
    all_nsubj = [
        word for word in context.parsed_words
        if word.deprel.startswith("nsubj")
    ]
    if not all_nsubj:
        all_nsubj = [
            word for word in context.parsed_words
            if word.deprel == "root"
        ]

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
                if (word.upos == "PROPN" or 
                    any(t.upos == "PROPN" for t in context.parsed_words 
                        if word.start <= t.start < word.end)):
                    return candidate

        # B: Subtree resolution (Nested Name)
        subtree_found = _find_entity_in_subtree(word.index)
        if subtree_found:
            return subtree_found

        # C: Referential proxy (Noun looking backwards)
        # We also check the word text for kinship markers in case POS is noisy.
        kinship_markers = {
            "żona", "mąż", "syn", "córka", "brat", "siostra", "szwagier", "szwagierka", "kuzyn"
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
                c for c in context.previous_candidates
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
        if (candidate is not None 
            and abs(candidate.start_char - word.start) <= 45 
            and candidate.canonical_name not in speaker_names):
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


def _best_org_candidate(
    context: SentenceContext,
    person: EntityCandidate,
    role: EntityCandidate | None,
) -> EntityCandidate | None:
    if role is not None:
        organizations = [
            candidate
            for candidate in context.outgoing("role-at-organization", role.candidate_id)
            if candidate.candidate_type != CandidateType.POLITICAL_PARTY
        ]
        if organizations:
            return max(
                organizations,
                key=lambda org: (
                    context.edge_confidence(
                        "role-at-organization",
                        role.candidate_id,
                        org.candidate_id,
                    )
                    or 0.0,
                    _organization_priority(org),
                    -abs(role.start_char - org.start_char),
                ),
            )

    organizations = [
        candidate
        for candidate in context.outgoing("person-org-context", person.candidate_id)
        if candidate.candidate_type != CandidateType.POLITICAL_PARTY
    ]
    if organizations:
        return max(
            organizations,
            key=lambda org: (
                context.edge_confidence("person-org-context", person.candidate_id, org.candidate_id)
                or 0.0,
                _organization_priority(org),
                -abs(person.start_char - org.start_char),
            ),
        )
    paragraph_organizations = [
        candidate
        for candidate in context.paragraph_organizations
        if candidate.candidate_type != CandidateType.POLITICAL_PARTY
    ]
    if paragraph_organizations:
        return max(
            paragraph_organizations,
            key=lambda org: (
                _organization_priority(org),
                -abs(org.sentence_index - person.sentence_index),
                -abs(person.start_char - org.start_char)
                if org.sentence_index == person.sentence_index
                else 0,
            ),
        )
    if len(context.organizations) == 1:
        return context.organizations[0]
    return None


def _organization_priority(candidate: EntityCandidate) -> float:
    normalized = candidate.normalized_name.lower()
    kind = candidate.attributes.get("organization_kind")
    if kind == OrganizationKind.PUBLIC_INSTITUTION:
        base = 0.9
    elif kind == OrganizationKind.COMPANY:
        base = 1.0
    else:
        base = 0.5
    if normalized.startswith("zarząd") or normalized.startswith("rada"):
        base -= 0.25
    if "skarbu państwa" in normalized:
        base -= 0.2
    if normalized.isupper() and len(normalized) <= 6:
        base -= 0.1
    return base + min(len(candidate.canonical_name), 40) / 200


def _role_priority(candidate: EntityCandidate) -> float:
    role_name = candidate.normalized_name.lower()
    if role_name in PoliticalProfileFactExtractor.POLITICAL_ROLE_NAMES:
        return 0.2
    if role_name in {role.value for role in BOARD_ROLE_KINDS}:
        return 1.0 + min(len(role_name), 32) / 200
    return 0.8 + min(len(role_name), 32) / 300


def _supports_party_fact(
    context: SentenceContext,
    person: EntityCandidate,
    party: EntityCandidate,
    governance_signal: bool,
) -> bool:
    distance = abs(person.start_char - party.start_char)
    if governance_signal and distance > 36:
        return False
    party_window = context.lowered_text[
        max(0, min(person.start_char, party.start_char) - 8) : max(person.end_char, party.end_char)
        + 16
    ]
    return any(marker in party_window for marker in ("polityk", "działacz", "radny", "radna", "z "))


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
    if not (OFFICE_CANDIDACY_LEMMAS.intersection(lemmas) or "kandydat" in context.lowered_text):
        return False
    governing_words = [
        word
        for word in context.parsed_words
        if word.lemma in OFFICE_CANDIDACY_LEMMAS or word.lemma == "kandydat"
    ]
    return any(abs(person.start_char - word.start) <= 72 for word in governing_words)


def _nearest_candidate(
    candidates: list[EntityCandidate],
    index: int,
) -> EntityCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs(candidate.start_char - index))


def _governance_confidence(
    context: SentenceContext,
    person: EntityCandidate,
    role: EntityCandidate | None,
    organization: EntityCandidate,
    is_dismissal: bool,
) -> float:
    base = 0.8 if is_dismissal else 0.82
    if role is None:
        base -= 0.08
    else:
        role_edge = (
            context.edge_confidence(
                "person-has-role",
                person.candidate_id,
                role.candidate_id,
            )
            or 0.0
        )
        org_edge = (
            context.edge_confidence(
                "role-at-organization",
                role.candidate_id,
                organization.candidate_id,
            )
            or 0.0
        )
        base += (role_edge + org_edge - 1.0) * 0.1
    if organization.attributes.get("organization_kind") == OrganizationKind.COMPANY:
        base += 0.02
    return max(0.45, min(base, 0.95))
