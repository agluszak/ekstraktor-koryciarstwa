from __future__ import annotations

import uuid

from pipeline.config import PipelineConfig
from pipeline.domain_lexicons import ATTRIBUTION_SPEECH_LEMMAS, KINSHIP_LEMMAS
from pipeline.domain_types import ClusterID, EntityType, FrameID, GovernanceSignal
from pipeline.domains.governance import GovernanceTargetResolver
from pipeline.extraction_context import ExtractionContext
from pipeline.lemma_signals import has_lemma, has_lemma_pair, lemma_set
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    EntityCluster,
    EvidenceSpan,
    GovernanceFrame,
    ParsedWord,
)
from pipeline.nlp_rules import (
    APPOINTING_AUTHORITY_LEMMAS,
    APPOINTING_AUTHORITY_TITLE_LEMMAS,
    APPOINTMENT_NOUN_LEMMAS,
    APPOINTMENT_TRIGGER_LEMMAS,
    APPOINTMENT_TRIGGER_TEXTS,
    DISMISSAL_NOUN_LEMMAS,
    DISMISSAL_TRIGGER_LEMMAS,
    DISMISSAL_TRIGGER_TEXTS,
)
from pipeline.role_matching import (
    has_copular_role_appointment,
    has_governance_verb_with_role,
)
from pipeline.role_text import find_role_text

WEAK_APPOINTMENT_TRIGGER_LEMMAS = frozenset(
    {"objąć", "zająć", "pracować", "zatrudnić", "zatrudnienie", "trafić"}
)
PARLIAMENTARY_REMUNERATION_MARKERS = frozenset(
    {
        "uposaż",
        "dieta",
        "pieniądze publiczne",
        "kasy sejmu",
        "z sejmu",
        "mandatu posła",
        "pobrał",
        "pobiera",
        "posiedzeniu sejmu",
        "interpelacji",
    }
)
PARLIAMENTARY_CONTEXT_MARKERS = frozenset(
    {
        "do sejmu",
        "w sejmie",
        "w obecnej kadencji sejmu",
        "posiedzeniu sejmu",
        "prezydium sejmu",
    }
)


class PolishGovernanceFrameExtractor:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.target_resolver = GovernanceTargetResolver(config)

    def name(self) -> str:
        return "polish_governance_frame_extractor"

    def run(self, document: ArticleDocument, context: ExtractionContext) -> ArticleDocument:
        document.governance_frames = []
        for clause in document.clause_units:
            parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
            signal = self._detect_signal(clause, parsed_words)
            if signal is None:
                continue
            frame = self._extract_discourse_frame(clause, document, context, signal)
            if frame is not None:
                document.governance_frames.append(frame)
        return document

    def _detect_signal(
        self,
        clause: ClauseUnit,
        parsed_words: list[ParsedWord] | None = None,
    ) -> GovernanceSignal | None:
        lemma = clause.trigger_head_lemma.lower()
        lowered_text = clause.text.lower()
        if self._is_parliamentary_non_governance_context(lowered_text):
            return None
        if (
            self._has_trigger_head_appointment_signal(lemma, parsed_words or [])
            or self._has_appointment_lemma_signal(parsed_words or [])
            or any(trigger in lowered_text for trigger in APPOINTMENT_TRIGGER_TEXTS)
            or has_copular_role_appointment(parsed_words or [])
            or has_governance_verb_with_role(parsed_words or [], APPOINTMENT_TRIGGER_LEMMAS)
        ):
            return GovernanceSignal.APPOINTMENT
        if (
            lemma in DISMISSAL_TRIGGER_LEMMAS
            or self._has_dismissal_lemma_signal(parsed_words or [])
            or any(trigger in lowered_text for trigger in DISMISSAL_TRIGGER_TEXTS)
            or has_governance_verb_with_role(parsed_words or [], DISMISSAL_TRIGGER_LEMMAS)
        ):
            return GovernanceSignal.DISMISSAL
        return None

    @staticmethod
    def _is_parliamentary_non_governance_context(lowered_text: str) -> bool:
        if not any(marker in lowered_text for marker in PARLIAMENTARY_CONTEXT_MARKERS):
            return False
        return any(marker in lowered_text for marker in PARLIAMENTARY_REMUNERATION_MARKERS) or (
            "do sejmu" in lowered_text
            and "spół" not in lowered_text
            and "zarząd" not in lowered_text
        )

    @staticmethod
    def _has_trigger_head_appointment_signal(
        trigger_head_lemma: str,
        parsed_words: list[ParsedWord],
    ) -> bool:
        if trigger_head_lemma not in APPOINTMENT_TRIGGER_LEMMAS:
            return False
        if trigger_head_lemma not in WEAK_APPOINTMENT_TRIGGER_LEMMAS:
            # Strong trigger: if the verb is imperfective (habitual/ongoing) rather than
            # perfective (completed event), require additional noun support — imperfective
            # signals like "powoływać" describe repeated or background processes and produce
            # more noise than perfective "powołać" (single appointment event).
            if PolishGovernanceFrameExtractor._trigger_word_is_imperfective(
                trigger_head_lemma, parsed_words
            ):
                return PolishGovernanceFrameExtractor._has_appointment_lemma_signal(parsed_words)
            return True
        return PolishGovernanceFrameExtractor._has_appointment_lemma_signal(parsed_words)

    @staticmethod
    def _trigger_word_is_imperfective(trigger_lemma: str, parsed_words: list[ParsedWord]) -> bool:
        """Return True if the trigger verb has Aspect=Imp in Stanza morphological features."""
        for word in parsed_words:
            if (word.lemma or word.text).casefold() == trigger_lemma:
                if word.feats.get("Aspect") == "Imp":
                    return True
        return False

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
        signal: GovernanceSignal,
    ) -> GovernanceFrame | None:
        person_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        if not person_clusters:
            person_clusters = ExtractionContext.sort_clusters_by_clause_distance(
                context.previous_clusters(
                    clause,
                    {EntityType.PERSON},
                    max_distance=2,
                ),
                clause,
            )
            if not person_clusters and signal == GovernanceSignal.DISMISSAL:
                person_clusters = ExtractionContext.sort_clusters_by_clause_distance(
                    context.following_clusters(
                        clause,
                        {EntityType.PERSON},
                        max_distance=1,
                    ),
                    clause,
                )
        elif signal == GovernanceSignal.APPOINTMENT and self._has_object_pronoun(document, clause):
            person_clusters = ExtractionContext.merge_clusters(
                person_clusters,
                ExtractionContext.sort_clusters_by_clause_distance(
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

        role_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        role_cluster = (
            role_clusters[0] if role_clusters else self._find_role_from_text(document, clause)
        )
        role_text = None if role_cluster is not None else self._find_role_text(document, clause)

        clause_orgs = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )
        discourse_orgs = ExtractionContext.merge_clusters(
            clause_orgs,
            ExtractionContext.merge_clusters(
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
        org_clusters = ExtractionContext.sort_clusters_by_clause_distance(discourse_orgs, clause)
        if not org_clusters:
            return None

        person_cluster_id, appointing_authority_id = self._resolve_people(
            clause,
            document,
            person_clusters,
            signal,
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
            signal=signal,
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
        signal: GovernanceSignal,
        context: ExtractionContext,
    ) -> GovernanceFrame | None:
        person_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.PERSON},
        )
        role_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.POSITION},
        )
        org_clusters = context.clusters_for_mentions(
            clause.cluster_mentions,
            {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
        )
        if not person_clusters:
            person_clusters = context.paragraph_context_clusters(
                clause,
                {EntityType.PERSON},
            )
        elif signal == GovernanceSignal.APPOINTMENT and self._has_object_pronoun(document, clause):
            person_clusters = ExtractionContext.merge_clusters(
                person_clusters,
                context.paragraph_context_clusters(
                    clause,
                    {EntityType.PERSON},
                ),
            )
        if not org_clusters:
            org_clusters = context.paragraph_context_clusters(
                clause,
                {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION},
            )

        if not person_clusters:
            return None

        person_cluster_id, appointing_authority_id = self._resolve_people(
            clause,
            document,
            person_clusters,
            signal,
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
            signal=signal,
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

    def _resolve_people(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        person_clusters: list[EntityCluster],
        signal: GovernanceSignal,
    ) -> tuple[str | None, str | None]:
        appointees: list[ClusterID] = []
        authorities: list[ClusterID] = []
        person_cluster_ids = {cluster.cluster_id for cluster in person_clusters}
        speech_speaker_ids = self._speech_speaker_cluster_ids(clause, document, person_clusters)
        current_sentence_ids = {
            cluster.cluster_id
            for cluster in person_clusters
            if any(mention.sentence_index == clause.sentence_index for mention in cluster.mentions)
        }
        previous_authority_id = (
            self._recover_recent_appointing_authority(
                clause,
                document,
                excluded_cluster_ids=current_sentence_ids | speech_speaker_ids,
            )
            if signal == GovernanceSignal.APPOINTMENT
            else None
        )
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
            if role and (role.startswith("obj") or role == "nsubj:pass"):
                # obj* = direct/indirect object (active appointee);
                # nsubj:pass = passive subject — the recipient of the appointment, not
                # the appointing authority (e.g. "Jan Kowalski został powołany").
                appointees.append(cluster.cluster_id)
            elif role and role.startswith("nsubj"):
                authorities.append(cluster.cluster_id)

        if appointees:
            appointee_id = self._first_non_speaker(appointees, speech_speaker_ids)
            if appointee_id is None:
                appointee_id = appointees[0]
            return appointee_id, authorities[0] if authorities else previous_authority_id
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
                if signal == GovernanceSignal.DISMISSAL
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
        if signal == GovernanceSignal.APPOINTMENT and self._has_object_pronoun(document, clause):
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
            if signal == GovernanceSignal.DISMISSAL
            else person_clusters
        )
        if (
            not candidate_clusters
            and signal == GovernanceSignal.DISMISSAL
            and not self._near_family_subject(document, clause)
        ):
            candidate_clusters = [
                cluster
                for cluster in person_clusters
                if cluster.cluster_id not in speech_speaker_ids
            ]
        if not candidate_clusters:
            return None, None
        return candidate_clusters[0].cluster_id, previous_authority_id

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
        speech_heads = {
            word.index for word in parsed if word.lemma.casefold() in ATTRIBUTION_SPEECH_LEMMAS
        }
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
        return find_role_text(document, clause)

    def _find_cluster_for_mention(
        self,
        mention_ref: ClusterMention,
        context: ExtractionContext,
    ) -> EntityCluster | None:
        return context.cluster_for_mention(mention_ref)

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
            key=lambda cluster: ExtractionContext.cluster_clause_distance(cluster, clause),
        )

    def _previous_sentence_appointing_authority(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        *,
        excluded_cluster_ids: set[ClusterID],
    ) -> ClusterID | None:
        previous_sentence_index = clause.sentence_index - 1
        if previous_sentence_index < 0:
            return None
        previous_sentence = next(
            (
                sentence
                for sentence in document.sentences
                if sentence.sentence_index == previous_sentence_index
                and sentence.paragraph_index == clause.paragraph_index
            ),
            None,
        )
        if previous_sentence is None:
            return None
        parsed_words = document.parsed_sentences.get(previous_sentence_index, [])
        chooser_heads = {
            word.index
            for word in parsed_words
            if word.lemma.casefold() in APPOINTING_AUTHORITY_LEMMAS
        }
        if not chooser_heads:
            return None
        subject_indices = {
            word.index
            for word in parsed_words
            if word.head in chooser_heads and word.deprel.startswith("nsubj")
        }
        if not subject_indices:
            return None
        candidates = [
            cluster
            for cluster in document.clusters
            if cluster.entity_type == EntityType.PERSON
            and cluster.cluster_id not in excluded_cluster_ids
            and self._cluster_has_sentence_word_indices(
                previous_sentence.start_char,
                previous_sentence_index,
                cluster,
                parsed_words,
                subject_indices,
            )
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda cluster: len(cluster.canonical_name)).cluster_id

    def _recover_recent_appointing_authority(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        *,
        excluded_cluster_ids: set[ClusterID],
    ) -> ClusterID | None:
        previous_authority = self._previous_sentence_appointing_authority(
            clause,
            document,
            excluded_cluster_ids=excluded_cluster_ids,
        )
        if previous_authority is not None:
            return previous_authority
        title_lemmas = self._chooser_subject_title_lemmas(clause, document)
        if not title_lemmas and clause.sentence_index > 0:
            title_lemmas = self._chooser_subject_title_lemmas_for_sentence(
                clause.sentence_index - 1,
                document,
            )
        if not title_lemmas:
            return None
        return self._recent_titled_appointing_authority(
            clause,
            document,
            excluded_cluster_ids=excluded_cluster_ids,
            title_lemmas=title_lemmas,
        )

    @staticmethod
    def _chooser_subject_title_lemmas(
        clause: ClauseUnit,
        document: ArticleDocument,
    ) -> set[str]:
        return PolishGovernanceFrameExtractor._chooser_subject_title_lemmas_for_sentence(
            clause.sentence_index,
            document,
        )

    @staticmethod
    def _chooser_subject_title_lemmas_for_sentence(
        sentence_index: int,
        document: ArticleDocument,
    ) -> set[str]:
        parsed_words = document.parsed_sentences.get(sentence_index, [])
        chooser_heads = {
            word.index
            for word in parsed_words
            if word.lemma.casefold() in APPOINTING_AUTHORITY_LEMMAS
        }
        if not chooser_heads:
            return set()
        governing_heads = chooser_heads | {
            word.head
            for word in parsed_words
            if word.index in chooser_heads and word.deprel == "conj"
        }
        return {
            word.lemma.casefold()
            for word in parsed_words
            if word.deprel.startswith("nsubj")
            and word.head in governing_heads
            and word.lemma.casefold() in APPOINTING_AUTHORITY_TITLE_LEMMAS
        }

    def _recent_titled_appointing_authority(
        self,
        clause: ClauseUnit,
        document: ArticleDocument,
        *,
        excluded_cluster_ids: set[ClusterID],
        title_lemmas: set[str],
    ) -> ClusterID | None:
        candidate_matches: list[tuple[int, int, int, ClusterID]] = []
        min_sentence_index = max(0, clause.sentence_index - 4)
        for sentence in document.sentences:
            if (
                sentence.sentence_index < min_sentence_index
                or sentence.sentence_index >= clause.sentence_index
            ):
                continue
            if clause.paragraph_index - sentence.paragraph_index > 1:
                continue
            parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
            title_words = [word for word in parsed_words if word.lemma.casefold() in title_lemmas]
            if not title_words:
                continue
            for title_word in title_words:
                title_start = sentence.start_char + title_word.start
                for cluster in document.clusters:
                    if cluster.entity_type != EntityType.PERSON:
                        continue
                    if cluster.cluster_id in excluded_cluster_ids:
                        continue
                    sentence_mentions = [
                        mention
                        for mention in cluster.mentions
                        if mention.sentence_index == sentence.sentence_index
                        and title_start - 4 <= mention.start_char <= title_start + 48
                    ]
                    if not sentence_mentions:
                        continue
                    mention = min(
                        sentence_mentions,
                        key=lambda item: abs(item.start_char - title_start),
                    )
                    candidate_matches.append(
                        (
                            clause.sentence_index - sentence.sentence_index,
                            clause.paragraph_index - sentence.paragraph_index,
                            abs(mention.start_char - title_start),
                            cluster.cluster_id,
                        )
                    )
        if not candidate_matches:
            return None
        return min(candidate_matches)[3]

    @staticmethod
    def _has_object_pronoun(document: ArticleDocument, clause: ClauseUnit) -> bool:
        object_pronouns = {"go", "ją", "je", "ich", "jego", "jej"}
        return any(
            word.text.lower() in object_pronouns
            and (word.deprel.startswith("obj") or word.deprel in {"iobj", "obl"})
            for word in document.parsed_sentences.get(clause.sentence_index, [])
        )

    @staticmethod
    def _cluster_has_sentence_word_indices(
        sentence_start_char: int,
        sentence_index: int,
        cluster: EntityCluster,
        parsed: list[ParsedWord],
        indices: set[int],
    ) -> bool:
        if not indices:
            return False
        for mention in cluster.mentions:
            if mention.sentence_index != sentence_index:
                continue
            for word in parsed:
                abs_start = sentence_start_char + word.start
                if word.index in indices and mention.start_char <= abs_start < mention.end_char:
                    return True
        return False
