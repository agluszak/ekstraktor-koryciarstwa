from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.catalogues import POLITICAL_PARTY_NAMES
from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter, EmittedEvent
from pipeline_v2.entity_classification import entity_has_lexical_context_proposal
from pipeline_v2.event_frames import EventFrameBuilder
from pipeline_v2.governance.constants import (
    APPOINTMENT_LEMMAS,
    DISMISSAL_LEMMAS,
    FORMER_DESCRIPTOR_LEMMAS,
    GENERIC_APPOINTMENT_LEMMAS,
    ORG_LIKE_PERSON_HINT_TOKENS,
    PERSON_DESCRIPTOR_LEMMAS,
    POLITICAL_ROLE_LEMMAS,
    ROLE_TITLE_ONLY_PERSON_LEMMAS,
)
from pipeline_v2.governance.heuristics import (
    _heuristics,
    augment_local_roles_with_person_titles,
    clause_end_after_char,
    entity_source_sentence_id,
    expand_conjunct_people,
    first_holding_trigger,
    first_token_for_entity,
    has_governance_role,
    has_singular_person_role,
    office_person_for_role,
    previous_sentence_holding_people,
    role_has_former_descriptor,
    role_is_embedded_under_other_role,
    sentence_has_holding_predicate_title,
    sentence_is_first_person_departure_report,
    sentence_lemmas,
)
from pipeline_v2.ids import EntityCandidateId, EvidenceId, ProducerId
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    AppointerContextSignal,
    EntityKind,
    EntityTag,
    EventRole,
    FactKind,
    GroundingKind,
    ImplausiblePersonBindingSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    MentionKind,
    PartyOrganizationSignal,
    PublicRoleDomain,
    PublicRoleDomainSignal,
    Signal,
    WeakSyntacticBindingSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


@dataclass(frozen=True, slots=True)
class _GovernanceCandidates:
    """Role candidates collected for one sentence, shared across all fact kinds."""

    people: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]
    organizations: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]
    roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]


def collect_governance_candidates(
    document: ArticleDocument,
    sentence: Sentence,
) -> _GovernanceCandidates:
    from pipeline_v2.governance.heuristics import restrict_roles_to_clause

    retriever = SentenceEntityRetriever(document.store)
    entities = retriever.entities_for_sentence(sentence)
    window_entities = retriever.entities_for_sentence_window(sentence, before=1, after=0)
    organization_window_entities = window_entities
    if first_holding_trigger(document, sentence) is not None:
        organization_window_entities = retriever.entities_for_sentence_window(
            sentence,
            before=2,
            after=0,
        )
    elif sentence_lemmas(document, sentence) & APPOINTMENT_LEMMAS and sentence_lemmas(
        document, sentence
    ) & (FORMER_DESCRIPTOR_LEMMAS | {"dotychczasowy"}):
        organization_window_entities = retriever.entities_for_sentence_window(
            sentence,
            before=2,
            after=0,
        )

    raw_people = select_entities(
        document,
        sentence,
        entities,
        window_entities,
        EntityKind.PERSON,
        local_signal=LocalPersonSignal(),
        window_signal=WindowPersonSignal(),
    )
    if not any(entity.kind is EntityKind.PERSON for entity in entities):
        if first_holding_trigger(document, sentence) is not None:
            seen_ids = {person.id for person, _ in raw_people}
            previous_people = previous_sentence_holding_people(document, sentence)
            raw_people = raw_people + tuple(
                (person, (WindowPersonSignal(),))
                for person in previous_people
                if person.id not in seen_ids
            )

    roles = select_entities(
        document,
        sentence,
        entities,
        window_entities,
        EntityKind.ROLE,
        local_signal=LocalRoleSignal(),
        window_signal=WindowRoleSignal(),
    )
    if sentence_lemmas(document, sentence) & DISMISSAL_LEMMAS or (
        first_holding_trigger(document, sentence) is not None
    ):
        roles = augment_local_roles_with_person_titles(
            document=document,
            sentence=sentence,
            local_entities=entities,
            roles=roles,
        )

    if not raw_people:
        proxy = None
        if not sentence_is_first_person_departure_report(document, sentence):
            proxy = synthesize_proxy_person(document, sentence, roles)
        if proxy is not None:
            raw_people = (proxy,)
    if not raw_people:
        return _GovernanceCandidates(people=(), organizations=(), roles=())

    raw_people = expand_conjunct_people(document, sentence, raw_people, entities)

    # Apply zasiadać / holding-clause sentence-level role restriction.
    roles = restrict_roles_to_clause(document, sentence, roles)

    local_people_ids = frozenset(e.id for e in entities if e.kind == EntityKind.PERSON)
    syntax = SyntaxView(document.store)

    holding_trigger = first_holding_trigger(document, sentence)
    holding_clause_end_char = (
        clause_end_after_char(document, sentence, holding_trigger.start_char)
        if holding_trigger is not None and holding_trigger.lemma in {"być", "pozostawać"}
        else None
    )
    has_clause_local_post_trigger_person = (
        holding_trigger is not None
        and holding_clause_end_char is not None
        and any(
            entity_source_sentence_id(document, person.id) == sentence.id
            and holding_trigger.start_char < person.start_char < holding_clause_end_char
            for person, _ in raw_people
        )
    )
    trigger_token = syntax.first_token_with_lemmas(sentence, APPOINTMENT_LEMMAS)

    # Build per-person signal lists.
    people_out: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
    for person, p_signals in raw_people:
        extra: list[Signal] = []
        if is_implausible_person_candidate(document, person.id):
            extra.append(ImplausiblePersonBindingSignal())

        person_is_window_only = person.id not in local_people_ids

        if (
            has_clause_local_post_trigger_person
            and holding_trigger is not None
            and holding_clause_end_char is not None
            and (
                entity_source_sentence_id(document, person.id) != sentence.id
                or not (holding_trigger.start_char < person.start_char < holding_clause_end_char)
            )
        ):
            extra.append(
                WeakSyntacticBindingSignal(reason="window person competes with clause-local holder")
            )

        if trigger_token is not None and not person_is_window_only:
            relation = syntax.dependency_relation(
                sentence=sentence,
                trigger_token_id=trigger_token.id,
                entity_id=person.id,
            )
            if relation is not None and syntax.is_subject_relation(relation):
                trigger_lemmas = {analysis.lemma for analysis in trigger_token.morph}
                if not syntax.is_passive_sentence(sentence, trigger_token.id) and not (
                    trigger_lemmas & GENERIC_APPOINTMENT_LEMMAS
                ):
                    extra.append(
                        WeakSyntacticBindingSignal(reason="person is active subject of cue")
                    )
                    appointer_role = _heuristics._public_office_role_near_person(
                        document,
                        sentence,
                        person.id,
                    )
                    if appointer_role is not None:
                        extra.append(AppointerContextSignal(role_lemma=appointer_role))

            trigger_lemmas = {analysis.lemma for analysis in trigger_token.morph}
            re_relation = syntax.dependency_relation(
                sentence=sentence,
                trigger_token_id=trigger_token.id,
                entity_id=person.id,
            )
            generic_trigger_subject = bool(trigger_lemmas & GENERIC_APPOINTMENT_LEMMAS) and (
                re_relation is not None
                and syntax.is_subject_relation(re_relation)
                or _heuristics._person_is_adjacent_before_trigger(
                    document=document,
                    sentence=sentence,
                    person_id=person.id,
                    trigger_start_char=trigger_token.span.start_char,
                )
            )
            if not generic_trigger_subject and is_background_local_person(
                document,
                sentence,
                person,
                entities,
                trigger_token.span.start_char,
            ):
                extra.append(
                    WeakSyntacticBindingSignal(
                        reason="person appears in background context before cue"
                    )
                )

        people_out.append((person, tuple(p_signals) + tuple(extra)))

    organizations_raw = select_entities(
        document,
        sentence,
        entities,
        organization_window_entities,
        EntityKind.ORGANIZATION,
        local_signal=LocalOrganizationSignal(),
        window_signal=WindowOrganizationSignal(),
        merge_window_with_local=True,
    )
    if sentence_has_holding_predicate_title(document, sentence) and not any(
        entity.kind is EntityKind.ORGANIZATION for entity in entities
    ):
        organizations_raw = tuple(
            (
                org,
                (LocalOrganizationSignal(), WindowOrganizationSignal())
                if org_signals == (WindowOrganizationSignal(),)
                else org_signals,
            )
            for org, org_signals in organizations_raw
        )
    prior_role_org_ids = _heuristics._prior_role_org_ids(document, sentence)
    orgs_out: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
    for org, org_signals in organizations_raw:
        sigs: list[Signal] = list(org_signals)
        if is_party_like_organization(document, org.id):
            sigs.append(PartyOrganizationSignal())
        if org.id in prior_role_org_ids:
            sigs.append(WeakSyntacticBindingSignal(reason="organization in prior-role descriptor"))
        orgs_out.append((org, tuple(sigs)))

    return _GovernanceCandidates(
        people=tuple(people_out),
        organizations=tuple(orgs_out),
        roles=roles,
    )


def select_entities(
    document: ArticleDocument,
    anchor_sentence: Sentence,
    local_entities: tuple[SentenceEntity, ...],
    window_entities: tuple[SentenceEntity, ...],
    kind: EntityKind,
    *,
    local_signal: Signal,
    window_signal: Signal,
    merge_window_with_local: bool = False,
) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
    local = tuple(entity for entity in local_entities if entity.kind == kind)
    if kind is EntityKind.ORGANIZATION:
        local = tuple(
            entity
            for entity in local
            if not is_implausible_organization_candidate(document, entity.id)
        )
    seen_ids: set[EntityCandidateId] = {entity.id for entity in local}
    local_results: list[tuple[SentenceEntity, tuple[Signal, ...]]] = [
        (entity, (local_signal,)) for entity in local
    ]
    if local and not merge_window_with_local:
        return tuple(local_results)
    # Include window entities not already in local.
    window_results: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
    for entity in window_entities:
        if entity.kind != kind or entity.id in seen_ids:
            continue
        if kind is EntityKind.ORGANIZATION and is_implausible_organization_candidate(
            document, entity.id
        ):
            continue
        entity_min_dist = 999
        for evidence in document.store.evidence_for_entity(entity.id):
            if evidence.sentence_id is None:
                continue
            evidence_sentence = document.store.sentences[evidence.sentence_id]
            if evidence_sentence.paragraph_index != anchor_sentence.paragraph_index:
                continue
            dist = anchor_sentence.sentence_index - evidence_sentence.sentence_index
            if 0 <= dist < entity_min_dist:
                entity_min_dist = dist
        if entity_min_dist < 999:
            window_results.append((entity, (window_signal,)))
    if not local_results and not window_results:
        return ()
    return tuple(local_results + window_results)


def is_implausible_person_candidate(
    document: ArticleDocument,
    entity_id: EntityCandidateId,
) -> bool:
    candidate = document.store.entity_candidates.get(entity_id)
    if candidate is None:
        return False
    canonical_hint = (candidate.canonical_hint or "").casefold()
    hint_tokens = frozenset(canonical_hint.replace(".", " ").split())
    if hint_tokens & ORG_LIKE_PERSON_HINT_TOKENS:
        return True
    if (
        candidate.grounding is GroundingKind.OBSERVED
        and hint_tokens
        and person_candidate_is_role_title_only(document, entity_id)
    ):
        return True
    if any(
        token.isupper() and len(token) >= 2
        for token in (candidate.canonical_hint or "").split()[1:]
    ):
        return True
    if candidate.grounding is not GroundingKind.INFERRED:
        return False
    for mention in document.store.candidate_mentions(entity_id):
        if mention.kind is not MentionKind.DESCRIPTOR_NOUN_PHRASE:
            continue
        tokens = document.store.tokens_for_mention(mention.id)
        if not tokens:
            continue
        if all(any(analysis.number == "pl" for analysis in token.morph) for token in tokens):
            return True
    return False


def person_candidate_is_role_title_only(
    document: ArticleDocument,
    entity_id: EntityCandidateId,
) -> bool:
    lemmas: set[str] = set()
    for mention in document.store.candidate_mentions(entity_id):
        for token in document.store.tokens_for_mention(mention.id):
            lemmas.update(analysis.lemma for analysis in token.morph)
    return bool(lemmas) and lemmas <= ROLE_TITLE_ONLY_PERSON_LEMMAS


def is_implausible_organization_candidate(
    document: ArticleDocument,
    entity_id: EntityCandidateId,
) -> bool:
    candidate = document.store.entity_candidates.get(entity_id)
    if candidate is None:
        return False
    hint = (candidate.canonical_hint or "").strip()
    if not hint:
        return False
    hint_tokens = hint.split()
    if (
        len(hint_tokens) == 1
        and hint_tokens[0].islower()
        and not entity_has_lexical_context_proposal(
            document,
            entity_id,
            EntityTag.PUBLIC_INSTITUTION,
        )
        and not entity_has_lexical_context_proposal(
            document,
            entity_id,
            EntityTag.MEDIA_OUTLET,
        )
    ):
        return True
    return False


def is_party_like_organization(
    document: ArticleDocument,
    entity_id: EntityCandidateId,
) -> bool:
    candidate = document.store.entity_candidates[entity_id]
    canonical_hint = (candidate.canonical_hint or "").casefold()
    if canonical_hint in POLITICAL_PARTY_NAMES:
        return True
    if has_governance_role(document, entity_id):
        return True
    return overlaps_political_party(document, entity_id)


def overlaps_political_party(
    document: ArticleDocument,
    entity_id: EntityCandidateId,
) -> bool:
    organization_evidence = tuple(document.store.evidence_for_entity(entity_id))
    for candidate in document.store.candidates_by_kind(EntityKind.POLITICAL_PARTY):
        for party_evidence in document.store.evidence_for_entity(candidate.id):
            for organization_span in organization_evidence:
                if organization_span.sentence_id != party_evidence.sentence_id:
                    continue
                if organization_span.span.end_char <= party_evidence.span.start_char:
                    continue
                if party_evidence.span.end_char <= organization_span.span.start_char:
                    continue
                return True
    return False


def is_political_role(document: ArticleDocument, role_id: EntityCandidateId) -> bool:
    return public_role_domain_for_role(document, role_id) is PublicRoleDomain.POLITICAL_OFFICE


def public_role_domain_for_role(
    document: ArticleDocument,
    role_id: EntityCandidateId,
) -> PublicRoleDomain:
    role_candidate = document.store.entity_candidates[role_id]
    text = (role_candidate.canonical_hint or "").lower()
    lemmas = set()
    for mention_id in role_candidate.mention_ids:
        mention = document.store.mentions[mention_id]
        for token_id in mention.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma.lower())
    if "sekretarz stanu" in text:
        return PublicRoleDomain.POLITICAL_OFFICE
    if bool(POLITICAL_ROLE_LEMMAS & lemmas) or any(
        lemma_word in text for lemma_word in POLITICAL_ROLE_LEMMAS
    ):
        return PublicRoleDomain.POLITICAL_OFFICE
    if "rada nadzorcza" in text or {"rada", "nadzorczy"} <= lemmas:
        return PublicRoleDomain.SUPERVISORY_BOARD
    if {"prezes", "wiceprezes", "zarząd"} & lemmas:
        return PublicRoleDomain.PUBLIC_COMPANY_MANAGEMENT
    if {"dyrektor", "wicedyrektor", "kierownik", "szef", "wiceszef"} & lemmas:
        return PublicRoleDomain.INSTITUTION_MANAGEMENT
    if {"sekretarz", "naczelnik", "skarbnik"} & lemmas:
        return PublicRoleDomain.ADMINISTRATIVE_OFFICE
    return PublicRoleDomain.OTHER_PUBLIC_ROLE


def synthesize_proxy_person(
    document: ArticleDocument,
    sentence: Sentence,
    roles: tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...],
) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
    local_entity_ids = {
        e.id
        for e in document.store.entity_candidates.values()
        if any(
            document.store.evidence.get(m.evidence_id) is not None
            and document.store.evidence[m.evidence_id].sentence_id == sentence.id
            for m in document.store.candidate_mentions(e.id)
        )
    }
    # First, try a singular-person governance-role entity local to the sentence.
    for role_entity, _role_sigs in roles:
        if role_entity.id not in local_entity_ids:
            continue
        if not has_singular_person_role(document, role_entity.id):
            continue
        return proxy_from_role_entity(document, sentence, role_entity)
    # Second, scan tokens for person-descriptor common nouns.
    return proxy_from_descriptor_token(document, sentence)


def proxy_from_role_entity(
    document: ArticleDocument,
    sentence: Sentence,
    role_entity: SentenceEntity,
) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
    role_candidate = document.store.entity_candidates.get(role_entity.id)
    if role_candidate is None or not role_candidate.mention_ids:
        return None
    role_mention = document.store.mentions.get(role_candidate.mention_ids[0])
    if role_mention is None:
        return None
    role_evidence = document.store.evidence.get(role_mention.evidence_id)
    if role_evidence is None:
        return None
    return create_proxy_person_candidate(
        document=document,
        sentence=sentence,
        text=role_mention.text,
        span=role_evidence.span,
        head_lemma=role_mention.head_lemma,
    )


def proxy_from_descriptor_token(
    document: ArticleDocument,
    sentence: Sentence,
) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
    for token_id in sentence.token_ids:
        token = document.store.tokens[token_id]
        token_lemmas = {analysis.lemma for analysis in token.morph}
        if not (token_lemmas & PERSON_DESCRIPTOR_LEMMAS):
            continue
        if any(analysis.number == "pl" for analysis in token.morph if analysis.number is not None):
            continue
        lemma = next(iter(token_lemmas & PERSON_DESCRIPTOR_LEMMAS))
        span = Span(token.span.start_char, token.span.end_char)
        return create_proxy_person_candidate(
            document=document,
            sentence=sentence,
            text=token.text,
            span=span,
            head_lemma=lemma,
        )
    return None


def create_proxy_person_candidate(
    document: ArticleDocument,
    sentence: Sentence,
    *,
    text: str,
    span: Span,
    head_lemma: str | None,
) -> tuple[SentenceEntity, tuple[Signal, ...]] | None:
    evidence_id = document.store.next_evidence_id()
    evidence = EvidenceSpan(
        id=evidence_id,
        text=text,
        span=span,
        sentence_id=sentence.id,
        paragraph_index=sentence.paragraph_index,
        source=ProducerId("governance_candidate_stage_v2"),
    )
    document.store.add_evidence(evidence)
    mention_id = document.store.next_mention_id()
    mention = Mention(
        id=mention_id,
        text=text,
        kind=MentionKind.DESCRIPTOR_NOUN_PHRASE,
        evidence_id=evidence_id,
        sentence_id=sentence.id,
        token_ids=tuple(
            token_id
            for token_id in sentence.token_ids
            if not (
                document.store.tokens[token_id].span.end_char <= span.start_char
                or document.store.tokens[token_id].span.start_char >= span.end_char
            )
        ),
        head_lemma=head_lemma,
    )
    document.store.add_mention(mention)
    candidate_id = document.store.next_entity_candidate_id()
    candidate = EntityCandidate(
        id=candidate_id,
        kind=EntityKind.PERSON,
        grounding=GroundingKind.INFERRED,
        canonical_hint=text,
        mention_ids=(mention_id,),
        source=ProducerId("governance_candidate_stage_v2"),
    )
    document.store.add_entity_candidate(candidate)
    proxy_entity = SentenceEntity(
        id=candidate_id,
        kind=EntityKind.PERSON,
        start_char=span.start_char,
        end_char=span.end_char,
    )
    return (
        proxy_entity,
        (LocalPersonSignal(),),
    )


def is_background_local_person(
    document: ArticleDocument,
    sentence: Sentence,
    person: SentenceEntity,
    entities: tuple[SentenceEntity, ...],
    trigger_start_char: int,
) -> bool:
    if person.end_char >= trigger_start_char:
        return False
    for other in entities:
        if other.kind != EntityKind.PERSON or other.id == person.id:
            continue
        if other.start_char <= trigger_start_char:
            continue
        return True
    return False


def add_public_role_holding_candidates(
    document: ArticleDocument,
    sentence: Sentence,
) -> None:
    if not (sentence_lemmas(document, sentence) & POLITICAL_ROLE_LEMMAS):
        return
    frame_builder = EventFrameBuilder(document.store)
    entities = SentenceEntityRetriever(document.store).entities_for_sentence(sentence)
    people = tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)
    roles = tuple(entity for entity in entities if entity.kind == EntityKind.ROLE)
    if not people or not roles:
        return

    bindings: list[tuple[SentenceEntity, SentenceEntity]] = []
    for role in roles:
        if not is_political_role(document, role.id):
            continue
        if role_has_former_descriptor(document, sentence, role):
            continue
        if role_is_embedded_under_other_role(document, sentence, role):
            continue
        role_frame = frame_builder.frame_for_trigger(
            sentence,
            first_token_for_entity(document, sentence, role),
        )
        person = office_person_for_role(document, role_frame, role, people)
        if person is not None:
            bindings.append((person, role))

    if not bindings:
        return

    # Standardized EvidenceSpan creation using from_sentence
    evidence = EvidenceSpan.from_sentence(
        evidence_id=document.store.next_evidence_id(),
        sentence=sentence,
        source=ProducerId("governance_candidate_stage_v2"),
    )
    document.store.add_evidence(evidence)
    emitter = DomainEventEmitter(document, ProducerId("governance_candidate_stage_v2"))
    for person, role in bindings:
        event = emitter.event(
            kind=FactKind.PUBLIC_ROLE_HOLDING,
            trigger_evidence_id=evidence.id,
            evidence_ids=(evidence.id,),
            signals=(),
        )
        emitter.bind_entity(
            event=event,
            role=EventRole.PERSON,
            entity_id=person.id,
            evidence_ids=(evidence.id,),
            signals=(LocalPersonSignal(),),
        )
        emitter.bind_entity(
            event=event,
            role=EventRole.ROLE,
            entity_id=role.id,
            evidence_ids=(evidence.id,),
            signals=(LocalRoleSignal(),),
        )
        add_role_domain_bindings(
            document=document,
            emitter=emitter,
            event=event,
            role_bindings={role.id: (LocalRoleSignal(),)},
            evidence_id=evidence.id,
        )


def add_role_domain_bindings(
    document: ArticleDocument,
    emitter: DomainEventEmitter,
    event: EmittedEvent,
    role_bindings: dict[EntityCandidateId, tuple[Signal, ...]],
    evidence_id: EvidenceId,
) -> None:
    for role_id, _sigs in role_bindings.items():
        domain = public_role_domain_for_role(document, role_id)
        if domain is not None:
            emitter.bind_text(
                event=event,
                role=EventRole.ROLE_DOMAIN,
                value=domain.value,
                evidence_ids=(evidence_id,),
                signals=(PublicRoleDomainSignal(domain=domain),),
            )
