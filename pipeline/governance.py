from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    EntityID,
    EventType,
    FactID,
    FactType,
    OrganizationKind,
    TimeScope,
)
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    EntityCluster,
    EvidenceSpan,
    Fact,
    GovernanceFrame,
)
from pipeline.nlp_rules import (
    APPOINTMENT_TRIGGER_LEMMAS,
    BOARD_ROLE_KINDS,
    BODY_CONTEXT_TERMS,
    DISMISSAL_TRIGGER_LEMMAS,
    OWNER_CONTEXT_TERMS,
)
from pipeline.role_matching import (
    has_copular_role_appointment,
    has_governance_verb_with_role,
)
from pipeline.utils import extract_role_from_text, stable_id


@dataclass(slots=True)
class GovernanceTargetResolution:
    target_org: EntityCluster | None
    owner_context: EntityCluster | None
    governing_body: EntityCluster | None
    confidence: float
    reason: str


class GovernanceTargetResolver:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def resolve(
        self,
        *,
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
        role_cluster: EntityCluster | None,
    ) -> GovernanceTargetResolution:
        owner_context = self._best_context_cluster(org_clusters, self._is_owner_like_cluster)
        governing_body = self._best_context_cluster(org_clusters, self._is_body_like_cluster)
        candidates = [
            cluster
            for cluster in org_clusters
            if not self._is_rejected_target(cluster)
            and not self._is_owner_like_cluster(cluster)
            and not self._is_body_like_cluster(cluster)
        ]
        if not candidates:
            return GovernanceTargetResolution(
                target_org=None,
                owner_context=owner_context,
                governing_body=governing_body,
                confidence=0.0,
                reason="no_target_candidate",
            )

        target = max(
            candidates,
            key=lambda cluster: self._target_score(document, clause, cluster, role_cluster),
        )
        score, reason = self._target_score(document, clause, target, role_cluster)
        confidence = max(0.55, min(0.95, 0.62 + score * 0.08))
        return GovernanceTargetResolution(
            target_org=target,
            owner_context=owner_context,
            governing_body=governing_body,
            confidence=confidence,
            reason=reason,
        )

    def is_party_like_cluster(self, cluster: EntityCluster) -> bool:
        normalized = cluster.normalized_name.lower()
        aliases = {
            alias.lower()
            for alias in [
                cluster.canonical_name,
                cluster.normalized_name,
                *cluster.aliases,
            ]
            if isinstance(alias, str)
        }
        known_parties = {
            alias.lower() for pair in self.config.party_aliases.items() for alias in pair
        }
        if aliases.intersection(known_parties):
            return True
        if any(
            self._looks_like_inflected_party_alias(alias, party)
            for alias in aliases
            for party in known_parties
        ):
            return True
        party_heads = {"partia", "stronnictwo", "koalicja", "ruch"}
        return any(head in normalized for head in party_heads | {"koalicj"})

    def _target_score(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        cluster: EntityCluster,
        role_cluster: EntityCluster | None,
    ) -> tuple[float, str]:
        score = 0.0
        reasons: list[str] = []
        if self._cluster_in_clause(cluster, clause):
            score += 3.0
            reasons.append("same_clause")
        if role_cluster is not None and self._cluster_near_role(cluster, role_cluster):
            score += 2.0
            reasons.append("near_role")
        if self._is_target_like_cluster(cluster):
            score += 1.5
            reasons.append("target_like")
        if self._is_expanded_name(cluster):
            score += 0.8
            reasons.append("expanded_name")
        if self._is_paragraph_continuation(cluster, clause):
            score += 0.5
            reasons.append("paragraph_context")
        if self._is_generic_fragment(cluster):
            score -= 3.0
            reasons.append("generic_fragment")
        if self._is_media_like_cluster(cluster):
            score -= 4.0
            reasons.append("media_like")

        distance = self._cluster_clause_distance(cluster, clause)
        score -= min(1.0, distance[0] * 0.35)
        if not reasons:
            reasons.append("fallback")
        _ = document
        return score, "+".join(reasons)

    @staticmethod
    def _best_context_cluster(
        clusters: list[EntityCluster],
        predicate,
    ) -> EntityCluster | None:
        matches = [cluster for cluster in clusters if predicate(cluster)]
        if not matches:
            return None
        return max(matches, key=lambda cluster: len(cluster.canonical_name))

    def _is_rejected_target(self, cluster: EntityCluster) -> bool:
        return (
            self.is_party_like_cluster(cluster)
            or self._is_generic_fragment(cluster)
            or self._is_media_like_cluster(cluster)
        )

    @staticmethod
    def _is_owner_like_cluster(cluster: EntityCluster) -> bool:
        normalized = cluster.normalized_name.lower()
        if "skarbu państwa" in normalized:
            return True
        if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
            return any(term in normalized for term in OWNER_CONTEXT_TERMS)
        return any(term in normalized for term in OWNER_CONTEXT_TERMS)

    @staticmethod
    def _is_body_like_cluster(cluster: EntityCluster) -> bool:
        normalized = cluster.normalized_name.lower()
        kind = cluster.organization_kind
        if kind == OrganizationKind.GOVERNING_BODY:
            return True
        if normalized in BODY_CONTEXT_TERMS:
            return True
        return normalized.startswith("rada nadzorcza")

    @staticmethod
    def _is_target_like_cluster(cluster: EntityCluster) -> bool:
        normalized = cluster.normalized_name.lower()
        if cluster.organization_kind == OrganizationKind.COMPANY:
            return True
        return any(
            marker in normalized
            for marker in (
                "spół",
                "stadnin",
                "rewita",
                "tour",
                "wodociąg",
                "centrum",
                "hotel",
                "totalizator",
                "agencja",
            )
        )

    @staticmethod
    def _is_generic_fragment(cluster: EntityCluster) -> bool:
        normalized = cluster.normalized_name.lower().strip(" .,:;")
        return normalized in {
            "polska",
            "polsce",
            "kraju",
            "kraj",
            "państwo",
            "państwa",
            "rzeczpospolita",
        }

    @staticmethod
    def _is_media_like_cluster(cluster: EntityCluster) -> bool:
        normalized = cluster.normalized_name.lower()
        media_markers = {
            "onet",
            "pap",
            "wp",
            "wirtualna polska",
            "rzeczpospolita",
            "fakt",
            "tvn",
            "tvp",
            "interia",
        }
        # Note: 'is_media' was not in EntityCluster fields but used in attributes.get before.
        # It's not in the new model either, so I'll just check markers.
        return any(marker in normalized for marker in media_markers)

    @staticmethod
    def _is_expanded_name(cluster: EntityCluster) -> bool:
        return len(cluster.canonical_name.split()) >= 2

    @staticmethod
    def _cluster_in_clause(cluster: EntityCluster, clause: ClauseUnit) -> bool:
        return any(
            mention.sentence_index == clause.sentence_index
            and mention.start_char >= clause.start_char
            and mention.end_char <= clause.end_char
            for mention in cluster.mentions
        )

    @staticmethod
    def _is_paragraph_continuation(cluster: EntityCluster, clause: ClauseUnit) -> bool:
        return any(
            mention.paragraph_index == clause.paragraph_index for mention in cluster.mentions
        )

    @staticmethod
    def _cluster_near_role(cluster: EntityCluster, role_cluster: EntityCluster) -> bool:
        return any(
            org_mention.sentence_index == role_mention.sentence_index
            and abs(org_mention.start_char - role_mention.start_char) <= 80
            for org_mention in cluster.mentions
            for role_mention in role_cluster.mentions
        )

    @staticmethod
    def _cluster_clause_distance(cluster: EntityCluster, clause: ClauseUnit) -> tuple[int, int]:
        distances = [
            (
                abs(mention.sentence_index - clause.sentence_index),
                abs(mention.start_char - clause.start_char),
            )
            for mention in cluster.mentions
        ]
        return min(distances, default=(9999, 9999))

    @staticmethod
    def _looks_like_inflected_party_alias(surface: str, party_name: str) -> bool:
        if len(party_name) < 5:
            return False
        party_head = party_name.split()[0]
        surface_head = surface.split()[0] if surface.split() else surface
        stem = party_head[: max(4, len(party_head) - 1)]
        return len(stem) >= 4 and surface_head.startswith(stem)


class GovernanceFactBuilder:
    def build(self, document: ArticleDocument) -> list[Fact]:
        cluster_to_entity_id: dict[str, str] = {
            str(cluster.cluster_id): str(self._get_best_entity_id(cluster))
            for cluster in document.clusters
        }
        facts = [
            fact
            for frame in document.governance_frames
            if (fact := self._fact_for_frame(document, frame, cluster_to_entity_id)) is not None
        ]
        return self._deduplicate_governance_facts(facts)

    def _fact_for_frame(
        self,
        document: ArticleDocument,
        frame: GovernanceFrame,
        cluster_to_entity_id: dict[str, str],
    ) -> Fact | None:
        subject_id = cluster_to_entity_id.get(frame.person_cluster_id or "")
        target_id = cluster_to_entity_id.get(frame.target_org_cluster_id or "")
        if not subject_id or not target_id:
            return None

        role_id = cluster_to_entity_id.get(frame.role_cluster_id or "")
        role_name = next(
            (
                cluster.canonical_name
                for cluster in document.clusters
                if cluster.cluster_id == frame.role_cluster_id
            ),
            None,
        )
        role_text = role_name or frame.found_role
        fact_type = (
            FactType.DISMISSAL if frame.event_type == EventType.DISMISSAL else FactType.APPOINTMENT
        )
        evidence = self._combined_evidence(frame.evidence)

        fact = Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    fact_type,
                    subject_id,
                    target_id,
                    role_text or "",
                    frame.frame_id,
                )
            ),
            fact_type=fact_type,
            subject_entity_id=EntityID(subject_id),
            object_entity_id=EntityID(target_id),
            value_text=role_text,
            value_normalized=role_text.lower() if role_text else None,
            time_scope=TimeScope.CURRENT,
            event_date=document.publication_date,
            confidence=frame.confidence,
            evidence=evidence,
            position_entity_id=EntityID(role_id) if role_id else None,
            owner_context_entity_id=EntityID(
                cluster_to_entity_id.get(frame.owner_context_cluster_id or "") or ""
            )
            if frame.owner_context_cluster_id
            else None,
            governing_body_entity_id=EntityID(
                cluster_to_entity_id.get(frame.governing_body_cluster_id or "") or ""
            )
            if frame.governing_body_cluster_id
            else None,
            appointing_authority_entity_id=EntityID(
                cluster_to_entity_id.get(frame.appointing_authority_cluster_id or "") or ""
            )
            if frame.appointing_authority_cluster_id
            else None,
            source_extractor="governance_frame",
        )
        if role_text:
            fact.role = role_text
            role_kind, role_modifier = extract_role_from_text(role_text)
            fact.role_kind = role_kind
            fact.role_modifier = role_modifier
            fact.board_role = role_kind in BOARD_ROLE_KINDS if role_kind else False
        return fact

    @staticmethod
    def _get_best_entity_id(cluster: EntityCluster) -> str:
        entity_ids = [mention.entity_id for mention in cluster.mentions if mention.entity_id]
        if entity_ids:
            return Counter(entity_ids).most_common(1)[0][0]
        return cluster.cluster_id

    @staticmethod
    def _combined_evidence(evidence: list[EvidenceSpan]) -> EvidenceSpan:
        if not evidence:
            return EvidenceSpan(text="")
        if len(evidence) == 1:
            return evidence[0]
        return EvidenceSpan(
            text=" ".join(span.text for span in evidence if span.text),
            sentence_index=evidence[0].sentence_index,
            paragraph_index=evidence[0].paragraph_index,
            start_char=evidence[0].start_char,
            end_char=evidence[-1].end_char,
        )

    @classmethod
    def _deduplicate_governance_facts(cls, facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[FactType, str, str | None, str | None, int | None], Fact] = {}
        for fact in facts:
            key = (
                fact.fact_type,
                fact.subject_entity_id,
                fact.object_entity_id,
                fact.event_date,
                fact.evidence.paragraph_index,
            )
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = fact
                continue
            deduplicated[key] = cls._merge_duplicate_fact(existing, fact)
        return list(deduplicated.values())

    @staticmethod
    def _merge_duplicate_fact(left: Fact, right: Fact) -> Fact:
        left_has_role = bool(left.value_text)
        right_has_role = bool(right.value_text)
        winner = right if right_has_role and not left_has_role else left
        loser = left if winner is right else right

        # Merge optional fields from loser to winner if winner's fields are None
        for field_name in [
            "position_entity_id",
            "owner_context_entity_id",
            "governing_body_entity_id",
            "appointing_authority_entity_id",
            "role",
            "role_kind",
            "board_role",
        ]:
            if getattr(winner, field_name, None) is None:
                setattr(winner, field_name, getattr(loser, field_name, None))

        winner.confidence = max(winner.confidence, loser.confidence)
        return winner
