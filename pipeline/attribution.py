from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import KINSHIP_LEMMAS
from pipeline.domain_types import CandidateType, OrganizationKind
from pipeline.entity_classifiers import is_party_like_name, is_public_employer_name
from pipeline.extraction_context import SentenceContext
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    EntityCandidate,
    EntityCluster,
    ParsedWord,
)
from pipeline.nlp_rules import (
    BOARD_ROLE_KINDS,
    BODY_CONTEXT_TERMS,
    OFFICE_CANDIDACY_LEMMAS,
    OWNER_CONTEXT_TERMS,
    TARGET_CONTEXT_TERMS,
)
from pipeline.relation_signals import (
    party_context_window_supports,
    party_syntactic_signal,
    person_role_syntactic_signal,
)
from pipeline.secondary_fact_helpers import POLITICAL_ROLE_NAMES, SecondaryFactScore


@dataclass(frozen=True, slots=True)
class ResolvedPartyAttribution:
    person: EntityCandidate
    party: EntityCandidate
    score: SecondaryFactScore


@dataclass(frozen=True, slots=True)
class ResolvedRoleAttribution:
    person: EntityCandidate
    role: EntityCandidate
    score: SecondaryFactScore


@dataclass(frozen=True, slots=True)
class ResolvedPublicEmploymentAttribution:
    employee: EntityCluster
    employer: EntityCluster
    role_cluster: EntityCluster | None


def resolve_party_attributions(
    context: SentenceContext,
    person: EntityCandidate,
    *,
    governance_signal: bool,
) -> list[ResolvedPartyAttribution]:
    if person.is_proxy_person:
        return []

    attributed: list[ResolvedPartyAttribution] = []
    seen_targets: set[str] = set()
    parties = [*context.outgoing("person-affiliated-party", person.candidate_id), *context.parties]
    for party in parties:
        target_key = str(party.entity_id or party.candidate_id)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        if (
            context.edge_confidence(
                "person-affiliated-party", person.candidate_id, party.candidate_id
            )
            is None
        ):
            if _other_person_between(person, party, context.persons):
                continue
        score = _party_membership_score(context, person, party, governance_signal=governance_signal)
        if score is None:
            continue
        attributed.append(ResolvedPartyAttribution(person=person, party=party, score=score))
    return attributed


def resolve_political_role_attributions(
    context: SentenceContext,
    person: EntityCandidate,
    *,
    governance_signal: bool,
) -> list[ResolvedRoleAttribution]:
    if person.is_proxy_person:
        return []

    attributed: list[ResolvedRoleAttribution] = []
    for role in context.outgoing("person-has-role", person.candidate_id):
        if role.normalized_name.lower() not in POLITICAL_ROLE_NAMES:
            continue
        score = _political_office_score(context, person, role, governance_signal=governance_signal)
        if score is None:
            continue
        attributed.append(ResolvedRoleAttribution(person=person, role=role, score=score))
    return attributed


def resolve_candidacy_score(
    context: SentenceContext,
    person: EntityCandidate,
) -> SecondaryFactScore | None:
    if person.is_proxy_person:
        return None
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
        return _score(0.72, "dependency_edge", "same_sentence", "candidacy")
    return _score(0.55, "same_sentence", "same_sentence", "election_context")


def resolve_public_employment_attribution(
    document: ArticleDocument,
    clause: ClauseUnit,
    *,
    config: PipelineConfig,
) -> ResolvedPublicEmploymentAttribution | None:
    employer = _resolve_public_employment_employer(document, clause, config=config)
    employee = _resolve_public_employment_employee(document, clause)
    if employer is None or employee is None:
        return None
    role_cluster = _resolve_public_employment_role_cluster(document, clause, employee)
    return ResolvedPublicEmploymentAttribution(
        employee=employee,
        employer=employer,
        role_cluster=role_cluster,
    )


def _party_membership_score(
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
    syntactic_signal = party_syntactic_signal(
        parsed_words=context.parsed_words,
        sentence_text=context.sentence.text,
        lowered_text=context.lowered_text,
        person=person,
        party=party,
    )
    distance = abs(person.start_char - party.start_char)

    if syntactic_signal == "syntactic_direct":
        return _score(
            max(0.85, edge_confidence or 0.0),
            syntactic_signal,
            "same_sentence",
            "direct_party_edge",
        )
    if syntactic_signal == "appositive_context":
        return _score(
            max(0.78, edge_confidence or 0.0), syntactic_signal, "same_sentence", "party_apposition"
        )
    if edge_confidence is not None:
        confidence = max(0.72, edge_confidence)
        if governance_signal:
            confidence -= 0.12
        return _score(confidence, "dependency_edge", "same_sentence", "candidate_graph_party_edge")
    if distance <= 40 and party_context_window_supports(
        parsed_words=context.parsed_words,
        lowered_text=context.lowered_text,
        person=person,
        party=party,
    ):
        return _score(
            0.55 - (0.1 if governance_signal else 0.0),
            "same_sentence",
            "same_sentence",
            "near_party_context",
        )
    return None


def _political_office_score(
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
    syntactic_signal = person_role_syntactic_signal(
        parsed_words=context.parsed_words,
        lowered_text=context.lowered_text,
        person=person,
        role=role,
        sentence_persons=context.persons,
    )
    distance = abs(person.start_char - role.start_char)

    if syntactic_signal == "syntactic_direct":
        confidence = max(0.85, edge_confidence or 0.0)
        if governance_signal:
            confidence -= 0.08
        return _score(confidence, syntactic_signal, "same_sentence", "direct_office_role")
    if syntactic_signal == "appositive_context":
        confidence = max(0.78, edge_confidence or 0.0)
        if governance_signal:
            confidence -= 0.08
        return _score(confidence, syntactic_signal, "same_sentence", "office_apposition")
    if edge_confidence is not None and edge_confidence >= 0.72:
        confidence = max(0.72, edge_confidence)
        if governance_signal:
            confidence -= 0.1
        return _score(confidence, "dependency_edge", "same_sentence", "person_role_edge")
    if distance <= 20 and not governance_signal:
        return _score(0.51, "same_sentence", "same_sentence", "near_title")
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
    return (confidence * 0.65 + priority * 0.35, priority, -distance)


def _role_priority(candidate: EntityCandidate) -> float:
    role_name = candidate.normalized_name.lower()
    if role_name in POLITICAL_ROLE_NAMES:
        return 0.2
    if role_name in {role.value for role in BOARD_ROLE_KINDS}:
        return 1.0 + min(len(role_name), 32) / 200
    return 0.8 + min(len(role_name), 32) / 300


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


def _other_person_between(
    left: EntityCandidate,
    right: EntityCandidate,
    persons: list[EntityCandidate],
) -> bool:
    between_start = min(left.end_char, right.end_char)
    between_end = max(left.start_char, right.start_char)
    return any(
        candidate.candidate_id not in {left.candidate_id, right.candidate_id}
        and candidate.start_char >= between_start
        and candidate.end_char <= between_end
        for candidate in persons
    )


def _resolve_public_employment_employer(
    document: ArticleDocument,
    clause: ClauseUnit,
    *,
    config: PipelineConfig,
) -> EntityCluster | None:
    current = [
        cluster
        for cluster in _clusters_for_clause(document, clause)
        if _is_public_employer_cluster(cluster) and not _is_party_cluster(cluster, config)
    ]
    if current:
        return min(current, key=lambda cluster: _cluster_clause_distance(cluster, clause))

    adjacent = [
        cluster
        for cluster in document.clusters
        if cluster.entity_type.name in {"ORGANIZATION", "PUBLIC_INSTITUTION"}
        and _is_public_employer_cluster(cluster)
        and not _is_party_cluster(cluster, config)
        and any(
            mention.paragraph_index == clause.paragraph_index
            and abs(mention.sentence_index - clause.sentence_index) <= 2
            for mention in cluster.mentions
        )
    ]
    fallback = adjacent or _document_level_employer_candidates(
        document,
        clause,
        config=config,
    )
    return min(
        fallback,
        key=lambda cluster: _cluster_clause_distance(cluster, clause),
        default=None,
    )


def _resolve_public_employment_employee(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> EntityCluster | None:
    patient = _employment_patient_cluster(document, clause)
    if patient is not None:
        return patient
    subject = _subject_cluster(document, clause)
    if subject is not None:
        return _proxy_cluster_for_anchor(document, clause, subject) or subject
    return min(
        (
            cluster
            for cluster in _clusters_for_clause(document, clause)
            if cluster.entity_type.name == "PERSON"
        ),
        key=lambda cluster: _cluster_clause_distance(cluster, clause),
        default=None,
    )


def _resolve_public_employment_role_cluster(
    document: ArticleDocument,
    clause: ClauseUnit,
    employee: EntityCluster,
) -> EntityCluster | None:
    roles = [
        cluster
        for cluster in _clusters_for_clause(document, clause)
        if cluster.entity_type.name == "POSITION"
    ]
    employee_distance = _cluster_clause_distance(employee, clause)
    return min(
        roles,
        key=lambda cluster: abs(_cluster_clause_distance(cluster, clause) - employee_distance),
        default=None,
    )


def _document_level_employer_candidates(
    document: ArticleDocument,
    clause: ClauseUnit,
    *,
    config: PipelineConfig,
) -> list[EntityCluster]:
    lowered = clause.text.casefold()
    if not any(
        marker in lowered
        for marker in ("urząd", "urzędzie", "gmina", "gminy", "koordynator", "projekt")
    ):
        return []
    return [
        cluster
        for cluster in document.clusters
        if cluster.entity_type.name in {"ORGANIZATION", "PUBLIC_INSTITUTION"}
        and _is_public_employer_cluster(cluster)
        and not _is_party_cluster(cluster, config)
        and any(
            marker in cluster.normalized_name.casefold()
            for marker in ("urząd gmin", "gmin", "starostw", "powiatow")
        )
    ]


def _employment_patient_cluster(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> EntityCluster | None:
    parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
    for trigger_word in [word for word in parsed_words if word.lemma.casefold() == "zatrudnić"]:
        object_words = [
            word
            for word in parsed_words
            if word.head == trigger_word.index
            and (word.deprel in {"obj", "iobj"} or word.deprel.startswith("nsubj:pass"))
        ]
        for object_word in object_words:
            cluster = _person_cluster_overlapping_word(document, clause, object_word)
            if cluster is not None:
                return cluster
            cluster = _person_cluster_in_subtree(document, clause, object_word.index)
            if cluster is not None:
                return cluster
            if object_word.lemma.casefold() in KINSHIP_LEMMAS:
                return _nearest_proxy_cluster(document, clause, object_word.start)
    return None


def _subject_cluster(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> EntityCluster | None:
    parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
    for word in [word for word in parsed_words if word.deprel.startswith("nsubj")]:
        cluster = _person_cluster_overlapping_word(document, clause, word)
        if cluster is not None:
            return cluster
        cluster = _person_cluster_in_subtree(document, clause, word.index)
        if cluster is not None:
            return cluster
    return None


def _person_cluster_in_subtree(
    document: ArticleDocument,
    clause: ClauseUnit,
    head_index: int,
    *,
    seen: set[int] | None = None,
) -> EntityCluster | None:
    if seen is None:
        seen = set()
    if head_index in seen:
        return None
    seen.add(head_index)
    parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
    for child in parsed_words:
        if child.head != head_index:
            continue
        cluster = _person_cluster_overlapping_word(document, clause, child)
        if cluster is not None:
            return cluster
        descendant = _person_cluster_in_subtree(document, clause, child.index, seen=seen)
        if descendant is not None:
            return descendant
    return None


def _person_cluster_overlapping_word(
    document: ArticleDocument,
    clause: ClauseUnit,
    word: ParsedWord,
) -> EntityCluster | None:
    for cluster in _clusters_for_clause(document, clause):
        if cluster.entity_type.name != "PERSON":
            continue
        if any(
            _mention_local_start(mention, clause)
            <= word.start
            < _mention_local_end(mention, clause)
            for mention in cluster.mentions
            if mention.sentence_index == clause.sentence_index
        ):
            return cluster
    return None


def _nearest_proxy_cluster(
    document: ArticleDocument,
    clause: ClauseUnit,
    local_start: int,
) -> EntityCluster | None:
    proxies = [
        cluster
        for cluster in _clusters_for_clause(document, clause)
        if cluster.entity_type.name == "PERSON" and cluster.is_proxy_person
    ]
    return min(
        proxies,
        key=lambda cluster: _cluster_clause_distance(cluster, clause) + local_start,
        default=None,
    )


def _proxy_cluster_for_anchor(
    document: ArticleDocument,
    clause: ClauseUnit,
    subject: EntityCluster,
) -> EntityCluster | None:
    subject_entity_ids = {mention.entity_id for mention in subject.mentions if mention.entity_id}
    return next(
        (
            cluster
            for cluster in document.clusters
            if cluster.is_proxy_person
            and cluster.proxy_anchor_entity_id in subject_entity_ids
            and any(mention.sentence_index == clause.sentence_index for mention in cluster.mentions)
        ),
        None,
    )


def _clusters_for_clause(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> list[EntityCluster]:
    mention_keys = {
        (mention.entity_id, mention.start_char, mention.end_char)
        for mention in clause.cluster_mentions
    }
    return [
        cluster
        for cluster in document.clusters
        if any(
            (mention.entity_id, mention.start_char, mention.end_char) in mention_keys
            for mention in cluster.mentions
        )
    ]


def _is_public_employer_cluster(cluster: EntityCluster) -> bool:
    if cluster.entity_type.name == "PUBLIC_INSTITUTION":
        return True
    if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
        return True
    return is_public_employer_name(cluster.normalized_name.casefold())


def _is_party_cluster(cluster: EntityCluster, config: PipelineConfig) -> bool:
    return is_party_like_name(cluster.normalized_name, config)


def _mention_local_start(mention: ClusterMention, clause: ClauseUnit) -> int:
    return max(0, mention.start_char - clause.start_char)


def _mention_local_end(mention: ClusterMention, clause: ClauseUnit) -> int:
    return max(0, mention.end_char - clause.start_char)


def _cluster_clause_distance(cluster: EntityCluster, clause: ClauseUnit) -> int:
    return min(
        (
            abs(_mention_local_start(mention, clause))
            for mention in cluster.mentions
            if mention.sentence_index == clause.sentence_index
        ),
        default=9999,
    )


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
