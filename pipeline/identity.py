from __future__ import annotations

from dataclasses import dataclass

from pipeline.base import IdentityResolver
from pipeline.config import PipelineConfig
from pipeline.document_graph import (
    ensure_entity,
    ensure_entity_view,
)
from pipeline.document_graph import (
    entity_by_id as lookup_entity_by_id,
)
from pipeline.domain_lexicons import KINSHIP_BY_LEMMA
from pipeline.domain_types import (
    EntityID,
    EntityResolutionReason,
    EntityResolutionStatus,
    EntityType,
    FactID,
    FactType,
    KinshipDetail,
    MentionKind,
    ProxyKind,
    RelationshipType,
    TimeScope,
)
from pipeline.identity_signals import (
    FamilyMention,
    HonorificMention,
    collect_family_mentions,
    collect_honorific_mentions,
    resolve_anchor,
    resolve_possessive_anchor,
    surname_tokens_compatible,
)
from pipeline.identity_signals import (
    surname as surname_for_name,
)
from pipeline.models import (
    ArticleDocument,
    Entity,
    EntityCluster,
    EntityResolutionHypothesis,
    EvidenceSpan,
    Fact,
)
from pipeline.utils import normalize_entity_name, stable_id


@dataclass(slots=True)
class _ProxyRecord:
    entity: Entity
    cluster: EntityCluster
    kinship_detail: KinshipDetail
    anchor_entity_id: str
    anchor_cluster_id: str


@dataclass(slots=True)
class _ResolvedFamilyMention:
    mention: FamilyMention
    anchor: EntityCluster


class PolishFamilyIdentityResolver(IdentityResolver):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_family_identity_resolver"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        _ = self.config
        resolved_family_mentions = self._collect_resolved_family_mentions(document)
        honorific_mentions = self._collect_honorific_mentions(document)
        proxies = self._materialize_family_proxies(document, resolved_family_mentions)
        self._materialize_honorific_hypotheses(document, honorific_mentions)

        self._add_proxy_family_facts(document, proxies)
        self._add_proxy_entity_resolution_hypotheses(document, proxies)
        self._add_full_name_entity_resolution_hypotheses(document)
        self._add_single_token_family_context_hypotheses(document)
        return document

    def _collect_resolved_family_mentions(
        self,
        document: ArticleDocument,
    ) -> list[_ResolvedFamilyMention]:
        resolved: list[_ResolvedFamilyMention] = []
        for sentence in document.sentences:
            words = document.parsed_sentences.get(sentence.sentence_index, [])
            for mention in collect_family_mentions(sentence, words):
                anchor = (
                    resolve_possessive_anchor(document, sentence.sentence_index)
                    if mention.is_possessive
                    else resolve_anchor(document, sentence.sentence_index, mention.anchor_surface)
                )
                if anchor is None:
                    continue
                resolved.append(_ResolvedFamilyMention(mention=mention, anchor=anchor))
        return resolved

    def _collect_honorific_mentions(
        self,
        document: ArticleDocument,
    ) -> list[HonorificMention]:
        collected: list[HonorificMention] = []
        for sentence in document.sentences:
            words = document.parsed_sentences.get(sentence.sentence_index, [])
            collected.extend(collect_honorific_mentions(sentence, words))
        return collected

    def _materialize_family_proxies(
        self,
        document: ArticleDocument,
        resolved_mentions: list[_ResolvedFamilyMention],
    ) -> list[_ProxyRecord]:
        proxies: list[_ProxyRecord] = []
        for resolved in resolved_mentions:
            mention = resolved.mention
            proxies.append(
                self._ensure_proxy(
                    document,
                    sentence_index=mention.sentence_index,
                    paragraph_index=mention.paragraph_index,
                    start_char=mention.start_char,
                    end_char=mention.end_char,
                    surface=mention.surface,
                    kinship_detail=mention.kinship_detail,
                    anchor=resolved.anchor,
                )
            )
        return proxies

    def _materialize_honorific_hypotheses(
        self,
        document: ArticleDocument,
        mentions: list[HonorificMention],
    ) -> None:
        for mention in mentions:
            self._add_honorific_hypotheses(
                document,
                sentence_index=mention.sentence_index,
                paragraph_index=mention.paragraph_index,
                start_char=mention.start_char,
                end_char=mention.end_char,
                surface=mention.surface,
                surname=mention.surname,
            )

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
        evidence = EvidenceSpan(
            text=surface,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
        )
        existing_entity = ensure_entity(
            document,
            entity_id=entity_id,
            entity_type=EntityType.PERSON,
            canonical_name=canonical_name,
            aliases=[surface],
            evidence=evidence,
            is_proxy_person=True,
            proxy_kind=ProxyKind.FAMILY,
            kinship_detail=kinship_detail,
            proxy_anchor_entity_id=EntityID(anchor_entity_id),
            lemmas=[kinship_detail.value],
        )

        cluster = ensure_entity_view(
            document,
            entity=existing_entity,
            surface=surface,
            normalized_text=canonical_name,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
            mention_kind=MentionKind.DERIVED_ENTITY,
        )
        return _ProxyRecord(
            entity=existing_entity,
            cluster=cluster,
            kinship_detail=kinship_detail,
            anchor_entity_id=anchor_entity_id,
            anchor_cluster_id=anchor.cluster_id,
        )

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

    def _add_proxy_entity_resolution_hypotheses(
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
                    status=EntityResolutionStatus.PROBABLE,
                    reason=EntityResolutionReason.SAME_ANCHOR_COMPATIBLE_FAMILY_PROXY,
                    evidence=[*previous.entity.evidence[-1:], *proxy.entity.evidence[-1:]],
                )
                continue
            by_anchor_and_kind[key] = proxy

    def _add_full_name_entity_resolution_hypotheses(self, document: ArticleDocument) -> None:
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
            anchor = lookup_entity_by_id(document, anchor_id)
            if anchor is None:
                continue
            anchor_surname = surname_for_name(anchor.canonical_name)
            proxy_kind = proxy.kinship_detail
            for person in full_people:
                if person.entity_id == anchor_id:
                    continue
                if not surname_tokens_compatible(
                    surname_for_name(person.canonical_name),
                    anchor_surname,
                ):
                    continue
                status = EntityResolutionStatus.POSSIBLE
                confidence = 0.55
                reason = EntityResolutionReason.SURNAME_COMPATIBLE_FAMILY_PROXY
                if self._near_family_context(document, person, proxy):
                    status = EntityResolutionStatus.PROBABLE
                    confidence = 0.74
                    reason = EntityResolutionReason.SURNAME_COMPATIBLE_NEAR_FAMILY_CONTEXT
                if proxy_kind in {KinshipDetail.SIBLING_SISTER, KinshipDetail.SIBLING_BROTHER}:
                    status = EntityResolutionStatus.POSSIBLE
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

    def _add_single_token_family_context_hypotheses(self, document: ArticleDocument) -> None:
        singletons = [
            entity
            for entity in document.entities
            if entity.entity_type == EntityType.PERSON
            and not entity.is_proxy_person
            and not entity.is_honorific_person_ref
            and len(entity.canonical_name.split()) == 1
        ]
        full_people = [
            entity
            for entity in document.entities
            if entity.entity_type == EntityType.PERSON
            and not entity.is_proxy_person
            and not entity.is_honorific_person_ref
            and len(entity.canonical_name.split()) >= 2
        ]
        for singleton in singletons:
            compatible_candidates = [
                person
                for person in full_people
                if person.entity_id != singleton.entity_id
                and surname_tokens_compatible(
                    surname_for_name(person.canonical_name),
                    normalize_entity_name(singleton.canonical_name),
                )
            ]
            if not compatible_candidates:
                continue
            near_candidates = [
                person
                for person in compatible_candidates
                if self._near_family_context(document, person, singleton)
            ]
            if not near_candidates:
                continue
            distant_candidates = [
                person for person in compatible_candidates if person not in near_candidates
            ]
            for person in near_candidates:
                status = (
                    EntityResolutionStatus.PROBABLE
                    if len(near_candidates) == 1
                    else EntityResolutionStatus.POSSIBLE
                )
                confidence = 0.72 if status == EntityResolutionStatus.PROBABLE else 0.52
                self._add_hypothesis(
                    document,
                    singleton.entity_id,
                    person.entity_id,
                    confidence=confidence,
                    status=status,
                    reason=EntityResolutionReason.SURNAME_ONLY_NEAR_FAMILY_CONTEXT,
                    evidence=[*singleton.evidence[-1:], *person.evidence[-1:]],
                )
            if len(distant_candidates) == 1:
                distant = distant_candidates[0]
                self._add_hypothesis(
                    document,
                    singleton.entity_id,
                    distant.entity_id,
                    confidence=0.46,
                    status=EntityResolutionStatus.POSSIBLE,
                    reason=EntityResolutionReason.SURNAME_ONLY_NEAR_FAMILY_CONTEXT,
                    evidence=[*singleton.evidence[-1:], *distant.evidence[-1:]],
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
            if not surname_tokens_compatible(
                surname_for_name(candidate.canonical_name),
                normalize_entity_name(surname),
            ):
                continue
            self._add_hypothesis(
                document,
                entity.entity_id,
                candidate.entity_id,
                confidence=0.48,
                status=EntityResolutionStatus.POSSIBLE,
                reason=EntityResolutionReason.HONORIFIC_SURNAME_ONLY,
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
        evidence = EvidenceSpan(
            text=surface,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
        )
        entity = ensure_entity(
            document,
            entity_id=entity_id,
            entity_type=EntityType.PERSON,
            canonical_name=canonical,
            aliases=[surface],
            evidence=evidence,
            is_honorific_person_ref=True,
        )
        ensure_entity_view(
            document,
            entity=entity,
            surface=surface,
            normalized_text=canonical,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            start_char=start_char,
            end_char=end_char,
            mention_kind=MentionKind.DERIVED_ENTITY,
        )
        return entity

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
        reason: EntityResolutionReason,
        evidence: list[EvidenceSpan],
        status: EntityResolutionStatus,
    ) -> None:
        if left_entity_id == right_entity_id:
            return
        key = frozenset({left_entity_id, right_entity_id})
        existing = next(
            (
                hypothesis
                for hypothesis in document.entity_resolution_hypotheses
                if frozenset({hypothesis.left_entity_id, hypothesis.right_entity_id}) == key
            ),
            None,
        )
        if existing is None:
            document.entity_resolution_hypotheses.append(
                EntityResolutionHypothesis(
                    hypothesis_id=stable_id(
                        "entity_resolution",
                        document.document_id,
                        left_entity_id,
                        right_entity_id,
                        reason.value,
                    ),
                    left_entity_id=EntityID(left_entity_id),
                    right_entity_id=EntityID(right_entity_id),
                    confidence=confidence,
                    reason=reason,
                    evidence=evidence,
                    status=status,
                    source_stage=self.name(),
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
    def _best_entity_id(cluster: EntityCluster) -> str:
        for mention in cluster.mentions:
            if mention.entity_id:
                return mention.entity_id
        return cluster.cluster_id
