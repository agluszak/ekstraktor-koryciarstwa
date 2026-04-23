from __future__ import annotations

from pipeline.base import EntityEnricher
from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import PUBLIC_OFFICE_ROLE_KINDS
from pipeline.domain_types import ClusterID, EntityID, EntityType, OrganizationKind
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    Mention,
    SentenceFragment,
)
from pipeline.relations.org_typing import OrganizationMentionClassifier
from pipeline.role_matching import RoleMatch, match_role_mentions
from pipeline.utils import stable_id


class SharedEntityEnricher(EntityEnricher):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.organization_classifier = OrganizationMentionClassifier(config)

    def name(self) -> str:
        return "shared_entity_enricher"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        self._enrich_public_institutions(document)
        self._ensure_public_office_positions(document)
        self._refresh_clause_mentions(document)
        return document

    def _enrich_public_institutions(self, document: ArticleDocument) -> None:
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        for cluster in document.clusters:
            if cluster.entity_type not in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                continue
            best_mention = cluster.mentions[0] if cluster.mentions else None
            parsed_words = (
                document.parsed_sentences.get(best_mention.sentence_index, [])
                if best_mention is not None
                else []
            )
            typing_result = self.organization_classifier.classify(
                surface_text=cluster.canonical_name,
                normalized_text=cluster.normalized_name,
                parsed_words=parsed_words,
                start_char=best_mention.start_char if best_mention is not None else 0,
                end_char=best_mention.end_char if best_mention is not None else 0,
            )
            if typing_result.organization_kind is not None:
                cluster.organization_kind = typing_result.organization_kind
            if typing_result.candidate_type.value == EntityType.PUBLIC_INSTITUTION.value:
                cluster.entity_type = EntityType.PUBLIC_INSTITUTION
                cluster.organization_kind = OrganizationKind.PUBLIC_INSTITUTION
                if typing_result.canonical_name is not None:
                    cluster.canonical_name = typing_result.canonical_name
                    cluster.normalized_name = typing_result.canonical_name
            for mention in cluster.mentions:
                if mention.entity_id is None:
                    continue
                entity = entity_by_id.get(mention.entity_id)
                if entity is None:
                    continue
                entity.organization_kind = cluster.organization_kind
                if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
                    entity.entity_type = EntityType.PUBLIC_INSTITUTION
                    if typing_result.canonical_name is not None:
                        entity.canonical_name = typing_result.canonical_name
                        entity.normalized_name = typing_result.canonical_name
                    mention.entity_type = EntityType.PUBLIC_INSTITUTION

    def _ensure_public_office_positions(self, document: ArticleDocument) -> None:
        existing_keys = {
            (
                mention.sentence_index,
                mention.start_char,
                mention.end_char,
                cluster.role_kind,
                cluster.role_modifier,
            )
            for cluster in document.clusters
            if cluster.entity_type == EntityType.POSITION
            for mention in cluster.mentions
        }
        for sentence in document.sentences:
            parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
            for match in match_role_mentions(parsed_words):
                if match.role_kind not in PUBLIC_OFFICE_ROLE_KINDS:
                    continue
                start_char = sentence.start_char + match.start
                end_char = sentence.start_char + match.end
                key = (
                    sentence.sentence_index,
                    start_char,
                    end_char,
                    match.role_kind,
                    match.role_modifier,
                )
                if key in existing_keys:
                    continue
                self._add_position(document, sentence, match, start_char, end_char)
                existing_keys.add(key)

    @staticmethod
    def _add_position(
        document: ArticleDocument,
        sentence: SentenceFragment,
        match: RoleMatch,
        start_char: int,
        end_char: int,
    ) -> None:
        surface = sentence.text[match.start : match.end]
        entity_id = EntityID(
            stable_id(
                "position",
                document.document_id,
                match.canonical_name,
                str(sentence.sentence_index),
                str(start_char),
                str(end_char),
            )
        )
        evidence = EvidenceSpan(
            text=surface,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=start_char,
            end_char=end_char,
        )
        entity = Entity(
            entity_id=entity_id,
            entity_type=EntityType.POSITION,
            canonical_name=match.canonical_name,
            normalized_name=match.canonical_name,
            aliases=[surface],
            evidence=[evidence],
            role_kind=match.role_kind,
            role_modifier=match.role_modifier,
        )
        mention = Mention(
            text=surface,
            normalized_text=match.canonical_name,
            mention_type=EntityType.POSITION,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=start_char,
            end_char=end_char,
            entity_id=entity_id,
        )
        cluster_mention = ClusterMention(
            text=surface,
            entity_type=EntityType.POSITION,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=start_char,
            end_char=end_char,
            entity_id=entity_id,
        )
        cluster = EntityCluster(
            cluster_id=ClusterID(stable_id("cluster", document.document_id, entity_id)),
            entity_type=EntityType.POSITION,
            canonical_name=match.canonical_name,
            normalized_name=match.canonical_name,
            mentions=[cluster_mention],
            aliases=[surface],
            role_kind=match.role_kind,
            role_modifier=match.role_modifier,
        )
        document.entities.append(entity)
        document.mentions.append(mention)
        document.clusters.append(cluster)

    @staticmethod
    def _refresh_clause_mentions(document: ArticleDocument) -> None:
        by_sentence: dict[int, list[ClusterMention]] = {}
        for cluster in document.clusters:
            for mention in cluster.mentions:
                by_sentence.setdefault(mention.sentence_index, []).append(mention)
        for clause in document.clause_units:
            seen = {
                (mention.entity_id, mention.start_char, mention.end_char)
                for mention in clause.cluster_mentions
            }
            for mention in by_sentence.get(clause.sentence_index, []):
                key = (mention.entity_id, mention.start_char, mention.end_char)
                if key in seen:
                    continue
                clause.cluster_mentions.append(mention)
                seen.add(key)
