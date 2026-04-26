from __future__ import annotations

import uuid

from pipeline.base import FrameExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import (
    INVALID_PUBLIC_EMPLOYMENT_ROLE_HEADS,
    KINSHIP_LEMMAS,
    PUBLIC_EMPLOYER_TERMS,
    PUBLIC_OFFICE_ROLE_KINDS,
)
from pipeline.domain_types import EntityType, FrameID, OrganizationKind, PublicEmploymentSignal
from pipeline.entity_classifiers import is_party_like_name, is_public_employer_name
from pipeline.frame_grounding import FrameSlotGrounder
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    EntityCluster,
    EvidenceSpan,
    ParsedWord,
    PublicEmploymentFrame,
)
from pipeline.semantic_signals import EMPLOYMENT_CONTEXT_MARKERS
from pipeline.utils import normalize_entity_name


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
        self.slot_grounder = FrameSlotGrounder(config)

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
            grounded_role = self.slot_grounder.ground_public_employment_role(
                document,
                clause,
                employee=employee,
                role_cluster=role_cluster,
            )
            role_label = grounded_role.label if grounded_role is not None else None
            role_cluster_id = grounded_role.role_cluster_id if grounded_role is not None else None
            if (
                signal == PublicEmploymentSignal.ENTRY
                and role_label is None
                and not self._has_explicit_employment_context(clause.text)
            ):
                continue
            document.public_employment_frames.append(
                PublicEmploymentFrame(
                    frame_id=FrameID(f"public-employment-frame-{uuid.uuid4().hex[:8]}"),
                    signal=signal,
                    employee_cluster_id=employee.cluster_id,
                    employer_cluster_id=employer.cluster_id,
                    role_label=role_label,
                    role_cluster_id=role_cluster_id,
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
            if self._is_public_employer(cluster) and not self._is_party_cluster(cluster)
        ]
        if current:
            return min(current, key=lambda cluster: self._cluster_clause_distance(cluster, clause))
        adjacent = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
            and self._is_public_employer(cluster)
            and not self._is_party_cluster(cluster)
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
            and not self._is_party_cluster(cluster)
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
        return is_public_employer_name(normalized)

    def _is_party_cluster(self, cluster: EntityCluster) -> bool:
        return is_party_like_name(cluster.normalized_name, self.config)

    @classmethod
    def _has_explicit_employment_context(cls, text: str) -> bool:
        lowered = text.casefold()
        return any(marker in lowered for marker in EMPLOYMENT_CONTEXT_MARKERS)

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
