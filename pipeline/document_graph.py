from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.domain_types import (
    ClusterID,
    EntityID,
    EntityType,
    KinshipDetail,
    MentionID,
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


@dataclass(slots=True)
class DocumentGraph:
    document: ArticleDocument
    entities_by_id: dict[EntityID, Entity] = field(init=False)
    mentions_by_id: dict[MentionID, Mention] = field(init=False)
    mentions_by_entity_id: dict[EntityID, list[Mention]] = field(init=False)

    def __post_init__(self) -> None:
        self.entities_by_id = {entity.entity_id: entity for entity in self.document.entities}
        self.mentions_by_id = {mention.mention_id: mention for mention in self.document.mentions}
        self.mentions_by_entity_id = {}
        for entity in self.document.entities:
            self.mentions_by_entity_id[entity.entity_id] = [
                self.mentions_by_id[mention_id]
                for mention_id in entity.mention_ids
                if mention_id in self.mentions_by_id
            ]

    def entity_by_id(self, entity_id: EntityID) -> Entity | None:
        return self.entities_by_id.get(entity_id)

    def mentions_for_entity(self, entity_id: EntityID) -> list[Mention]:
        return list(self.mentions_by_entity_id.get(entity_id, []))


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
    seen: set[MentionID] = set()
    for mention in document.mentions:
        if mention.sentence_index != clause.sentence_index:
            continue
        if not (clause.start_char <= mention.start_char and mention.end_char <= clause.end_char):
            continue
        if mention.mention_id in seen:
            continue
        seen.add(mention.mention_id)
        mentions.append(mention)
    return mentions


def entity_by_id(document: ArticleDocument, entity_id: EntityID) -> Entity | None:
    return next((entity for entity in document.entities if entity.entity_id == entity_id), None)


def mentions_for_entity(document: ArticleDocument, entity_id: EntityID) -> list[Mention]:
    entity = entity_by_id(document, entity_id)
    if entity is None:
        return []
    if not entity.mention_ids:
        return [mention for mention in document.mentions if mention.entity_id == entity_id]
    mentions_by_id = {mention.mention_id: mention for mention in document.mentions}
    return [
        mentions_by_id[mention_id]
        for mention_id in entity.mention_ids
        if mention_id in mentions_by_id
    ]


def attach_mention_to_entity(entity: Entity, mention: Mention) -> None:
    if mention.mention_id not in entity.mention_ids:
        entity.mention_ids.append(mention.mention_id)


def sync_entity_mentions(document: ArticleDocument) -> None:
    entities_by_id = {entity.entity_id: entity for entity in document.entities}
    for entity in document.entities:
        entity.mention_ids = []
    for mention in document.mentions:
        if mention.entity_id is None:
            continue
        entity = entities_by_id.get(mention.entity_id)
        if entity is None:
            continue
        attach_mention_to_entity(entity, mention)


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
    mention_record = next(
        (
            mention
            for mention in document.mentions
            if mention.entity_id == entity.entity_id
            and mention.sentence_index == sentence_index
            and mention.start_char == start_char
            and mention.end_char == end_char
            and mention.text == surface
        ),
        None,
    )
    if mention_record is None:
        mention_record = Mention(
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
        document.mentions.append(mention_record)
    else:
        mention_record.normalized_text = normalized_text
        mention_record.paragraph_index = paragraph_index
        mention_record.start_char = start_char
        mention_record.end_char = end_char
        mention_record.entity_id = entity.entity_id
        if mention_record.mention_kind == MentionKind.DERIVED_ENTITY:
            mention_record.entity_type = resolved_type
            mention_record.mention_kind = mention_kind
        elif mention_kind != MentionKind.DERIVED_ENTITY:
            mention_record.entity_type = resolved_type
    attach_mention_to_entity(entity, mention_record)

    target_cluster = cluster or cluster_for_entity(document, entity.entity_id)
    if target_cluster is None:
        target_cluster = EntityCluster(
            cluster_id=cluster_id
            or ClusterID(stable_id("cluster", document.document_id, entity.entity_id)),
            mentions=[mention_record],
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
        target_cluster.mentions.append(mention_record)
    return target_cluster
