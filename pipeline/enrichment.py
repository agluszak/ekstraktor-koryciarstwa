from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.base import EntityEnricher
from pipeline.cluster_reads import (
    canonical_name_for_cluster as read_canonical_name_for_cluster,
)
from pipeline.cluster_reads import (
    entity_for_cluster as read_entity_for_cluster,
)
from pipeline.cluster_reads import (
    entity_type_for_cluster as read_entity_type_for_cluster,
)
from pipeline.cluster_reads import (
    normalized_name_for_cluster as read_normalized_name_for_cluster,
)
from pipeline.config import PipelineConfig
from pipeline.document_graph import derived_clusters, ensure_entity, ensure_entity_view
from pipeline.domain_lexicons import (
    DERIVED_ORGANIZATION_HEADS,
    DERIVED_ORGANIZATION_PATTERN,
    ORGANIZATION_GROUNDING_MARKERS,
)
from pipeline.domain_types import (
    EntityID,
    EntityType,
    MentionKind,
    OrganizationKind,
    RoleKind,
    RoleModifier,
)
from pipeline.frame_grounding import FrameSlotGrounder
from pipeline.models import (
    ArticleDocument,
    Entity,
    ParsedWord,
    SentenceFragment,
)
from pipeline.relations.org_typing import OrganizationMentionClassifier
from pipeline.role_matching import RoleMatch, match_role_mentions
from pipeline.runtime import PipelineRuntime
from pipeline.utils import stable_id


@dataclass(frozen=True, slots=True)
class DerivedOrganizationMention:
    surface: str
    canonical_name: str
    entity_type: EntityType
    organization_kind: OrganizationKind
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int


class SharedEntityEnricher(EntityEnricher):
    def __init__(
        self,
        config: PipelineConfig,
        runtime: PipelineRuntime | None = None,
    ) -> None:
        self.config = config
        self.organization_classifier = OrganizationMentionClassifier(config, runtime=runtime)
        self.slot_grounder = FrameSlotGrounder(config, runtime=runtime)

    def name(self) -> str:
        return "shared_entity_enricher"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        self._derive_missing_organizations(document)
        self._combine_initial_surname_person_mentions(document)
        self._derive_missing_party_mentions(document)
        self._derive_missing_role_mentions(document)
        self._enrich_public_institutions(document)
        return document

    def _derive_missing_organizations(self, document: ArticleDocument) -> None:
        self.slot_grounder.ensure_document_organizations(document)

    def _derived_organization_mentions(
        self,
        document: ArticleDocument,
    ) -> list[DerivedOrganizationMention]:
        mentions: list[DerivedOrganizationMention] = []
        for sentence in document.sentences:
            sentence_mentions = self._sentence_derived_organization_mentions(document, sentence)
            mentions.extend(sentence_mentions)
        return mentions

    def _sentence_derived_organization_mentions(
        self,
        document: ArticleDocument,
        sentence: SentenceFragment,
    ) -> list[DerivedOrganizationMention]:
        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        mentions: list[DerivedOrganizationMention] = []
        for match in DERIVED_ORGANIZATION_PATTERN.finditer(sentence.text):
            surface = match.group("surface")
            surface_head = self._surface_head(surface, parsed_words, match.start(), match.end())
            if surface_head not in DERIVED_ORGANIZATION_HEADS:
                continue
            start_char = sentence.start_char + match.start()
            end_char = sentence.start_char + match.end()
            typing_result = self.organization_classifier.classify(
                surface_text=surface,
                normalized_text=surface,
                parsed_words=parsed_words,
                start_char=match.start(),
                end_char=match.end(),
            )
            canonical_name = typing_result.canonical_name
            if canonical_name is None:
                canonical_name = self._derived_canonical_name(
                    document=document,
                    sentence=sentence,
                    surface=surface,
                    surface_head=surface_head,
                    start_char=start_char,
                    end_char=end_char,
                )
            if canonical_name is None:
                continue
            entity_type = (
                EntityType.PUBLIC_INSTITUTION
                if typing_result.candidate_type.value == EntityType.PUBLIC_INSTITUTION.value
                else EntityType.ORGANIZATION
            )
            mentions.append(
                DerivedOrganizationMention(
                    surface=surface,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    organization_kind=typing_result.organization_kind,
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    start_char=start_char,
                    end_char=end_char,
                )
            )
        return mentions

    @staticmethod
    def _surface_head(
        surface: str,
        parsed_words: list[ParsedWord],
        start_char: int,
        end_char: int,
    ) -> str:
        span_words = [
            word for word in parsed_words if not (word.end <= start_char or word.start >= end_char)
        ]
        if span_words:
            return (span_words[0].lemma or span_words[0].text).casefold()
        return surface.split()[0].casefold()

    @staticmethod
    def _derived_canonical_name(
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        surface: str,
        surface_head: str,
        start_char: int,
        end_char: int,
    ) -> str | None:
        lowered = sentence.text.casefold()
        if surface_head == "urząd":
            if "marszałk" in lowered[max(0, start_char - sentence.start_char - 6) :]:
                return "Urząd Marszałkowski"
            return "Urząd"
        if surface_head not in {"fundacja", "stowarzyszenie", "instytut", "pogotowie"}:
            return None
        if not any(marker in lowered for marker in ORGANIZATION_GROUNDING_MARKERS):
            return None
        owner = SharedEntityEnricher._nearest_person_name(document, sentence, end_char)
        if surface_head == "fundacja" and owner is not None:
            return f"Fundacja {owner}"
        if len(surface.split()) > 1:
            return surface
        if surface_head == "pogotowie":
            return "Pogotowie"
        return None

    @staticmethod
    def _nearest_person_name(
        document: ArticleDocument,
        sentence: SentenceFragment,
        anchor: int,
    ) -> str | None:
        entities_by_id = {entity.entity_id: entity for entity in document.entities}
        person_mentions = [
            mention
            for cluster in derived_clusters(document)
            if read_entity_type_for_cluster(cluster, entities_by_id) == EntityType.PERSON
            for mention in cluster.mentions
            if mention.paragraph_index == sentence.paragraph_index
        ]
        if not person_mentions:
            return None
        return min(person_mentions, key=lambda mention: abs(mention.start_char - anchor)).text

    def _derive_missing_party_mentions(self, document: ArticleDocument) -> None:
        party_tokens = set(self.config.party_aliases.keys()).union(
            set(self.config.party_aliases.values())
        )
        for sentence in document.sentences:
            for token in party_tokens:
                flags = 0 if token.isupper() and len(token) <= 3 else re.IGNORECASE
                for match in re.finditer(rf"(?<!\w){re.escape(token)}(?!\w)", sentence.text, flags):
                    start_char = sentence.start_char + match.start()
                    end_char = sentence.start_char + match.end()
                    if self._overlaps_non_party_organization(
                        document=document,
                        sentence_index=sentence.sentence_index,
                        start_char=start_char,
                        end_char=end_char,
                    ):
                        continue
                    canonical_name = self.organization_classifier.resolve_party_name(
                        surface_text=match.group(0),
                        normalized_text=match.group(0),
                    )
                    if canonical_name is None:
                        continue
                    self._add_or_update_entity_view(
                        document=document,
                        sentence=sentence,
                        surface=match.group(0),
                        canonical_name=canonical_name,
                        entity_type=EntityType.POLITICAL_PARTY,
                        start_char=start_char,
                        end_char=end_char,
                    )

    def _combine_initial_surname_person_mentions(self, document: ArticleDocument) -> None:
        for sentence in document.sentences:
            entities_by_id = {entity.entity_id: entity for entity in document.entities}
            person_views = [
                (cluster, mention)
                for cluster in derived_clusters(document)
                if read_entity_type_for_cluster(cluster, entities_by_id) == EntityType.PERSON
                for mention in cluster.mentions
                if mention.sentence_index == sentence.sentence_index
            ]
            initials = [
                (cluster, mention)
                for cluster, mention in person_views
                if len(read_canonical_name_for_cluster(cluster, entities_by_id).rstrip(".")) == 1
            ]
            surnames = [
                (cluster, mention)
                for cluster, mention in person_views
                if len(read_canonical_name_for_cluster(cluster, entities_by_id).split()) == 1
                and len(read_canonical_name_for_cluster(cluster, entities_by_id).rstrip(".")) > 1
            ]
            for initial_cluster, initial_mention in initials:
                for surname_cluster, surname_mention in surnames:
                    if surname_mention.start_char <= initial_mention.end_char:
                        continue
                    between = document.cleaned_text[
                        initial_mention.end_char : surname_mention.start_char
                    ]
                    if between not in {". ", ".\u00a0"}:
                        continue
                    first = read_canonical_name_for_cluster(
                        initial_cluster,
                        entities_by_id,
                    ).rstrip(".")
                    surname = read_canonical_name_for_cluster(
                        surname_cluster,
                        entities_by_id,
                    )
                    canonical_name = f"{first}. {surname}"
                    if any(
                        entity.entity_type == EntityType.PERSON
                        and entity.canonical_name == canonical_name
                        for entity in document.entities
                    ):
                        continue
                    start_char = initial_mention.start_char
                    end_char = surname_mention.end_char
                    surface = document.cleaned_text[start_char:end_char]
                    if not surface:
                        surface = f"{first}. {surname_mention.text}"
                    self._add_or_update_entity_view(
                        document=document,
                        sentence=sentence,
                        surface=surface,
                        canonical_name=canonical_name,
                        entity_type=EntityType.PERSON,
                        start_char=start_char,
                        end_char=end_char,
                    )
                    continue

    def _derive_missing_role_mentions(self, document: ArticleDocument) -> None:
        for sentence in document.sentences:
            parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
            for match in match_role_mentions(parsed_words):
                self._add_role_match(document, sentence, match)

    def _add_role_match(
        self,
        document: ArticleDocument,
        sentence: SentenceFragment,
        match: RoleMatch,
    ) -> None:
        start_char = sentence.start_char + match.start
        end_char = sentence.start_char + match.end
        surface = sentence.text[match.start : match.end]
        self._add_or_update_entity_view(
            document=document,
            sentence=sentence,
            surface=surface,
            canonical_name=match.canonical_name,
            entity_type=EntityType.POSITION,
            start_char=start_char,
            end_char=end_char,
            role_kind=match.role_kind,
            role_modifier=match.role_modifier,
        )

    @staticmethod
    def _add_or_update_entity_view(
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        surface: str,
        canonical_name: str,
        entity_type: EntityType,
        start_char: int,
        end_char: int,
        organization_kind: OrganizationKind | None = None,
        role_kind: RoleKind | None = None,
        role_modifier: RoleModifier | None = None,
    ) -> None:
        entities_by_id = {entity.entity_id: entity for entity in document.entities}
        if SharedEntityEnricher._has_existing_view(
            document=document,
            entity_type=entity_type,
            canonical_name=canonical_name,
            sentence_index=sentence.sentence_index,
            start_char=start_char,
            end_char=end_char,
            entities_by_id=entities_by_id,
        ):
            return

        entity = next(
            (
                existing
                for existing in document.entities
                if existing.entity_type == entity_type
                and existing.normalized_name.casefold() == canonical_name.casefold()
            ),
            None,
        )
        entity = ensure_entity(
            document,
            entity_id=(
                EntityID(stable_id(entity_type.lower(), document.document_id, canonical_name))
                if entity is None
                else entity.entity_id
            ),
            entity_type=entity_type,
            canonical_name=canonical_name,
            aliases=[surface],
            organization_kind=organization_kind,
            role_kind=role_kind,
            role_modifier=role_modifier,
        )
        ensure_entity_view(
            document,
            entity=entity,
            surface=surface,
            normalized_text=canonical_name,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=start_char,
            end_char=end_char,
            mention_kind=MentionKind.DERIVED_ENTITY,
            entity_type=entity_type,
        )

    @staticmethod
    def _has_existing_view(
        *,
        document: ArticleDocument,
        entity_type: EntityType,
        canonical_name: str,
        sentence_index: int,
        start_char: int,
        end_char: int,
        entities_by_id: dict[EntityID, Entity] | None = None,
    ) -> bool:
        cluster_entities = {} if entities_by_id is None else entities_by_id
        return any(
            read_entity_type_for_cluster(cluster, cluster_entities) == entity_type
            and read_normalized_name_for_cluster(cluster, cluster_entities).casefold()
            == canonical_name.casefold()
            and any(
                mention.sentence_index == sentence_index
                and mention.start_char == start_char
                and mention.end_char == end_char
                for mention in cluster.mentions
            )
            for cluster in derived_clusters(document)
        )

    @staticmethod
    def _overlaps_non_party_organization(
        *,
        document: ArticleDocument,
        sentence_index: int,
        start_char: int,
        end_char: int,
    ) -> bool:
        entities_by_id = {entity.entity_id: entity for entity in document.entities}
        for cluster in derived_clusters(document):
            if read_entity_type_for_cluster(cluster, entities_by_id) not in {
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            }:
                continue
            for mention in cluster.mentions:
                if mention.sentence_index != sentence_index:
                    continue
                if mention.start_char <= start_char and end_char <= mention.end_char:
                    return mention.start_char != start_char or mention.end_char != end_char
        for mention in document.mentions:
            if mention.entity_type not in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                continue
            if mention.sentence_index != sentence_index:
                continue
            if mention.start_char <= start_char and end_char <= mention.end_char:
                return mention.start_char != start_char or mention.end_char != end_char
        return False

    def _enrich_public_institutions(self, document: ArticleDocument) -> None:
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        for cluster in derived_clusters(document):
            cluster_entity = read_entity_for_cluster(cluster, entity_by_id)
            if cluster_entity is None:
                continue
            if cluster_entity.entity_type not in {
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            }:
                continue
            best_mention = cluster.mentions[0] if cluster.mentions else None
            parsed_words = (
                document.parsed_sentences.get(best_mention.sentence_index, [])
                if best_mention is not None
                else []
            )
            typing_result = self.organization_classifier.classify(
                surface_text=cluster_entity.canonical_name,
                normalized_text=cluster_entity.normalized_name,
                parsed_words=parsed_words,
                start_char=best_mention.start_char if best_mention is not None else 0,
                end_char=best_mention.end_char if best_mention is not None else 0,
            )
            if typing_result.organization_kind is not None:
                cluster_entity.organization_kind = typing_result.organization_kind
            if typing_result.candidate_type in {
                EntityType.PUBLIC_INSTITUTION,
                EntityType.POLITICAL_PARTY,
            }:
                if (
                    typing_result.candidate_type == EntityType.POLITICAL_PARTY
                    and _has_non_party_organization_head(cluster_entity.normalized_name)
                ):
                    continue
                cluster_entity.entity_type = typing_result.candidate_type
                if typing_result.candidate_type == EntityType.PUBLIC_INSTITUTION:
                    cluster_entity.organization_kind = OrganizationKind.PUBLIC_INSTITUTION
                if typing_result.canonical_name is not None:
                    cluster_entity.canonical_name = typing_result.canonical_name
                    cluster_entity.normalized_name = typing_result.canonical_name
            for mention in cluster.mentions:
                if mention.entity_id is None:
                    continue
                entity = entity_by_id.get(mention.entity_id)
                if entity is None:
                    continue
                entity.organization_kind = cluster_entity.organization_kind
                if cluster_entity.entity_type in {
                    EntityType.PUBLIC_INSTITUTION,
                    EntityType.POLITICAL_PARTY,
                }:
                    entity.entity_type = cluster_entity.entity_type
                    if typing_result.canonical_name is not None:
                        entity.canonical_name = typing_result.canonical_name
                        entity.normalized_name = typing_result.canonical_name
                    mention.entity_type = cluster_entity.entity_type


def _has_non_party_organization_head(name: str) -> bool:
    lowered = name.casefold()
    return any(
        marker in lowered
        for marker in (
            "fundacj",
            "spół",
            "przedsiębiorst",
            "stowarzyszen",
            "instytut",
        )
    )
