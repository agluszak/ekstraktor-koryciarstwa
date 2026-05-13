from __future__ import annotations

from dataclasses import dataclass, replace

from pipeline.domain_lexicons import KINSHIP_BY_LEMMA
from pipeline.domain_types import (
    EntityID,
    EntityResolutionStatus,
    EntityType,
    FactID,
    FactType,
    KinshipDetail,
    RelationshipType,
    TimeScope,
)
from pipeline.extraction_context import ALL_ENTITY_TYPES, ExtractionContext
from pipeline.lemma_signals import word_by_index
from pipeline.models import (
    ArticleDocument,
    ClusterMentionView,
    EntityCluster,
    EntityResolutionMetadata,
    EvidenceSpan,
    Fact,
    ParsedWord,
    SentenceFragment,
)
from pipeline.utils import stable_id


@dataclass(frozen=True, slots=True)
class KinshipTieEvidence:
    subject: ClusterMentionView
    target: ClusterMentionView
    kinship_detail: KinshipDetail
    confidence: float
    extraction_signal: str
    evidence_scope: str
    sentence: SentenceFragment
    possible_entity_matches: tuple[EntityID, ...] = ()
    entity_resolution: EntityResolutionMetadata | None = None


class KinshipTieBuilder:
    def build(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
    ) -> list[Fact]:
        evidence_items: list[KinshipTieEvidence] = []
        for sentence in document.sentences:
            sentence_views = context.mention_views_in_sentence(
                sentence.sentence_index, ALL_ENTITY_TYPES
            )
            evidence_items.extend(
                self._direct_sentence_ties(
                    document=document,
                    sentence=sentence,
                    sentence_views=sentence_views,
                )
            )
        views_by_entity_id = _build_views_by_entity_id(context, document.clusters)
        evidence_items.extend(self._resolution_backed_direct_ties(document, evidence_items))
        evidence_items.extend(self._resolution_backed_proxy_ties(document, views_by_entity_id))
        return [self._fact(document, evidence) for evidence in evidence_items]

    def _direct_sentence_ties(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        sentence_views: list[ClusterMentionView],
    ) -> list[KinshipTieEvidence]:
        persons = [v for v in sentence_views if v.entity_type == EntityType.PERSON]
        if not persons:
            return []
        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        if not parsed_words:
            return self._text_fallback_ties(sentence, persons)

        ties: list[KinshipTieEvidence] = []
        for word in parsed_words:
            kinship_detail = self._kinship_detail(word)
            if kinship_detail is None:
                continue

            # 1. Resolve subject (the "anchor" person who has the relative)
            subject = self._resolve_subject(word, sentence, parsed_words, persons, document)
            if subject is None:
                continue

            # 2. Resolve target (the relative person mentioned in the context)
            target = self._resolve_target(word, sentence, parsed_words, persons)
            if target is None or subject.cluster_id == target.cluster_id:
                continue

            ties.append(
                KinshipTieEvidence(
                    subject=subject,
                    target=target,
                    kinship_detail=kinship_detail,
                    confidence=0.88,
                    extraction_signal="kinship_dependency",
                    evidence_scope="same_sentence",
                    sentence=sentence,
                )
            )
        return ties

    def _resolve_subject(
        self,
        kinship_word: ParsedWord,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        sentence_persons: list[ClusterMentionView],
        document: ArticleDocument,
    ) -> ClusterMentionView | None:
        """Find the person who 'owns' the kinship relation (e.g. the 'his' in 'his wife')."""
        # A. Look for nominal modifiers or possessives (e.g. "żona Jana", "jego żona")
        subject_indices = {
            w.index
            for w in parsed_words
            if w.head == kinship_word.index and w.deprel in {"nmod", "det:poss", "nmod:poss"}
        }

        # Check for coreferent pronouns or direct mentions
        for idx in subject_indices:
            word = word_by_index(parsed_words, idx)
            if not word:
                continue

            # Try to find a PERSON cluster mention at this word's offset
            abs_start = sentence.start_char + word.start
            abs_end = sentence.start_char + word.end

            for mention in document.mentions:
                if (
                    mention.sentence_index == sentence.sentence_index
                    and mention.start_char <= abs_start
                    and mention.end_char >= abs_end
                    and mention.entity_id is not None
                ):
                    for view in sentence_persons:
                        if view.entity_id == mention.entity_id:
                            # Prefer non-proxy if available
                            if not view.is_proxy_person:
                                return view
                            # If it is a proxy, try to find the anchor
                            anchor_view = self._resolve_proxy_to_named(view, sentence_persons)
                            if anchor_view:
                                return anchor_view
                            return view

        # B. Fallback: apposition (e.g. "Jan Kowalski, mąż...")
        if kinship_word.deprel == "appos":
            head_idx = kinship_word.head
            for view in sentence_persons:
                if self._view_overlaps_word_index(view, sentence, parsed_words, head_idx):
                    if not view.is_proxy_person:
                        return view
                    anchor_view = self._resolve_proxy_to_named(view, sentence_persons)
                    if anchor_view:
                        return anchor_view
                    return view

        # C. Fallback: strict character distance (generous margin)
        kinship_start = sentence.start_char + kinship_word.start
        preceding = [
            person
            for person in sentence_persons
            if person.end_char <= kinship_start and kinship_start - person.end_char <= 36
        ]
        if preceding:
            best = max(preceding, key=lambda person: person.end_char)
            if best.is_proxy_person:
                anchor = self._resolve_proxy_to_named(best, sentence_persons)
                if anchor:
                    return anchor
            return best

        return None

    def _resolve_proxy_to_named(
        self,
        proxy_view: ClusterMentionView,
        sentence_persons: list[ClusterMentionView],
    ) -> ClusterMentionView | None:
        """Resolve a proxy person to a named person in the same sentence if they are linked."""
        if not proxy_view.is_proxy_person:
            return None

        # Check for proximity and apposition-like structure
        # (Named Person, Proxy) e.g. "Rafał Dobosz, kuzyn..."
        for view in sentence_persons:
            if view.is_proxy_person or view.cluster_id == proxy_view.cluster_id:
                continue

            # If they are very close and separated by a comma or similar
            if (
                abs(view.end_char - proxy_view.start_char) <= 4
                or abs(proxy_view.end_char - view.start_char) <= 4
            ):
                return view
        return None

    def _resolve_target(
        self,
        kinship_word: ParsedWord,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        sentence_persons: list[ClusterMentionView],
    ) -> ClusterMentionView | None:
        """Find the person who IS the relative (e.g. the 'Anna' in 'his wife Anna')."""
        # A. Apposition to the kinship word (e.g. "żona Anna")
        target_indices = {
            w.index
            for w in parsed_words
            if w.head == kinship_word.index and w.deprel in {"appos", "flat"}
        }
        for idx in target_indices:
            for view in sentence_persons:
                if self._view_overlaps_word_index(view, sentence, parsed_words, idx):
                    return view

        # B. Descendant search (e.g. "żona ... Anny")
        descendants = self._descendant_indices(parsed_words, kinship_word.index)
        kinship_end = sentence.start_char + kinship_word.end
        after_candidates = [
            person
            for person in sentence_persons
            if person.start_char >= kinship_end and person.start_char - kinship_end <= 120
        ]
        dependency_matches = [
            person
            for person in after_candidates
            if self._view_overlaps_word_indices(person, sentence, parsed_words, descendants)
        ]
        if dependency_matches:
            return min(dependency_matches, key=lambda person: person.start_char)

        # C. Fallback: nearest person after kinship word
        if after_candidates:
            return min(after_candidates, key=lambda person: person.start_char)

        return None

    @staticmethod
    def _view_overlaps_word_index(
        view: ClusterMentionView,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        word_index: int,
    ) -> bool:
        word = next((w for w in parsed_words if w.index == word_index), None)
        if not word:
            return False
        word_start = sentence.start_char + word.start
        word_end = sentence.start_char + word.end
        return (
            view.start_char <= word_start < view.end_char
            or word_start <= view.start_char < word_end
        )

    @staticmethod
    def _descendant_indices(parsed_words: list[ParsedWord], root_index: int) -> set[int]:
        descendants: set[int] = set()
        frontier = {root_index}
        while frontier:
            parent = frontier.pop()
            children = {word.index for word in parsed_words if word.head == parent}
            children -= descendants
            descendants.update(children)
            frontier.update(children)
        return descendants

    @staticmethod
    def _view_overlaps_word_indices(
        view: ClusterMentionView,
        sentence: SentenceFragment,
        parsed_words: list[ParsedWord],
        word_indices: set[int],
    ) -> bool:
        return any(
            word.index in word_indices
            and (
                view.start_char <= sentence.start_char + word.start < view.end_char
                or sentence.start_char + word.start
                <= view.start_char
                < sentence.start_char + word.end
            )
            for word in parsed_words
        )

    def _text_fallback_ties(
        self,
        sentence: SentenceFragment,
        persons: list[ClusterMentionView],
    ) -> list[KinshipTieEvidence]:
        lowered = sentence.text.casefold()
        ties: list[KinshipTieEvidence] = []
        for surface, kinship_detail in KINSHIP_BY_LEMMA.items():
            local_anchor = lowered.find(surface)
            if local_anchor < 0:
                continue
            anchor = sentence.start_char + local_anchor
            subject = max(
                (person for person in persons if person.end_char <= anchor),
                key=lambda person: person.end_char,
                default=None,
            )
            target = min(
                (person for person in persons if person.start_char >= anchor + len(surface)),
                key=lambda person: person.start_char,
                default=None,
            )
            if subject is None or target is None or subject.entity_id == target.entity_id:
                continue
            between_subject = lowered[
                max(0, subject.end_char - sentence.start_char) : max(
                    0, anchor - sentence.start_char
                )
            ]
            if len(between_subject) > 12 or "," not in between_subject:
                continue
            ties.append(
                KinshipTieEvidence(
                    subject=subject,
                    target=target,
                    kinship_detail=kinship_detail,
                    confidence=0.76,
                    extraction_signal="kinship_apposition_text",
                    evidence_scope="same_sentence",
                    sentence=sentence,
                )
            )
        return ties

    def _resolution_backed_proxy_ties(
        self,
        document: ArticleDocument,
        views_by_entity_id: dict[EntityID, ClusterMentionView],
    ) -> list[KinshipTieEvidence]:
        facts_by_proxy = {
            fact.subject_entity_id: fact
            for fact in document.facts
            if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
            and fact.relationship_type == RelationshipType.FAMILY
            and fact.kinship_detail is not None
        }
        ties: list[KinshipTieEvidence] = []
        for hypothesis in document.entity_resolution_hypotheses:
            if hypothesis.status not in {
                EntityResolutionStatus.PROBABLE,
                EntityResolutionStatus.CONFIRMED,
            }:
                continue
            left_fact = facts_by_proxy.get(hypothesis.left_entity_id)
            right_fact = facts_by_proxy.get(hypothesis.right_entity_id)
            proxy_fact = left_fact or right_fact
            if proxy_fact is None or proxy_fact.object_entity_id is None:
                continue
            kinship_detail = proxy_fact.kinship_detail
            if kinship_detail is None:
                continue
            proxy_entity_id = (
                hypothesis.left_entity_id if left_fact is not None else hypothesis.right_entity_id
            )
            matched_entity_id = (
                hypothesis.right_entity_id
                if proxy_entity_id == hypothesis.left_entity_id
                else hypothesis.left_entity_id
            )
            subject_id = (
                matched_entity_id
                if hypothesis.status == EntityResolutionStatus.CONFIRMED
                else proxy_entity_id
            )
            subject = views_by_entity_id.get(subject_id)
            target = views_by_entity_id.get(proxy_fact.object_entity_id)
            if subject is None or target is None or subject.entity_id == target.entity_id:
                continue
            sentence = self._sentence_for_evidence(document, proxy_fact.evidence)
            if sentence is None or not self._same_or_adjacent_paragraph_sentence(
                proxy_fact.evidence,
                sentence,
            ):
                continue
            entity_resolution = None
            possible_matches: tuple[EntityID, ...] = ()
            confidence = min(0.78, hypothesis.confidence)
            if hypothesis.status == EntityResolutionStatus.CONFIRMED:
                entity_resolution = EntityResolutionMetadata(
                    matched_entity_id=matched_entity_id,
                    confidence=hypothesis.confidence,
                    status=hypothesis.status,
                    hypothesis_id=hypothesis.hypothesis_id,
                )
            else:
                possible_matches = (matched_entity_id,)
                confidence = min(confidence, 0.68)
            ties.append(
                KinshipTieEvidence(
                    subject=subject,
                    target=target,
                    kinship_detail=kinship_detail,
                    confidence=confidence,
                    extraction_signal="identity_hypothesis",
                    evidence_scope="same_paragraph_adjacent_sentence",
                    sentence=sentence,
                    possible_entity_matches=possible_matches,
                    entity_resolution=entity_resolution,
                )
            )
        return ties

    def _resolution_backed_direct_ties(
        self,
        document: ArticleDocument,
        evidence_items: list[KinshipTieEvidence],
    ) -> list[KinshipTieEvidence]:
        augmented: list[KinshipTieEvidence] = []
        for evidence in evidence_items:
            if evidence.possible_entity_matches or evidence.entity_resolution is not None:
                continue
            subject_id = evidence.subject.entity_id
            target_id = evidence.target.entity_id
            if subject_id is None or target_id is None:
                continue
            exclude_ids = {subject_id, target_id}
            target_matches = self._hypothesis_matches_for_entity(
                document,
                target_id,
                exclude_ids=exclude_ids,
            )
            if target_matches:
                augmented.append(
                    replace(
                        evidence,
                        confidence=min(evidence.confidence, 0.68),
                        extraction_signal="entity_resolution_hypothesis",
                        evidence_scope="same_paragraph_adjacent_sentence",
                        possible_entity_matches=target_matches,
                    )
                )
                continue
            subject_matches = self._hypothesis_matches_for_entity(
                document,
                subject_id,
                exclude_ids=exclude_ids,
            )
            if subject_matches:
                augmented.append(
                    replace(
                        evidence,
                        confidence=min(evidence.confidence, 0.68),
                        extraction_signal="entity_resolution_hypothesis",
                        evidence_scope="same_paragraph_adjacent_sentence",
                        possible_entity_matches=subject_matches,
                    )
                )
        return augmented

    @staticmethod
    def _hypothesis_matches_for_entity(
        document: ArticleDocument,
        entity_id: EntityID,
        *,
        exclude_ids: set[EntityID],
    ) -> tuple[EntityID, ...]:
        ranked_matches: list[tuple[float, EntityID]] = []
        for hypothesis in document.entity_resolution_hypotheses:
            if hypothesis.status not in {
                EntityResolutionStatus.POSSIBLE,
                EntityResolutionStatus.PROBABLE,
                EntityResolutionStatus.CONFIRMED,
            }:
                continue
            if entity_id == hypothesis.left_entity_id:
                matched_entity_id = hypothesis.right_entity_id
            elif entity_id == hypothesis.right_entity_id:
                matched_entity_id = hypothesis.left_entity_id
            else:
                continue
            if matched_entity_id in exclude_ids:
                continue
            ranked_matches.append((hypothesis.confidence, matched_entity_id))
        ordered_matches: list[EntityID] = []
        for _, matched_entity_id in sorted(ranked_matches, reverse=True):
            if matched_entity_id not in ordered_matches:
                ordered_matches.append(matched_entity_id)
        return tuple(ordered_matches)

    @staticmethod
    def _sentence_for_evidence(
        document: ArticleDocument,
        evidence: EvidenceSpan,
    ) -> SentenceFragment | None:
        if evidence.sentence_index is None:
            return None
        return next(
            (
                sentence
                for sentence in document.sentences
                if sentence.sentence_index == evidence.sentence_index
            ),
            None,
        )

    @staticmethod
    def _same_or_adjacent_paragraph_sentence(
        evidence: EvidenceSpan,
        sentence: SentenceFragment,
    ) -> bool:
        if (
            evidence.paragraph_index is not None
            and evidence.paragraph_index != sentence.paragraph_index
        ):
            return False
        if evidence.sentence_index is None:
            return False
        return abs(evidence.sentence_index - sentence.sentence_index) <= 1

    @staticmethod
    def _kinship_detail(word: ParsedWord) -> KinshipDetail | None:
        return KINSHIP_BY_LEMMA.get(word.lemma.casefold()) or KINSHIP_BY_LEMMA.get(
            word.text.casefold()
        )

    @staticmethod
    def _fact(document: ArticleDocument, evidence: KinshipTieEvidence) -> Fact:
        fact_id = FactID(
            stable_id(
                "fact",
                document.document_id,
                FactType.PERSONAL_OR_POLITICAL_TIE,
                evidence.subject.entity_id or evidence.subject.cluster_id,
                evidence.target.entity_id or evidence.target.cluster_id,
                evidence.kinship_detail.value,
                str(evidence.sentence.sentence_index),
                evidence.extraction_signal,
            )
        )
        return Fact(
            fact_id=fact_id,
            fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
            subject_entity_id=EntityID(evidence.subject.entity_id or evidence.subject.cluster_id),
            object_entity_id=EntityID(evidence.target.entity_id or evidence.target.cluster_id),
            value_text=evidence.kinship_detail.value,
            value_normalized=evidence.kinship_detail.value,
            time_scope=TimeScope.CURRENT,
            event_date=document.publication_date,
            confidence=evidence.confidence,
            evidence=EvidenceSpan(
                text=evidence.sentence.text,
                sentence_index=evidence.sentence.sentence_index,
                paragraph_index=evidence.sentence.paragraph_index,
                start_char=evidence.sentence.start_char,
                end_char=evidence.sentence.end_char,
            ),
            relationship_type=RelationshipType.FAMILY,
            kinship_detail=evidence.kinship_detail,
            entity_resolution=evidence.entity_resolution,
            possible_entity_matches=list(evidence.possible_entity_matches),
            source_extractor="kinship_tie_builder",
            extraction_signal=evidence.extraction_signal,
            evidence_scope=evidence.evidence_scope,
        )


def _cluster_to_view(context: ExtractionContext, cluster: EntityCluster) -> ClusterMentionView:
    """Build a ClusterMentionView for identity-resolution lookups where positional info is
    not required (only canonical_name, entity_id, and entity_type are accessed downstream).
    Uses the first real mention when available, or a zero-position sentinel when
    ``cluster.mentions`` is empty. Callers must not rely on start/end offsets from the
    sentinel view."""
    mention = cluster.mentions[0] if cluster.mentions else None
    return context.mention_view(cluster, mention)


def _build_views_by_entity_id(
    context: ExtractionContext,
    clusters: list[EntityCluster],
) -> dict[EntityID, ClusterMentionView]:
    result: dict[EntityID, ClusterMentionView] = {}
    for cluster in clusters:
        base_view = _cluster_to_view(context, cluster)
        for entity_id in context.entity_ids_for_cluster(cluster):
            mention = next(
                (item for item in cluster.mentions if item.entity_id == entity_id),
                base_view.mention,
            )
            view = ClusterMentionView(
                cluster=cluster,
                mention=mention,
                entity=context.entity_by_id(entity_id),
            )
            if entity_id not in result:
                result[entity_id] = view
    return result
