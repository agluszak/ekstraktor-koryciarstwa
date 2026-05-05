from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import (
    DERIVED_ORGANIZATION_HEADS,
    DERIVED_ORGANIZATION_PATTERN,
    INVALID_PUBLIC_EMPLOYMENT_ROLE_HEADS,
    KINSHIP_LEMMAS,
    ORGANIZATION_GROUNDING_MARKERS,
    PUBLIC_EMPLOYER_TERMS,
    PUBLIC_OFFICE_ROLE_KINDS,
)
from pipeline.domain_types import ClusterID, EntityID, EntityType, OrganizationKind
from pipeline.entity_naming import org_token_base
from pipeline.lemma_signals import word_by_index
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    Mention,
    ParsedWord,
    SentenceFragment,
)
from pipeline.relations.org_typing import OrganizationMentionClassifier
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_entity_name, stable_id

ROLE_STOP_WORDS = frozenset(
    {"w", "we", "do", "na", "od", "przy", "oraz", "i", "a", "ale", "który", "która"}
)
ROLE_ANCHOR_HEADS = frozenset({"dyrektor", "koordynator", "specjalista", "doradca", "ekodoradca"})
ROLE_NOISE_TOKENS = frozenset({"potrzebna", "potrzebny", "potrzebne", "potrzebni"})
ORGANIZATION_CANONICAL_NOISE_MARKERS = frozenset(
    {
        "założ",
        "przez",
        "dotycz",
        "działań",
        "otrzyma",
        "generalnego",
        "wojewody",
    }
)
DATE_ROLE_PATTERN = re.compile(
    r"\b\d{1,2}(?:[./-]\d{1,2}(?:[./-]\d{2,4})?)?\b|\b(?:r\.|rok|stycz|lut|marc|kwiet|maj|czerwc|lip|sierp|wrze|paźdz|listop|grudn)",
    re.IGNORECASE,
)
ALL_CAPS_PATTERN = re.compile(r"\b[A-ZŁŚŻŹĆŃÓĘ]{2,6}\b")
MIXED_CASE_ORG_ALIAS_PATTERN = re.compile(
    r"\b[A-ZŁŚŻŹĆŃÓĘ][a-ząćęłńóśźż]{2,}[A-ZŁŚŻŹĆŃÓĘ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{1,10}\b"
)
COMPACT_ALIAS_EMBEDDING_THRESHOLD = 0.74


@dataclass(frozen=True, slots=True)
class SlotEvidence:
    text: str
    sentence_index: int
    paragraph_index: int
    start_char: int
    end_char: int

    def to_evidence_span(self) -> EvidenceSpan:
        return EvidenceSpan(
            text=self.text,
            sentence_index=self.sentence_index,
            paragraph_index=self.paragraph_index,
            start_char=self.start_char,
            end_char=self.end_char,
        )


@dataclass(frozen=True, slots=True)
class GroundedRoleLabel:
    label: str
    head_lemma: str
    evidence: SlotEvidence
    source: str
    role_cluster_id: ClusterID | None = None


@dataclass(frozen=True, slots=True)
class GroundedOrganizationMention:
    surface: str
    canonical_name: str
    entity_type: EntityType
    organization_kind: OrganizationKind
    evidence: SlotEvidence
    cluster_id: ClusterID | None = None
    entity_id: EntityID | None = None
    synthetic: bool = False


@dataclass(frozen=True, slots=True)
class _RoleLabelCandidate:
    label: str
    head_lemma: str
    words: tuple[ParsedWord, ...]
    source: str
    role_cluster_id: ClusterID | None = None


class FrameSlotGrounder:
    def __init__(
        self,
        config: PipelineConfig,
        runtime: PipelineRuntime | None = None,
    ) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)
        self.organization_classifier = OrganizationMentionClassifier(config)
        self._embedding_cache: dict[str, np.ndarray] = {}

    def ground_public_employment_role(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        *,
        employee: EntityCluster | None,
        role_cluster: EntityCluster | None,
    ) -> GroundedRoleLabel | None:
        if role_cluster is not None and not self._is_public_office_role(role_cluster):
            evidence = self._slot_evidence_for_cluster(clause, role_cluster)
            if evidence is not None:
                return GroundedRoleLabel(
                    label=role_cluster.canonical_name,
                    head_lemma=role_cluster.normalized_name.split()[0].casefold(),
                    evidence=evidence,
                    source="role_cluster",
                    role_cluster_id=role_cluster.cluster_id,
                )

        candidate = None
        if employee is not None:
            candidate = self._role_candidate_near_employee(document, clause, employee)
        if candidate is None:
            candidate = self._role_candidate_for_clause(document, clause)
        if candidate is None:
            return None
        if self._invalid_role_candidate(document, clause, candidate):
            return None
        return GroundedRoleLabel(
            label=candidate.label,
            head_lemma=candidate.head_lemma,
            evidence=self._slot_evidence_for_words(clause, candidate.words),
            source=candidate.source,
            role_cluster_id=candidate.role_cluster_id,
        )

    def ensure_document_organizations(self, document: ArticleDocument) -> None:
        for sentence in document.sentences:
            self.ensure_sentence_organizations(document, sentence)

    def ensure_sentence_organizations(
        self,
        document: ArticleDocument,
        sentence: SentenceFragment,
    ) -> list[GroundedOrganizationMention]:
        grounded = self._sentence_grounded_organization_mentions(document, sentence)
        for mention in grounded:
            self._upsert_grounded_organization(document, mention)
        self.refresh_clause_mentions(document)
        return grounded

    def ground_organization_mentions(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> list[GroundedOrganizationMention]:
        sentence = next(
            (
                sentence
                for sentence in document.sentences
                if sentence.sentence_index == clause.sentence_index
            ),
            None,
        )
        if sentence is None:
            sentence = SentenceFragment(
                text=clause.text,
                paragraph_index=clause.paragraph_index,
                sentence_index=clause.sentence_index,
                start_char=clause.start_char,
                end_char=clause.end_char,
            )
        self.ensure_sentence_organizations(document, sentence)
        grounded: list[GroundedOrganizationMention] = []
        seen: set[ClusterID] = set()
        mention_keys = {
            (mention.entity_id, mention.start_char, mention.end_char)
            for mention in clause.cluster_mentions
            if mention.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        }
        for cluster in document.clusters:
            if cluster.entity_type not in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                continue
            mention = next(
                (
                    item
                    for item in cluster.mentions
                    if (item.entity_id, item.start_char, item.end_char) in mention_keys
                ),
                None,
            )
            if mention is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            entity_id = next((item.entity_id for item in cluster.mentions if item.entity_id), None)
            grounded.append(
                GroundedOrganizationMention(
                    surface=mention.text,
                    canonical_name=cluster.canonical_name,
                    entity_type=cluster.entity_type,
                    organization_kind=cluster.organization_kind or OrganizationKind.ORGANIZATION,
                    evidence=SlotEvidence(
                        text=mention.text,
                        sentence_index=mention.sentence_index,
                        paragraph_index=mention.paragraph_index,
                        start_char=mention.start_char,
                        end_char=mention.end_char,
                    ),
                    cluster_id=cluster.cluster_id,
                    entity_id=entity_id,
                )
            )
        return grounded

    @staticmethod
    def refresh_clause_mentions(document: ArticleDocument) -> None:
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

    def _sentence_grounded_organization_mentions(
        self,
        document: ArticleDocument,
        sentence: SentenceFragment,
    ) -> list[GroundedOrganizationMention]:
        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        mentions: list[GroundedOrganizationMention] = []
        seen_ranges: set[tuple[int, int]] = set()

        for match in DERIVED_ORGANIZATION_PATTERN.finditer(sentence.text):
            start_char = sentence.start_char + match.start()
            end_char = sentence.start_char + match.end()
            if grounded := self._ground_organization_surface(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                surface=match.group("surface"),
                local_start=match.start(),
                local_end=match.end(),
            ):
                seen_ranges.add((start_char, end_char))
                mentions.append(grounded)

        for word in parsed_words:
            lemma = (word.lemma or word.text).casefold()
            if lemma not in DERIVED_ORGANIZATION_HEADS:
                continue
            start_char = sentence.start_char + word.start
            end_char = sentence.start_char + word.end
            if any(
                existing_start <= start_char < existing_end
                for existing_start, existing_end in seen_ranges
            ):
                continue
            if grounded := self._ground_head_word(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                head=word,
            ):
                mentions.append(grounded)

        for match in ALL_CAPS_PATTERN.finditer(sentence.text):
            if grounded := self._ground_institution_acronym(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                acronym=match.group(0),
                local_start=match.start(),
                local_end=match.end(),
            ):
                mentions.append(grounded)

        for match in MIXED_CASE_ORG_ALIAS_PATTERN.finditer(sentence.text):
            if grounded := self._ground_compact_org_alias(
                document=document,
                sentence=sentence,
                alias=match.group(0),
                local_start=match.start(),
                local_end=match.end(),
            ):
                mentions.append(grounded)

        return self._deduplicate_grounded_mentions(mentions)

    def _ground_organization_surface(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        surface: str,
        local_start: int,
        local_end: int,
    ) -> GroundedOrganizationMention | None:
        surface_head = self._surface_head(surface, parsed_words, local_start, local_end)
        if surface_head not in DERIVED_ORGANIZATION_HEADS:
            return None
        canonical_name = self._canonical_name_for_grounding(
            document=document,
            sentence=sentence,
            parsed_words=parsed_words,
            surface=surface,
            surface_head=surface_head,
            local_start=local_start,
            local_end=local_end,
        )
        if canonical_name is None:
            return None
        typing_result = self.organization_classifier.classify(
            surface_text=surface,
            normalized_text=canonical_name,
            parsed_words=parsed_words,
            start_char=local_start,
            end_char=local_end,
        )
        entity_type = (
            EntityType.PUBLIC_INSTITUTION
            if typing_result.candidate_type.value == EntityType.PUBLIC_INSTITUTION.value
            else EntityType.ORGANIZATION
        )
        organization_kind = (
            typing_result.organization_kind
            if typing_result.organization_kind is not None
            else OrganizationKind.ORGANIZATION
        )
        return GroundedOrganizationMention(
            surface=surface,
            canonical_name=canonical_name,
            entity_type=entity_type,
            organization_kind=organization_kind,
            evidence=SlotEvidence(
                text=surface,
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                start_char=sentence.start_char + local_start,
                end_char=sentence.start_char + local_end,
            ),
            synthetic=True,
        )

    def _ground_head_word(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        head: ParsedWord,
    ) -> GroundedOrganizationMention | None:
        surface = head.text
        canonical_name = self._canonical_name_for_grounding(
            document=document,
            sentence=sentence,
            parsed_words=parsed_words,
            surface=surface,
            surface_head=(head.lemma or head.text).casefold(),
            local_start=head.start,
            local_end=head.end,
        )
        if canonical_name is None:
            return None
        typing_result = self.organization_classifier.classify(
            surface_text=surface,
            normalized_text=canonical_name,
            parsed_words=parsed_words,
            start_char=head.start,
            end_char=head.end,
        )
        entity_type = (
            EntityType.PUBLIC_INSTITUTION
            if typing_result.candidate_type.value == EntityType.PUBLIC_INSTITUTION.value
            else EntityType.ORGANIZATION
        )
        organization_kind = (
            typing_result.organization_kind
            if typing_result.organization_kind is not None
            else OrganizationKind.ORGANIZATION
        )
        return GroundedOrganizationMention(
            surface=surface,
            canonical_name=canonical_name,
            entity_type=entity_type,
            organization_kind=organization_kind,
            evidence=SlotEvidence(
                text=surface,
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                start_char=sentence.start_char + head.start,
                end_char=sentence.start_char + head.end,
            ),
            synthetic=True,
        )

    def _ground_institution_acronym(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        acronym: str,
        local_start: int,
        local_end: int,
    ) -> GroundedOrganizationMention | None:
        canonical_name = self._existing_canonical_for_acronym(document, acronym)
        if canonical_name is None:
            return None
        return GroundedOrganizationMention(
            surface=acronym,
            canonical_name=canonical_name,
            entity_type=EntityType.PUBLIC_INSTITUTION,
            organization_kind=OrganizationKind.PUBLIC_INSTITUTION,
            evidence=SlotEvidence(
                text=acronym,
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                start_char=sentence.start_char + local_start,
                end_char=sentence.start_char + local_end,
            ),
            synthetic=True,
        )

    def _ground_compact_org_alias(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        alias: str,
        local_start: int,
        local_end: int,
    ) -> GroundedOrganizationMention | None:
        existing_cluster = self._existing_cluster_for_compact_alias(document, sentence, alias)
        if existing_cluster is None:
            return None
        return GroundedOrganizationMention(
            surface=alias,
            canonical_name=existing_cluster.canonical_name,
            entity_type=existing_cluster.entity_type,
            organization_kind=existing_cluster.organization_kind or OrganizationKind.ORGANIZATION,
            evidence=SlotEvidence(
                text=alias,
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                start_char=sentence.start_char + local_start,
                end_char=sentence.start_char + local_end,
            ),
            cluster_id=existing_cluster.cluster_id,
            synthetic=True,
        )

    def _existing_canonical_for_acronym(
        self,
        document: ArticleDocument,
        acronym: str,
    ) -> str | None:
        normalized_acronym = acronym.casefold()
        explicit = self.organization_classifier.resolve_institution_name(
            surface_text=acronym,
            normalized_text=acronym,
        )
        if explicit is not None:
            return explicit
        candidates = [
            cluster.canonical_name
            for cluster in document.clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        ]
        for candidate in candidates:
            initials = "".join(
                token[0] for token in candidate.split() if token and token[0].isalnum()
            )
            if initials.casefold() == normalized_acronym:
                return candidate
        return None

    def _existing_cluster_for_compact_alias(
        self,
        document: ArticleDocument,
        sentence: SentenceFragment,
        alias: str,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and any(
                mention.paragraph_index == sentence.paragraph_index for mention in cluster.mentions
            )
        ]
        matches = [
            (self._compact_alias_match_score(alias, cluster), cluster) for cluster in candidates
        ]
        ranked_matches = [(score, cluster) for score, cluster in matches if score > 0]
        if not ranked_matches:
            return self._embedding_cluster_for_compact_alias(alias, candidates)
        return max(ranked_matches, key=lambda item: (item[0], len(item[1].canonical_name)))[1]

    def _embedding_cluster_for_compact_alias(
        self,
        alias: str,
        candidates: list[EntityCluster],
    ) -> EntityCluster | None:
        alias_tokens = self._compact_alias_tokens(alias)
        alias_bases = {
            org_token_base(token.casefold()) for token in alias_tokens if len(token) >= 4
        }
        if len(alias_tokens) < 2 or not alias_bases:
            return None
        alias_embedding = self._encode_text(" ".join(alias_tokens))
        ranked: list[tuple[float, EntityCluster]] = []
        for cluster in candidates:
            cluster_bases = {
                org_token_base(token.casefold())
                for token in normalize_entity_name(cluster.canonical_name).split()
                if len(token) >= 4
            }
            if not alias_bases.intersection(cluster_bases):
                continue
            similarity = self._cosine_similarity(
                alias_embedding,
                self._encode_text(cluster.canonical_name),
            )
            if similarity >= COMPACT_ALIAS_EMBEDDING_THRESHOLD:
                ranked.append((similarity, cluster))
        if not ranked:
            return None
        return max(ranked, key=lambda item: (item[0], len(item[1].canonical_name)))[1]

    def _canonical_name_for_grounding(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        surface: str,
        surface_head: str,
        local_start: int,
        local_end: int,
    ) -> str | None:
        lowered_sentence = sentence.text.casefold()
        office_head = next(
            (
                word
                for word in parsed_words
                if (word.lemma or word.text).casefold() == "urząd"
                and word.start >= max(0, local_start - 2)
                and word.start <= local_end
            ),
            None,
        )
        office_window = lowered_sentence[
            max(0, local_start - 24) : min(len(lowered_sentence), local_end + 28)
        ]
        if surface_head == "urząd":
            if "marszałk" in office_window:
                return "Urząd Marszałkowski"
            if "wojewódzk" in office_window:
                adjective = self._preceding_office_adjective(parsed_words, local_start, office_head)
                if adjective is not None:
                    return f"{adjective} Urząd Wojewódzki"
                return "Urząd Wojewódzki"
            if "gmin" in office_window:
                return "Urząd Gminy"
            return None
        if surface_head not in {"fundacja", "stowarzyszenie", "instytut", "pogotowie"}:
            return None
        owner = self._nearest_person_name(document, sentence, sentence.start_char + local_end)
        has_grounding_evidence = any(
            marker in lowered_sentence for marker in ORGANIZATION_GROUNDING_MARKERS
        )
        if owner is not None and has_grounding_evidence:
            return f"{surface_head.capitalize()} {owner}"
        title_tokens = self._title_case_tokens_after_head(parsed_words, local_start, local_end)
        if title_tokens:
            return normalize_entity_name(f"{surface_head} {' '.join(title_tokens)}")
        if surface_head == "pogotowie":
            return "Pogotowie"
        return None

    @staticmethod
    def _preceding_office_adjective(
        parsed_words: list[ParsedWord],
        local_start: int,
        office_head: ParsedWord | None,
    ) -> str | None:
        if office_head is not None:
            attached = [
                word
                for word in parsed_words
                if word.head == office_head.index
                and (word.deprel == "amod" or word.upos in {"ADJ", "PROPN"})
                and (word.lemma or word.text).casefold()
                not in {"wojewódzki", "marszałkowski", "gminny", "miejski", "powiatowy"}
            ]
            if attached:
                best = min(attached, key=lambda word: word.start)
                return normalize_entity_name(best.lemma or best.text)
        preceding = [
            word
            for word in parsed_words
            if word.end <= local_start and word.upos in {"ADJ", "PROPN"}
        ]
        if not preceding:
            return None
        candidate = max(preceding, key=lambda word: word.end)
        lemma = normalize_entity_name(candidate.lemma or candidate.text)
        if lemma.casefold() in PUBLIC_EMPLOYER_TERMS:
            return None
        return lemma

    @staticmethod
    def _title_case_tokens_after_head(
        parsed_words: list[ParsedWord],
        local_start: int,
        local_end: int,
    ) -> list[str]:
        tokens: list[str] = []
        for word in parsed_words:
            if word.start < local_end or len(tokens) >= 4:
                continue
            if word.upos not in {"PROPN", "ADJ", "NOUN"}:
                break
            if not word.text[:1].isupper():
                break
            tokens.append(word.text)
        return tokens

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

    def _upsert_grounded_organization(
        self,
        document: ArticleDocument,
        grounded: GroundedOrganizationMention,
    ) -> None:
        overlapping = next(
            (
                cluster
                for cluster in document.clusters
                if any(
                    mention.sentence_index == grounded.evidence.sentence_index
                    and mention.start_char == grounded.evidence.start_char
                    and mention.end_char == grounded.evidence.end_char
                    for mention in cluster.mentions
                )
            ),
            None,
        )
        existing = next(
            (
                cluster
                for cluster in document.clusters
                if cluster.entity_type == grounded.entity_type
                and cluster.normalized_name.casefold() == grounded.canonical_name.casefold()
            ),
            None,
        )
        if (
            existing is not None
            and overlapping is not None
            and overlapping.cluster_id != existing.cluster_id
            and overlapping.entity_type
            not in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        ):
            self._append_alias_mention(document, existing, grounded)
            self._remove_cluster(document, overlapping)
            return
        if overlapping is not None and self._grounding_beats_existing(overlapping, grounded):
            self._replace_cluster_canonical(document, overlapping, grounded)
            self._append_alias_mention(document, overlapping, grounded)
            return
        if existing is not None:
            self._append_alias_mention(document, existing, grounded)
            return
        noisy_match = next(
            (
                cluster
                for cluster in document.clusters
                if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
                and cluster.canonical_name.casefold().startswith(grounded.canonical_name.casefold())
                and any(
                    marker in cluster.canonical_name.casefold()
                    for marker in ORGANIZATION_CANONICAL_NOISE_MARKERS
                )
            ),
            None,
        )
        if noisy_match is not None:
            self._replace_cluster_canonical(document, noisy_match, grounded)
            self._append_alias_mention(document, noisy_match, grounded)
            return

        entity_id = EntityID(
            stable_id(
                "entity",
                document.document_id,
                grounded.canonical_name,
                str(grounded.evidence.sentence_index),
                str(grounded.evidence.start_char),
                str(grounded.evidence.end_char),
            )
        )
        evidence = grounded.evidence.to_evidence_span()
        entity = Entity(
            entity_id=entity_id,
            entity_type=grounded.entity_type,
            canonical_name=grounded.canonical_name,
            normalized_name=grounded.canonical_name,
            aliases=[grounded.surface],
            evidence=[evidence],
            organization_kind=grounded.organization_kind,
        )
        mention = Mention(
            text=grounded.surface,
            normalized_text=grounded.canonical_name,
            mention_type=grounded.entity_type,
            sentence_index=grounded.evidence.sentence_index,
            paragraph_index=grounded.evidence.paragraph_index,
            start_char=grounded.evidence.start_char,
            end_char=grounded.evidence.end_char,
            entity_id=entity_id,
        )
        cluster_mention = ClusterMention(
            text=grounded.surface,
            entity_type=grounded.entity_type,
            sentence_index=grounded.evidence.sentence_index,
            paragraph_index=grounded.evidence.paragraph_index,
            start_char=grounded.evidence.start_char,
            end_char=grounded.evidence.end_char,
            entity_id=entity_id,
        )
        cluster = EntityCluster(
            cluster_id=ClusterID(stable_id("cluster", document.document_id, entity_id)),
            entity_type=grounded.entity_type,
            canonical_name=grounded.canonical_name,
            normalized_name=grounded.canonical_name,
            mentions=[cluster_mention],
            aliases=[grounded.surface],
            organization_kind=grounded.organization_kind,
        )
        document.entities.append(entity)
        document.mentions.append(mention)
        document.clusters.append(cluster)

    @staticmethod
    def _grounding_beats_existing(
        cluster: EntityCluster,
        grounded: GroundedOrganizationMention,
    ) -> bool:
        existing = cluster.canonical_name.casefold()
        candidate = grounded.canonical_name.casefold()
        if existing == candidate:
            return cluster.entity_type != grounded.entity_type and (
                FrameSlotGrounder._looks_like_compact_org_alias(grounded.surface)
            )
        if any(marker in existing for marker in ORGANIZATION_CANONICAL_NOISE_MARKERS):
            return True
        if len(existing.split()) > len(candidate.split()) + 2:
            return True
        if candidate.startswith("urząd") and "urząd" in existing:
            return True
        return cluster.entity_type == EntityType.PERSON and (
            FrameSlotGrounder._looks_like_compact_org_alias(grounded.surface)
        )

    @staticmethod
    def _remove_cluster(
        document: ArticleDocument,
        cluster: EntityCluster,
    ) -> None:
        entity_ids = {
            mention.entity_id for mention in cluster.mentions if mention.entity_id is not None
        }
        document.clusters = [
            item for item in document.clusters if item.cluster_id != cluster.cluster_id
        ]
        document.entities = [item for item in document.entities if item.entity_id not in entity_ids]
        document.mentions = [item for item in document.mentions if item.entity_id not in entity_ids]
        for clause in document.clause_units:
            clause.cluster_mentions = [
                mention
                for mention in clause.cluster_mentions
                if mention.entity_id not in entity_ids
            ]

    @staticmethod
    def _replace_cluster_canonical(
        document: ArticleDocument,
        cluster: EntityCluster,
        grounded: GroundedOrganizationMention,
    ) -> None:
        previous_name = cluster.canonical_name
        cluster.canonical_name = grounded.canonical_name
        cluster.normalized_name = grounded.canonical_name
        cluster.entity_type = grounded.entity_type
        cluster.organization_kind = grounded.organization_kind
        if previous_name not in cluster.aliases:
            cluster.aliases.append(previous_name)
        for mention in cluster.mentions:
            mention.entity_type = grounded.entity_type
            for document_mention in document.mentions:
                if (
                    document_mention.entity_id == mention.entity_id
                    and document_mention.start_char == mention.start_char
                    and document_mention.end_char == mention.end_char
                    and document_mention.sentence_index == mention.sentence_index
                ):
                    document_mention.mention_type = grounded.entity_type
            entity = next(
                (item for item in document.entities if item.entity_id == mention.entity_id),
                None,
            )
            if entity is None:
                continue
            entity.canonical_name = grounded.canonical_name
            entity.normalized_name = grounded.canonical_name
            entity.entity_type = grounded.entity_type
            entity.organization_kind = grounded.organization_kind
            if previous_name not in entity.aliases:
                entity.aliases.append(previous_name)

    @staticmethod
    def _append_alias_mention(
        document: ArticleDocument,
        cluster: EntityCluster,
        grounded: GroundedOrganizationMention,
    ) -> None:
        if any(
            mention.start_char == grounded.evidence.start_char
            and mention.end_char == grounded.evidence.end_char
            and mention.sentence_index == grounded.evidence.sentence_index
            for mention in cluster.mentions
        ):
            return
        entity_id = next(
            (mention.entity_id for mention in cluster.mentions if mention.entity_id),
            None,
        )
        cluster.mentions.append(
            ClusterMention(
                text=grounded.surface,
                entity_type=cluster.entity_type,
                sentence_index=grounded.evidence.sentence_index,
                paragraph_index=grounded.evidence.paragraph_index,
                start_char=grounded.evidence.start_char,
                end_char=grounded.evidence.end_char,
                entity_id=entity_id,
            )
        )
        if grounded.surface not in cluster.aliases:
            cluster.aliases.append(grounded.surface)
        entity = next(
            (item for item in document.entities if item.entity_id == entity_id),
            None,
        )
        if entity is None:
            return
        if grounded.surface not in entity.aliases:
            entity.aliases.append(grounded.surface)
        entity.evidence.append(grounded.evidence.to_evidence_span())
        document.mentions.append(
            Mention(
                text=grounded.surface,
                normalized_text=cluster.canonical_name,
                mention_type=cluster.entity_type,
                sentence_index=grounded.evidence.sentence_index,
                paragraph_index=grounded.evidence.paragraph_index,
                start_char=grounded.evidence.start_char,
                end_char=grounded.evidence.end_char,
                entity_id=entity_id,
            )
        )

    @staticmethod
    def _compact_alias_match_score(alias: str, cluster: EntityCluster) -> int:
        if not FrameSlotGrounder._looks_like_compact_org_alias(alias):
            return 0
        lowered_alias = alias.casefold()
        cluster_tokens = [
            token.casefold()
            for token in normalize_entity_name(cluster.canonical_name).split()
            if len(token) >= 4
        ]
        if len(cluster_tokens) < 2:
            return 0
        matched_tokens = sum(
            1
            for token in cluster_tokens
            if lowered_alias.startswith(token[:3])
            or token[:3] in lowered_alias
            or token[:4] in lowered_alias
        )
        if matched_tokens < 2:
            return 0
        kind_bonus = (
            1
            if cluster.organization_kind
            in {OrganizationKind.COMPANY, OrganizationKind.PUBLIC_INSTITUTION}
            else 0
        )
        return matched_tokens + kind_bonus

    @staticmethod
    def _looks_like_compact_org_alias(surface: str) -> bool:
        return bool(MIXED_CASE_ORG_ALIAS_PATTERN.fullmatch(surface))

    @staticmethod
    def _compact_alias_tokens(surface: str) -> list[str]:
        expanded = re.sub(r"(?<=[a-ząćęłńóśźż])(?=[A-ZŁŚŻŹĆŃÓĘ])", " ", surface)
        return [token for token in expanded.split() if token]

    def _encode_text(self, text: str) -> np.ndarray:
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached
        model = self.runtime.get_sentence_transformer_model()
        try:
            encoded = model.encode(text, normalize_embeddings=True)
        except TypeError:
            encoded = model.encode(text)
        vector = np.asarray(encoded, dtype=float)
        if vector.ndim != 1:
            vector = vector.reshape(-1)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        self._embedding_cache[text] = vector
        return vector

    @staticmethod
    def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
        if left.size == 0 or right.size == 0:
            return 0.0
        return float(np.dot(left, right))

    @staticmethod
    def _deduplicate_grounded_mentions(
        mentions: list[GroundedOrganizationMention],
    ) -> list[GroundedOrganizationMention]:
        deduplicated: dict[tuple[str, int, int, int], GroundedOrganizationMention] = {}
        for mention in mentions:
            key = (
                mention.canonical_name.casefold(),
                mention.evidence.sentence_index,
                mention.evidence.start_char,
                mention.evidence.end_char,
            )
            current = deduplicated.get(key)
            if current is None or len(current.canonical_name) < len(mention.canonical_name):
                deduplicated[key] = mention
        return list(deduplicated.values())

    def _role_candidate_near_employee(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        employee: EntityCluster,
    ) -> _RoleLabelCandidate | None:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        employee_words = [
            word
            for mention in employee.mentions
            if mention.sentence_index == clause.sentence_index
            for word in parsed_words
            if self._mention_local_start(mention, clause)
            <= word.start
            < self._mention_local_end(mention, clause)
        ]
        for employee_word in employee_words:
            stanowisko = self._first_descendant_with_lemma(
                parsed_words,
                employee_word.index,
                "stanowisko",
            )
            if stanowisko is not None and (
                candidate := self._role_candidate_from_subtree(parsed_words, stanowisko.index)
            ):
                return candidate
            governing_word = word_by_index(parsed_words, employee_word.head)
            if governing_word is None:
                continue
            stanowisko = self._first_child_with_lemma(
                parsed_words,
                governing_word.index,
                "stanowisko",
            )
            if stanowisko is not None and (
                candidate := self._role_candidate_from_subtree(parsed_words, stanowisko.index)
            ):
                return candidate
        return None

    def _role_candidate_for_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> _RoleLabelCandidate | None:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        if candidate := self._role_candidate_from_words(parsed_words):
            return candidate
        lowered = clause.text.casefold()
        for marker in (
            "jako",
            "na stanowisku",
            "w charakterze",
            "dostał pracę jako",
            "dostała pracę jako",
            "objął funkcję",
            "objęła funkcję",
        ):
            marker_index = lowered.find(marker)
            if marker_index >= 0 and (
                candidate := self._role_candidate_from_tail(
                    document,
                    clause,
                    marker_index + len(marker),
                )
            ):
                return candidate
        return None

    def _role_candidate_from_words(
        self,
        parsed_words: list[ParsedWord],
    ) -> _RoleLabelCandidate | None:
        marker_indices = [
            index
            for index, word in enumerate(parsed_words)
            if (word.lemma or word.text).casefold()
            in frozenset({"zatrudnić", "dostać", "objąć", "zostać", "trafić", "pracować", "być"})
            or word.text.casefold() == "jako"
        ]
        if not marker_indices:
            return None
        marker_index = next(
            (index for index in marker_indices if parsed_words[index].text.casefold() == "jako"),
            marker_indices[0],
        )
        phrase_words: list[ParsedWord] = []
        source = "role_phrase"
        for word in parsed_words[marker_index + 1 :]:
            lemma = (word.lemma or word.text).casefold()
            if lemma in ROLE_STOP_WORDS or word.upos in {"ADP", "SCONJ", "CCONJ", "VERB"}:
                if phrase_words:
                    break
                continue
            if lemma in PUBLIC_EMPLOYER_TERMS:
                break
            if lemma == "stanowisko" and not phrase_words:
                source = "stanowisko_phrase"
                continue
            if word.upos in {"ADJ", "NOUN", "PROPN"}:
                phrase_words.append(word)
                if len(phrase_words) >= 4:
                    break
            elif phrase_words:
                break
        if not phrase_words:
            return None
        label = normalize_entity_name(
            " ".join(
                word.text if word.deprel.casefold() == "nmod" or word.upos == "ADJ" else word.lemma
                for word in phrase_words
            )
        )
        return _RoleLabelCandidate(
            label=label,
            head_lemma=self._role_head_lemma(phrase_words),
            words=tuple(phrase_words),
            source=source,
        )

    def _role_candidate_from_subtree(
        self,
        parsed_words: list[ParsedWord],
        head_index: int,
    ) -> _RoleLabelCandidate | None:
        by_head: dict[int, list[ParsedWord]] = {}
        for word in parsed_words:
            by_head.setdefault(word.head, []).append(word)
        head_nouns = [
            word
            for word in by_head.get(head_index, [])
            if word.upos in {"NOUN", "PROPN"}
            and (word.lemma or word.text).casefold() != "stanowisko"
        ]
        if not head_nouns:
            return None
        head = min(head_nouns, key=lambda word: word.start)
        phrase_words = [head]
        phrase_words.extend(
            word for word in by_head.get(head.index, []) if word.upos in {"ADJ", "NOUN", "PROPN"}
        )
        ordered_words = tuple(sorted(phrase_words, key=lambda word: word.start)[:4])
        has_preceding_modifier = any(
            word.index != head.index and word.start < head.start for word in ordered_words
        )
        label = normalize_entity_name(
            " ".join(
                self._role_label_token(
                    word,
                    head,
                    has_preceding_modifier=has_preceding_modifier,
                )
                for word in ordered_words
            )
        )
        return _RoleLabelCandidate(
            label=label,
            head_lemma=(head.lemma or head.text).casefold(),
            words=ordered_words,
            source="stanowisko_subtree",
        )

    def _role_candidate_from_tail(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        start_offset: int,
    ) -> _RoleLabelCandidate | None:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        words = [
            word
            for word in parsed_words
            if word.start >= start_offset and word.upos in {"ADJ", "NOUN", "PROPN"}
        ]
        phrase_words: list[ParsedWord] = []
        for word in words:
            lemma = (word.lemma or word.text).casefold()
            if lemma in ROLE_STOP_WORDS:
                break
            if lemma in {"zatrudniony", "zatrudniona", "praca", "pracę"}:
                continue
            if lemma in PUBLIC_EMPLOYER_TERMS:
                break
            phrase_words.append(word)
            if len(phrase_words) >= 4:
                break
        if not phrase_words:
            return None
        label = normalize_entity_name(
            " ".join(word.text if word.upos == "ADJ" else word.lemma for word in phrase_words)
        )
        return _RoleLabelCandidate(
            label=label,
            head_lemma=self._role_head_lemma(phrase_words),
            words=tuple(phrase_words),
            source="role_tail",
        )

    def _invalid_role_candidate(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        candidate: _RoleLabelCandidate,
    ) -> bool:
        label = candidate.label
        if not label:
            return True
        first_token = label.split()[0].casefold() if label.split() else ""
        if first_token in INVALID_PUBLIC_EMPLOYMENT_ROLE_HEADS:
            return True
        if any(token.casefold() in ROLE_NOISE_TOKENS for token in label.split()):
            return True
        if DATE_ROLE_PATTERN.search(label):
            return True
        if any((word.lemma or word.text).casefold() in KINSHIP_LEMMAS for word in candidate.words):
            return True
        if (
            candidate.source != "stanowisko_subtree"
            and candidate.head_lemma not in ROLE_ANCHOR_HEADS
        ):
            return True
        if any(word.upos == "PROPN" for word in candidate.words):
            person_tokens = {
                token.casefold()
                for cluster in document.clusters
                if cluster.entity_type == EntityType.PERSON
                for mention in cluster.mentions
                if mention.sentence_index == clause.sentence_index
                for token in mention.text.split()
            }
            if any(
                (word.text or word.lemma).casefold() in person_tokens for word in candidate.words
            ):
                return True
        if any(
            cluster.entity_type == EntityType.POSITION
            and cluster.role_kind in PUBLIC_OFFICE_ROLE_KINDS
            and cluster.canonical_name.casefold() == label.casefold()
            for cluster in document.clusters
        ):
            return True
        return False

    @staticmethod
    def _slot_evidence_for_cluster(
        clause: ClauseUnit,
        cluster: EntityCluster,
    ) -> SlotEvidence | None:
        mention = next(
            (item for item in cluster.mentions if item.sentence_index == clause.sentence_index),
            None,
        )
        if mention is None:
            return None
        return SlotEvidence(
            text=mention.text,
            sentence_index=mention.sentence_index,
            paragraph_index=mention.paragraph_index,
            start_char=mention.start_char,
            end_char=mention.end_char,
        )

    @staticmethod
    def _slot_evidence_for_words(
        clause: ClauseUnit,
        words: tuple[ParsedWord, ...],
    ) -> SlotEvidence:
        start = clause.start_char + min(word.start for word in words)
        end = clause.start_char + max(word.end for word in words)
        local_start = min(word.start for word in words)
        local_end = max(word.end for word in words)
        return SlotEvidence(
            text=clause.text[local_start:local_end],
            sentence_index=clause.sentence_index,
            paragraph_index=clause.paragraph_index,
            start_char=start,
            end_char=end,
        )

    @staticmethod
    def _role_head_lemma(words: list[ParsedWord]) -> str:
        noun = next(
            (
                word
                for word in words
                if word.upos in {"NOUN", "PROPN"} and word.deprel.casefold() != "amod"
            ),
            None,
        )
        if noun is None:
            noun = next((word for word in words if word.upos in {"NOUN", "PROPN"}), words[0])
        return (noun.lemma or noun.text).casefold()

    @staticmethod
    def _first_child_with_lemma(
        parsed_words: list[ParsedWord],
        head_index: int,
        lemma: str,
    ) -> ParsedWord | None:
        return next(
            (
                word
                for word in parsed_words
                if word.head == head_index and (word.lemma or word.text).casefold() == lemma
            ),
            None,
        )

    def _first_descendant_with_lemma(
        self,
        parsed_words: list[ParsedWord],
        head_index: int,
        lemma: str,
        *,
        seen: set[int] | None = None,
    ) -> ParsedWord | None:
        if seen is None:
            seen = set()
        if head_index in seen:
            return None
        seen.add(head_index)
        for child in parsed_words:
            if child.head != head_index:
                continue
            if (child.lemma or child.text).casefold() == lemma:
                return child
            if descendant := self._first_descendant_with_lemma(
                parsed_words,
                child.index,
                lemma,
                seen=seen,
            ):
                return descendant
        return None

    @staticmethod
    def _role_label_token(
        word: ParsedWord,
        head: ParsedWord,
        *,
        has_preceding_modifier: bool,
    ) -> str:
        if word.index == head.index and has_preceding_modifier:
            return word.lemma
        if word.upos == "ADJ" and word.start < head.start:
            return word.lemma
        if word.deprel.casefold() == "amod" and word.start > head.start and head.deprel == "nmod":
            return word.text
        if word.deprel.casefold() == "nmod" or word.upos == "ADJ":
            return word.text
        return word.lemma

    @staticmethod
    def _mention_local_start(mention: ClusterMention, clause: ClauseUnit) -> int:
        return max(0, mention.start_char - clause.start_char)

    @staticmethod
    def _mention_local_end(mention: ClusterMention, clause: ClauseUnit) -> int:
        return max(0, mention.end_char - clause.start_char)

    @staticmethod
    def _is_public_office_role(cluster: EntityCluster) -> bool:
        if cluster.role_kind in PUBLIC_OFFICE_ROLE_KINDS:
            return True
        normalized = cluster.normalized_name.casefold()
        return any(
            marker in normalized
            for marker in ("wójt", "wojt", "starosta", "sekretarz", "marszałek", "wojewoda")
        )
