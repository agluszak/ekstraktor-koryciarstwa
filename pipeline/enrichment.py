from __future__ import annotations

import re
from dataclasses import dataclass

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

DERIVED_ORGANIZATION_HEADS = frozenset(
    {
        "fundacja",
        "instytut",
        "pogotowie",
        "stowarzyszenie",
        "urząd",
    }
)

DERIVED_ORGANIZATION_PATTERN = re.compile(
    r"\b(?P<surface>"
    r"(?:fundacj(?:a|ę|i|ą)|stowarzyszeni(?:e|a|u|em)|instytut(?:em|u)?|pogotowi(?:e|a|u|em))"
    r"(?:\s+[A-ZŁŚŻŹĆŃÓĘ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ.-]*){0,4}"
    r"|urz(?:ąd|ędu|ędzie|ędem)(?:\s+(?!za\b|od\b|z\b|ze\b|do\b)[a-ząćęłńóśźż-]+){0,3})\b",
    re.IGNORECASE,
)

ORGANIZATION_GROUNDING_MARKERS = frozenset(
    {
        "założ",
        "fundator",
        "należąc",
        "prowadz",
        "otrzyma",
        "przekaza",
        "przela",
        "dotacj",
        "dofinansowa",
        "100 tysi",
        "zł",
        "umow",
        "promocyj",
    }
)


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
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.organization_classifier = OrganizationMentionClassifier(config)

    def name(self) -> str:
        return "shared_entity_enricher"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        self._derive_missing_organizations(document)
        self._enrich_public_institutions(document)
        self._ensure_public_office_positions(document)
        self._refresh_clause_mentions(document)
        return document

    def _derive_missing_organizations(self, document: ArticleDocument) -> None:
        existing_spans = {
            (mention.sentence_index, mention.start_char, mention.end_char)
            for cluster in document.clusters
            for mention in cluster.mentions
        }
        existing_names = {cluster.normalized_name.casefold() for cluster in document.clusters}
        for mention in self._derived_organization_mentions(document):
            key = (mention.sentence_index, mention.start_char, mention.end_char)
            if key in existing_spans:
                continue
            if mention.canonical_name.casefold() in existing_names:
                continue
            self._add_organization(document, mention)
            existing_spans.add(key)
            existing_names.add(mention.canonical_name.casefold())

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
        parsed_words: list,
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
        person_mentions = [
            mention
            for cluster in document.clusters
            if cluster.entity_type == EntityType.PERSON
            for mention in cluster.mentions
            if mention.paragraph_index == sentence.paragraph_index
        ]
        if not person_mentions:
            return None
        return min(person_mentions, key=lambda mention: abs(mention.start_char - anchor)).text

    @staticmethod
    def _add_organization(
        document: ArticleDocument,
        derived: DerivedOrganizationMention,
    ) -> None:
        entity_id = EntityID(
            stable_id(
                "entity",
                document.document_id,
                derived.canonical_name,
                str(derived.sentence_index),
                str(derived.start_char),
                str(derived.end_char),
            )
        )
        evidence = EvidenceSpan(
            text=derived.surface,
            sentence_index=derived.sentence_index,
            paragraph_index=derived.paragraph_index,
            start_char=derived.start_char,
            end_char=derived.end_char,
        )
        entity = Entity(
            entity_id=entity_id,
            entity_type=derived.entity_type,
            canonical_name=derived.canonical_name,
            normalized_name=derived.canonical_name,
            aliases=[derived.surface],
            evidence=[evidence],
            organization_kind=derived.organization_kind,
        )
        mention = Mention(
            text=derived.surface,
            normalized_text=derived.canonical_name,
            mention_type=derived.entity_type,
            sentence_index=derived.sentence_index,
            paragraph_index=derived.paragraph_index,
            start_char=derived.start_char,
            end_char=derived.end_char,
            entity_id=entity_id,
        )
        cluster_mention = ClusterMention(
            text=derived.surface,
            entity_type=derived.entity_type,
            sentence_index=derived.sentence_index,
            paragraph_index=derived.paragraph_index,
            start_char=derived.start_char,
            end_char=derived.end_char,
            entity_id=entity_id,
        )
        cluster = EntityCluster(
            cluster_id=ClusterID(stable_id("cluster", document.document_id, entity_id)),
            entity_type=derived.entity_type,
            canonical_name=derived.canonical_name,
            normalized_name=derived.canonical_name,
            mentions=[cluster_mention],
            aliases=[derived.surface],
            organization_kind=derived.organization_kind,
        )
        document.entities.append(entity)
        document.mentions.append(mention)
        document.clusters.append(cluster)

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
