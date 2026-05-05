from __future__ import annotations

import uuid
from collections import Counter

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import (
    ACCOUNTABILITY_INSTITUTION_MARKERS,
    ATTRIBUTION_SPEECH_LEMMAS,
    INVESTIGATION_NOUN_LEMMAS,
    INVESTIGATION_TRIGGER_LEMMAS,
    PROCUREMENT_ABUSE_LEMMAS,
    REFERRAL_NOUN_LEMMAS,
    REFERRAL_TRIGGER_LEMMAS,
)
from pipeline.domain_types import (
    ClusterID,
    EntityID,
    EntityType,
    FactID,
    FactType,
    FrameID,
    TimeScope,
)
from pipeline.extraction_context import ExtractionContext
from pipeline.lemma_signals import lemma_set
from pipeline.models import (
    AntiCorruptionInvestigationFrame,
    AntiCorruptionReferralFrame,
    ArticleDocument,
    ClauseUnit,
    EntityCluster,
    EvidenceSpan,
    Fact,
    ParsedWord,
    PublicProcurementAbuseFrame,
)
from pipeline.nlp_rules import COMPENSATION_PATTERN
from pipeline.public_money_signals import is_public_counterparty
from pipeline.temporal import resolve_event_date
from pipeline.utils import normalize_entity_name, stable_id


class PolishAntiCorruptionReferralFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_anti_corruption_referral_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.anti_corruption_referral_frames = []
        for clause in document.clause_units:
            if not self._has_referral_context(document, clause):
                continue
            frame = self._extract_frame_from_clause(document, clause)
            if frame is not None:
                document.anti_corruption_referral_frames.append(frame)
        return document

    def _extract_frame_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> AntiCorruptionReferralFrame | None:
        clusters = ExtractionContext.build(document).clusters_for_mentions(
            clause.cluster_mentions,
            {
                EntityType.PERSON,
                EntityType.POLITICAL_PARTY,
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            },
        )
        target = self._target_institution(clause, clusters)
        if target is None:
            return None
        complainant = self._complainant_actor(document, clause, clusters, target)
        if complainant is None:
            return None

        return AntiCorruptionReferralFrame(
            frame_id=FrameID(f"referral-frame-{uuid.uuid4().hex[:8]}"),
            complainant_cluster_id=complainant.cluster_id,
            target_cluster_id=target.cluster_id,
            confidence=0.82 if complainant.entity_type == EntityType.PERSON else 0.74,
            evidence=[
                EvidenceSpan(
                    text=clause.text,
                    sentence_index=clause.sentence_index,
                    paragraph_index=clause.paragraph_index,
                    start_char=clause.start_char,
                    end_char=clause.end_char,
                )
            ],
            extraction_signal="dependency_edge",
            evidence_scope="same_clause",
            score_reason="anti_corruption_referral",
        )

    @staticmethod
    def _has_referral_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        has_trigger = bool(lemmas.intersection(REFERRAL_TRIGGER_LEMMAS))
        has_noun = bool(lemmas.intersection(REFERRAL_NOUN_LEMMAS))
        if not parsed_words:
            has_trigger = any(
                trigger in lowered for trigger in ("złoży", "złożą", "skieruj", "zapowied")
            )
            has_noun = any(
                noun in lowered for noun in ("zawiadomienie", "doniesienie", "skarg", "wniosek")
            )
        has_target = any(marker in lowered for marker in ACCOUNTABILITY_INSTITUTION_MARKERS)
        return has_target and has_noun and has_trigger

    @staticmethod
    def _target_institution(
        clause: ClauseUnit,
        clusters: list[EntityCluster],
    ) -> EntityCluster | None:
        target_candidates = [
            cluster
            for cluster in clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and any(
                marker in cluster.normalized_name.lower()
                or marker in cluster.canonical_name.lower()
                for marker in ACCOUNTABILITY_INSTITUTION_MARKERS
            )
        ]
        if target_candidates:
            return min(
                target_candidates,
                key=lambda cluster: ExtractionContext.cluster_clause_distance(
                    cluster,
                    clause,
                ),
            )
        return None

    @staticmethod
    def _complainant_actor(
        document: ArticleDocument,
        clause: ClauseUnit,
        clusters: list[EntityCluster],
        target: EntityCluster,
    ) -> EntityCluster | None:
        parsed = document.parsed_sentences.get(clause.sentence_index, [])
        subject_word_indices = {word.index for word in parsed if word.deprel.startswith("nsubj")}
        person_candidates = [
            cluster
            for cluster in clusters
            if cluster.entity_type == EntityType.PERSON and cluster.cluster_id != target.cluster_id
        ]
        for cluster in person_candidates:
            if PolishAntiCorruptionReferralFrameExtractor._cluster_overlaps_word_indices(
                clause,
                cluster,
                parsed,
                subject_word_indices,
            ):
                return cluster
        if person_candidates:
            speech_heads = {
                word.index for word in parsed if word.lemma.casefold() in ATTRIBUTION_SPEECH_LEMMAS
            }
            speaker_indices = {
                word.index
                for word in parsed
                if word.head in speech_heads and word.deprel.startswith("nsubj")
            }
            non_speakers = [
                cluster
                for cluster in person_candidates
                if not PolishAntiCorruptionReferralFrameExtractor._cluster_overlaps_word_indices(
                    clause,
                    cluster,
                    parsed,
                    speaker_indices,
                )
            ]
            return (non_speakers or person_candidates)[0]

        party_candidates = [
            cluster
            for cluster in clusters
            if cluster.entity_type == EntityType.POLITICAL_PARTY
            and cluster.cluster_id != target.cluster_id
        ]
        lowered = clause.text.lower()
        if party_candidates and any(
            marker in lowered for marker in ("radni", "radnych", "reprezentujący")
        ):
            return party_candidates[0]
        return None

    @staticmethod
    def _cluster_overlaps_word_indices(
        clause: ClauseUnit,
        cluster: EntityCluster,
        parsed: list[ParsedWord],
        indices: set[int],
    ) -> bool:
        if not indices:
            return False
        for mention in cluster.mentions:
            if mention.sentence_index != clause.sentence_index:
                continue
            for word in parsed:
                abs_start = clause.start_char + word.start
                if word.index in indices and mention.start_char <= abs_start < mention.end_char:
                    return True
        return False


class PolishAntiCorruptionAbuseFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_anti_corruption_abuse_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.anti_corruption_investigation_frames = []
        document.public_procurement_abuse_frames = []
        recent_public_actor: EntityCluster | None = None
        for clause in document.clause_units:
            clusters = ExtractionContext.build(document).clusters_for_mentions(
                clause.cluster_mentions,
                {
                    EntityType.PERSON,
                    EntityType.POSITION,
                    EntityType.ORGANIZATION,
                    EntityType.PUBLIC_INSTITUTION,
                },
            )
            local_actor = self._public_actor_or_office(clause, clusters, exclude=None)
            if local_actor is not None:
                recent_public_actor = local_actor
            if not clusters and recent_public_actor is None:
                continue
            if self._has_investigation_context(document, clause):
                frame = self._investigation_frame(clause, clusters)
                if frame is not None:
                    document.anti_corruption_investigation_frames.append(frame)
            if self._has_procurement_abuse_context(document, clause):
                frame = self._procurement_abuse_frame(
                    clause,
                    clusters,
                    fallback_actor=recent_public_actor,
                )
                if frame is not None:
                    document.public_procurement_abuse_frames.append(frame)
        return document

    @staticmethod
    def _has_investigation_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        has_institution = any(marker in lowered for marker in ACCOUNTABILITY_INSTITUTION_MARKERS)
        has_action = bool(
            lemmas.intersection(INVESTIGATION_TRIGGER_LEMMAS)
            or lemmas.intersection(INVESTIGATION_NOUN_LEMMAS)
        )
        if not parsed_words:
            has_action = any(
                marker in lowered
                for marker in (
                    "zatrzyma",
                    "zarzut",
                    "łapów",
                    "korupcj",
                    "śledztw",
                    "postępow",
                    "podejrz",
                )
            )
        return has_institution and has_action

    @staticmethod
    def _has_procurement_abuse_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        has_public_work = bool(
            lemmas.intersection(PROCUREMENT_ABUSE_LEMMAS)
            or any(
                marker in lowered
                for marker in (
                    "zamówienia publiczne",
                    "zamówień publicznych",
                    "zlecanie remontów",
                    "ustawian",
                    "przetarg",
                )
            )
        )
        has_abuse = bool(
            lemmas.intersection({"łapówka", "korupcja", "ustawiać", "zarzut"})
            or any(marker in lowered for marker in ("łapów", "korupcj", "ustawian", "zarzut"))
        )
        return has_public_work and has_abuse

    def _investigation_frame(
        self,
        clause: ClauseUnit,
        clusters: list[EntityCluster],
    ) -> AntiCorruptionInvestigationFrame | None:
        institution = self._accountability_institution(clause, clusters)
        target = self._public_actor_or_office(clause, clusters, exclude=institution)
        if institution is None or target is None:
            return None
        return AntiCorruptionInvestigationFrame(
            frame_id=FrameID(f"investigation-frame-{uuid.uuid4().hex[:8]}"),
            institution_cluster_id=institution.cluster_id,
            target_cluster_id=target.cluster_id,
            confidence=0.78,
            evidence=[self._evidence(clause)],
            extraction_signal="dependency_edge",
            evidence_scope="same_clause",
            score_reason="anti_corruption_investigation",
        )

    def _procurement_abuse_frame(
        self,
        clause: ClauseUnit,
        clusters: list[EntityCluster],
        *,
        fallback_actor: EntityCluster | None,
    ) -> PublicProcurementAbuseFrame | None:
        actor = self._public_actor_or_office(clause, clusters, exclude=None) or fallback_actor
        if actor is None:
            return None
        context = self._public_context(clause, clusters, exclude=actor)
        amount_match = COMPENSATION_PATTERN.search(clause.text)
        amount_text = amount_match.group("amount") if amount_match else None
        return PublicProcurementAbuseFrame(
            frame_id=FrameID(f"procurement-abuse-frame-{uuid.uuid4().hex[:8]}"),
            actor_cluster_id=actor.cluster_id,
            public_context_cluster_id=context.cluster_id if context is not None else None,
            amount_text=amount_text,
            amount_normalized=normalize_entity_name(amount_text.lower()) if amount_text else None,
            confidence=0.72 if context is not None else 0.64,
            evidence=[self._evidence(clause)],
            extraction_signal="dependency_edge",
            evidence_scope="same_clause",
            score_reason="public_procurement_abuse",
        )

    @staticmethod
    def _accountability_institution(
        clause: ClauseUnit,
        clusters: list[EntityCluster],
    ) -> EntityCluster | None:
        return PolishAntiCorruptionReferralFrameExtractor._target_institution(clause, clusters)

    @staticmethod
    def _public_actor_or_office(
        clause: ClauseUnit,
        clusters: list[EntityCluster],
        *,
        exclude: EntityCluster | None,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in clusters
            if (exclude is None or cluster.cluster_id != exclude.cluster_id)
            and cluster.entity_type in {EntityType.PERSON, EntityType.POSITION}
        ]
        public_office_candidates = [
            cluster
            for cluster in candidates
            if cluster.entity_type == EntityType.POSITION
            or any(
                marker in cluster.normalized_name.lower()
                for marker in ("wójt", "wojt", "starosta", "sekretarz", "marszałek", "wojewoda")
            )
        ]
        return min(
            public_office_candidates or candidates,
            key=lambda cluster: ExtractionContext.cluster_clause_distance(
                cluster,
                clause,
            ),
            default=None,
        )

    @staticmethod
    def _public_context(
        clause: ClauseUnit,
        clusters: list[EntityCluster],
        *,
        exclude: EntityCluster,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in clusters
            if cluster.cluster_id != exclude.cluster_id
            and cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and not any(
                marker in cluster.normalized_name.lower()
                or marker in cluster.canonical_name.lower()
                for marker in ACCOUNTABILITY_INSTITUTION_MARKERS
            )
            and is_public_counterparty(clause, cluster)
        ]
        return min(
            candidates,
            key=lambda cluster: ExtractionContext.cluster_clause_distance(
                cluster,
                clause,
            ),
            default=None,
        )

    @staticmethod
    def _evidence(clause: ClauseUnit) -> EvidenceSpan:
        return EvidenceSpan(
            text=clause.text,
            sentence_index=clause.sentence_index,
            paragraph_index=clause.paragraph_index,
            start_char=clause.start_char,
            end_char=clause.end_char,
        )


def _ac_cluster_to_entity_id(document: ArticleDocument) -> dict[ClusterID, EntityID]:
    return {cluster.cluster_id: _ac_get_best_entity_id(cluster) for cluster in document.clusters}


def _ac_get_best_entity_id(cluster: EntityCluster) -> EntityID:
    entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
    if entity_ids:
        return EntityID(Counter(entity_ids).most_common(1)[0][0])
    return EntityID(cluster.cluster_id)


def _ac_cluster_by_id(document: ArticleDocument, cluster_id: ClusterID) -> EntityCluster | None:
    return next(
        (cluster for cluster in document.clusters if cluster.cluster_id == cluster_id), None
    )


def _ac_deduplicate_facts(facts: list[Fact]) -> list[Fact]:
    deduplicated: dict[tuple[FactType, EntityID, EntityID | None, str | None, str], Fact] = {}
    for fact in facts:
        key = (
            fact.fact_type,
            fact.subject_entity_id,
            fact.object_entity_id,
            fact.value_normalized,
            fact.evidence.text,
        )
        if key not in deduplicated or deduplicated[key].confidence < fact.confidence:
            deduplicated[key] = fact
    return list(deduplicated.values())


class AntiCorruptionReferralFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _ac_cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.anti_corruption_referral_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _ac_deduplicate_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: AntiCorruptionReferralFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        complainant_id = cluster_to_entity_id.get(frame.complainant_cluster_id)
        target_id = cluster_to_entity_id.get(frame.target_cluster_id)
        if complainant_id is None or target_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        target = _ac_cluster_by_id(document, frame.target_cluster_id)
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.ANTI_CORRUPTION_REFERRAL,
                    complainant_id,
                    target_id,
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.ANTI_CORRUPTION_REFERRAL,
            subject_entity_id=EntityID(complainant_id),
            object_entity_id=EntityID(target_id),
            value_text=target.canonical_name if target is not None else None,
            value_normalized=target.normalized_name if target is not None else None,
            time_scope=TimeScope.UNKNOWN,
            event_date=resolve_event_date(
                document,
                sentence_index=evidence.sentence_index,
                text=evidence.text,
                start_char=evidence.start_char,
                end_char=evidence.end_char,
            ),
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            organization_kind=target.organization_kind if target is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="anti_corruption_referral_frame",
            score_reason=frame.score_reason,
        )


class AntiCorruptionInvestigationFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _ac_cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.anti_corruption_investigation_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _ac_deduplicate_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: AntiCorruptionInvestigationFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        institution_id = cluster_to_entity_id.get(frame.institution_cluster_id)
        target_id = cluster_to_entity_id.get(frame.target_cluster_id)
        if institution_id is None or target_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        target = _ac_cluster_by_id(document, frame.target_cluster_id)
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.ANTI_CORRUPTION_INVESTIGATION,
                    institution_id,
                    target_id,
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.ANTI_CORRUPTION_INVESTIGATION,
            subject_entity_id=EntityID(institution_id),
            object_entity_id=EntityID(target_id),
            value_text=target.canonical_name if target is not None else None,
            value_normalized=target.normalized_name if target is not None else None,
            time_scope=TimeScope.UNKNOWN,
            event_date=resolve_event_date(
                document,
                sentence_index=evidence.sentence_index,
                text=evidence.text,
                start_char=evidence.start_char,
                end_char=evidence.end_char,
            ),
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            organization_kind=target.organization_kind if target is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="anti_corruption_investigation_frame",
            score_reason=frame.score_reason,
        )


class PublicProcurementAbuseFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id = _ac_cluster_to_entity_id(document)
        facts = [
            fact
            for frame in document.public_procurement_abuse_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return _ac_deduplicate_facts(facts)

    @staticmethod
    def _fact_for_frame(
        document: ArticleDocument,
        frame: PublicProcurementAbuseFrame,
        cluster_to_entity_id: dict[ClusterID, EntityID],
    ) -> Fact | None:
        actor_id = cluster_to_entity_id.get(frame.actor_cluster_id)
        context_id = (
            cluster_to_entity_id.get(frame.public_context_cluster_id)
            if frame.public_context_cluster_id is not None
            else None
        )
        if actor_id is None:
            return None
        evidence = frame.evidence[0] if frame.evidence else EvidenceSpan(text="")
        context = (
            _ac_cluster_by_id(document, frame.public_context_cluster_id)
            if frame.public_context_cluster_id is not None
            else None
        )
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.PUBLIC_PROCUREMENT_ABUSE,
                    actor_id,
                    context_id or "",
                    frame.amount_normalized or "",
                    str(evidence.start_char or ""),
                )
            ),
            fact_type=FactType.PUBLIC_PROCUREMENT_ABUSE,
            subject_entity_id=EntityID(actor_id),
            object_entity_id=EntityID(context_id) if context_id is not None else None,
            value_text=frame.amount_text,
            value_normalized=frame.amount_normalized,
            time_scope=TimeScope.UNKNOWN,
            event_date=resolve_event_date(
                document,
                sentence_index=evidence.sentence_index,
                text=evidence.text,
                start_char=evidence.start_char,
                end_char=evidence.end_char,
            ),
            confidence=round(frame.confidence, 3),
            evidence=evidence,
            amount_text=frame.amount_normalized,
            organization_kind=context.organization_kind if context is not None else None,
            extraction_signal=frame.extraction_signal,
            evidence_scope=frame.evidence_scope,
            source_extractor="public_procurement_abuse_frame",
            score_reason=frame.score_reason,
        )
