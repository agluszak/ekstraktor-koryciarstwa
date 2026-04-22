from __future__ import annotations

import uuid
from collections.abc import Iterable

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    ClusterID,
    EntityType,
    EventType,
    FrameID,
    OrganizationKind,
)
from pipeline.extraction_context import ExtractionContext
from pipeline.governance import GovernanceTargetResolver
from pipeline.lemma_signals import has_lemma, has_lemma_pair, lemma_set, words_with_lemmas
from pipeline.models import (
    AntiCorruptionReferralFrame,
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    CompensationFrame,
    EntityCluster,
    EvidenceSpan,
    FundingFrame,
    GovernanceFrame,
    ParsedWord,
    PublicContractFrame,
)
from pipeline.nlp_rules import (
    APPOINTMENT_NOUN_LEMMAS,
    APPOINTMENT_TRIGGER_LEMMAS,
    APPOINTMENT_TRIGGER_TEXTS,
    COMPENSATION_PATTERN,
    DISMISSAL_NOUN_LEMMAS,
    DISMISSAL_TRIGGER_LEMMAS,
    DISMISSAL_TRIGGER_TEXTS,
    FUNDING_HINTS,
    ROLE_PATTERNS,
)
from pipeline.role_matching import (
    has_copular_role_appointment,
    has_governance_verb_with_role,
    match_role_mentions,
)
from pipeline.utils import normalize_entity_name

COMPENSATION_CONTEXT_LEMMAS = frozenset(
    {
        "zarabiać",
        "zarobić",
        "wynagrodzenie",
        "pensja",
        "płaca",
        "uposażenie",
        "dieta",
        "brutto",
        "netto",
    }
)

COMPENSATION_CONTEXT_TEXTS = frozenset(
    {
        "miesięcznie",
        "rocznie",
        "za miesiąc",
        "wynagrodzenia",
        "wynagrodzenie",
        "pensję",
        "pensja",
        "zarabia",
        "zarabiał",
        "zarobić",
        "brutto",
    }
)

SPEECH_LEMMAS = frozenset(
    {
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
)

KINSHIP_LEMMAS = frozenset(
    {
        "żona",
        "małżonka",
        "mąż",
        "małżonek",
        "partnerka",
        "partner",
        "siostra",
        "brat",
        "córka",
        "syn",
        "szwagierka",
        "szwagier",
    }
)

REFERRAL_TRIGGER_LEMMAS = frozenset({"złożyć", "skierować", "zapowiedzieć"})
REFERRAL_NOUN_LEMMAS = frozenset({"zawiadomienie", "doniesienie", "skarga", "wniosek"})
REPORTING_RECIPIENT_LEMMAS = frozenset({"my", "redakcja", "dziennikarz", "czytelnik"})
REPORTING_OBJECT_LEMMAS = frozenset(
    {"informacja", "wiadomość", "odpowiedź", "komentarz", "oświadczenie", "stanowisko"}
)
ACCOUNTABILITY_INSTITUTION_MARKERS = frozenset(
    {
        "cba",
        "centralne biuro antykorupcyjne",
        "prokuratura",
        "prokuratury",
        "nik",
        "najwyższa izba kontroli",
    }
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
WEAK_APPOINTMENT_TRIGGER_LEMMAS = frozenset(
    {"objąć", "zająć", "pracować", "zatrudnić", "zatrudnienie", "trafić"}
)


class PolishFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.governance = PolishGovernanceFrameExtractor(config)
        self.compensation = PolishCompensationFrameExtractor(config)
        self.funding = PolishFundingFrameExtractor(config)
        self.public_contracts = PolishPublicContractFrameExtractor(config)
        self.anti_corruption_referrals = PolishAntiCorruptionReferralFrameExtractor(config)

    def name(self) -> str:
        return "polish_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document = self.governance.run(document)
        document = self.compensation.run(document)
        document = self.funding.run(document)
        document = self.public_contracts.run(document)
        return self.anti_corruption_referrals.run(document)


class PolishPublicContractFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_public_contract_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.public_contract_frames = []
        for clause in document.clause_units:
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
        seen: set[ClusterID] = set()
        clusters: list[EntityCluster] = []
        for mention in mentions:
            if mention.entity_type not in entity_types:
                continue
            cluster = PolishCompensationFrameExtractor._find_cluster_for_mention(
                mention,
                document,
            )
            if cluster is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

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
            if PolishPublicContractFrameExtractor._cluster_before_offset(
                cluster, trigger_offset, clause
            )
        ]
        company_candidates = [
            cluster
            for cluster in before_trigger or organizations
            if PolishPublicContractFrameExtractor._is_company_like_contractor(clause, cluster)
        ]
        if company_candidates:
            return max(
                company_candidates, key=lambda cluster: cluster.organization_kind is not None
            )

        person_contractors = [
            cluster
            for cluster in clusters
            if cluster.entity_type == EntityType.PERSON
            and PolishPublicContractFrameExtractor._has_person_firm_context(clause, cluster)
        ]
        if person_contractors:
            return min(
                person_contractors,
                key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
                    cluster,
                    clause,
                ),
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
            if not PolishPublicContractFrameExtractor._cluster_after_or_near_trigger(
                cluster,
                trigger_offset,
                clause,
            ):
                continue
            if PolishPublicContractFrameExtractor._is_public_counterparty(clause, cluster):
                counterparties.append(cluster)
        return counterparties

    @staticmethod
    def _cluster_before_offset(
        cluster: EntityCluster,
        offset: int,
        clause: ClauseUnit,
    ) -> bool:
        return any(
            mention.sentence_index == clause.sentence_index and mention.start_char < offset
            for mention in cluster.mentions
        )

    @staticmethod
    def _cluster_after_or_near_trigger(
        cluster: EntityCluster,
        offset: int,
        clause: ClauseUnit,
    ) -> bool:
        return any(
            mention.sentence_index == clause.sentence_index and mention.end_char >= offset - 12
            for mention in cluster.mentions
        )

    @staticmethod
    def _is_company_like_contractor(clause: ClauseUnit, cluster: EntityCluster) -> bool:
        if cluster.organization_kind == OrganizationKind.COMPANY:
            return True
        lowered_name = cluster.normalized_name.lower()
        if any(marker in lowered_name for marker in ("consulting", "group", "spół", "firma")):
            return True
        return PolishPublicContractFrameExtractor._cluster_has_context_marker(
            clause,
            cluster,
            CONTRACTOR_CONTEXT_MARKERS,
            before=18,
            after=6,
        )

    @staticmethod
    def _is_public_counterparty(clause: ClauseUnit, cluster: EntityCluster) -> bool:
        if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
            return True
        if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
            return True
        lowered_name = cluster.normalized_name.lower()
        if any(marker in lowered_name for marker in PUBLIC_COUNTERPARTY_MARKERS):
            return True
        if any(
            marker in clause.text.lower() for marker in ("miast", "gmin", "komunal")
        ) and PolishPublicContractFrameExtractor._cluster_has_context_marker(
            clause,
            cluster,
            {"spółką", "spółce", "spółka"},
            before=12,
            after=4,
        ):
            return True
        return PolishPublicContractFrameExtractor._cluster_has_context_marker(
            clause,
            cluster,
            PUBLIC_COUNTERPARTY_MARKERS,
            before=18,
            after=10,
        )

    @staticmethod
    def _has_person_firm_context(clause: ClauseUnit, cluster: EntityCluster) -> bool:
        return PolishPublicContractFrameExtractor._cluster_has_context_marker(
            clause,
            cluster,
            {"firma", "firmy", "prowadzona przez", "prowadzonej przez", "należąca do"},
            before=34,
            after=6,
        )

    @staticmethod
    def _cluster_has_context_marker(
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
        clusters = self._clusters_for_mentions(
            document,
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

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        seen: set[ClusterID] = set()
        clusters: list[EntityCluster] = []
        for mention in mentions:
            if mention.entity_type not in entity_types:
                continue
            cluster = PolishCompensationFrameExtractor._find_cluster_for_mention(
                mention,
                document,
            )
            if cluster is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

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
                key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
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
            speech_heads = {word.index for word in parsed if word.lemma.casefold() in SPEECH_LEMMAS}
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


class PolishGovernanceFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.target_resolver = GovernanceTargetResolver(config)

    def name(self) -> str:
        return "polish_governance_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.governance_frames = []
        context = ExtractionContext.build(document)
        for clause in document.clause_units:
            parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
            event_type = self._detect_event_type(clause, parsed_words)
            if event_type is None:
                continue
            frame = self._extract_discourse_frame(clause, document, context, event_type)
            if frame is not None:
                document.governance_frames.append(frame)
        return document

    def _detect_event_type(
        self,
        clause: ClauseUnit,
        parsed_words: list[ParsedWord] | None = None,
    ) -> EventType | None:
        lemma = clause.trigger_head_lemma.lower()
        lowered_text = clause.text.lower()
        if (
            self._has_trigger_head_appointment_signal(lemma, parsed_words or [])
            or self._has_appointment_lemma_signal(parsed_words or [])
            or any(trigger in lowered_text for trigger in APPOINTMENT_TRIGGER_TEXTS)
            or has_copular_role_appointment(parsed_words or [])
            or has_governance_verb_with_role(parsed_words or [], APPOINTMENT_TRIGGER_LEMMAS)
        ):
            return EventType.APPOINTMENT
        if (
            lemma in DISMISSAL_TRIGGER_LEMMAS
            or self._has_dismissal_lemma_signal(parsed_words or [])
            or any(trigger in lowered_text for trigger in DISMISSAL_TRIGGER_TEXTS)
            or has_governance_verb_with_role(parsed_words or [], DISMISSAL_TRIGGER_LEMMAS)
        ):
            return EventType.DISMISSAL
        return None

    @staticmethod
    def _has_trigger_head_appointment_signal(
        trigger_head_lemma: str,
        parsed_words: list[ParsedWord],
    ) -> bool:
        if trigger_head_lemma not in APPOINTMENT_TRIGGER_LEMMAS:
            return False
        if trigger_head_lemma not in WEAK_APPOINTMENT_TRIGGER_LEMMAS:
            return True
        return PolishGovernanceFrameExtractor._has_appointment_lemma_signal(parsed_words)

    @staticmethod
    def _has_appointment_lemma_signal(parsed_words: list[ParsedWord]) -> bool:
        lemmas = lemma_set(parsed_words)
        if lemmas.intersection(APPOINTMENT_TRIGGER_LEMMAS) and lemmas.intersection(
            APPOINTMENT_NOUN_LEMMAS
        ):
            return True
        return has_lemma_pair(
            parsed_words,
            APPOINTMENT_TRIGGER_LEMMAS,
            APPOINTMENT_NOUN_LEMMAS,
        )

    @staticmethod
    def _has_dismissal_lemma_signal(parsed_words: list[ParsedWord]) -> bool:
        if has_lemma(parsed_words, DISMISSAL_TRIGGER_LEMMAS):
            return True
        lemmas = lemma_set(parsed_words)
        if lemmas.intersection({"złożyć", "przyjąć"}) and lemmas.intersection(
            DISMISSAL_NOUN_LEMMAS
        ):
            return True
        return has_lemma_pair(
            parsed_words,
            frozenset({"złożyć", "przyjąć"}),
            DISMISSAL_NOUN_LEMMAS,
        )

    def _extract_discourse_frame(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        context: ExtractionContext,
        event_type: EventType,
    ) -> GovernanceFrame | None:
        person_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        if not person_clusters:
            person_clusters = self._sort_clusters_by_clause_distance(
                context.previous_clusters(
                    clause,
                    {EntityType.PERSON},
                    max_distance=2,
                ),
                clause,
            )
            if not person_clusters and event_type == EventType.DISMISSAL:
                person_clusters = self._sort_clusters_by_clause_distance(
                    context.following_clusters(
                        clause,
                        {EntityType.PERSON},
                        max_distance=1,
                    ),
                    clause,
                )
        elif event_type == EventType.APPOINTMENT and self._has_object_pronoun(document, clause):
            person_clusters = self._merge_clusters(
                person_clusters,
                self._sort_clusters_by_clause_distance(
                    context.previous_clusters(
                        clause,
                        {EntityType.PERSON},
                        max_distance=2,
                    ),
                    clause,
                ),
            )
        if not person_clusters:
            return None

        role_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        role_cluster = (
            role_clusters[0] if role_clusters else self._find_role_from_text(document, clause)
        )
        role_text = None if role_cluster is not None else self._find_role_text(document, clause)

        clause_orgs = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )
        discourse_orgs = self._merge_clusters(
            clause_orgs,
            self._merge_clusters(
                context.following_clusters(
                    clause,
                    {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                    max_distance=2,
                    same_paragraph=False,
                ),
                context.previous_clusters(
                    clause,
                    {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                    max_distance=2,
                ),
            ),
        )
        org_clusters = self._sort_clusters_by_clause_distance(discourse_orgs, clause)
        if not org_clusters:
            return None

        person_cluster_id, appointing_authority_id = self._resolve_people(
            clause,
            document,
            person_clusters,
            event_type,
        )
        if person_cluster_id is None:
            return None

        target_resolution = self.target_resolver.resolve(
            document=document,
            clause=clause,
            org_clusters=org_clusters,
            role_cluster=role_cluster,
        )
        if target_resolution.target_org is None:
            return None

        target_res_reason = target_resolution.reason
        found_role = role_text
        evidence_scope = None
        if (
            not clause_orgs
            or len(
                {
                    evidence.sentence_index
                    for evidence in context.evidence_window(
                        clause,
                        [
                            *person_clusters,
                            *org_clusters,
                            *([role_cluster] if role_cluster is not None else []),
                        ],
                    )
                }
            )
            > 1
        ):
            evidence_scope = "discourse_window"

        evidence = context.evidence_window(
            clause,
            [
                *person_clusters,
                target_resolution.target_org,
                *(
                    [target_resolution.owner_context]
                    if target_resolution.owner_context is not None
                    else []
                ),
                *(
                    [target_resolution.governing_body]
                    if target_resolution.governing_body is not None
                    else []
                ),
                *([role_cluster] if role_cluster is not None else []),
            ],
        )

        return GovernanceFrame(
            frame_id=FrameID(f"frame-{uuid.uuid4().hex[:8]}"),
            event_type=event_type,
            person_cluster_id=ClusterID(person_cluster_id) if person_cluster_id else None,
            role_cluster_id=role_cluster.cluster_id if role_cluster is not None else None,
            target_org_cluster_id=target_resolution.target_org.cluster_id,
            owner_context_cluster_id=target_resolution.owner_context.cluster_id
            if target_resolution.owner_context
            else None,
            governing_body_cluster_id=target_resolution.governing_body.cluster_id
            if target_resolution.governing_body
            else None,
            appointing_authority_cluster_id=ClusterID(appointing_authority_id)
            if appointing_authority_id
            else None,
            confidence=target_resolution.confidence,
            evidence=evidence,
            target_resolution=target_res_reason,
            found_role=found_role,
            evidence_scope=evidence_scope,
        )

    def _extract_frame_from_clause(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        event_type: EventType,
    ) -> GovernanceFrame | None:
        person_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        role_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        org_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )
        if not person_clusters:
            person_clusters = self._paragraph_context_clusters(
                document,
                clause,
                {EntityType.PERSON},
            )
        elif event_type == EventType.APPOINTMENT and self._has_object_pronoun(document, clause):
            person_clusters = self._merge_clusters(
                person_clusters,
                self._paragraph_context_clusters(
                    document,
                    clause,
                    {EntityType.PERSON},
                ),
            )
        if not org_clusters:
            org_clusters = self._paragraph_context_clusters(
                document,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
            )

        if not person_clusters:
            return None

        person_cluster_id, appointing_authority_id = self._resolve_people(
            clause,
            document,
            person_clusters,
            event_type,
        )
        if person_cluster_id is None:
            return None

        role_cluster = (
            role_clusters[0] if role_clusters else self._find_role_from_text(document, clause)
        )
        role_cluster_id = role_cluster.cluster_id if role_cluster is not None else None
        role_text = None if role_cluster is not None else self._find_role_text(document, clause)

        target_resolution = self.target_resolver.resolve(
            document=document,
            clause=clause,
            org_clusters=org_clusters,
            role_cluster=role_cluster,
        )
        if target_resolution.target_org is None:
            return None

        return GovernanceFrame(
            frame_id=FrameID(f"frame-{uuid.uuid4().hex[:8]}"),
            event_type=event_type,
            person_cluster_id=ClusterID(person_cluster_id) if person_cluster_id else None,
            role_cluster_id=role_cluster_id,
            target_org_cluster_id=target_resolution.target_org.cluster_id,
            owner_context_cluster_id=target_resolution.owner_context.cluster_id
            if target_resolution.owner_context
            else None,
            governing_body_cluster_id=target_resolution.governing_body.cluster_id
            if target_resolution.governing_body
            else None,
            appointing_authority_cluster_id=ClusterID(appointing_authority_id)
            if appointing_authority_id
            else None,
            confidence=target_resolution.confidence,
            evidence=[
                EvidenceSpan(
                    text=clause.text,
                    sentence_index=clause.sentence_index,
                    paragraph_index=clause.paragraph_index,
                    start_char=clause.start_char,
                    end_char=clause.end_char,
                )
            ],
            target_resolution=target_resolution.reason,
            found_role=role_text,
        )

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        seen: set[str] = set()
        clusters: list[EntityCluster] = []
        for mention in mentions:
            if mention.entity_type not in entity_types:
                continue
            cluster = self._find_cluster_for_mention(mention, document)
            if cluster is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

    def _resolve_people(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        person_clusters: list[EntityCluster],
        event_type: EventType,
    ) -> tuple[str | None, str | None]:
        appointees: list[ClusterID] = []
        authorities: list[ClusterID] = []
        person_cluster_ids = {cluster.cluster_id for cluster in person_clusters}
        speech_speaker_ids = self._speech_speaker_cluster_ids(clause, document, person_clusters)
        for mention in clause.cluster_mentions:
            cluster = next(
                (
                    cluster
                    for cluster in person_clusters
                    if self._cluster_matches_mention(cluster, mention)
                ),
                None,
            )
            if cluster is None or cluster.cluster_id not in person_cluster_ids:
                continue
            role = clause.mention_roles.get(mention.text)
            if role and role.startswith("obj"):
                appointees.append(cluster.cluster_id)
            elif role and (role.startswith("nsubj") or role == "appos"):
                authorities.append(cluster.cluster_id)

        if appointees:
            appointee_id = self._first_non_speaker(appointees, speech_speaker_ids)
            if appointee_id is None:
                appointee_id = appointees[0]
            return appointee_id, authorities[0] if authorities else None
        if authorities and self._has_object_pronoun(document, clause):
            authority_ids = self._non_speaker_ids(authorities, speech_speaker_ids)
            previous_person = self._nearest_context_person(
                clause,
                person_clusters,
                excluded_cluster_ids=set(authorities) | speech_speaker_ids,
            )
            if previous_person is not None:
                return previous_person.cluster_id, authority_ids[0] if authority_ids else None
        if authorities:
            authority_ids = (
                self._non_speaker_ids(authorities, speech_speaker_ids)
                if event_type == EventType.DISMISSAL
                else authorities
            )
            if authority_ids:
                return authority_ids[0], None
            previous_person = self._nearest_context_person(
                clause,
                person_clusters,
                excluded_cluster_ids=speech_speaker_ids,
            )
            if previous_person is None:
                return None, None
            return previous_person.cluster_id, None
        candidate_clusters = (
            [
                cluster
                for cluster in person_clusters
                if cluster.cluster_id not in speech_speaker_ids
                and self._cluster_has_dismissal_subject_signal(clause, cluster)
            ]
            if event_type == EventType.DISMISSAL
            else person_clusters
        )
        if (
            not candidate_clusters
            and event_type == EventType.DISMISSAL
            and not self._near_family_subject(document, clause)
        ):
            candidate_clusters = [
                cluster
                for cluster in person_clusters
                if cluster.cluster_id not in speech_speaker_ids
            ]
        if not candidate_clusters:
            return None, None
        return candidate_clusters[0].cluster_id, None

    @staticmethod
    def _cluster_has_dismissal_subject_signal(
        clause: ClauseUnit,
        cluster: EntityCluster,
    ) -> bool:
        for mention in cluster.mentions:
            if mention.sentence_index != clause.sentence_index:
                continue
            role = clause.mention_roles.get(mention.text)
            if role and (role.startswith("nsubj") or role.startswith("obj")):
                return True
            if cluster.is_proxy_person and role == "det:poss":
                return True
        return False

    @staticmethod
    def _near_family_subject(document: ArticleDocument, clause: ClauseUnit) -> bool:
        for sentence_index in {clause.sentence_index, clause.sentence_index - 1}:
            for word in document.parsed_sentences.get(sentence_index, []):
                if word.lemma.casefold() in KINSHIP_LEMMAS and word.deprel.startswith("nsubj"):
                    return True
        return False

    @staticmethod
    def _first_non_speaker(
        cluster_ids: list[ClusterID],
        speech_speaker_ids: set[ClusterID],
    ) -> ClusterID | None:
        return next(
            (cluster_id for cluster_id in cluster_ids if cluster_id not in speech_speaker_ids),
            None,
        )

    @staticmethod
    def _non_speaker_ids(
        cluster_ids: list[ClusterID],
        speech_speaker_ids: set[ClusterID],
    ) -> list[ClusterID]:
        return [cluster_id for cluster_id in cluster_ids if cluster_id not in speech_speaker_ids]

    def _speech_speaker_cluster_ids(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        person_clusters: list[EntityCluster],
    ) -> set[ClusterID]:
        parsed = document.parsed_sentences.get(clause.sentence_index, [])
        speech_heads = {word.index for word in parsed if word.lemma.casefold() in SPEECH_LEMMAS}
        if not speech_heads:
            return set()
        subject_indices = {
            word.index
            for word in parsed
            if word.head in speech_heads and word.deprel.startswith("nsubj")
        }
        if subject_indices:
            subject_indices |= {word.index for word in parsed if word.head in subject_indices}
        result: set[ClusterID] = set()
        for cluster in person_clusters:
            if self._cluster_has_word_indices(clause, cluster, parsed, subject_indices):
                result.add(cluster.cluster_id)
        return result

    @staticmethod
    def _cluster_has_word_indices(
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

    def _find_role_from_text(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        role_text = self._find_role_text(document, clause)
        if role_text is None:
            return None
        for cluster in document.clusters:
            if cluster.entity_type != EntityType.POSITION:
                continue
            if cluster.canonical_name.lower() == role_text.lower():
                return cluster
        return None

    @staticmethod
    def _find_role_text(document: ArticleDocument, clause: ClauseUnit) -> str | None:
        parsed = document.parsed_sentences.get(clause.sentence_index, [])
        role_matches = match_role_mentions(parsed)
        if role_matches:
            return role_matches[0].canonical_name
        return PolishGovernanceFrameExtractor._find_role_text_from_text(clause)

    @staticmethod
    def _find_role_text_from_text(clause: ClauseUnit) -> str | None:
        for role, modifier, pattern in sorted(
            ROLE_PATTERNS,
            key=lambda item: len(item[0].value) + (len(item[1].value) if item[1] else 0),
            reverse=True,
        ):
            if pattern.search(clause.text):
                base_name = normalize_entity_name(role.value)
                return f"{modifier.value} {base_name}" if modifier else base_name
        return None

    def _find_cluster_for_mention(
        self,
        mention_ref: ClusterMention,
        document: ArticleDocument,
    ) -> EntityCluster | None:
        for cluster in document.clusters:
            for mention in cluster.mentions:
                if (
                    mention.start_char == mention_ref.start_char
                    and mention.end_char == mention_ref.end_char
                    and mention.sentence_index == mention_ref.sentence_index
                    and mention.entity_type == mention_ref.entity_type
                ):
                    return cluster
                if (
                    mention.text == mention_ref.text
                    and mention.sentence_index == mention_ref.sentence_index
                    and mention.entity_type == mention_ref.entity_type
                ):
                    return cluster
        return None

    def _cluster_matches_mention(
        self,
        cluster: EntityCluster,
        mention_ref: ClusterMention,
    ) -> bool:
        return any(
            mention.text == mention_ref.text
            and mention.sentence_index == mention_ref.sentence_index
            and mention.entity_type == mention_ref.entity_type
            for mention in cluster.mentions
        )

    def _paragraph_context_clusters(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        candidates: list[EntityCluster] = []
        seen: set[str] = set()
        for cluster in document.clusters:
            if cluster.entity_type not in entity_types or cluster.cluster_id in seen:
                continue
            if not any(
                mention.paragraph_index == clause.paragraph_index for mention in cluster.mentions
            ):
                continue
            seen.add(cluster.cluster_id)
            candidates.append(cluster)
        return sorted(
            candidates,
            key=lambda cluster: self._cluster_clause_distance(cluster, clause),
        )

    @staticmethod
    def _merge_clusters(
        primary: list[EntityCluster],
        secondary: list[EntityCluster],
    ) -> list[EntityCluster]:
        merged: list[EntityCluster] = []
        seen: set[str] = set()
        for cluster in [*primary, *secondary]:
            if cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            merged.append(cluster)
        return merged

    @staticmethod
    def _sort_clusters_by_clause_distance(
        clusters: list[EntityCluster],
        clause: ClauseUnit,
    ) -> list[EntityCluster]:
        return sorted(
            clusters,
            key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
                cluster,
                clause,
            ),
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
    def _nearest_context_person(
        clause: ClauseUnit,
        person_clusters: list[EntityCluster],
        *,
        excluded_cluster_ids: set[ClusterID],
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in person_clusters
            if cluster.cluster_id not in excluded_cluster_ids
            and any(mention.sentence_index <= clause.sentence_index for mention in cluster.mentions)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
                cluster,
                clause,
            ),
        )

    @staticmethod
    def _has_object_pronoun(document: ArticleDocument, clause: ClauseUnit) -> bool:
        object_pronouns = {"go", "ją", "je", "ich", "jego", "jej"}
        return any(
            word.text.lower() in object_pronouns
            and (word.deprel.startswith("obj") or word.deprel in {"iobj", "obl"})
            for word in document.parsed_sentences.get(clause.sentence_index, [])
        )


class PolishCompensationFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_compensation_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.compensation_frames = []
        for clause in document.clause_units:
            if self._looks_like_funding_clause(document, clause):
                continue
            for match in COMPENSATION_PATTERN.finditer(clause.text):
                if not self._has_compensation_context(document, clause):
                    continue
                frame = self._extract_frame_from_clause(document, clause, match)
                if frame is not None:
                    document.compensation_frames.append(frame)
        return document

    def _extract_frame_from_clause(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        match,
    ) -> CompensationFrame | None:
        amount_text = match.group("amount")
        if not amount_text:
            return None
        period = match.group("period")
        amount_start = clause.start_char + match.start("amount")

        person_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        role_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        org_clusters = self._clusters_for_mentions(
            document,
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )

        person_cluster = self._best_cluster_near_offset(person_clusters, amount_start)
        role_cluster = self._best_cluster_near_offset(role_clusters, amount_start)
        if role_cluster is None:
            role_cluster = self._find_role_from_text(document, clause)
        org_cluster = self._best_cluster_near_offset(org_clusters, amount_start)

        context_reason = "same_clause"
        if person_cluster is None:
            person_cluster = self._paragraph_context_cluster(
                document,
                clause,
                {EntityType.PERSON},
                amount_start,
            )
            if person_cluster is not None:
                context_reason = "paragraph_carryover"
        if org_cluster is None:
            org_cluster = self._paragraph_context_cluster(
                document,
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
                amount_start,
            )
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "paragraph_org"

        governance_context = self._governance_context(document, clause, person_cluster)
        if role_cluster is None and governance_context is not None:
            role_cluster = self._cluster_by_id(document, governance_context.role_cluster_id)
        if org_cluster is None and governance_context is not None:
            org_cluster = self._cluster_by_id(document, governance_context.target_org_cluster_id)
            if org_cluster is not None and context_reason == "same_clause":
                context_reason = "governance_context"

        if person_cluster is None and role_cluster is None and org_cluster is None:
            return None

        confidence, score_reason = self._score_frame(
            person_cluster=person_cluster,
            role_cluster=role_cluster,
            org_cluster=org_cluster,
            context_reason=context_reason,
        )
        return CompensationFrame(
            frame_id=FrameID(f"comp-frame-{uuid.uuid4().hex[:8]}"),
            amount_text=amount_text,
            amount_normalized=normalize_entity_name(amount_text.lower()),
            period=normalize_entity_name(period.lower()) if period else None,
            person_cluster_id=person_cluster.cluster_id if person_cluster else None,
            role_cluster_id=role_cluster.cluster_id if role_cluster else None,
            organization_cluster_id=org_cluster.cluster_id if org_cluster else None,
            confidence=confidence,
            evidence=[
                EvidenceSpan(
                    text=clause.text,
                    sentence_index=clause.sentence_index,
                    paragraph_index=clause.paragraph_index,
                    start_char=clause.start_char,
                    end_char=clause.end_char,
                )
            ],
            extraction_signal=self._extraction_signal(score_reason),
            evidence_scope="same_clause" if context_reason == "same_clause" else "same_paragraph",
            score_reason=score_reason,
            context_reason=context_reason,
        )

    def _has_compensation_context(self, document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        if any(trigger in lowered for trigger in COMPENSATION_CONTEXT_TEXTS):
            return True
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        return bool(
            {word.lemma.lower() for word in parsed_words}.intersection(COMPENSATION_CONTEXT_LEMMAS)
        )

    @staticmethod
    def _looks_like_funding_clause(document: ArticleDocument, clause: ClauseUnit) -> bool:
        lowered = clause.text.lower()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = lemma_set(parsed_words)
        return bool(
            lemmas.intersection(FUNDING_HINTS)
            or clause.trigger_head_lemma.lower() in FUNDING_HINTS
            or (not parsed_words and any(hint in lowered for hint in FUNDING_SURFACE_FALLBACKS))
        )

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        seen: set[str] = set()
        clusters: list[EntityCluster] = []
        for mention in mentions:
            if mention.entity_type not in entity_types:
                continue
            cluster = self._find_cluster_for_mention(mention, document)
            if cluster is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

    @staticmethod
    def _find_cluster_for_mention(
        mention_ref: ClusterMention,
        document: ArticleDocument,
    ) -> EntityCluster | None:
        for cluster in document.clusters:
            for mention in cluster.mentions:
                if (
                    mention.start_char == mention_ref.start_char
                    and mention.end_char == mention_ref.end_char
                    and mention.sentence_index == mention_ref.sentence_index
                    and mention.entity_type == mention_ref.entity_type
                ):
                    return cluster
                if (
                    mention.text == mention_ref.text
                    and mention.sentence_index == mention_ref.sentence_index
                    and mention.entity_type == mention_ref.entity_type
                ):
                    return cluster
        return None

    @staticmethod
    def _best_cluster_near_offset(
        clusters: list[EntityCluster],
        offset: int,
    ) -> EntityCluster | None:
        if not clusters:
            return None
        return min(
            clusters,
            key=lambda cluster: min(
                abs(mention.start_char - offset) for mention in cluster.mentions
            ),
        )

    @classmethod
    def _paragraph_context_cluster(
        cls,
        document: ArticleDocument,
        clause: ClauseUnit,
        entity_types: set[EntityType],
        offset: int,
    ) -> EntityCluster | None:
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in entity_types
            and any(
                mention.paragraph_index == clause.paragraph_index
                and mention.sentence_index <= clause.sentence_index
                for mention in cluster.mentions
            )
        ]
        return cls._best_cluster_near_offset(candidates, offset)

    def _find_role_from_text(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        role_text = PolishGovernanceFrameExtractor._find_role_text(document, clause)
        if role_text is None:
            return None
        for cluster in document.clusters:
            if cluster.entity_type != EntityType.POSITION:
                continue
            if cluster.canonical_name.lower() == role_text.lower():
                return cluster
        return None

    @staticmethod
    def _governance_context(
        document: ArticleDocument,
        clause: ClauseUnit,
        person: EntityCluster | None,
    ):
        for frame in document.governance_frames:
            if not frame.evidence:
                continue
            evidence = frame.evidence[0]
            same_paragraph = evidence.paragraph_index == clause.paragraph_index
            same_person = person is not None and frame.person_cluster_id == person.cluster_id
            if same_paragraph and (same_person or person is None):
                return frame
        return None

    @staticmethod
    def _cluster_by_id(document: ArticleDocument, cluster_id: str | None) -> EntityCluster | None:
        if cluster_id is None:
            return None
        return next(
            (cluster for cluster in document.clusters if cluster.cluster_id == cluster_id),
            None,
        )

    @staticmethod
    def _score_frame(
        *,
        person_cluster: EntityCluster | None,
        role_cluster: EntityCluster | None,
        org_cluster: EntityCluster | None,
        context_reason: str,
    ) -> tuple[float, str]:
        if person_cluster is not None and org_cluster is not None and role_cluster is not None:
            return 0.85, "person_amount_role_org_same_clause"
        if person_cluster is not None and org_cluster is not None:
            if context_reason == "same_clause":
                return 0.74, "person_amount_org_same_clause"
            return 0.66, "person_amount_paragraph_org"
        if role_cluster is not None and org_cluster is not None:
            return 0.66, "role_amount_org"
        if org_cluster is not None:
            return 0.55, "public_org_amount_salary_context"
        if person_cluster is not None:
            return 0.55, "amount_person"
        return 0.42, "paragraph_carryover"

    @staticmethod
    def _extraction_signal(score_reason: str) -> str:
        if score_reason == "person_amount_role_org_same_clause":
            return "syntactic_direct"
        if "same_clause" in score_reason:
            return "dependency_edge"
        if "paragraph" in score_reason:
            return "same_paragraph"
        return "same_clause"


class PolishFundingFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_funding_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.funding_frames = []
        for clause in document.clause_units:
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
            evidence=[
                EvidenceSpan(
                    text=clause.text,
                    sentence_index=clause.sentence_index,
                    paragraph_index=clause.paragraph_index,
                    start_char=clause.start_char,
                    end_char=clause.end_char,
                )
            ],
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
        seen: set[str] = set()
        clusters: list[EntityCluster] = []
        for mention in mentions:
            if mention.entity_type not in entity_types:
                continue
            cluster = PolishCompensationFrameExtractor._find_cluster_for_mention(
                mention,
                document,
            )
            if cluster is None or cluster.cluster_id in seen:
                continue
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
        return clusters

    @staticmethod
    def _paragraph_context_clusters(
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> list[EntityCluster]:
        clusters = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and any(
                mention.paragraph_index == clause.paragraph_index for mention in cluster.mentions
            )
        ]
        return sorted(
            clusters,
            key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
                cluster,
                clause,
            ),
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
            key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
                cluster,
                clause,
            ),
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
