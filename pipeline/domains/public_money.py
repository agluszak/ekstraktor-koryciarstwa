from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, FrameID, OrganizationKind
from pipeline.extraction_context import ExtractionContext
from pipeline.lemma_signals import has_lemma, lemma_set, words_with_lemmas
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    EntityCluster,
    FundingFrame,
    ParsedWord,
    PublicContractFrame,
)
from pipeline.nlp_rules import COMPENSATION_PATTERN, FUNDING_HINTS
from pipeline.utils import normalize_entity_name

REPORTING_RECIPIENT_LEMMAS = frozenset({"my", "redakcja", "dziennikarz", "czytelnik"})
REPORTING_OBJECT_LEMMAS = frozenset(
    {"informacja", "wiadomość", "odpowiedź", "komentarz", "oświadczenie", "stanowisko"}
)
CONTRACT_TRIGGER_LEMMAS = frozenset(
    {
        "umowa",
        "kontrakt",
        "zamówienie",
        "podpisać",
        "zawrzeć",
        "udzielić",
        "realizować",
    }
)
CONTRACT_TEXT_MARKERS = frozenset(
    {
        "umow",
        "kontrakt",
        "zamówie",
        "zamówienia publicz",
        "przetarg",
        "podpisał",
        "podpisała",
        "zawarł",
        "zawarła",
    }
)
PUBLIC_COUNTERPARTY_MARKERS = frozenset(
    {
        "gmina",
        "miasto",
        "urząd",
        "miejski",
        "miejska",
        "miejskie",
        "komunaln",
        "publiczn",
        "pec",
        "bpk",
        "przedsiębiorstwo komunalne",
    }
)
CONTRACTOR_CONTEXT_MARKERS = frozenset(
    {"firma", "firmy", "firmą", "spółka", "spółki", "spółką", "podmiot"}
)
FUNDING_SURFACE_FALLBACKS = frozenset(
    {"dotacj", "dofinansowa", "wyłożył", "wyłożyła", "wyłożyły", "sfinansowa", "pochłon"}
)
PUBLIC_MONEY_TRANSFER_LEMMAS = FUNDING_HINTS | frozenset({"otrzymać", "przelać", "zapłacić"})
PUBLIC_MONEY_CONTRACT_TEXT_MARKERS = frozenset(
    {
        "za promowanie",
        "działań promocyjnych",
        "działania promocyjne",
        "promocyjn",
        "umow",
        "zamówie",
    }
)
PUBLIC_MONEY_FUNDING_TEXT_MARKERS = frozenset({"dotacj", "dofinansowa", "darowizn"})
PUBLIC_MONEY_AMOUNT_PATTERN = re.compile(
    r"\b(?P<amount>\d+(?:[ .,]\d+)*\s*(?:tysi(?:ąc|ęcy)|tys\.)\s*złotych)\b",
    re.IGNORECASE,
)


class PublicMoneyFlowKind(StrEnum):
    FUNDING = "funding"
    PUBLIC_CONTRACT = "public_contract"


@dataclass(frozen=True, slots=True)
class PublicMoneyFlowSignal:
    kind: PublicMoneyFlowKind
    payer_cluster: EntityCluster | None
    recipient_cluster: EntityCluster | None
    amount_text: str | None
    amount_normalized: str | None
    confidence: float
    evidence_scope: str
    score_reason: str


class PolishPublicContractFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_public_contract_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.public_contract_frames = []
        for clause in document.clause_units:
            signal = _public_money_flow_signal(document, clause)
            if (
                signal is not None
                and signal.kind == PublicMoneyFlowKind.PUBLIC_CONTRACT
                and signal.payer_cluster is not None
                and signal.recipient_cluster is not None
            ):
                document.public_contract_frames.append(
                    PublicContractFrame(
                        frame_id=FrameID(f"contract-frame-{uuid.uuid4().hex[:8]}"),
                        contractor_cluster_id=signal.recipient_cluster.cluster_id,
                        counterparty_cluster_id=signal.payer_cluster.cluster_id,
                        amount_text=signal.amount_text,
                        amount_normalized=signal.amount_normalized,
                        confidence=signal.confidence,
                        evidence=[ExtractionContext.evidence_for_clause(clause)],
                        extraction_signal="public_money_flow",
                        evidence_scope=signal.evidence_scope,
                        score_reason=signal.score_reason,
                    )
                )
                continue
            if not self._has_contract_context(document, clause):
                continue
            amount_match = COMPENSATION_PATTERN.search(clause.text)
            explicit_public_procurement = self._has_public_procurement_context(clause)
            if amount_match is None and self._is_generic_contract_compliance_clause(clause):
                continue
            if amount_match is None and not explicit_public_procurement:
                continue
            for frame in self._extract_frames_from_clause(
                document,
                clause,
                amount_match,
                explicit_public_procurement=explicit_public_procurement,
            ):
                document.public_contract_frames.append(frame)
        return document

    def _extract_frames_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        amount_match,
        *,
        explicit_public_procurement: bool,
    ) -> list[PublicContractFrame]:
        clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION, EntityType.PERSON},
        )
        if not clusters:
            return []

        trigger_offset = self._contract_trigger_offset(document, clause)
        contractor = self._best_contractor(clause, clusters, trigger_offset)
        if contractor is None:
            return []
        counterparties = self._public_counterparties(clause, clusters, contractor, trigger_offset)
        if not counterparties:
            return []

        amount_text = amount_match.group("amount") if amount_match else None
        confidence = 0.82 if amount_text else 0.68
        if contractor.entity_type == EntityType.PERSON:
            confidence -= 0.12
        if explicit_public_procurement:
            confidence += 0.04
        frames: list[PublicContractFrame] = []
        for counterparty in counterparties:
            if counterparty.cluster_id == contractor.cluster_id:
                continue
            frames.append(
                PublicContractFrame(
                    frame_id=FrameID(f"contract-frame-{uuid.uuid4().hex[:8]}"),
                    contractor_cluster_id=contractor.cluster_id,
                    counterparty_cluster_id=counterparty.cluster_id,
                    amount_text=amount_text,
                    amount_normalized=normalize_entity_name(amount_text.lower())
                    if amount_text
                    else None,
                    confidence=max(0.05, min(confidence, 0.95)),
                    evidence=[ExtractionContext.evidence_for_clause(clause)],
                    extraction_signal="dependency_edge",
                    evidence_scope="same_clause",
                    score_reason="contract_amount_public_counterparty"
                    if amount_text
                    else "public_procurement_counterparty",
                )
            )
        return frames

    @staticmethod
    def _has_contract_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = {word.lemma.lower() for word in parsed_words}
        return bool(
            lemmas.intersection(CONTRACT_TRIGGER_LEMMAS)
            or clause.trigger_head_lemma.lower() in CONTRACT_TRIGGER_LEMMAS
            or any(marker in lowered for marker in CONTRACT_TEXT_MARKERS)
        )

    @staticmethod
    def _has_public_procurement_context(clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        return any(
            marker in lowered
            for marker in ("zamówień publicznych", "zamówienia publiczne", "przetarg")
        )

    @staticmethod
    def _is_generic_contract_compliance_clause(clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        return (
            "zgodnie z prawem" in lowered
            and "zamówień publicznych" in lowered
            and not any(marker in lowered for marker in ("kwot", "zł", "podpisa", "zawar"))
        )

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

    @staticmethod
    def _contract_trigger_offset(document: ArticleDocument, clause: ClauseUnit) -> int:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        trigger_words = [
            word
            for word in parsed_words
            if word.lemma.lower() in CONTRACT_TRIGGER_LEMMAS
            or any(marker in word.text.lower() for marker in ("umow", "kontrakt", "zamówie"))
        ]
        if trigger_words:
            return clause.start_char + min(word.start for word in trigger_words)
        lowered = clause.text.lower()
        offsets = [
            lowered.find(marker) for marker in CONTRACT_TEXT_MARKERS if lowered.find(marker) >= 0
        ]
        return clause.start_char + min(offsets, default=0)

    @staticmethod
    def _best_contractor(
        clause: ClauseUnit,
        clusters: list[EntityCluster],
        trigger_offset: int,
    ) -> EntityCluster | None:
        organizations = [
            cluster
            for cluster in clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        ]
        before_trigger = [
            cluster
            for cluster in organizations
            if cluster_before_offset(cluster, trigger_offset, clause)
        ]
        company_candidates = [
            cluster
            for cluster in before_trigger or organizations
            if is_company_like_contractor(clause, cluster)
        ]
        if company_candidates:
            return max(
                company_candidates, key=lambda cluster: cluster.organization_kind is not None
            )

        person_contractors = [
            cluster
            for cluster in clusters
            if cluster.entity_type == EntityType.PERSON and has_person_firm_context(clause, cluster)
        ]
        if person_contractors:
            return min(
                person_contractors,
                key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause),
            )
        return before_trigger[0] if before_trigger else None

    @staticmethod
    def _public_counterparties(
        clause: ClauseUnit,
        clusters: list[EntityCluster],
        contractor: EntityCluster,
        trigger_offset: int,
    ) -> list[EntityCluster]:
        counterparties: list[EntityCluster] = []
        for cluster in clusters:
            if cluster.cluster_id == contractor.cluster_id:
                continue
            if cluster.entity_type not in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}:
                continue
            if not cluster_after_or_near_trigger(cluster, trigger_offset, clause):
                continue
            if is_public_counterparty(clause, cluster):
                counterparties.append(cluster)
        return counterparties

    @staticmethod
    def _cluster_before_offset(
        cluster: EntityCluster,
        offset: int,
        clause: ClauseUnit,
    ) -> bool:
        return cluster_before_offset(cluster, offset, clause)

    @staticmethod
    def _cluster_after_or_near_trigger(
        cluster: EntityCluster,
        offset: int,
        clause: ClauseUnit,
    ) -> bool:
        return cluster_after_or_near_trigger(cluster, offset, clause)

    @staticmethod
    def _is_company_like_contractor(clause: ClauseUnit, cluster: EntityCluster) -> bool:
        return is_company_like_contractor(clause, cluster)

    @staticmethod
    def _is_public_counterparty(clause: ClauseUnit, cluster: EntityCluster) -> bool:
        return is_public_counterparty(clause, cluster)

    @staticmethod
    def _has_person_firm_context(clause: ClauseUnit, cluster: EntityCluster) -> bool:
        return has_person_firm_context(clause, cluster)

    @staticmethod
    def _cluster_has_context_marker(
        clause: ClauseUnit,
        cluster: EntityCluster,
        markers: Iterable[str],
        *,
        before: int,
        after: int,
    ) -> bool:
        return cluster_has_context_marker(clause, cluster, markers, before=before, after=after)


class PolishFundingFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_funding_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.funding_frames = []
        for clause in document.clause_units:
            signal = _public_money_flow_signal(document, clause)
            if signal is not None:
                if signal.kind != PublicMoneyFlowKind.FUNDING:
                    continue
                document.funding_frames.append(
                    FundingFrame(
                        frame_id=FrameID(f"funding-frame-{uuid.uuid4().hex[:8]}"),
                        amount_text=signal.amount_text,
                        amount_normalized=signal.amount_normalized,
                        funder_cluster_id=signal.payer_cluster.cluster_id
                        if signal.payer_cluster is not None
                        else None,
                        recipient_cluster_id=signal.recipient_cluster.cluster_id
                        if signal.recipient_cluster is not None
                        else None,
                        confidence=signal.confidence,
                        evidence=[ExtractionContext.evidence_for_clause(clause)],
                        extraction_signal="public_money_flow",
                        evidence_scope=signal.evidence_scope,
                        score_reason=signal.score_reason,
                    )
                )
                continue
            if not self._has_funding_context(document, clause):
                continue
            amount_match = COMPENSATION_PATTERN.search(clause.text)
            if self._is_reporting_przekazac_context(document, clause):
                continue
            if self._is_reporting_przekazac_without_amount(document, clause, amount_match):
                continue
            frame = self._extract_frame_from_clause(document, clause, amount_match)
            if frame is not None:
                document.funding_frames.append(frame)
        return document

    def _extract_frame_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        amount_match,
    ) -> FundingFrame | None:
        org_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )
        if not org_clusters:
            org_clusters = self._paragraph_context_clusters(document, clause)
        if not org_clusters:
            return None

        funder = self._best_funder(document, clause, org_clusters)
        recipient = self._best_recipient(document, clause, org_clusters, funder)
        project = self._best_project(document, clause, org_clusters, funder, recipient)
        if recipient is None and project is not None:
            recipient = project
            project = None
        if funder is None and recipient is None:
            return None

        amount_text = amount_match.group("amount") if amount_match else None
        confidence, score_reason = self._score_frame(
            funder=funder,
            recipient=recipient,
            amount_text=amount_text,
            same_clause_org_count=len(org_clusters),
        )
        return FundingFrame(
            frame_id=FrameID(f"funding-frame-{uuid.uuid4().hex[:8]}"),
            amount_text=amount_text,
            amount_normalized=normalize_entity_name(amount_text.lower()) if amount_text else None,
            funder_cluster_id=funder.cluster_id if funder else None,
            recipient_cluster_id=recipient.cluster_id if recipient else None,
            project_cluster_id=project.cluster_id if project else None,
            confidence=confidence,
            evidence=[ExtractionContext.evidence_for_clause(clause)],
            extraction_signal=self._extraction_signal(score_reason),
            evidence_scope="same_clause" if len(org_clusters) >= 2 else "same_paragraph",
            score_reason=score_reason,
        )

    @staticmethod
    def _has_funding_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        return bool(
            lemmas.intersection(FUNDING_HINTS)
            or clause.trigger_head_lemma.lower() in FUNDING_HINTS
            or (not parsed_words and any(hint in lowered for hint in FUNDING_SURFACE_FALLBACKS))
        )

    @staticmethod
    def _is_reporting_przekazac_context(document: ArticleDocument, clause: ClauseUnit) -> bool:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        przekazac_words = words_with_lemmas(parsed_words, frozenset({"przekazać"}))
        if not przekazac_words:
            return False
        if has_lemma(parsed_words, frozenset({"dotacja", "dofinansowanie"})):
            return False
        reporting_lemmas = REPORTING_RECIPIENT_LEMMAS | REPORTING_OBJECT_LEMMAS
        return any(
            child.head == trigger.index
            and child.deprel in {"obj", "iobj", "obl"}
            and child.lemma.casefold() in reporting_lemmas
            for trigger in przekazac_words
            for child in parsed_words
        )

    @staticmethod
    def _is_reporting_przekazac_without_amount(
        document: ArticleDocument,
        clause: ClauseUnit,
        amount_match,
    ) -> bool:
        if amount_match is not None:
            return False
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        has_przekazac = clause.trigger_head_lemma.lower() == "przekazać" or any(
            word.lemma.lower() == "przekazać" for word in parsed_words
        )
        if not has_przekazac:
            return False
        if has_lemma(parsed_words, frozenset({"dotacja", "dofinansowanie"})):
            return False
        if not parsed_words and ("dotacj" in lowered or "dofinansowa" in lowered):
            return False
        return True

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

    @staticmethod
    def _paragraph_context_clusters(
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> list[EntityCluster]:
        return ExtractionContext.build(document).paragraph_context_clusters(
            clause,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )

    def _best_funder(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
    ) -> EntityCluster | None:
        if not org_clusters:
            return None
        trigger_index = self._funding_trigger_index(document, clause)
        if self._trigger_prefers_postposed_funder(document, clause):
            after_trigger = [
                cluster
                for cluster in org_clusters
                if self._cluster_after_offset_in_clause(cluster, trigger_index, clause)
            ]
            if after_trigger:
                return max(after_trigger, key=lambda cluster: self._funder_score(cluster))
        before_trigger = [
            cluster
            for cluster in org_clusters
            if self._cluster_before_offset(cluster, trigger_index)
        ]
        candidates = before_trigger or org_clusters
        return max(candidates, key=lambda cluster: self._funder_score(cluster))

    def _best_recipient(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
        funder: EntityCluster | None,
    ) -> EntityCluster | None:
        candidates = [cluster for cluster in org_clusters if cluster != funder]
        if not candidates:
            return None
        trigger_index = self._funding_trigger_index(document, clause)
        after_trigger = [
            cluster
            for cluster in candidates
            if not self._cluster_before_offset(cluster, trigger_index)
        ]
        candidates = after_trigger or candidates
        return max(candidates, key=lambda cluster: self._recipient_score(cluster))

    @staticmethod
    def _best_project(
        document: ArticleDocument,
        clause: ClauseUnit,
        org_clusters: list[EntityCluster],
        funder: EntityCluster | None,
        recipient: EntityCluster | None,
    ) -> EntityCluster | None:
        _ = document
        project_markers = ("projekt", "park", "program", "inwestyc", "budow")
        excluded_ids = {
            cluster.cluster_id for cluster in (funder, recipient) if cluster is not None
        }
        candidates = [
            cluster
            for cluster in org_clusters
            if cluster.cluster_id not in excluded_ids
            and any(marker in cluster.normalized_name.lower() for marker in project_markers)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause),
        )

    @staticmethod
    def _funder_score(cluster: EntityCluster) -> tuple[int, int, int]:
        normalized = cluster.normalized_name.lower()
        public_bonus = 2 if cluster.entity_type == EntityType.PUBLIC_INSTITUTION else 0
        if any(term in normalized for term in ("minister", "fundusz", "urząd", "nfoś", "wfoś")):
            public_bonus += 2
        if any(term in normalized for term in ("spółka", "agencja", "krajowy")):
            public_bonus += 1
        return (public_bonus, len(cluster.canonical_name.split()), len(cluster.canonical_name))

    @staticmethod
    def _recipient_score(cluster: EntityCluster) -> tuple[int, int, int]:
        normalized = cluster.normalized_name.lower()
        recipient_bonus = 0
        if any(term in normalized for term in ("fundacja", "stowarzyszenie", "instytut")):
            recipient_bonus += 3
        if any(term in normalized for term in ("projekt", "park", "program")):
            recipient_bonus += 2
        if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
            recipient_bonus -= 1
        return (recipient_bonus, len(cluster.canonical_name.split()), len(cluster.canonical_name))

    @staticmethod
    def _funding_trigger_index(document: ArticleDocument, clause: ClauseUnit) -> int:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        trigger_words = [
            clause.start_char + word.start
            for word in parsed_words
            if word.lemma.lower() in FUNDING_HINTS
        ]
        if trigger_words:
            return min(trigger_words)
        lowered = clause.text.lower()
        positions = [
            lowered.find(hint) for hint in FUNDING_SURFACE_FALLBACKS if lowered.find(hint) >= 0
        ]
        if positions:
            return clause.start_char + min(positions)
        return clause.start_char

    @staticmethod
    def _trigger_prefers_postposed_funder(
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> bool:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        if any(word.lemma.lower() == "wyłożyć" for word in parsed_words):
            return True
        return "wyłożył" in clause.text.lower() or "wyłożyły" in clause.text.lower()

    @staticmethod
    def _cluster_before_offset(cluster: EntityCluster, offset: int) -> bool:
        return any(mention.end_char <= offset for mention in cluster.mentions)

    @staticmethod
    def _cluster_after_offset_in_clause(
        cluster: EntityCluster,
        offset: int,
        clause: ClauseUnit,
    ) -> bool:
        return any(
            mention.sentence_index == clause.sentence_index
            and mention.start_char >= offset
            and mention.start_char <= clause.end_char
            for mention in cluster.mentions
        )

    @staticmethod
    def _score_frame(
        *,
        funder: EntityCluster | None,
        recipient: EntityCluster | None,
        amount_text: str | None,
        same_clause_org_count: int,
    ) -> tuple[float, str]:
        if funder is not None and recipient is not None and amount_text is not None:
            return 0.82, "funder_recipient_amount_same_clause"
        if funder is not None and recipient is not None:
            return 0.74, "funder_recipient_no_amount"
        if amount_text is not None and same_clause_org_count >= 1:
            return 0.68, "amount_paragraph_context"
        if funder is not None and amount_text is not None:
            return 0.58, "public_funder_amount"
        return 0.45, "weak_public_money_context"

    @staticmethod
    def _extraction_signal(score_reason: str) -> str:
        if score_reason == "funder_recipient_amount_same_clause":
            return "syntactic_direct"
        if "same_clause" in score_reason:
            return "dependency_edge"
        if "paragraph" in score_reason:
            return "same_paragraph"
        return "same_clause"


def cluster_before_offset(
    cluster: EntityCluster,
    offset: int,
    clause: ClauseUnit,
) -> bool:
    return any(
        mention.sentence_index == clause.sentence_index and mention.start_char < offset
        for mention in cluster.mentions
    )


def cluster_after_or_near_trigger(
    cluster: EntityCluster,
    offset: int,
    clause: ClauseUnit,
) -> bool:
    return any(
        mention.sentence_index == clause.sentence_index and mention.end_char >= offset - 12
        for mention in cluster.mentions
    )


def is_company_like_contractor(clause: ClauseUnit, cluster: EntityCluster) -> bool:
    if cluster.organization_kind == OrganizationKind.COMPANY:
        return True
    lowered_name = cluster.normalized_name.lower()
    if any(marker in lowered_name for marker in ("consulting", "group", "spół", "firma")):
        return True
    return cluster_has_context_marker(
        clause,
        cluster,
        CONTRACTOR_CONTEXT_MARKERS,
        before=18,
        after=6,
    )


def is_public_counterparty(clause: ClauseUnit, cluster: EntityCluster) -> bool:
    if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
        return True
    if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
        return True
    lowered_name = cluster.normalized_name.lower()
    if any(marker in lowered_name for marker in PUBLIC_COUNTERPARTY_MARKERS):
        return True
    if any(marker in clause.text.lower() for marker in ("miast", "gmin", "komunal")) and (
        cluster_has_context_marker(
            clause,
            cluster,
            {"spółką", "spółce", "spółka"},
            before=12,
            after=4,
        )
    ):
        return True
    return cluster_has_context_marker(
        clause,
        cluster,
        PUBLIC_COUNTERPARTY_MARKERS,
        before=18,
        after=10,
    )


def has_person_firm_context(clause: ClauseUnit, cluster: EntityCluster) -> bool:
    return cluster_has_context_marker(
        clause,
        cluster,
        {"firma", "firmy", "prowadzona przez", "prowadzonej przez", "należąca do"},
        before=34,
        after=6,
    )


def cluster_has_context_marker(
    clause: ClauseUnit,
    cluster: EntityCluster,
    markers: Iterable[str],
    *,
    before: int,
    after: int,
) -> bool:
    lowered = clause.text.lower()
    for mention in cluster.mentions:
        if mention.sentence_index != clause.sentence_index:
            continue
        start = max(0, mention.start_char - clause.start_char)
        end = max(start, mention.end_char - clause.start_char)
        window = lowered[max(0, start - before) : min(len(lowered), end + after)]
        if any(marker in window for marker in markers):
            return True
    return False


def _public_money_flow_signal(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> PublicMoneyFlowSignal | None:
    amount_match = COMPENSATION_PATTERN.search(clause.text) or PUBLIC_MONEY_AMOUNT_PATTERN.search(
        clause.text
    )
    amount_text = amount_match.group("amount") if amount_match else None
    parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
    lowered = clause.text.casefold()
    if not _has_transfer_or_paid_promotion_signal(parsed_words, lowered):
        return None
    if not _has_public_money_context(parsed_words, lowered, amount_text):
        return None
    if PolishFundingFrameExtractor._is_reporting_przekazac_context(document, clause):
        return None
    if PolishFundingFrameExtractor._is_reporting_przekazac_without_amount(
        document,
        clause,
        amount_match,
    ) and not _has_explicit_public_money_noun(parsed_words, lowered):
        return None

    org_clusters = _public_money_clusters(document, clause)
    if len(org_clusters) < 2:
        return None
    payer = _public_money_payer(clause, org_clusters)
    recipient = _public_money_recipient(clause, org_clusters, payer)
    if payer is None or recipient is None or payer.cluster_id == recipient.cluster_id:
        return None
    kind = (
        PublicMoneyFlowKind.PUBLIC_CONTRACT
        if _has_contract_money_signal(parsed_words, lowered)
        else PublicMoneyFlowKind.FUNDING
    )
    amount_normalized = normalize_entity_name(amount_text.lower()) if amount_text else None
    confidence = 0.84 if amount_text else 0.7
    if kind == PublicMoneyFlowKind.PUBLIC_CONTRACT:
        confidence += 0.03
    return PublicMoneyFlowSignal(
        kind=kind,
        payer_cluster=payer,
        recipient_cluster=recipient,
        amount_text=amount_text,
        amount_normalized=amount_normalized,
        confidence=min(confidence, 0.94),
        evidence_scope="same_clause",
        score_reason=(
            "public_money_contract_flow"
            if kind == PublicMoneyFlowKind.PUBLIC_CONTRACT
            else "public_money_funding_flow"
        ),
    )


def _has_public_money_context(
    parsed_words: list[ParsedWord],
    lowered: str,
    amount_text: str | None,
) -> bool:
    lemmas = lemma_set(parsed_words)
    if amount_text and lemmas.intersection(PUBLIC_MONEY_TRANSFER_LEMMAS):
        return True
    if amount_text and any(marker in lowered for marker in PUBLIC_MONEY_CONTRACT_TEXT_MARKERS):
        return True
    return _has_explicit_public_money_noun(parsed_words, lowered)


def _has_transfer_or_paid_promotion_signal(parsed_words: list[ParsedWord], lowered: str) -> bool:
    lemmas = lemma_set(parsed_words)
    return bool(
        lemmas.intersection(PUBLIC_MONEY_TRANSFER_LEMMAS)
        or "za promowanie" in lowered
        or "działań promocyjnych" in lowered
        or "działania promocyjne" in lowered
    )


def _has_explicit_public_money_noun(parsed_words: list[ParsedWord], lowered: str) -> bool:
    lemmas = lemma_set(parsed_words)
    return bool(
        lemmas.intersection({"dotacja", "dofinansowanie", "umowa", "zamówienie"})
        or any(marker in lowered for marker in PUBLIC_MONEY_FUNDING_TEXT_MARKERS)
        or any(marker in lowered for marker in CONTRACT_TEXT_MARKERS)
    )


def _has_contract_money_signal(parsed_words: list[ParsedWord], lowered: str) -> bool:
    lemmas = lemma_set(parsed_words)
    return bool(
        lemmas.intersection(CONTRACT_TRIGGER_LEMMAS)
        or any(marker in lowered for marker in PUBLIC_MONEY_CONTRACT_TEXT_MARKERS)
    )


def _public_money_clusters(
    document: ArticleDocument,
    clause: ClauseUnit,
) -> list[EntityCluster]:
    return ExtractionContext.build(document).clusters_for_mentions(
        clause.cluster_mentions,
        {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
    )


def _public_money_payer(
    clause: ClauseUnit,
    clusters: list[EntityCluster],
) -> EntityCluster | None:
    candidates = [cluster for cluster in clusters if is_public_counterparty(clause, cluster)]
    if not candidates:
        return None
    z_context = [
        cluster
        for cluster in candidates
        if cluster_has_context_marker(
            clause,
            cluster,
            {"z ", "ze ", "od "},
            before=4,
            after=0,
        )
    ]
    return min(
        z_context or candidates,
        key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause),
    )


def _public_money_recipient(
    clause: ClauseUnit,
    clusters: list[EntityCluster],
    payer: EntityCluster | None,
) -> EntityCluster | None:
    candidates = [
        cluster for cluster in clusters if payer is None or cluster.cluster_id != payer.cluster_id
    ]
    if not candidates:
        return None
    recipient_candidates = [
        cluster
        for cluster in candidates
        if PolishFundingFrameExtractor._recipient_score(cluster)[0] > 1
        or not is_public_counterparty(clause, cluster)
    ]
    return min(
        recipient_candidates or candidates,
        key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause),
    )
