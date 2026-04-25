from __future__ import annotations

import uuid
from collections.abc import Iterable

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import (
    ACCOUNTABILITY_INSTITUTION_MARKERS,
    INVALID_PUBLIC_EMPLOYMENT_ROLE_HEADS,
    INVESTIGATION_NOUN_LEMMAS,
    INVESTIGATION_TRIGGER_LEMMAS,
    KINSHIP_LEMMAS,
    PROCUREMENT_ABUSE_LEMMAS,
    PUBLIC_EMPLOYER_TERMS,
    PUBLIC_OFFICE_ROLE_KINDS,
    REFERRAL_NOUN_LEMMAS,
    REFERRAL_TRIGGER_LEMMAS,
)
from pipeline.domain_types import (
    ClusterID,
    EntityType,
    EventType,
    FrameID,
    OrganizationKind,
    PublicEmploymentSignal,
)
from pipeline.domains.public_money import (
    FUNDING_SURFACE_FALLBACKS,
    PolishFundingFrameExtractor,
    PolishPublicContractFrameExtractor,
    is_public_counterparty,
)
from pipeline.extraction_context import ExtractionContext
from pipeline.governance import GovernanceTargetResolver
from pipeline.lemma_signals import has_lemma, has_lemma_pair, lemma_set
from pipeline.models import (
    AntiCorruptionInvestigationFrame,
    AntiCorruptionReferralFrame,
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    CompensationFrame,
    EntityCluster,
    EvidenceSpan,
    GovernanceFrame,
    ParsedWord,
    PublicEmploymentFrame,
    PublicProcurementAbuseFrame,
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

WEAK_APPOINTMENT_TRIGGER_LEMMAS = frozenset(
    {"objąć", "zająć", "pracować", "zatrudnić", "zatrudnienie", "trafić"}
)


class PolishFrameExtractor(FrameExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.governance = PolishGovernanceFrameExtractor(config)
        self.compensation = PolishCompensationFrameExtractor(config)
        self.funding = PolishFundingFrameExtractor(config)
        self.public_contracts = PolishPublicContractFrameExtractor(config)
        self.public_employment = PolishPublicEmploymentFrameExtractor(config)
        self.anti_corruption_referrals = PolishAntiCorruptionReferralFrameExtractor(config)
        self.anti_corruption_abuse = PolishAntiCorruptionAbuseFrameExtractor(config)

    def name(self) -> str:
        return "polish_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document = self.governance.run(document)
        document = self.compensation.run(document)
        document = self.funding.run(document)
        document = self.public_contracts.run(document)
        document = self.public_employment.run(document)
        document = self.anti_corruption_referrals.run(document)
        return self.anti_corruption_abuse.run(document)


class PolishPublicEmploymentFrameExtractor(FrameExtractor):
    ENTRY_LEMMAS = frozenset({"zatrudnić", "dostać", "objąć", "zostać", "trafić"})
    STATUS_LEMMAS = frozenset({"pracować", "być"})
    ENTRY_TEXT_MARKERS = (
        "dostał pracę",
        "dostała pracę",
        "został zatrudniony",
        "została zatrudniona",
        "zatrudniono",
        "został koordynatorem",
        "została koordynatorką",
        "objął funkcję",
        "objęła funkcję",
    )
    STATUS_TEXT_MARKERS = (
        "pracuje",
        "pracowała",
        "pracował",
        "jest zatrudniona",
        "jest zatrudniony",
        "była zatrudniona",
        "był zatrudniony",
        "jest dyrektorem",
        "jest dyrektorką",
    )
    ROLE_STOP_WORDS = frozenset(
        {"w", "we", "do", "na", "od", "przy", "oraz", "i", "a", "ale", "który", "która"}
    )

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def name(self) -> str:
        return "polish_public_employment_frame_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.public_employment_frames = []
        for clause in document.clause_units:
            signal = self._signal(document, clause)
            if signal is None:
                continue
            employer = self._employer_cluster(document, clause)
            employee = self._employee_cluster(document, clause)
            if employer is None or employee is None:
                continue
            role_cluster = self._role_cluster(document, clause, employee)
            if role_cluster is not None and self._is_public_office_role(role_cluster):
                role_cluster = None
            role_label = (
                role_cluster.canonical_name
                if role_cluster is not None
                else self._role_label_near_employee(document, clause, employee)
                or self._role_label(document, clause)
            )
            if self._invalid_role_label(role_label):
                continue
            document.public_employment_frames.append(
                PublicEmploymentFrame(
                    frame_id=FrameID(f"public-employment-frame-{uuid.uuid4().hex[:8]}"),
                    signal=signal,
                    employee_cluster_id=employee.cluster_id,
                    employer_cluster_id=employer.cluster_id,
                    role_label=role_label,
                    role_cluster_id=role_cluster.cluster_id if role_cluster is not None else None,
                    confidence=0.78 if role_label is not None else 0.64,
                    evidence=[self._evidence(clause)],
                    extraction_signal=(
                        "dependency_edge" if role_label is not None else "same_clause"
                    ),
                    evidence_scope="same_clause",
                    score_reason="public_employment",
                )
            )
        return document

    def _signal(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> PublicEmploymentSignal | None:
        lowered = clause.text.casefold()
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        lemmas = {word.lemma.casefold() for word in parsed_words}
        if any(marker in lowered for marker in self.ENTRY_TEXT_MARKERS):
            return PublicEmploymentSignal.ENTRY
        if "zostać" in lemmas and any(
            marker in lowered for marker in ("koordynator", "specjalist", "stanowisk")
        ):
            return PublicEmploymentSignal.ENTRY
        if lemmas.intersection(self.ENTRY_LEMMAS - {"zostać"}):
            return PublicEmploymentSignal.ENTRY
        if any(marker in lowered for marker in self.STATUS_TEXT_MARKERS):
            return PublicEmploymentSignal.STATUS
        if lemmas.intersection(self.STATUS_LEMMAS) and "zatrudn" in lowered:
            return PublicEmploymentSignal.STATUS
        if "pracuje" in lowered or "pracował" in lowered:
            return PublicEmploymentSignal.STATUS
        return None

    def _employer_cluster(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        current = [
            cluster
            for cluster in self._clusters_for_clause(document, clause)
            if self._is_public_employer(cluster)
        ]
        if current:
            return min(current, key=lambda cluster: self._cluster_clause_distance(cluster, clause))
        adjacent = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and self._is_public_employer(cluster)
            and any(
                mention.paragraph_index == clause.paragraph_index
                and abs(mention.sentence_index - clause.sentence_index) <= 2
                for mention in cluster.mentions
            )
        ]
        return min(
            adjacent or self._document_level_employer_candidates(document, clause),
            key=lambda cluster: self._cluster_clause_distance(cluster, clause),
            default=None,
        )

    def _document_level_employer_candidates(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> list[EntityCluster]:
        lowered = clause.text.casefold()
        if not any(
            marker in lowered
            for marker in (
                "urząd",
                "urzędzie",
                "gmina",
                "gminy",
                "koordynator",
                "projekt",
            )
        ):
            return []
        return [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and self._is_public_employer(cluster)
            and any(
                marker in cluster.normalized_name.casefold()
                for marker in ("urząd gmin", "gmin", "starostw", "powiatow")
            )
        ]

    def _employee_cluster(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        patient = self._employment_patient_cluster(document, clause)
        if patient is not None:
            return patient
        subject = self._subject_cluster(document, clause)
        if subject is not None:
            return self._proxy_cluster_for_anchor(document, clause, subject) or subject
        return min(
            (
                cluster
                for cluster in self._clusters_for_clause(document, clause)
                if cluster.entity_type == EntityType.PERSON
            ),
            key=lambda cluster: self._cluster_clause_distance(cluster, clause),
            default=None,
        )

    def _employment_patient_cluster(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        for trigger_word in [word for word in parsed_words if word.lemma.casefold() == "zatrudnić"]:
            object_words = [
                word
                for word in parsed_words
                if word.head == trigger_word.index
                and (word.deprel in {"obj", "iobj"} or word.deprel.startswith("nsubj:pass"))
            ]
            for object_word in object_words:
                cluster = self._person_cluster_overlapping_word(document, clause, object_word)
                if cluster is not None:
                    return cluster
                cluster = self._person_cluster_in_subtree(document, clause, object_word.index)
                if cluster is not None:
                    return cluster
                if object_word.lemma.casefold() in KINSHIP_LEMMAS:
                    return self._nearest_proxy_cluster(document, clause, object_word.start)
        return None

    def _subject_cluster(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
    ) -> EntityCluster | None:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        for word in [word for word in parsed_words if word.deprel.startswith("nsubj")]:
            cluster = self._person_cluster_overlapping_word(document, clause, word)
            if cluster is not None:
                return cluster
            cluster = self._person_cluster_in_subtree(document, clause, word.index)
            if cluster is not None:
                return cluster
        return None

    def _person_cluster_in_subtree(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        head_index: int,
        *,
        seen: set[int] | None = None,
    ) -> EntityCluster | None:
        if seen is None:
            seen = set()
        if head_index in seen:
            return None
        seen.add(head_index)
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        for child in parsed_words:
            if child.head != head_index:
                continue
            cluster = self._person_cluster_overlapping_word(document, clause, child)
            if cluster is not None:
                return cluster
            descendant = self._person_cluster_in_subtree(
                document,
                clause,
                child.index,
                seen=seen,
            )
            if descendant is not None:
                return descendant
        return None

    def _person_cluster_overlapping_word(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        word: ParsedWord,
    ) -> EntityCluster | None:
        for cluster in self._clusters_for_clause(document, clause):
            if cluster.entity_type != EntityType.PERSON:
                continue
            if any(
                self._mention_local_start(mention, clause)
                <= word.start
                < self._mention_local_end(mention, clause)
                for mention in cluster.mentions
                if mention.sentence_index == clause.sentence_index
            ):
                return cluster
        return None

    def _nearest_proxy_cluster(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        local_start: int,
    ) -> EntityCluster | None:
        proxies = [
            cluster
            for cluster in self._clusters_for_clause(document, clause)
            if cluster.entity_type == EntityType.PERSON and cluster.is_proxy_person
        ]
        return min(
            proxies,
            key=lambda cluster: self._cluster_clause_distance(cluster, clause) + local_start,
            default=None,
        )

    @staticmethod
    def _proxy_cluster_for_anchor(
        document: ArticleDocument,
        clause: ClauseUnit,
        subject: EntityCluster,
    ) -> EntityCluster | None:
        subject_entity_ids = {
            mention.entity_id for mention in subject.mentions if mention.entity_id
        }
        return next(
            (
                cluster
                for cluster in document.clusters
                if cluster.is_proxy_person
                and cluster.proxy_anchor_entity_id in subject_entity_ids
                and any(
                    mention.sentence_index == clause.sentence_index for mention in cluster.mentions
                )
            ),
            None,
        )

    def _role_cluster(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        employee: EntityCluster,
    ) -> EntityCluster | None:
        roles = [
            cluster
            for cluster in self._clusters_for_clause(document, clause)
            if cluster.entity_type == EntityType.POSITION
        ]
        employee_distance = self._cluster_clause_distance(employee, clause)
        return min(
            roles,
            key=lambda cluster: abs(
                self._cluster_clause_distance(cluster, clause) - employee_distance
            ),
            default=None,
        )

    def _role_label_near_employee(
        self,
        document: ArticleDocument,
        clause: ClauseUnit,
        employee: EntityCluster,
    ) -> str | None:
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
                label := self._role_label_from_subtree(parsed_words, stanowisko.index)
            ):
                return label
            governing_word = next(
                (word for word in parsed_words if word.index == employee_word.head),
                None,
            )
            if governing_word is None:
                continue
            stanowisko = self._first_child_with_lemma(
                parsed_words,
                governing_word.index,
                "stanowisko",
            )
            if stanowisko is not None and (
                label := self._role_label_from_subtree(parsed_words, stanowisko.index)
            ):
                return label
        return None

    def _role_label(self, document: ArticleDocument, clause: ClauseUnit) -> str | None:
        parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
        if parsed_label := self._role_label_from_words(parsed_words):
            return parsed_label
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
                label := self._clean_role_label(clause.text[marker_index + len(marker) :])
            ):
                return label
        return None

    def _role_label_from_words(self, parsed_words: list[ParsedWord]) -> str | None:
        marker_indices = [
            index
            for index, word in enumerate(parsed_words)
            if word.lemma.casefold() in self.ENTRY_LEMMAS | self.STATUS_LEMMAS
            or word.text.casefold() == "jako"
        ]
        if not marker_indices:
            return None
        marker_index = next(
            (index for index in marker_indices if parsed_words[index].text.casefold() == "jako"),
            marker_indices[0],
        )
        phrase_words: list[ParsedWord] = []
        for word in parsed_words[marker_index + 1 :]:
            lemma = word.lemma.casefold()
            if lemma in self.ROLE_STOP_WORDS or word.upos in {"ADP", "SCONJ", "CCONJ", "VERB"}:
                if phrase_words:
                    break
                continue
            if lemma in PUBLIC_EMPLOYER_TERMS:
                break
            if lemma == "stanowisko" and not phrase_words:
                continue
            if word.upos in {"ADJ", "NOUN", "PROPN"}:
                phrase_words.append(word)
                if len(phrase_words) >= 4:
                    break
            elif phrase_words:
                break
        if not phrase_words:
            return None
        return normalize_entity_name(
            " ".join(
                word.text if word.deprel.casefold() == "nmod" or word.upos == "ADJ" else word.lemma
                for word in phrase_words
            )
        )

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
                if word.head == head_index and word.lemma.casefold() == lemma
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
            if child.lemma.casefold() == lemma:
                return child
            if descendant := self._first_descendant_with_lemma(
                parsed_words,
                child.index,
                lemma,
                seen=seen,
            ):
                return descendant
        return None

    def _role_label_from_subtree(
        self,
        parsed_words: list[ParsedWord],
        head_index: int,
    ) -> str | None:
        by_head: dict[int, list[ParsedWord]] = {}
        for word in parsed_words:
            by_head.setdefault(word.head, []).append(word)
        head_nouns = [
            word
            for word in by_head.get(head_index, [])
            if word.upos in {"NOUN", "PROPN"} and word.lemma.casefold() != "stanowisko"
        ]
        if not head_nouns:
            return None
        head = min(head_nouns, key=lambda word: word.start)
        phrase_words = [head]
        phrase_words.extend(
            word for word in by_head.get(head.index, []) if word.upos in {"ADJ", "NOUN", "PROPN"}
        )
        ordered_words = sorted(phrase_words, key=lambda word: word.start)[:4]
        has_preceding_modifier = any(
            word.index != head.index and word.start < head.start for word in ordered_words
        )
        return normalize_entity_name(
            " ".join(
                self._role_label_token(
                    word,
                    head,
                    has_preceding_modifier=has_preceding_modifier,
                )
                for word in ordered_words
            )
        )

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

    def _clean_role_label(self, tail: str) -> str | None:
        words: list[str] = []
        for raw_word in tail.replace(".", " ").replace(",", " ").split():
            cleaned = raw_word.strip("()[]:;").casefold()
            if cleaned in self.ROLE_STOP_WORDS:
                break
            if cleaned in {"zatrudniony", "zatrudniona", "pracę", "prace"}:
                continue
            words.append(raw_word)
            if len(words) >= 4:
                break
        label = normalize_entity_name(" ".join(words))
        return label if label else None

    @staticmethod
    def _clusters_for_clause(document: ArticleDocument, clause: ClauseUnit) -> list[EntityCluster]:
        mention_keys = {
            (mention.entity_id, mention.start_char, mention.end_char)
            for mention in clause.cluster_mentions
        }
        return [
            cluster
            for cluster in document.clusters
            if any(
                (mention.entity_id, mention.start_char, mention.end_char) in mention_keys
                for mention in cluster.mentions
            )
        ]

    @staticmethod
    def _is_public_employer(cluster: EntityCluster) -> bool:
        if cluster.entity_type == EntityType.PUBLIC_INSTITUTION:
            return True
        if cluster.organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
            return True
        normalized = cluster.normalized_name.casefold()
        return any(term in normalized for term in PUBLIC_EMPLOYER_TERMS)

    @staticmethod
    def _is_public_office_role(cluster: EntityCluster) -> bool:
        if cluster.role_kind in PUBLIC_OFFICE_ROLE_KINDS:
            return True
        normalized = cluster.normalized_name.casefold()
        return any(
            marker in normalized
            for marker in ("wójt", "wojt", "starosta", "sekretarz", "marszałek", "wojewoda")
        )

    @staticmethod
    def _invalid_role_label(role_label: str | None) -> bool:
        if role_label is None:
            return False
        first_token = role_label.split()[0].casefold() if role_label.split() else ""
        return first_token in INVALID_PUBLIC_EMPLOYMENT_ROLE_HEADS

    @staticmethod
    def _mention_local_start(mention: ClusterMention, clause: ClauseUnit) -> int:
        return max(0, mention.start_char - clause.start_char)

    @staticmethod
    def _mention_local_end(mention: ClusterMention, clause: ClauseUnit) -> int:
        return max(0, mention.end_char - clause.start_char)

    @staticmethod
    def _cluster_clause_distance(cluster: EntityCluster, clause: ClauseUnit) -> int:
        return min(
            (
                abs(PolishPublicEmploymentFrameExtractor._mention_local_start(mention, clause))
                for mention in cluster.mentions
                if mention.sentence_index == clause.sentence_index
            ),
            default=9999,
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
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

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
            clusters = self._clusters_for_mentions(
                document,
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

    def _clusters_for_mentions(
        self,
        document: ArticleDocument,
        mentions: Iterable[ClusterMention],
        entity_types: set[EntityType],
    ) -> list[EntityCluster]:
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

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
            key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
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
            key=lambda cluster: PolishGovernanceFrameExtractor._cluster_clause_distance(
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
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

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
            elif role and role.startswith("nsubj"):
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
        if event_type == EventType.APPOINTMENT and self._has_object_pronoun(document, clause):
            current_sentence_ids = {
                cluster.cluster_id
                for cluster in person_clusters
                if any(
                    mention.sentence_index == clause.sentence_index for mention in cluster.mentions
                )
            }
            previous_person = self._nearest_context_person(
                clause,
                person_clusters,
                excluded_cluster_ids=current_sentence_ids | speech_speaker_ids,
            )
            if previous_person is not None:
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
        return ExtractionContext.build(document).cluster_for_mention(mention_ref)

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
        return ExtractionContext.build(document).paragraph_context_clusters(clause, entity_types)

    @staticmethod
    def _merge_clusters(
        primary: list[EntityCluster],
        secondary: list[EntityCluster],
    ) -> list[EntityCluster]:
        return ExtractionContext.merge_clusters(primary, secondary)

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
        return ExtractionContext.cluster_clause_distance(cluster, clause)

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
        return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)

    @staticmethod
    def _find_cluster_for_mention(
        mention_ref: ClusterMention,
        document: ArticleDocument,
    ) -> EntityCluster | None:
        return ExtractionContext.build(document).cluster_for_mention(mention_ref)

    @staticmethod
    def _best_cluster_near_offset(
        clusters: list[EntityCluster],
        offset: int,
    ) -> EntityCluster | None:
        return ExtractionContext.best_cluster_near_offset(clusters, offset)

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
        return ExtractionContext.build(document).cluster_by_id(
            ClusterID(cluster_id) if cluster_id is not None else None
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
