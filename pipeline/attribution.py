from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import KINSHIP_LEMMAS
from pipeline.domain_types import EntityType, OrganizationKind
from pipeline.entity_classifiers import is_party_like_name, is_public_employer_name
from pipeline.extraction_context import ExtractionContext
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMentionView,
    EntityCluster,
    ParsedWord,
    SentenceFragment,
)
from pipeline.nlp_rules import (
    OFFICE_CANDIDACY_LEMMAS,
)
from pipeline.relation_signals import (
    _other_person_between,
    candidate_head_word,
    candidate_words,
    party_context_window_supports,
    party_syntactic_signal,
    person_role_syntactic_signal,
    supports_person_role_link,
)
from pipeline.secondary_fact_helpers import SecondaryFactScore


@dataclass(frozen=True, slots=True)
class ResolvedPartyAttribution:
    person: ClusterMentionView
    party: ClusterMentionView
    score: SecondaryFactScore


@dataclass(frozen=True, slots=True)
class ResolvedRoleAttribution:
    person: ClusterMentionView
    role: ClusterMentionView
    score: SecondaryFactScore


@dataclass(frozen=True, slots=True)
class ResolvedPublicEmploymentAttribution:
    employee: ClusterMentionView
    employer: ClusterMentionView
    role_cluster: ClusterMentionView | None


def resolve_party_attributions(
    context: ExtractionContext,
    sentence: SentenceFragment,
    person: ClusterMentionView,
    *,
    governance_signal: bool,
) -> list[ResolvedPartyAttribution]:
    if person.is_proxy_person:
        return []

    parsed_words = context.document.parsed_sentences.get(sentence.sentence_index, [])
    lowered_text = sentence.text.lower()
    parties = context.mention_views_in_sentence(
        sentence.sentence_index, {EntityType.POLITICAL_PARTY}
    )
    persons = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.PERSON})

    attributed: list[ResolvedPartyAttribution] = []
    seen_targets: set[str] = set()
    for party in parties:
        target_key = party.normalized_name.casefold()
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        score = _party_membership_score(
            parsed_words,
            sentence.text,
            lowered_text,
            person,
            party,
            sentence_start=sentence.start_char,
            governance_signal=governance_signal,
        )
        if score is None:
            continue
        if _other_person_between(person, party, persons) and not _party_context_links_person(
            parsed_words,
            person,
            party,
            sentence_start=sentence.start_char,
        ):
            continue
        attributed.append(ResolvedPartyAttribution(person=person, party=party, score=score))
    return attributed


def _party_context_links_person(
    parsed_words: list[ParsedWord],
    person: ClusterMentionView,
    party: ClusterMentionView,
    *,
    sentence_start: int = 0,
) -> bool:
    party_word = candidate_head_word(parsed_words, party, sentence_start=sentence_start)
    person_words = candidate_words(parsed_words, person, sentence_start=sentence_start)
    if party_word is None or not person_words:
        return False

    person_word_indices = {word.index for word in person_words}

    # 1. Direct link: party depends on person or vice versa
    if party_word.head in person_word_indices:
        return True
    if any(word.head == party_word.index for word in person_words):
        return True

    # 2. Linked via a joining head (preposition "z", bracket, or appositive)
    context_head = next((word for word in parsed_words if word.index == party_word.head), None)
    if context_head is not None:
        # Check if the join is valid (e.g. "z", "w", or a role like "posłanka")
        is_valid_join = context_head.upos in {
            "ADP",
            "PUNCT",
            "NOUN",
        } or context_head.lemma.casefold() in {"z", "w", "za", "od"}
        if is_valid_join:
            if context_head.head in person_word_indices:
                return True
            if any(word.head == context_head.index for word in person_words):
                return True

            # 3. Path search: Razem -> partii -> posłanka -> Zawisza
            grand_head = next(
                (word for word in parsed_words if word.index == context_head.head), None
            )
            if grand_head is not None:
                if (
                    grand_head.index in person_word_indices
                    or grand_head.head in person_word_indices
                ):
                    return True

    return False


def resolve_political_role_attributions(
    context: ExtractionContext,
    sentence: SentenceFragment,
    person: ClusterMentionView,
    *,
    governance_signal: bool,
) -> list[ResolvedRoleAttribution]:
    if person.is_proxy_person:
        return []

    parsed_words = context.document.parsed_sentences.get(sentence.sentence_index, [])
    lowered_text = sentence.text.lower()
    positions = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.POSITION})
    persons = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.PERSON})

    attributed: list[ResolvedRoleAttribution] = []
    for role in positions:
        # Precision: ignore very generic roles if they don't have enough context
        generic_roles = {"prezes", "dyrektor", "kierownik", "członek", "pracownik"}
        if role.normalized_name.lower() in generic_roles:
            # Check for linked organization in same sentence
            orgs = context.mention_views_in_sentence(
                sentence.sentence_index, {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            )
            has_org_link = any(
                _supports_descriptive_tail_link(
                    parsed_words, role, org, sentence_start=sentence.start_char
                )
                for org in orgs
            )
            if not (governance_signal or has_org_link):
                continue

        if not supports_person_role_link(
            parsed_words=parsed_words,
            sentence_text=sentence.text,
            person=person,
            role=role,
            sentence_persons=persons,
            sentence_start=sentence.start_char,
        ):
            continue
        score = _political_office_score(
            parsed_words,
            lowered_text,
            persons,
            person,
            role,
            sentence_start=sentence.start_char,
            governance_signal=governance_signal,
        )
        if score is None:
            continue
        attributed.append(ResolvedRoleAttribution(person=person, role=role, score=score))
    return attributed


def resolve_candidacy_score(
    context: ExtractionContext,
    sentence: SentenceFragment,
    person: ClusterMentionView,
) -> SecondaryFactScore | None:
    if person.is_proxy_person:
        return None
    parsed_words = context.document.parsed_sentences.get(sentence.sentence_index, [])
    lowered_text = sentence.text.lower()
    lemmas = {word.lemma for word in parsed_words}
    if not (
        OFFICE_CANDIDACY_LEMMAS.intersection(lemmas)
        or "kandydat" in lowered_text
        or "wybory" in lowered_text
    ):
        return None
    governing_words = [
        word
        for word in parsed_words
        if word.lemma in OFFICE_CANDIDACY_LEMMAS or word.lemma == "kandydat"
    ]
    if "wybory" not in lowered_text and "kandydat" not in lowered_text:
        return None
    if any(
        abs(person.start_char - (sentence.start_char + word.start)) <= 28
        for word in governing_words
    ):
        return _score(0.72, "dependency_edge", "same_sentence", "candidacy")
    return _score(0.55, "same_sentence", "same_sentence", "election_context")


def resolve_public_employment_attribution(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
    *,
    config: PipelineConfig,
) -> ResolvedPublicEmploymentAttribution | None:
    employer = _resolve_public_employment_employer(context, sentence, clause, config=config)
    employee = _resolve_public_employment_employee(context, sentence, clause)
    if employer is None or employee is None:
        return None
    role_cluster = _resolve_public_employment_role_cluster(context, sentence, clause, employee)
    return ResolvedPublicEmploymentAttribution(
        employee=employee,
        employer=employer,
        role_cluster=role_cluster,
    )


def _party_membership_score(
    parsed_words: list[ParsedWord],
    # Original sentence text for token/dependency-level heuristics.
    sentence_text: str,
    # Lowercased sentence reused for substring/window checks.
    lowered_text: str,
    person: ClusterMentionView,
    party: ClusterMentionView,
    *,
    sentence_start: int = 0,
    governance_signal: bool,
) -> SecondaryFactScore | None:
    syntactic_signal = party_syntactic_signal(
        parsed_words=parsed_words,
        sentence_text=sentence_text,
        lowered_text=lowered_text,
        person=person,
        party=party,
        sentence_start=sentence_start,
    )
    distance = abs(person.start_char - party.start_char)

    if syntactic_signal == "syntactic_direct":
        return _score(0.85, syntactic_signal, "same_sentence", "direct_party_edge")
    if syntactic_signal == "appositive_context":
        return _score(0.78, syntactic_signal, "same_sentence", "party_apposition")
    if distance <= 40 and party_context_window_supports(
        parsed_words=parsed_words,
        lowered_text=lowered_text,
        person=person,
        party=party,
        sentence_start=sentence_start,
    ):
        return _score(
            0.55 - (0.1 if governance_signal else 0.0),
            "same_sentence",
            "same_sentence",
            "near_party_context",
        )
    return None


def _political_office_score(
    parsed_words: list[ParsedWord],
    lowered_text: str,
    persons: list[ClusterMentionView],
    person: ClusterMentionView,
    role: ClusterMentionView,
    *,
    sentence_start: int = 0,
    governance_signal: bool,
) -> SecondaryFactScore | None:
    syntactic_signal = person_role_syntactic_signal(
        parsed_words=parsed_words,
        lowered_text=lowered_text,
        person=person,
        role=role,
        sentence_persons=persons,
        sentence_start=sentence_start,
    )
    distance = abs(person.start_char - role.start_char)

    if syntactic_signal == "syntactic_direct":
        confidence = 0.85
        if governance_signal:
            confidence -= 0.08
        return _score(confidence, syntactic_signal, "same_sentence", "direct_office_role")
    if syntactic_signal == "appositive_context":
        confidence = 0.78
        if governance_signal:
            confidence -= 0.08
        return _score(confidence, syntactic_signal, "same_sentence", "office_apposition")
    if distance <= 20 and not governance_signal:
        return _score(0.51, "same_sentence", "same_sentence", "near_title")
    return None


def _resolve_public_employment_employer(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
    *,
    config: PipelineConfig,
) -> ClusterMentionView | None:
    # 1. Look in the current sentence
    sentence_views = context.mention_views_in_sentence(
        sentence.sentence_index, {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
    )
    current = [
        view
        for view in sentence_views
        if _is_public_employer_cluster(view.cluster) and not _is_party_cluster(view.cluster, config)
    ]
    if current:
        return min(current, key=lambda view: abs(view.start_char - clause.start_char))

    # 2. Look in the paragraph context (proximity within 2 sentences)
    paragraph_views = context.mention_views_in_paragraph(
        sentence.paragraph_index, {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
    )
    adjacent = [
        view
        for view in paragraph_views
        if _is_public_employer_cluster(view.cluster)
        and not _is_party_cluster(view.cluster, config)
        and abs(view.sentence_index - sentence.sentence_index) <= 2
    ]
    if adjacent:
        return min(adjacent, key=lambda view: abs(view.sentence_index - sentence.sentence_index))

    # 3. Document-level fallback
    fallback_clusters = _document_level_employer_candidates(context.document, clause, config=config)
    if fallback_clusters:
        # Use a sentinel view for document-level fallback
        from pipeline.domains.kinship import _cluster_to_view

        best_cluster = min(
            fallback_clusters,
            key=lambda cluster: _cluster_clause_distance(cluster, clause),
        )
        return _cluster_to_view(best_cluster)

    return None


def _resolve_public_employment_employee(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
) -> ClusterMentionView | None:
    patient = _employment_patient_view(context, sentence, clause)
    if patient is not None:
        return patient
    subject = _subject_view(context, sentence, clause)
    if subject is not None:
        # Check if subject is an anchor for a proxy person
        proxy_view = _proxy_view_for_anchor(context, sentence, clause, subject)
        return proxy_view or subject

    # Fallback: nearest person in sentence
    persons = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.PERSON})
    if persons:
        return min(persons, key=lambda view: abs(view.start_char - clause.start_char))

    return None


def _resolve_public_employment_role_cluster(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
    employee: ClusterMentionView,
) -> ClusterMentionView | None:
    roles = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.POSITION})
    if not roles:
        return None

    return min(roles, key=lambda view: abs(view.start_char - employee.start_char))


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
        if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        and _is_public_employer_cluster(cluster)
        and not _is_party_cluster(cluster, config)
        and any(
            marker in cluster.normalized_name.casefold()
            for marker in ("urząd gmin", "gmin", "starostw", "powiatow")
        )
    ]


def _employment_patient_view(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
) -> ClusterMentionView | None:
    parsed_words = context.document.parsed_sentences.get(sentence.sentence_index, [])
    for trigger_word in [word for word in parsed_words if word.lemma.casefold() == "zatrudnić"]:
        object_words = [
            word
            for word in parsed_words
            if word.head == trigger_word.index
            and (word.deprel in {"obj", "iobj"} or word.deprel.startswith("nsubj:pass"))
        ]
        for object_word in object_words:
            view = _person_view_overlapping_word(context, sentence, object_word)
            if view is not None:
                return view
            view = _person_view_in_subtree(context, sentence, object_word.index)
            if view is not None:
                return view
            if object_word.lemma.casefold() in KINSHIP_LEMMAS:
                return _nearest_proxy_view(context, sentence, clause, object_word.start)
    return None


def _subject_view(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
) -> ClusterMentionView | None:
    parsed_words = context.document.parsed_sentences.get(sentence.sentence_index, [])
    for word in [word for word in parsed_words if word.deprel.startswith("nsubj")]:
        view = _person_view_overlapping_word(context, sentence, word)
        if view is not None:
            return view
        view = _person_view_in_subtree(context, sentence, word.index)
        if view is not None:
            return view
    return None


def _person_view_in_subtree(
    context: ExtractionContext,
    sentence: SentenceFragment,
    head_index: int,
    *,
    seen: set[int] | None = None,
) -> ClusterMentionView | None:
    if seen is None:
        seen = set()
    if head_index in seen:
        return None
    seen.add(head_index)
    parsed_words = context.document.parsed_sentences.get(sentence.sentence_index, [])
    for child in parsed_words:
        if child.head != head_index:
            continue
        view = _person_view_overlapping_word(context, sentence, child)
        if view is not None:
            return view
        descendant = _person_view_in_subtree(context, sentence, child.index, seen=seen)
        if descendant is not None:
            return descendant
    return None


def _person_view_overlapping_word(
    context: ExtractionContext,
    sentence: SentenceFragment,
    word: ParsedWord,
) -> ClusterMentionView | None:
    person_views = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.PERSON})
    for view in person_views:
        if view.start_char <= sentence.start_char + word.start < view.end_char:
            return view
    return None


def _nearest_proxy_view(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
    local_offset: int,
) -> ClusterMentionView | None:
    person_views = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.PERSON})
    proxies = [view for view in person_views if view.is_proxy_person]
    if not proxies:
        return None
    abs_offset = sentence.start_char + local_offset
    return min(proxies, key=lambda view: abs(view.start_char - abs_offset))


def _proxy_view_for_anchor(
    context: ExtractionContext,
    sentence: SentenceFragment,
    clause: ClauseUnit,
    subject: ClusterMentionView,
) -> ClusterMentionView | None:
    person_views = context.mention_views_in_sentence(sentence.sentence_index, {EntityType.PERSON})
    subject_entity_ids = {
        mention.entity_id for mention in subject.cluster.mentions if mention.entity_id
    }
    return next(
        (
            view
            for view in person_views
            if view.is_proxy_person and view.cluster.proxy_anchor_entity_id in subject_entity_ids
        ),
        None,
    )


def _is_public_employer_cluster(cluster: EntityCluster) -> bool:
    if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
        return True
    if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
        return True
    return is_public_employer_name(cluster.normalized_name.casefold())


def _is_party_cluster(cluster: EntityCluster, config: PipelineConfig) -> bool:
    return is_party_like_name(cluster.normalized_name, config)


def _cluster_clause_distance(cluster: EntityCluster, clause: ClauseUnit) -> int:
    return min(
        (
            abs(mention.start_char - clause.start_char)
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
