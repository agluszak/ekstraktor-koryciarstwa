from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

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
from pipeline.utils import stable_id, unique_preserve_order


@dataclass(slots=True)
class DocumentGraph:
    document: ArticleDocument
    entities_by_id: dict[EntityID, Entity] = field(init=False)
    mentions_by_id: dict[MentionID, Mention] = field(init=False)
    mentions_by_entity_id: dict[EntityID, list[Mention]] = field(init=False)
    clusters_by_id: dict[ClusterID, EntityCluster] = field(init=False)
    clusters_by_entity_id: dict[EntityID, EntityCluster] = field(init=False)
    cluster_list: list[EntityCluster] = field(init=False)

    def __post_init__(self) -> None:
        self.entities_by_id = {entity.entity_id: entity for entity in self.document.entities}
        self.mentions_by_id = {mention.mention_id: mention for mention in self.document.mentions}
        self.mentions_by_entity_id = {entity.entity_id: [] for entity in self.document.entities}
        seen_mentions_by_entity: dict[EntityID, set[MentionID]] = {
            entity.entity_id: set() for entity in self.document.entities
        }
        for entity in self.document.entities:
            for mention_id in entity.mention_ids:
                mention = self.mentions_by_id.get(mention_id)
                if (
                    mention is None
                    or mention.mention_id in seen_mentions_by_entity[entity.entity_id]
                ):
                    continue
                self.mentions_by_entity_id[entity.entity_id].append(mention)
                seen_mentions_by_entity[entity.entity_id].add(mention.mention_id)
        for mention in self.document.mentions:
            if mention.entity_id is None or mention.entity_id not in self.mentions_by_entity_id:
                continue
            seen_mentions = seen_mentions_by_entity[mention.entity_id]
            if mention.mention_id in seen_mentions:
                continue
            self.mentions_by_entity_id[mention.entity_id].append(mention)
            seen_mentions.add(mention.mention_id)

        self.cluster_list = []
        self.clusters_by_id = {}
        self.clusters_by_entity_id = {}
        for entity in self.document.entities:
            cluster = EntityCluster(
                cluster_id=_entity_cluster_id(self.document, entity.entity_id),
                mentions=list(self.mentions_by_entity_id.get(entity.entity_id, [])),
                primary_entity_id=entity.entity_id,
            )
            self.cluster_list.append(cluster)
            self.clusters_by_id[cluster.cluster_id] = cluster
            self.clusters_by_entity_id[entity.entity_id] = cluster

        unlinked_clusters: dict[ClusterID, EntityCluster] = {}
        for mention in self.document.mentions:
            if mention.entity_id is not None:
                cluster = self.clusters_by_entity_id.get(mention.entity_id)
                if cluster is None:
                    cluster = EntityCluster(
                        cluster_id=_entity_cluster_id(self.document, mention.entity_id),
                        mentions=[],
                        primary_entity_id=mention.entity_id,
                    )
                    self.cluster_list.append(cluster)
                    self.clusters_by_id[cluster.cluster_id] = cluster
                    self.clusters_by_entity_id[mention.entity_id] = cluster
                if all(existing.mention_id != mention.mention_id for existing in cluster.mentions):
                    cluster.mentions.append(mention)
                continue
            cluster_id = _mention_cluster_id(self.document, mention)
            cluster = unlinked_clusters.get(cluster_id)
            if cluster is None:
                cluster = EntityCluster(cluster_id=cluster_id, mentions=[mention])
                unlinked_clusters[cluster_id] = cluster
                self.cluster_list.append(cluster)
                self.clusters_by_id[cluster_id] = cluster
            else:
                cluster.mentions.append(mention)

    def entity_by_id(self, entity_id: EntityID) -> Entity | None:
        return self.entities_by_id.get(entity_id)

    def mentions_for_entity(self, entity_id: EntityID) -> list[Mention]:
        return list(self.mentions_by_entity_id.get(entity_id, []))

    def clusters(self) -> list[EntityCluster]:
        return list(self.cluster_list)

    def cluster_by_id(self, cluster_id: ClusterID | None) -> EntityCluster | None:
        if cluster_id is None:
            return None
        return self.clusters_by_id.get(cluster_id)

    def cluster_for_entity(self, entity_id: EntityID) -> EntityCluster | None:
        return self.clusters_by_entity_id.get(entity_id)


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


def derived_clusters(document: ArticleDocument) -> list[EntityCluster]:
    return DocumentGraph(document).clusters()


def cluster_by_id(document: ArticleDocument, cluster_id: ClusterID | None) -> EntityCluster | None:
    return DocumentGraph(document).cluster_by_id(cluster_id)


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
    return DocumentGraph(document).cluster_for_entity(entity_id)


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
    graph = DocumentGraph(document)
    target_cluster = graph.cluster_for_entity(entity.entity_id)
    if target_cluster is not None:
        return target_cluster
    return EntityCluster(
        cluster_id=_entity_cluster_id(document, entity.entity_id),
        mentions=[mention_record],
        primary_entity_id=entity.entity_id,
    )


def merge_entities(
    document: ArticleDocument,
    remap: dict[EntityID, EntityID],
    *,
    merge_fn: Callable[[Entity, Entity], None] | None = None,
) -> None:
    canonical_remap = _canonicalize_entity_remap(remap)
    if not canonical_remap:
        return

    merge_impl = merge_fn or _merge_entity
    entities = {entity.entity_id: entity for entity in document.entities}
    for source_id, target_id in canonical_remap.items():
        source = entities.get(source_id)
        target = entities.get(target_id)
        if source is None or target is None or source.entity_id == target.entity_id:
            continue
        merge_impl(target, source)

    _remap_mentions(document, canonical_remap, entities)
    _remap_facts(document, canonical_remap)
    removed_entity_ids = set(canonical_remap.keys())
    document.entities = [
        entity for entity in document.entities if entity.entity_id not in removed_entity_ids
    ]
    sync_entity_mentions(document)


def _entity_cluster_id(document: ArticleDocument, entity_id: EntityID) -> ClusterID:
    return ClusterID(stable_id("cluster", document.document_id, entity_id))


def _mention_cluster_id(document: ArticleDocument, mention: Mention) -> ClusterID:
    return ClusterID(
        stable_id(
            "cluster-mention",
            document.document_id,
            mention.entity_type.value,
            mention.mention_kind.value,
            str(mention.sentence_index),
            str(mention.paragraph_index),
            str(mention.start_char),
            str(mention.end_char),
            mention.normalized_text or mention.text,
        )
    )


def _canonicalize_entity_remap(remap: dict[EntityID, EntityID]) -> dict[EntityID, EntityID]:
    canonical: dict[EntityID, EntityID] = {}
    for source_id, target_id in remap.items():
        if source_id == target_id:
            continue
        resolved = target_id
        seen: set[EntityID] = {source_id}
        while resolved in remap and resolved not in seen:
            seen.add(resolved)
            next_target = remap[resolved]
            if next_target == resolved:
                break
            resolved = next_target
        if source_id != resolved:
            canonical[source_id] = resolved
    return canonical


def _merge_entity(target: Entity, source: Entity) -> None:
    target.aliases = unique_preserve_order(
        [*target.aliases, target.canonical_name, source.canonical_name, *source.aliases]
    )
    target.evidence.extend(
        evidence
        for evidence in source.evidence
        if not any(
            current.text == evidence.text
            and current.sentence_index == evidence.sentence_index
            and current.paragraph_index == evidence.paragraph_index
            and current.start_char == evidence.start_char
            and current.end_char == evidence.end_char
            for current in target.evidence
        )
    )
    merged_mention_ids: list[MentionID] = list(target.mention_ids)
    for mention_id in source.mention_ids:
        if mention_id not in merged_mention_ids:
            merged_mention_ids.append(mention_id)
    target.mention_ids = merged_mention_ids
    target.lemmas = unique_preserve_order([*target.lemmas, *source.lemmas])
    target.registry_id = target.registry_id or source.registry_id
    target.organization_kind = target.organization_kind or source.organization_kind
    target.is_proxy_person = target.is_proxy_person or source.is_proxy_person
    target.is_honorific_person_ref = (
        target.is_honorific_person_ref or source.is_honorific_person_ref
    )
    target.proxy_kind = target.proxy_kind or source.proxy_kind
    target.kinship_detail = target.kinship_detail or source.kinship_detail
    target.proxy_anchor_entity_id = target.proxy_anchor_entity_id or source.proxy_anchor_entity_id
    target.role_kind = target.role_kind or source.role_kind
    target.role_modifier = target.role_modifier or source.role_modifier


def _remap_mentions(
    document: ArticleDocument,
    remap: dict[EntityID, EntityID],
    entities_before_merge: dict[EntityID, Entity],
) -> None:
    deduplicated_mentions: dict[
        tuple[EntityID | None, int, int, int, int, str, str, str],
        Mention,
    ] = {}
    canonical_entities = {entity.entity_id: entity for entity in document.entities}
    for mention in document.mentions:
        if mention.entity_id is not None:
            mention.entity_id = remap.get(mention.entity_id, mention.entity_id)
        target_entity = None
        if mention.entity_id is not None:
            target_entity = canonical_entities.get(mention.entity_id) or entities_before_merge.get(
                mention.entity_id
            )
        if target_entity is not None:
            mention.normalized_text = target_entity.normalized_name
            mention.entity_type = target_entity.entity_type
        key = (
            mention.entity_id,
            mention.sentence_index,
            mention.paragraph_index,
            mention.start_char,
            mention.end_char,
            mention.text,
            mention.mention_kind.value,
            mention.entity_type.value,
        )
        deduplicated_mentions[key] = mention
    document.mentions = list(deduplicated_mentions.values())


def _remap_facts(document: ArticleDocument, remap: dict[EntityID, EntityID]) -> None:
    for fact in document.facts:
        fact.subject_entity_id = remap.get(fact.subject_entity_id, fact.subject_entity_id)
        if fact.object_entity_id:
            fact.object_entity_id = remap.get(fact.object_entity_id, fact.object_entity_id)
        for field_name in (
            "position_entity_id",
            "owner_context_entity_id",
            "appointing_authority_entity_id",
            "governing_body_entity_id",
        ):
            entity_id = getattr(fact, field_name)
            if entity_id is None:
                continue
            setattr(fact, field_name, remap.get(entity_id, entity_id))
