from __future__ import annotations

import uuid
from dataclasses import dataclass

from pipeline.base import IdentityResolver
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    ClusterID,
    EntityID,
    EntityType,
    FactID,
    FactType,
    IdentityHypothesisReason,
    IdentityHypothesisStatus,
    KinshipDetail,
    ProxyKind,
    RelationshipType,
    TimeScope,
)
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    Fact,
    IdentityHypothesis,
    Mention,
    ParsedWord,
    SentenceFragment,
)
from pipeline.utils import normalize_entity_name, stable_id

KINSHIP_BY_LEMMA: dict[str, KinshipDetail] = {
    "żona": KinshipDetail.SPOUSE,
    "małżonka": KinshipDetail.SPOUSE,
    "mąż": KinshipDetail.SPOUSE,
    "małżonek": KinshipDetail.SPOUSE,
    "partnerka": KinshipDetail.PARTNER,
    "partner": KinshipDetail.PARTNER,
    "siostra": KinshipDetail.SIBLING_SISTER,
    "brat": KinshipDetail.SIBLING_BROTHER,
    "córka": KinshipDetail.CHILD_DAUGHTER,
    "syn": KinshipDetail.CHILD_SON,
}
POSSESSIVE_LEMMAS = {"mój"}
HONORIFIC_LEMMAS = {"pani"}
SPEECH_LEMMAS = {
    "mówić",
    "powiedzieć",
    "tłumaczyć",
    "przekonywać",
    "dodać",
    "komentować",
    "zaznaczyć",
    "podkreślić",
    "wyjaśnić",
    "ocenić",
    "przypomnieć",
    "stwierdzić",
    "odnieść",
}


@dataclass(slots=True)
class _FamilyMention:
    kinship_detail: KinshipDetail
    surface: str
    start_char: int
    end_char: int
    anchor_surface: str | None = None
    is_possessive: bool = False


@dataclass(slots=True)
class _HonorificMention:
    surface: str
    surname: str
    start_char: int
    end_char: int


@dataclass(slots=True)
class _ProxyRecord:
    entity: Entity
    cluster: EntityCluster
    kinship_detail: KinshipDetail
    anchor_entity_id: str
    anchor_cluster_id: str


class PolishFamilyIdentityResolver(IdentityResolver):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_family_identity_resolver"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        _ = self.config
        proxies: list[_ProxyRecord] = []
        for sentence in document.sentences:
            words = document.parsed_sentences.get(sentence.sentence_index, [])
            for mention in self._family_mentions(sentence, words):
                anchor = (
                    self._resolve_possessive_anchor(document, sentence.sentence_index)
                    if mention.is_possessive
                    else self._resolve_anchor(
                        document,
                        sentence.sentence_index,
                        mention.anchor_surface,
                    )
                )
                if anchor is None:
                    continue
                proxies.append(
                    self._ensure_proxy(
                        document,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=mention.start_char,
                        end_char=mention.end_char,
                        surface=mention.surface,
                        kinship_detail=mention.kinship_detail,
                        anchor=anchor,
                    )
                )

            for mention in self._honorific_mentions(sentence, words):
                self._add_honorific_hypotheses(
                    document,
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    start_char=mention.start_char,
                    end_char=mention.end_char,
                    surface=mention.surface,
                    surname=mention.surname,
                )

        self._add_proxy_family_facts(document, proxies)
        self._add_proxy_identity_hypotheses(document, proxies)
        self._add_full_name_identity_hypotheses(document)
        self._refresh_clause_mentions(document)
        return document

    def _family_mentions(
        self,
        sentence: SentenceFragment,
        words: list[ParsedWord],
    ) -> list[_FamilyMention]:
        mentions: list[_FamilyMention] = []
        for index, word in enumerate(words):
            kinship_detail = self._kinship_detail(word)
            if kinship_detail is None:
                continue
            possessive_word = self._possessive_modifier(words, word, index)
            if possessive_word is not None:
                start = sentence.start_char + min(possessive_word.start, word.start)
                end = sentence.start_char + max(possessive_word.end, word.end)
                surface = self._surface_for_span(sentence, start, end, [possessive_word, word])
                if not surface:
                    continue
                mentions.append(
                    _FamilyMention(
                        kinship_detail=kinship_detail,
                        surface=surface,
                        start_char=start,
                        end_char=end,
                        is_possessive=True,
                    )
                )
                continue

            anchor_words = self._anchor_words(words, index)
            if not anchor_words:
                continue
            start = sentence.start_char + word.start
            end = sentence.start_char + anchor_words[-1].end
            anchor_surface = self._surface_from_words(sentence, anchor_words)
            surface = self._surface_for_span(sentence, start, end, [word, *anchor_words])
            if not surface:
                continue
            mentions.append(
                _FamilyMention(
                    kinship_detail=kinship_detail,
                    surface=surface,
                    start_char=start,
                    end_char=end,
                    anchor_surface=anchor_surface,
                )
            )
        return mentions

    @staticmethod
    def _honorific_mentions(
        sentence: SentenceFragment,
        words: list[ParsedWord],
    ) -> list[_HonorificMention]:
        mentions: list[_HonorificMention] = []
        for index, word in enumerate(words[:-1]):
            if word.lemma.casefold() not in HONORIFIC_LEMMAS:
                continue
            surname_word = words[index + 1]
            if surname_word.upos not in {"PROPN", "NOUN"}:
                continue
            if not surname_word.text[:1].isupper():
                continue
            start = sentence.start_char + word.start
            end = sentence.start_char + surname_word.end
            surface = PolishFamilyIdentityResolver._surface_for_span(
                sentence,
                start,
                end,
                [word, surname_word],
            )
            if not surface:
                continue
            mentions.append(
                _HonorificMention(
                    surface=surface,
                    surname=surname_word.text,
                    start_char=start,
                    end_char=end,
                )
            )
        return mentions

    @staticmethod
    def _kinship_detail(word: ParsedWord) -> KinshipDetail | None:
        lemma = normalize_entity_name(word.lemma).casefold()
        text = normalize_entity_name(word.text).casefold()
        return KINSHIP_BY_LEMMA.get(lemma) or KINSHIP_BY_LEMMA.get(text)

    @staticmethod
    def _possessive_modifier(
        words: list[ParsedWord],
        kinship_word: ParsedWord,
        kinship_index: int,
    ) -> ParsedWord | None:
        candidates = [
            word
            for word in words
            if word.head == kinship_word.index
            and word.lemma.casefold() in POSSESSIVE_LEMMAS
            and word.deprel.startswith("det")
        ]
        if candidates:
            return candidates[0]
        if kinship_index > 0 and words[kinship_index - 1].lemma.casefold() in POSSESSIVE_LEMMAS:
            return words[kinship_index - 1]
        return None

    @staticmethod
    def _anchor_words(words: list[ParsedWord], kinship_index: int) -> list[ParsedWord]:
        after = words[kinship_index + 1 : kinship_index + 5]
        if (
            len(after) >= 2
            and after[0].lemma.casefold() == "pan"
            and after[1].lemma.casefold() == "przewodniczący"
        ):
            return after[:2]
        proper: list[ParsedWord] = []
        for word in after:
            if word.upos != "PROPN":
                break
            proper.append(word)
        return proper

    @staticmethod
    def _surface_from_words(sentence: SentenceFragment, words: list[ParsedWord]) -> str:
        if not words:
            return ""
        return PolishFamilyIdentityResolver._surface_for_span(
            sentence,
            sentence.start_char + words[0].start,
            sentence.start_char + words[-1].end,
            words,
        )

    @staticmethod
    def _sentence_slice(sentence: SentenceFragment, start_char: int, end_char: int) -> str:
        local_start = max(0, start_char - sentence.start_char)
        local_end = max(local_start, end_char - sentence.start_char)
        return sentence.text[local_start:local_end]

    @staticmethod
    def _surface_for_span(
        sentence: SentenceFragment,
        start_char: int,
        end_char: int,
        words: list[ParsedWord],
    ) -> str:
        surface = PolishFamilyIdentityResolver._sentence_slice(sentence, start_char, end_char)
        if surface.strip():
            return surface
        return " ".join(word.text for word in words if word.text).strip()

    def _ensure_proxy(
        self,
        document: ArticleDocument,
        *,
        sentence_index: int,
        paragraph_index: int,
        start_char: int,
        end_char: int,
        surface: str,
        kinship_detail: KinshipDetail,
        anchor: EntityCluster,
    ) -> _ProxyRecord:
        anchor_entity_id = self._best_entity_id(anchor)
        canonical_name = normalize_entity_name(surface)
        entity_id = EntityID(
            stable_id(
                "proxy_person",
                document.document_id,
                canonical_name,
                anchor_entity_id,
                kinship_detail.value,
            )
        )
        existing_entity = next(
            (entity for entity in document.entities if entity.entity_id == entity_id),
            None,
        )
        evidence = EvidenceSpan(
            text=surface,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
        )
        if existing_entity is None:
            existing_entity = Entity(
                entity_id=entity_id,
                entity_type=EntityType.PERSON,
                canonical_name=canonical_name,
                normalized_name=canonical_name,
                aliases=[surface],
                is_proxy_person=True,
                proxy_kind=ProxyKind.FAMILY,
                kinship_detail=kinship_detail,
                proxy_anchor_entity_id=EntityID(anchor_entity_id),
                proxy_surface=surface,
                lemmas=[kinship_detail.value],
                evidence=[evidence],
            )
            document.entities.append(existing_entity)
            document.mentions.append(
                Mention(
                    text=surface,
                    normalized_text=canonical_name,
                    mention_type=EntityType.PERSON.value,
                    sentence_index=sentence_index,
                    paragraph_index=paragraph_index,
                    start_char=start_char,
                    end_char=end_char,
                    entity_id=entity_id,
                )
            )
        elif not any(
            span.start_char == start_char and span.sentence_index == sentence_index
            for span in existing_entity.evidence
        ):
            existing_entity.evidence.append(evidence)

        cluster = self._ensure_proxy_cluster(
            document,
            existing_entity,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
            surface=surface,
        )
        return _ProxyRecord(
            entity=existing_entity,
            cluster=cluster,
            kinship_detail=kinship_detail,
            anchor_entity_id=anchor_entity_id,
            anchor_cluster_id=anchor.cluster_id,
        )

    def _ensure_proxy_cluster(
        self,
        document: ArticleDocument,
        entity: Entity,
        *,
        sentence_index: int,
        paragraph_index: int,
        start_char: int,
        end_char: int,
        surface: str,
    ) -> EntityCluster:
        existing = next(
            (
                cluster
                for cluster in document.clusters
                if cluster.proxy_entity_id == entity.entity_id
            ),
            None,
        )
        mention = ClusterMention(
            text=surface,
            entity_type=EntityType.PERSON,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
            entity_id=entity.entity_id,
        )
        if existing is None:
            cluster = EntityCluster(
                cluster_id=ClusterID(f"cluster-proxy-{uuid.uuid4().hex[:8]}"),
                entity_type=EntityType.PERSON,
                canonical_name=entity.canonical_name,
                normalized_name=entity.normalized_name,
                mentions=[mention],
                aliases=list(entity.aliases),
                is_proxy_person=True,
                proxy_entity_id=entity.entity_id,
                proxy_kind=ProxyKind.FAMILY,
                kinship_detail=entity.kinship_detail,
                proxy_anchor_entity_id=entity.proxy_anchor_entity_id,
            )
            document.clusters.append(cluster)
            return cluster
        if not any(
            item.start_char == start_char and item.sentence_index == sentence_index
            for item in existing.mentions
        ):
            existing.mentions.append(mention)
        return existing

    def _add_proxy_family_facts(
        self,
        document: ArticleDocument,
        proxies: list[_ProxyRecord],
    ) -> None:
        seen = {fact.fact_id for fact in document.facts}
        for proxy in proxies:
            evidence = proxy.entity.evidence[-1] if proxy.entity.evidence else EvidenceSpan(text="")
            fact_id = FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.PERSONAL_OR_POLITICAL_TIE,
                    proxy.entity.entity_id,
                    proxy.anchor_entity_id,
                    proxy.kinship_detail.value,
                )
            )
            if fact_id in seen:
                continue
            document.facts.append(
                Fact(
                    fact_id=fact_id,
                    fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                    subject_entity_id=proxy.entity.entity_id,
                    object_entity_id=EntityID(proxy.anchor_entity_id),
                    value_text=proxy.kinship_detail.value,
                    value_normalized=proxy.kinship_detail.value,
                    time_scope=TimeScope.CURRENT,
                    event_date=document.publication_date,
                    confidence=0.86,
                    evidence=evidence,
                    relationship_type=RelationshipType.FAMILY,
                    kinship_detail=proxy.kinship_detail,
                    source_extractor="family_identity_resolver",
                    extraction_signal="family_proxy",
                )
            )
            seen.add(fact_id)

    def _add_proxy_identity_hypotheses(
        self,
        document: ArticleDocument,
        proxies: list[_ProxyRecord],
    ) -> None:
        by_anchor_and_kind: dict[tuple[str, KinshipDetail], _ProxyRecord] = {}
        for proxy in proxies:
            family_group = self._family_group(proxy.kinship_detail)
            if family_group is None:
                continue
            key = (proxy.anchor_entity_id, family_group)
            previous = by_anchor_and_kind.get(key)
            if previous is not None and previous.entity.entity_id != proxy.entity.entity_id:
                self._add_hypothesis(
                    document,
                    previous.entity.entity_id,
                    proxy.entity.entity_id,
                    confidence=0.78,
                    status=IdentityHypothesisStatus.PROBABLE,
                    reason=IdentityHypothesisReason.SAME_ANCHOR_COMPATIBLE_FAMILY_PROXY,
                    evidence=[*previous.entity.evidence[-1:], *proxy.entity.evidence[-1:]],
                )
                continue
            by_anchor_and_kind[key] = proxy

    def _add_full_name_identity_hypotheses(self, document: ArticleDocument) -> None:
        proxies = [
            entity
            for entity in document.entities
            if entity.entity_type == EntityType.PERSON and entity.is_proxy_person
        ]
        full_people = [
            entity
            for entity in document.entities
            if entity.entity_type == EntityType.PERSON
            and not entity.is_proxy_person
            and not entity.is_honorific_person_ref
            and len(entity.canonical_name.split()) >= 2
        ]
        for proxy in proxies:
            anchor_id = proxy.proxy_anchor_entity_id
            if anchor_id is None:
                continue
            anchor = self._entity_by_id(document, anchor_id)
            if anchor is None:
                continue
            anchor_surname = self._surname(anchor.canonical_name)
            proxy_kind = proxy.kinship_detail
            for person in full_people:
                if person.entity_id == anchor_id:
                    continue
                if not self._surname_tokens_compatible(
                    self._surname(person.canonical_name),
                    anchor_surname,
                ):
                    continue
                status = IdentityHypothesisStatus.POSSIBLE
                confidence = 0.55
                reason = IdentityHypothesisReason.SURNAME_COMPATIBLE_FAMILY_PROXY
                if self._near_family_context(document, person, proxy):
                    status = IdentityHypothesisStatus.PROBABLE
                    confidence = 0.74
                    reason = IdentityHypothesisReason.SURNAME_COMPATIBLE_NEAR_FAMILY_CONTEXT
                if proxy_kind in {KinshipDetail.SIBLING_SISTER, KinshipDetail.SIBLING_BROTHER}:
                    status = IdentityHypothesisStatus.POSSIBLE
                    confidence = min(confidence, 0.56)
                self._add_hypothesis(
                    document,
                    proxy.entity_id,
                    person.entity_id,
                    confidence=confidence,
                    status=status,
                    reason=reason,
                    evidence=[*proxy.evidence[-1:], *person.evidence[-1:]],
                )

    def _add_honorific_hypotheses(
        self,
        document: ArticleDocument,
        *,
        sentence_index: int,
        paragraph_index: int,
        start_char: int,
        end_char: int,
        surface: str,
        surname: str,
    ) -> None:
        entity = self._ensure_honorific_entity(
            document,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
            surface=surface,
        )
        for candidate in document.entities:
            if (
                candidate.entity_type != EntityType.PERSON
                or candidate.entity_id == entity.entity_id
            ):
                continue
            if not self._surname_tokens_compatible(
                self._surname(candidate.canonical_name),
                normalize_entity_name(surname),
            ):
                continue
            self._add_hypothesis(
                document,
                entity.entity_id,
                candidate.entity_id,
                confidence=0.48,
                status=IdentityHypothesisStatus.POSSIBLE,
                reason=IdentityHypothesisReason.HONORIFIC_SURNAME_ONLY,
                evidence=[entity.evidence[-1], *candidate.evidence[-1:]],
            )

    def _ensure_honorific_entity(
        self,
        document: ArticleDocument,
        *,
        sentence_index: int,
        paragraph_index: int,
        start_char: int,
        end_char: int,
        surface: str,
    ) -> Entity:
        canonical = normalize_entity_name(surface)
        if not canonical:
            raise ValueError("Cannot create honorific person reference from an empty surface.")
        entity_id = EntityID(
            stable_id("person_ref", document.document_id, canonical, str(start_char))
        )
        existing = self._entity_by_id(document, entity_id)
        if existing is not None:
            return existing
        evidence = EvidenceSpan(
            text=surface,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
        )
        entity = Entity(
            entity_id=EntityID(entity_id),
            entity_type=EntityType.PERSON,
            canonical_name=canonical,
            normalized_name=canonical,
            aliases=[surface],
            is_honorific_person_ref=True,
            evidence=[evidence],
        )
        document.entities.append(entity)
        document.mentions.append(
            Mention(
                text=surface,
                normalized_text=canonical,
                mention_type=EntityType.PERSON.value,
                sentence_index=sentence_index,
                paragraph_index=paragraph_index,
                start_char=start_char,
                end_char=end_char,
                entity_id=EntityID(entity_id),
            )
        )
        document.clusters.append(
            EntityCluster(
                cluster_id=ClusterID(f"cluster-ref-{uuid.uuid4().hex[:8]}"),
                entity_type=EntityType.PERSON,
                canonical_name=canonical,
                normalized_name=canonical,
                mentions=[
                    ClusterMention(
                        text=surface,
                        entity_type=EntityType.PERSON,
                        sentence_index=sentence_index,
                        paragraph_index=paragraph_index,
                        start_char=start_char,
                        end_char=end_char,
                        entity_id=EntityID(entity_id),
                    )
                ],
                aliases=[surface],
            )
        )
        return entity

    def _refresh_clause_mentions(self, document: ArticleDocument) -> None:
        for clause in document.clause_units:
            for cluster in document.clusters:
                for mention in cluster.mentions:
                    if mention.sentence_index != clause.sentence_index:
                        continue
                    if not (
                        clause.start_char <= mention.start_char
                        and mention.end_char <= clause.end_char
                    ):
                        continue
                    if any(
                        existing.start_char == mention.start_char
                        and existing.end_char == mention.end_char
                        and existing.entity_type == mention.entity_type
                        for existing in clause.cluster_mentions
                    ):
                        continue
                    clause.cluster_mentions.append(mention)
                    role = self._mention_dependency_role(document, clause.sentence_index, mention)
                    if role is not None:
                        clause.mention_roles[mention.text] = role

    @staticmethod
    def _mention_dependency_role(
        document: ArticleDocument,
        sentence_index: int,
        mention: ClusterMention,
    ) -> str | None:
        sentence = next(
            (item for item in document.sentences if item.sentence_index == sentence_index),
            None,
        )
        if sentence is None:
            return None
        for word in document.parsed_sentences.get(sentence_index, []):
            abs_start = sentence.start_char + word.start
            if mention.start_char <= abs_start < mention.end_char:
                return word.deprel
        return None

    def _resolve_anchor(
        self,
        document: ArticleDocument,
        sentence_index: int,
        anchor_surface: str | None,
    ) -> EntityCluster | None:
        if anchor_surface is None:
            return None
        normalized = normalize_entity_name(anchor_surface)
        if "przewodnicz" in normalized.casefold():
            return self._nearest_person_cluster(document, sentence_index, before=3, after=0)
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type == EntityType.PERSON
            and not cluster.is_proxy_person
            and (
                cluster.canonical_name == normalized
                or normalized in cluster.aliases
                or self._surnames_compatible(cluster.canonical_name, normalized)
            )
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda cluster: self._cluster_sentence_distance(cluster, sentence_index),
        )

    def _resolve_possessive_anchor(
        self,
        document: ArticleDocument,
        sentence_index: int,
    ) -> EntityCluster | None:
        return self._speaker_cluster(document, sentence_index)

    @staticmethod
    def _speaker_cluster(document: ArticleDocument, sentence_index: int) -> EntityCluster | None:
        cluster = PolishFamilyIdentityResolver._speaker_cluster_raw(document, sentence_index)
        if cluster is not None:
            return cluster

        # Fallback for split quotes: check the next sentence if current is a quote
        sentence = next(
            (item for item in document.sentences if item.sentence_index == sentence_index),
            None,
        )
        if sentence and (
            sentence.text.strip().startswith("–")
            or sentence.text.strip().startswith("—")
            or sentence.text.strip().startswith('"')
        ):
            next_index = sentence_index + 1
            next_sentence = next(
                (item for item in document.sentences if item.sentence_index == next_index),
                None,
            )
            if next_sentence and next_sentence.paragraph_index == sentence.paragraph_index:
                return PolishFamilyIdentityResolver._speaker_cluster_raw(document, next_index)

        return None

    @staticmethod
    def _speaker_cluster_raw(
        document: ArticleDocument,
        sentence_index: int,
    ) -> EntityCluster | None:
        parsed = document.parsed_sentences.get(sentence_index, [])
        speech_heads = {word.index for word in parsed if word.lemma.casefold() in SPEECH_LEMMAS}
        if not speech_heads:
            return None
        sentence = next(
            (item for item in document.sentences if item.sentence_index == sentence_index),
            None,
        )
        if sentence is None:
            return None
        speaker_words = [
            word for word in parsed if word.head in speech_heads and word.deprel.startswith("nsubj")
        ]
        for cluster in document.clusters:
            if cluster.entity_type != EntityType.PERSON or cluster.is_proxy_person:
                continue
            for mention in cluster.mentions:
                if mention.sentence_index != sentence_index:
                    continue
                for word in speaker_words:
                    abs_start = sentence.start_char + word.start
                    if mention.start_char <= abs_start < mention.end_char:
                        return cluster
        return None

    @staticmethod
    def _nearest_person_cluster(
        document: ArticleDocument,
        sentence_index: int,
        *,
        before: int,
        after: int,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type == EntityType.PERSON
            and not cluster.is_proxy_person
            and any(
                sentence_index - before <= mention.sentence_index <= sentence_index + after
                for mention in cluster.mentions
            )
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda cluster: PolishFamilyIdentityResolver._cluster_sentence_distance(
                cluster,
                sentence_index,
            ),
        )

    @staticmethod
    def _cluster_sentence_distance(cluster: EntityCluster, sentence_index: int) -> tuple[int, int]:
        distances = [
            (abs(mention.sentence_index - sentence_index), mention.start_char)
            for mention in cluster.mentions
        ]
        return min(distances, default=(9999, 9999))

    def _near_family_context(
        self,
        document: ArticleDocument,
        person: Entity,
        proxy: Entity,
    ) -> bool:
        proxy_sentences = {
            evidence.sentence_index
            for evidence in proxy.evidence
            if evidence.sentence_index is not None
        }
        person_sentences = {
            evidence.sentence_index
            for evidence in person.evidence
            if evidence.sentence_index is not None
        }
        if not proxy_sentences or not person_sentences:
            return False
        if min(abs(left - right) for left in proxy_sentences for right in person_sentences) > 1:
            return False
        window = {
            index + delta for index in person_sentences | proxy_sentences for delta in {-1, 0, 1}
        }
        for sentence in document.sentences:
            if sentence.sentence_index not in window:
                continue
            parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
            if parsed_words and any(
                word.lemma.casefold() in KINSHIP_BY_LEMMA for word in parsed_words
            ):
                return True
            if not parsed_words and any(
                term in sentence.text.casefold() for term in KINSHIP_BY_LEMMA
            ):
                return True
        return False

    def _add_hypothesis(
        self,
        document: ArticleDocument,
        left_entity_id: str,
        right_entity_id: str,
        *,
        confidence: float,
        reason: IdentityHypothesisReason,
        evidence: list[EvidenceSpan],
        status: IdentityHypothesisStatus,
    ) -> None:
        if left_entity_id == right_entity_id:
            return
        key = frozenset({left_entity_id, right_entity_id})
        existing = next(
            (
                hypothesis
                for hypothesis in document.identity_hypotheses
                if frozenset({hypothesis.left_entity_id, hypothesis.right_entity_id}) == key
            ),
            None,
        )
        if existing is None:
            document.identity_hypotheses.append(
                IdentityHypothesis(
                    left_entity_id=EntityID(left_entity_id),
                    right_entity_id=EntityID(right_entity_id),
                    confidence=confidence,
                    reason=reason,
                    evidence=evidence,
                    status=status,
                )
            )
            return
        if confidence > existing.confidence:
            existing.confidence = confidence
            existing.reason = reason
            existing.evidence = evidence
            existing.status = status

    @staticmethod
    def _family_group(kinship_detail: KinshipDetail) -> KinshipDetail | None:
        if kinship_detail in {KinshipDetail.SPOUSE, KinshipDetail.PARTNER}:
            return KinshipDetail.PARTNER
        if kinship_detail in {KinshipDetail.SIBLING_SISTER, KinshipDetail.SIBLING_BROTHER}:
            return KinshipDetail.SIBLING_SISTER
        return None

    @staticmethod
    def _entity_by_id(document: ArticleDocument, entity_id: str) -> Entity | None:
        return next((entity for entity in document.entities if entity.entity_id == entity_id), None)

    @staticmethod
    def _best_entity_id(cluster: EntityCluster) -> str:
        for mention in cluster.mentions:
            if mention.entity_id:
                return mention.entity_id
        return cluster.cluster_id

    @staticmethod
    def _surname(name: str) -> str:
        tokens = normalize_entity_name(name).split()
        if not tokens:
            return ""
        return tokens[-1]

    @classmethod
    def _surnames_compatible(cls, left_name: str, right_name: str) -> bool:
        return cls._surname_tokens_compatible(cls._surname(left_name), cls._surname(right_name))

    @staticmethod
    def _surname_tokens_compatible(left: str, right: str) -> bool:
        left_key = left.rstrip(".").casefold()
        right_key = right.rstrip(".").casefold()
        if left_key == right_key:
            return True
        for suffix in ("iego", "ego", "ej", "ą", "a"):
            if left_key.endswith(suffix):
                left_key = left_key[: -len(suffix)]
                break
        for suffix in ("iego", "ego", "ej", "ą", "a"):
            if right_key.endswith(suffix):
                right_key = right_key[: -len(suffix)]
                break
        return (
            len(left_key) >= 5
            and len(right_key) >= 5
            and (left_key.startswith(right_key) or right_key.startswith(left_key))
        )
