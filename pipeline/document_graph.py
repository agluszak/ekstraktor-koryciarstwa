from __future__ import annotations

from pipeline.domain_types import (
    ClusterID,
    EntityID,
    EntityType,
    KinshipDetail,
    MentionKind,
    OrganizationKind,
    ProxyKind,
    RoleKind,
    RoleModifier,
)
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    Mention,
    SentenceFragment,
)
from pipeline.utils import stable_id


def refresh_clause_mentions(document: ArticleDocument) -> None:
    sentences_by_index = {sentence.sentence_index: sentence for sentence in document.sentences}

    for clause in document.clause_units:
        clause.cluster_mentions = clause_mentions(document, clause)
        sentence = sentences_by_index.get(clause.sentence_index)
        clause.mention_roles = {
            mention.text: role
            for mention in clause.cluster_mentions
            if (role := mention_dependency_role(document, sentence, mention)) is not None
        }


def mention_dependency_role(
    document: ArticleDocument,
    sentence: SentenceFragment | None,
    mention: ClusterMention,
) -> str | None:
    if sentence is None:
        return None
    for word in document.parsed_sentences.get(sentence.sentence_index, []):
        abs_start = sentence.start_char + word.start
        if mention.start_char <= abs_start < mention.end_char:
            return word.deprel
    return None


def clause_mentions(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> list[ClusterMention]:
    mentions: list[ClusterMention] = []
    seen: set[tuple[EntityID | None, int, int, str, EntityType]] = set()
    for cluster in document.clusters:
        for mention in cluster.mentions:
            if mention.sentence_index != clause.sentence_index:
                continue
            if not (
                clause.start_char <= mention.start_char and mention.end_char <= clause.end_char
            ):
                continue
            key = (
                mention.entity_id,
                mention.start_char,
                mention.end_char,
                mention.text,
                mention.entity_type,
            )
            if key in seen:
                continue
            seen.add(key)
            mentions.append(mention)
    return mentions


def entity_by_id(document: ArticleDocument, entity_id: EntityID) -> Entity | None:
    return next((entity for entity in document.entities if entity.entity_id == entity_id), None)


def cluster_for_entity(
    document: ArticleDocument,
    entity_id: EntityID,
) -> EntityCluster | None:
    return next(
        (
            cluster
            for cluster in document.clusters
            if cluster.primary_entity_id == entity_id
            or entity_id in cluster.member_entity_ids
            or any(mention.entity_id == entity_id for mention in cluster.mentions)
        ),
        None,
    )


def ensure_entity(
    document: ArticleDocument,
    *,
    entity_id: EntityID,
    entity_type: EntityType,
    canonical_name: str,
    normalized_name: str | None = None,
    aliases: list[str] | None = None,
    evidence: EvidenceSpan | None = None,
    organization_kind: OrganizationKind | None = None,
    role_kind: RoleKind | None = None,
    role_modifier: RoleModifier | None = None,
    is_proxy_person: bool | None = None,
    is_honorific_person_ref: bool | None = None,
    proxy_kind: ProxyKind | None = None,
    kinship_detail: KinshipDetail | None = None,
    proxy_anchor_entity_id: EntityID | None = None,
    lemmas: list[str] | None = None,
) -> Entity:
    entity = entity_by_id(document, entity_id)
    normalized = canonical_name if normalized_name is None else normalized_name

    if entity is None:
        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=normalized,
            aliases=list(aliases or []),
            evidence=[] if evidence is None else [evidence],
            organization_kind=organization_kind,
            is_proxy_person=False if is_proxy_person is None else is_proxy_person,
            is_honorific_person_ref=(
                False if is_honorific_person_ref is None else is_honorific_person_ref
            ),
            proxy_kind=proxy_kind,
            kinship_detail=kinship_detail,
            proxy_anchor_entity_id=proxy_anchor_entity_id,
            role_kind=role_kind,
            role_modifier=role_modifier,
            lemmas=[] if lemmas is None else list(lemmas),
        )
        document.entities.append(entity)
        return entity

    entity.entity_type = entity_type
    entity.canonical_name = canonical_name
    entity.normalized_name = normalized
    for alias in aliases or []:
        if alias not in entity.aliases:
            entity.aliases.append(alias)
    if evidence is not None and not any(
        span.sentence_index == evidence.sentence_index
        and span.start_char == evidence.start_char
        and span.end_char == evidence.end_char
        for span in entity.evidence
    ):
        entity.evidence.append(evidence)
    if organization_kind is not None:
        entity.organization_kind = organization_kind
    if role_kind is not None:
        entity.role_kind = role_kind
    if role_modifier is not None:
        entity.role_modifier = role_modifier
    if is_proxy_person is not None:
        entity.is_proxy_person = is_proxy_person
    if is_honorific_person_ref is not None:
        entity.is_honorific_person_ref = is_honorific_person_ref
    if proxy_kind is not None:
        entity.proxy_kind = proxy_kind
    if kinship_detail is not None:
        entity.kinship_detail = kinship_detail
    if proxy_anchor_entity_id is not None:
        entity.proxy_anchor_entity_id = proxy_anchor_entity_id
    for lemma in lemmas or []:
        if lemma not in entity.lemmas:
            entity.lemmas.append(lemma)
    return entity


def ensure_entity_view(
    document: ArticleDocument,
    *,
    entity: Entity,
    surface: str,
    normalized_text: str,
    sentence_index: int,
    paragraph_index: int,
    start_char: int,
    end_char: int,
    mention_kind: MentionKind = MentionKind.DERIVED_ENTITY,
    entity_type: EntityType | None = None,
    cluster: EntityCluster | None = None,
    cluster_id: ClusterID | None = None,
) -> EntityCluster:
    evidence = EvidenceSpan(
        text=surface,
        sentence_index=sentence_index,
        paragraph_index=paragraph_index,
        start_char=start_char,
        end_char=end_char,
    )
    if not any(
        span.sentence_index == sentence_index
        and span.start_char == start_char
        and span.end_char == end_char
        for span in entity.evidence
    ):
        entity.evidence.append(evidence)
    if surface not in entity.aliases:
        entity.aliases.append(surface)

    resolved_type = entity.entity_type if entity_type is None else entity_type
    if not any(
        mention.entity_id == entity.entity_id
        and mention.sentence_index == sentence_index
        and mention.start_char == start_char
        and mention.end_char == end_char
        and mention.text == surface
        for mention in document.mentions
    ):
        document.mentions.append(
            Mention(
                text=surface,
                normalized_text=normalized_text,
                entity_type=resolved_type,
                mention_kind=mention_kind,
                sentence_index=sentence_index,
                paragraph_index=paragraph_index,
                start_char=start_char,
                end_char=end_char,
                entity_id=entity.entity_id,
            )
        )

    cluster_mention = ClusterMention(
        text=surface,
        entity_type=resolved_type,
        sentence_index=sentence_index,
        paragraph_index=paragraph_index,
        start_char=start_char,
        end_char=end_char,
        mention_kind=mention_kind,
        entity_id=entity.entity_id,
    )
    target_cluster = cluster or cluster_for_entity(document, entity.entity_id)
    if target_cluster is None:
        target_cluster = EntityCluster(
            cluster_id=cluster_id
            or ClusterID(stable_id("cluster", document.document_id, entity.entity_id)),
            mentions=[cluster_mention],
            primary_entity_id=entity.entity_id,
        )
        document.clusters.append(target_cluster)
        return target_cluster

    if target_cluster.primary_entity_id is None:
        target_cluster.primary_entity_id = entity.entity_id
    elif (
        target_cluster.primary_entity_id != entity.entity_id
        and target_cluster.primary_entity_id not in target_cluster.member_entity_ids
    ):
        target_cluster.member_entity_ids.append(target_cluster.primary_entity_id)
    if (
        target_cluster.primary_entity_id != entity.entity_id
        and entity.entity_id not in target_cluster.member_entity_ids
    ):
        target_cluster.member_entity_ids.append(entity.entity_id)
    if not any(
        mention.entity_id == entity.entity_id
        and mention.sentence_index == sentence_index
        and mention.start_char == start_char
        and mention.end_char == end_char
        and mention.text == surface
        for mention in target_cluster.mentions
    ):
        target_cluster.mentions.append(cluster_mention)
    return target_cluster
