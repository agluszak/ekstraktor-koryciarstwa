from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    EntityID,
    EntityType,
    OrganizationKind,
    RoleKind,
    RoleModifier,
)
from pipeline.models import (
    ArticleDocument,
    CandidateEdge,
    CandidateGraph,
    CoreferenceResult,
    Entity,
    EntityCandidate,
    ParsedWord,
)
from pipeline.nlp_rules import (
    KINSHIP_LEMMAS,
    ROLE_PATTERNS,
    TIE_WORDS,
)
from pipeline.relation_signals import supports_party_link, supports_person_role_link
from pipeline.role_matching import RoleMatch, match_role_mentions
from pipeline.utils import (
    extract_role_from_text,
    normalize_entity_name,
    stable_id,
    unique_preserve_order,
)

from .org_typing import OrganizationMentionClassifier


@dataclass(slots=True)
class SentenceEntityAnchor:
    entity: Entity
    start: int
    end: int


class CandidateGraphBuilder:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.organization_classifier = OrganizationMentionClassifier(config)

    def build(
        self,
        *,
        document: ArticleDocument,
        coreference: CoreferenceResult,
        parsed_sentences: dict[int, list[ParsedWord]],
    ) -> CandidateGraph:
        graph = CandidateGraph()
        mention_candidates: dict[tuple[str, int, int], EntityCandidate] = {}

        for sentence in document.sentences:
            sentence_mentions = self._mentions_for_sentence(
                document, coreference, sentence.sentence_index
            )
            parsed_words = parsed_sentences.get(sentence.sentence_index, [])
            for anchor in sentence_mentions:
                candidate = self._candidate_for_anchor(
                    document,
                    sentence,
                    anchor,
                    parsed_words,
                )
                if candidate is None:
                    continue
                mention_candidates[(anchor.entity.entity_id, anchor.start, anchor.end)] = candidate
                graph.candidates.append(candidate)

            graph.candidates.extend(
                self._derived_person_candidates(
                    document=document,
                    sentence=sentence,
                    existing_candidates=graph.candidates,
                )
            )
            graph.candidates.extend(
                self._derived_party_candidates(
                    document=document,
                    sentence=sentence,
                    existing_candidates=graph.candidates,
                )
            )
            graph.candidates.extend(self._position_candidates(document, sentence, parsed_words))

        graph.candidates = self._deduplicate_candidates(graph.candidates)
        graph.edges = self._build_edges(document, graph.candidates, parsed_sentences)
        return graph

    def _candidate_for_anchor(
        self,
        document: ArticleDocument,
        sentence,
        anchor: SentenceEntityAnchor,
        parsed_words: list[ParsedWord],
    ) -> EntityCandidate | None:
        entity = anchor.entity
        if entity.entity_type == EntityType.PERSON and self._is_weak_person_name(
            entity.canonical_name
        ):
            return None
        candidate_type = CandidateType(entity.entity_type)
        entity_id = entity.entity_id
        canonical_name = entity.canonical_name
        normalized_name = entity.normalized_name

        organization_kind = entity.organization_kind

        if entity.entity_type == EntityType.ORGANIZATION:
            typing_result = self.organization_classifier.classify(
                surface_text=entity.canonical_name,
                normalized_text=entity.normalized_name,
                parsed_words=parsed_words,
                start_char=anchor.start,
                end_char=anchor.end,
            )
            if typing_result.candidate_type == CandidateType.POLITICAL_PARTY:
                party = self._get_or_create_entity(
                    document=document,
                    entity_type=EntityType.POLITICAL_PARTY,
                    canonical_name=typing_result.canonical_name or entity.normalized_name,
                    alias=entity.canonical_name,
                )
                candidate_type = CandidateType.POLITICAL_PARTY
                entity_id = party.entity_id
                canonical_name = party.canonical_name
                normalized_name = party.normalized_name
            elif typing_result.candidate_type == CandidateType.PUBLIC_INSTITUTION:
                institution = self._get_or_create_entity(
                    document=document,
                    entity_type=EntityType.PUBLIC_INSTITUTION,
                    canonical_name=typing_result.canonical_name or entity.normalized_name,
                    alias=entity.canonical_name,
                )
                candidate_type = CandidateType.PUBLIC_INSTITUTION
                entity_id = institution.entity_id
                canonical_name = institution.canonical_name
                normalized_name = institution.normalized_name
                organization_kind = OrganizationKind.PUBLIC_INSTITUTION
                institution.organization_kind = OrganizationKind.PUBLIC_INSTITUTION
            else:
                organization_kind = typing_result.organization_kind
                entity.organization_kind = organization_kind
                if organization_kind == OrganizationKind.PUBLIC_INSTITUTION:
                    candidate_type = CandidateType.PUBLIC_INSTITUTION

        return EntityCandidate(
            candidate_id=CandidateID(
                stable_id(
                    "candidate",
                    document.document_id,
                    entity_id or canonical_name,
                    str(sentence.sentence_index),
                    str(anchor.start),
                    str(anchor.end),
                )
            ),
            entity_id=entity_id,
            candidate_type=candidate_type,
            canonical_name=canonical_name,
            normalized_name=normalized_name,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=anchor.start,
            end_char=anchor.end,
            source="mention",
            organization_kind=organization_kind,
            is_proxy_person=entity.is_proxy_person,
            kinship_detail=entity.kinship_detail,
        )

    def _derived_person_candidates(
        self,
        *,
        document: ArticleDocument,
        sentence,
        existing_candidates: list[EntityCandidate],
    ) -> list[EntityCandidate]:
        occupied_candidates = [
            candidate
            for candidate in existing_candidates
            if candidate.sentence_index == sentence.sentence_index
        ]
        candidates: list[EntityCandidate] = []
        pattern = re.compile(
            r"\b(?:[A-ZŁŚŻŹĆŃÓ]\.|[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+)\s+"
            r"[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż-]+\b"
        )
        for match in pattern.finditer(sentence.text):
            if any(
                self._blocks_derived_person_candidate(
                    candidate,
                    candidate_start=match.start(),
                    candidate_end=match.end(),
                )
                for candidate in occupied_candidates
            ):
                continue
            surface = match.group(0)
            if self._looks_like_role_title(surface):
                continue
            person = self._get_or_create_person_entity(document=document, surface=surface)
            candidates.append(
                EntityCandidate(
                    candidate_id=CandidateID(
                        stable_id(
                            "candidate",
                            document.document_id,
                            person.entity_id,
                            str(sentence.sentence_index),
                            str(match.start()),
                            str(match.end()),
                        )
                    ),
                    entity_id=person.entity_id,
                    candidate_type=CandidateType.PERSON,
                    canonical_name=person.canonical_name,
                    normalized_name=person.normalized_name,
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    start_char=match.start(),
                    end_char=match.end(),
                    source="derived_person",
                    is_proxy_person=False,
                )
            )
        return candidates

    @staticmethod
    def _looks_like_role_title(surface: str) -> bool:
        normalized = normalize_entity_name(surface).casefold()
        if normalized in {role.value.casefold() for role in RoleKind}:
            return True
        first_token = normalized.split()[0] if normalized.split() else ""
        return first_token in {
            "sekretarz",
            "starosta",
            "starost",
            "wójt",
            "wojt",
            "marszałek",
            "marszałkiem",
            "wojewoda",
        }

    def _position_candidates(
        self,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
    ) -> list[EntityCandidate]:
        candidates: list[EntityCandidate] = []
        if parsed_words:
            for match in match_role_mentions(parsed_words):
                candidates.append(
                    self._position_candidate_from_role_match(document, sentence, match)
                )
            return candidates

        text = sentence.text
        occupied_spans: list[tuple[int, int]] = []
        for role, modifier, pattern in sorted(
            ROLE_PATTERNS,
            key=lambda item: len(item[0].value) + (len(item[1].value) if item[1] else 0),
            reverse=True,
        ):
            for match in pattern.finditer(text):
                if any(
                    start <= match.start() < end or start < match.end() <= end
                    for start, end in occupied_spans
                ):
                    continue
                base_name = normalize_entity_name(role.value)
                full_name = f"{modifier.value} {base_name}" if modifier else base_name

                position = self._get_or_create_entity(
                    document=document,
                    entity_type=EntityType.POSITION,
                    canonical_name=full_name,
                    alias=match.group(0),
                    role_kind=role,
                    role_modifier=modifier,
                )
                role_kind, role_modifier = extract_role_from_text(position.normalized_name)
                if role_kind is None:
                    role_kind = role
                    role_modifier = modifier
                candidates.append(
                    EntityCandidate(
                        candidate_id=CandidateID(
                            stable_id(
                                "candidate",
                                document.document_id,
                                position.entity_id,
                                str(sentence.sentence_index),
                                str(match.start()),
                                str(match.end()),
                            )
                        ),
                        entity_id=position.entity_id,
                        candidate_type=CandidateType.POSITION,
                        canonical_name=position.canonical_name,
                        normalized_name=position.normalized_name,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=match.start(),
                        end_char=match.end(),
                        source="derived_position",
                        role_kind=role_kind,
                        role_modifier=role_modifier,
                    )
                )
                occupied_spans.append((match.start(), match.end()))
        return candidates

    def _position_candidate_from_role_match(
        self,
        document: ArticleDocument,
        sentence,
        match: RoleMatch,
    ) -> EntityCandidate:
        alias = sentence.text[match.start : match.end]
        position = self._get_or_create_entity(
            document=document,
            entity_type=EntityType.POSITION,
            canonical_name=match.canonical_name,
            alias=alias,
            role_kind=match.role_kind,
            role_modifier=match.role_modifier,
        )
        return EntityCandidate(
            candidate_id=CandidateID(
                stable_id(
                    "candidate",
                    document.document_id,
                    position.entity_id,
                    str(sentence.sentence_index),
                    str(match.start),
                    str(match.end),
                )
            ),
            entity_id=position.entity_id,
            candidate_type=CandidateType.POSITION,
            canonical_name=position.canonical_name,
            normalized_name=position.normalized_name,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=match.start,
            end_char=match.end,
            source="derived_position",
            role_kind=match.role_kind,
            role_modifier=match.role_modifier,
        )

    def _derived_party_candidates(
        self,
        *,
        document: ArticleDocument,
        sentence,
        existing_candidates: list[EntityCandidate],
    ) -> list[EntityCandidate]:
        sentence_text = sentence.text
        occupied_entity_ids = {
            candidate.entity_id
            for candidate in existing_candidates
            if candidate.sentence_index == sentence.sentence_index
        }
        candidates: list[EntityCandidate] = []
        party_tokens = set(self.config.party_aliases.keys()).union(
            set(self.config.party_aliases.values())
        )
        for token in party_tokens:
            flags = 0 if token.isupper() and len(token) <= 3 else re.IGNORECASE
            match = re.search(rf"(?<!\w){re.escape(token)}(?!\w)", sentence_text, flags)
            if match is None:
                continue
            canonical_name = self.organization_classifier.resolve_party_name(
                surface_text=match.group(0),
                normalized_text=normalize_entity_name(match.group(0)),
            )
            party = self._get_or_create_entity(
                document=document,
                entity_type=EntityType.POLITICAL_PARTY,
                canonical_name=canonical_name or token,
                alias=match.group(0),
            )
            if party.entity_id in occupied_entity_ids:
                continue
            candidates.append(
                EntityCandidate(
                    candidate_id=CandidateID(
                        stable_id(
                            "candidate",
                            document.document_id,
                            party.entity_id,
                            str(sentence.sentence_index),
                            str(match.start()),
                            str(match.end()),
                        )
                    ),
                    entity_id=party.entity_id,
                    candidate_type=CandidateType.POLITICAL_PARTY,
                    canonical_name=party.canonical_name,
                    normalized_name=party.normalized_name,
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    start_char=match.start(),
                    end_char=match.end(),
                    source="derived_party",
                )
            )
            occupied_entity_ids.add(party.entity_id)
        return candidates

    def _build_edges(
        self,
        document: ArticleDocument,
        candidates: list[EntityCandidate],
        parsed_sentences: dict[int, list[ParsedWord]],
    ) -> list[CandidateEdge]:
        edges: list[CandidateEdge] = []
        by_sentence: dict[int, list[EntityCandidate]] = {}
        for candidate in candidates:
            by_sentence.setdefault(candidate.sentence_index, []).append(candidate)

        for sentence in document.sentences:
            sentence_candidates = by_sentence.get(sentence.sentence_index, [])
            parsed_words = parsed_sentences.get(sentence.sentence_index, [])
            text_lower = sentence.text.lower()
            persons = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == CandidateType.PERSON
            ]
            positions = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == CandidateType.POSITION
            ]
            orgs = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type
                in {CandidateType.ORGANIZATION, CandidateType.PUBLIC_INSTITUTION}
            ]
            parties = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == CandidateType.POLITICAL_PARTY
            ]

            for person in persons:
                for position in positions:
                    distance = abs(person.start_char - position.start_char)
                    if distance > 180:
                        continue
                    if not self._supports_person_role_link(
                        sentence.text,
                        parsed_words,
                        person=person,
                        role=position,
                        sentence_persons=persons,
                    ):
                        continue
                    edges.append(
                        CandidateEdge(
                            edge_type="person-has-role",
                            source_candidate_id=person.candidate_id,
                            target_candidate_id=position.candidate_id,
                            confidence=max(0.45, 0.88 - distance / 100),
                            sentence_index=sentence.sentence_index,
                        )
                    )
                for party in parties:
                    if self._supports_party_link(
                        sentence.text,
                        parsed_words,
                        person=person,
                        party=party,
                    ):
                        edges.append(
                            CandidateEdge(
                                edge_type="person-affiliated-party",
                                source_candidate_id=person.candidate_id,
                                target_candidate_id=party.candidate_id,
                                confidence=0.78,
                                sentence_index=sentence.sentence_index,
                            )
                        )
                for org in orgs:
                    distance = abs(person.start_char - org.start_char)
                    if distance <= 96:
                        edges.append(
                            CandidateEdge(
                                edge_type="person-org-context",
                                source_candidate_id=person.candidate_id,
                                target_candidate_id=org.candidate_id,
                                confidence=max(0.35, 0.7 - distance / 160),
                                sentence_index=sentence.sentence_index,
                            )
                        )

            for position in positions:
                for org in orgs:
                    distance = abs(position.start_char - org.start_char)
                    if distance <= 96:
                        edges.append(
                            CandidateEdge(
                                edge_type="role-at-organization",
                                source_candidate_id=position.candidate_id,
                                target_candidate_id=org.candidate_id,
                                confidence=max(0.45, 0.86 - distance / 120),
                                sentence_index=sentence.sentence_index,
                            )
                        )

            if any(
                word in text_lower
                for word in {
                    *TIE_WORDS.keys(),
                    *KINSHIP_LEMMAS,
                    "narzeczona",
                    "narzeczony",
                }
            ):
                edges.extend(
                    self._tie_edges_from_anchors(
                        sentence_text=sentence.text,
                        sentence_index=sentence.sentence_index,
                        persons=persons,
                    )
                )

        return self._deduplicate_edges(edges)

    @staticmethod
    def _tie_edges_from_anchors(
        *,
        sentence_text: str,
        sentence_index: int,
        persons: list[EntityCandidate],
    ) -> list[CandidateEdge]:
        lowered = sentence_text.lower()
        relation_markers = unique_preserve_order(
            [
                *TIE_WORDS.keys(),
                *KINSHIP_LEMMAS,
                "narzeczon",
                "koleg",
                "znajom",
                "przyjaciel",
                "doradc",
                "zaufan",
            ]
        )
        owner_markers = ("firma", "firmy", "spółka", "spółki", "właściciel", "prowadz")
        public_role_markers = (
            "prezydent",
            "burmistrz",
            "wójt",
            "minister",
            "poseł",
            "radny",
            "marszałek",
        )
        edges: list[CandidateEdge] = []
        for marker in relation_markers:
            anchor = lowered.find(marker)
            if anchor < 0:
                continue
            owner_persons = [
                person
                for person in persons
                if person.end_char <= anchor
                and any(
                    owner_marker
                    in lowered[
                        max(0, person.start_char - 80) : min(len(lowered), person.end_char + 18)
                    ]
                    for owner_marker in owner_markers
                )
            ]
            public_actor_persons = [
                person
                for person in persons
                if person.start_char >= anchor
                and any(
                    role_marker
                    in lowered[
                        max(0, person.start_char - 36) : min(len(lowered), person.end_char + 8)
                    ]
                    for role_marker in public_role_markers
                )
            ]
            if owner_persons and public_actor_persons:
                owner = max(owner_persons, key=lambda person: person.end_char)
                public_actor = min(public_actor_persons, key=lambda person: person.start_char)
                if owner.entity_id != public_actor.entity_id:
                    edges.append(
                        CandidateEdge(
                            edge_type="person-related-to-person",
                            source_candidate_id=public_actor.candidate_id,
                            target_candidate_id=owner.candidate_id,
                            confidence=0.82,
                            sentence_index=sentence_index,
                        )
                    )
                continue

            nearby = [
                person
                for person in persons
                if abs(person.start_char - anchor) <= 80 or abs(person.end_char - anchor) <= 80
            ]
            if len(nearby) == 2 and nearby[0].entity_id != nearby[1].entity_id:
                edges.append(
                    CandidateEdge(
                        edge_type="person-related-to-person",
                        source_candidate_id=nearby[0].candidate_id,
                        target_candidate_id=nearby[1].candidate_id,
                        confidence=0.72,
                        sentence_index=sentence_index,
                    )
                )
        return edges

    def _supports_party_link(
        self,
        sentence_text: str,
        parsed_words: list[ParsedWord],
        *,
        person: EntityCandidate,
        party: EntityCandidate,
    ) -> bool:
        return supports_party_link(
            sentence_text=sentence_text,
            parsed_words=parsed_words,
            person=person,
            party=party,
        )

    @staticmethod
    def _supports_person_role_link(
        sentence_text: str,
        parsed_words: list[ParsedWord],
        *,
        person: EntityCandidate,
        role: EntityCandidate,
        sentence_persons: list[EntityCandidate],
    ) -> bool:
        return supports_person_role_link(
            parsed_words=parsed_words,
            sentence_text=sentence_text,
            person=person,
            role=role,
            sentence_persons=sentence_persons,
        )

    def _mentions_for_sentence(
        self,
        document: ArticleDocument,
        coreference: CoreferenceResult,
        sentence_index: int,
    ) -> list[SentenceEntityAnchor]:
        entity_map = {entity.entity_id: entity for entity in document.entities}
        grouped: dict[tuple[str, int, int], SentenceEntityAnchor] = {}
        sentence_text = document.sentences[sentence_index].text.lower()
        for mention in [*document.mentions, *coreference.resolved_mentions]:
            if mention.sentence_index != sentence_index:
                continue
            if not mention.entity_id or mention.entity_id not in entity_map:
                continue
            start = sentence_text.find(mention.text.lower())
            if start < 0:
                start = self._approximate_mention_start(sentence_text, mention.text.lower())
            if start < 0:
                continue
            anchor = SentenceEntityAnchor(
                entity=entity_map[mention.entity_id],
                start=start,
                end=start + len(mention.text),
            )
            grouped[(anchor.entity.entity_id, anchor.start, anchor.end)] = anchor
        return list(grouped.values())

    @staticmethod
    def _approximate_mention_start(sentence_text: str, mention_text: str) -> int:
        tokens = [token for token in mention_text.split() if token]
        if not tokens:
            return -1
        last_token = tokens[-1]
        last_index = sentence_text.find(last_token)
        if last_index < 0:
            return -1
        return max(0, last_index - max(0, len(mention_text) - len(last_token)))

    def _get_or_create_person_entity(
        self,
        *,
        document: ArticleDocument,
        surface: str,
    ) -> Entity:
        normalized_surface = normalize_entity_name(surface)
        surname = normalized_surface.split()[-1]
        first_token = normalized_surface.split()[0].rstrip(".")
        for entity in document.entities:
            if entity.entity_type != EntityType.PERSON:
                continue
            tokens = entity.canonical_name.split()
            if len(tokens) < 2:
                continue
            if tokens[-1].lower() != surname.lower():
                continue
            existing_first = tokens[0].rstrip(".")
            if not first_token:
                continue
            if existing_first.lower().startswith(first_token[:1].lower()):
                if surface not in entity.aliases:
                    entity.aliases.append(surface)
                return entity
        return self._get_or_create_entity(
            document=document,
            entity_type=EntityType.PERSON,
            canonical_name=normalized_surface,
            alias=surface,
        )

    @staticmethod
    def _is_weak_person_name(text: str) -> bool:
        cleaned = normalize_entity_name(text).replace(".", "")
        return len(cleaned) <= 1

    def _blocks_derived_person_candidate(
        self,
        candidate: EntityCandidate,
        *,
        candidate_start: int,
        candidate_end: int,
    ) -> bool:
        overlaps = (
            candidate.start_char <= candidate_start < candidate.end_char
            or candidate.start_char < candidate_end <= candidate.end_char
            or candidate_start <= candidate.start_char < candidate_end
            or candidate_start < candidate.end_char <= candidate_end
        )
        if not overlaps:
            return False

        if candidate.candidate_type != CandidateType.PERSON:
            return True

        token_count = len(candidate.canonical_name.split())
        if token_count < 2:
            return False
        return True

    @staticmethod
    def _deduplicate_candidates(candidates: list[EntityCandidate]) -> list[EntityCandidate]:
        deduplicated: dict[tuple[str | None, str, int, int, int], EntityCandidate] = {}
        for candidate in candidates:
            key = (
                candidate.entity_id,
                candidate.candidate_type,
                candidate.sentence_index,
                candidate.start_char,
                candidate.end_char,
            )
            deduplicated[key] = candidate
        return list(deduplicated.values())

    @staticmethod
    def _deduplicate_edges(edges: list[CandidateEdge]) -> list[CandidateEdge]:
        deduplicated: dict[tuple[str, str, str, int], CandidateEdge] = {}
        for edge in edges:
            key = (
                edge.edge_type,
                edge.source_candidate_id,
                edge.target_candidate_id,
                edge.sentence_index,
            )
            if key not in deduplicated or deduplicated[key].confidence < edge.confidence:
                deduplicated[key] = edge
        return list(deduplicated.values())

    @staticmethod
    def _get_or_create_entity(
        *,
        document: ArticleDocument,
        entity_type: EntityType,
        canonical_name: str,
        alias: str,
        role_kind: RoleKind | None = None,
        role_modifier: RoleModifier | None = None,
    ) -> Entity:
        existing = next(
            (
                entity
                for entity in document.entities
                if entity.entity_type == entity_type and entity.normalized_name == canonical_name
            ),
            None,
        )
        if existing is not None:
            if alias not in existing.aliases:
                existing.aliases.append(alias)
            if role_kind is not None:
                existing.role_kind = role_kind
            if role_modifier is not None:
                existing.role_modifier = role_modifier
            return existing

        entity = Entity(
            entity_id=EntityID(
                stable_id(entity_type.lower(), document.document_id, canonical_name)
            ),
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name,
            aliases=[alias],
            role_kind=role_kind,
            role_modifier=role_modifier,
        )
        document.entities.append(entity)
        return entity
