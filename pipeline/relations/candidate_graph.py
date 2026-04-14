from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.models import (
    ArticleDocument,
    CandidateEdge,
    CandidateGraph,
    CoreferenceResult,
    Entity,
    EntityCandidate,
)
from pipeline.utils import normalize_entity_name, normalize_party_name, stable_id

from .constants import PARTY_CONTEXT_WORDS, ROLE_PATTERNS


@dataclass(slots=True)
class SentenceEntityAnchor:
    entity: Entity
    start: int
    end: int


@dataclass(slots=True)
class ParsedWord:
    index: int
    text: str
    lemma: str
    upos: str
    head: int
    deprel: str
    start: int
    end: int


class CandidateGraphBuilder:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

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
                candidate = self._candidate_for_anchor(document, sentence, anchor)
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
    ) -> EntityCandidate | None:
        entity = anchor.entity
        if entity.entity_type == "Person" and self._is_weak_person_name(entity.canonical_name):
            return None
        candidate_type = entity.entity_type
        entity_id = entity.entity_id
        canonical_name = entity.canonical_name
        normalized_name = entity.normalized_name
        attributes = dict(entity.attributes)

        if entity.entity_type == "Organization":
            party_name = self._party_name(entity)
            if party_name is not None:
                party = self._get_or_create_entity(
                    document=document,
                    entity_type="PoliticalParty",
                    canonical_name=party_name,
                    alias=entity.canonical_name,
                )
                candidate_type = "PoliticalParty"
                entity_id = party.entity_id
                canonical_name = party.canonical_name
                normalized_name = party.normalized_name
            else:
                organization_kind = self._organization_kind(entity)
                attributes["organization_kind"] = organization_kind
                if organization_kind == "public_institution":
                    candidate_type = "PublicInstitution"

        return EntityCandidate(
            candidate_id=stable_id(
                "candidate",
                document.document_id,
                entity_id or canonical_name,
                str(sentence.sentence_index),
                str(anchor.start),
                str(anchor.end),
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
            attributes=attributes,
        )

    def _derived_person_candidates(
        self,
        *,
        document: ArticleDocument,
        sentence,
        existing_candidates: list[EntityCandidate],
    ) -> list[EntityCandidate]:
        occupied_spans = {
            (candidate.start_char, candidate.end_char)
            for candidate in existing_candidates
            if candidate.sentence_index == sentence.sentence_index
            and candidate.candidate_type == "Person"
        }
        candidates: list[EntityCandidate] = []
        pattern = re.compile(
            r"\b(?:[A-ZŁŚŻŹĆŃÓ]\.|[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+)\s+"
            r"[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż-]+\b"
        )
        for match in pattern.finditer(sentence.text):
            span = (match.start(), match.end())
            if span in occupied_spans:
                continue
            surface = match.group(0)
            person = self._get_or_create_person_entity(document=document, surface=surface)
            candidates.append(
                EntityCandidate(
                    candidate_id=stable_id(
                        "candidate",
                        document.document_id,
                        person.entity_id,
                        str(sentence.sentence_index),
                        str(match.start()),
                        str(match.end()),
                    ),
                    entity_id=person.entity_id,
                    candidate_type="Person",
                    canonical_name=person.canonical_name,
                    normalized_name=person.normalized_name,
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    start_char=match.start(),
                    end_char=match.end(),
                    source="derived_person",
                )
            )
        return candidates

    def _position_candidates(
        self,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
    ) -> list[EntityCandidate]:
        text = sentence.text
        candidates: list[EntityCandidate] = []
        occupied_spans: list[tuple[int, int]] = []
        for role_name, pattern in sorted(
            ROLE_PATTERNS.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            for match in pattern.finditer(text):
                if any(
                    start <= match.start() < end or start < match.end() <= end
                    for start, end in occupied_spans
                ):
                    continue
                position = self._get_or_create_entity(
                    document=document,
                    entity_type="Position",
                    canonical_name=normalize_entity_name(role_name),
                    alias=match.group(0),
                )
                candidates.append(
                    EntityCandidate(
                        candidate_id=stable_id(
                            "candidate",
                            document.document_id,
                            position.entity_id,
                            str(sentence.sentence_index),
                            str(match.start()),
                            str(match.end()),
                        ),
                        entity_id=position.entity_id,
                        candidate_type="Position",
                        canonical_name=position.canonical_name,
                        normalized_name=position.normalized_name,
                        sentence_index=sentence.sentence_index,
                        paragraph_index=sentence.paragraph_index,
                        start_char=match.start(),
                        end_char=match.end(),
                        source="derived_position",
                        attributes={"role_kind": position.normalized_name.lower()},
                    )
                )
                occupied_spans.append((match.start(), match.end()))
        return candidates

    def _derived_party_candidates(
        self,
        *,
        document: ArticleDocument,
        sentence,
        existing_candidates: list[EntityCandidate],
    ) -> list[EntityCandidate]:
        sentence_text = sentence.text
        occupied_entity_ids = {candidate.entity_id for candidate in existing_candidates}
        candidates: list[EntityCandidate] = []
        for alias, canonical in self.config.party_aliases.items():
            match = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", sentence_text, re.IGNORECASE)
            if match is None:
                continue
            party = self._get_or_create_entity(
                document=document,
                entity_type="PoliticalParty",
                canonical_name=canonical,
                alias=alias,
            )
            if party.entity_id in occupied_entity_ids:
                continue
            candidates.append(
                EntityCandidate(
                    candidate_id=stable_id(
                        "candidate",
                        document.document_id,
                        party.entity_id,
                        str(sentence.sentence_index),
                        str(match.start()),
                        str(match.end()),
                    ),
                    entity_id=party.entity_id,
                    candidate_type="PoliticalParty",
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
                if candidate.candidate_type == "Person"
            ]
            positions = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == "Position"
            ]
            orgs = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type in {"Organization", "PublicInstitution"}
            ]
            parties = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == "PoliticalParty"
            ]

            for person in persons:
                for position in positions:
                    distance = abs(person.start_char - position.start_char)
                    if distance <= 96:
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
                for word in ("znajomy", "współpracownik", "przyjaciel", "doradca")
            ):
                for left, right in zip(persons, persons[1:], strict=False):
                    edges.append(
                        CandidateEdge(
                            edge_type="person-related-to-person",
                            source_candidate_id=left.candidate_id,
                            target_candidate_id=right.candidate_id,
                            confidence=0.68,
                            sentence_index=sentence.sentence_index,
                        )
                    )

        return self._deduplicate_edges(edges)

    def _supports_party_link(
        self,
        sentence_text: str,
        parsed_words: list[ParsedWord],
        *,
        person: EntityCandidate,
        party: EntityCandidate,
    ) -> bool:
        lower = sentence_text.lower()
        party_window = lower[max(0, party.start_char - 24) : party.end_char + 24]
        if any(marker in party_window for marker in PARTY_CONTEXT_WORDS):
            return abs(person.start_char - party.start_char) <= 72

        party_word = next(
            (
                word
                for word in parsed_words
                if word.start <= party.start_char < word.end
                or party.start_char <= word.start < party.end_char
            ),
            None,
        )
        if party_word is None:
            return False

        head = next((word for word in parsed_words if word.index == party_word.head), None)
        if head is None:
            return False
        return head.lemma in PARTY_CONTEXT_WORDS and abs(person.start_char - party.start_char) <= 72

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
            if entity.entity_type != "Person":
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
            entity_type="Person",
            canonical_name=normalized_surface,
            alias=surface,
        )

    def _party_name(self, entity: Entity) -> str | None:
        names = [entity.canonical_name, entity.normalized_name, *entity.aliases]
        for name in names:
            normalized = normalize_party_name(name, self.config.party_aliases)
            if normalized in self.config.party_aliases.values():
                return normalized
            cleaned = normalized.strip()
            if cleaned.isupper() and cleaned not in self.config.party_aliases:
                continue
            name_tokens = [token.lower() for token in normalized.split()]
            for canonical in self.config.party_aliases.values():
                alias_tokens = [token.lower() for token in canonical.split()]
                if len(name_tokens) != len(alias_tokens):
                    continue
                comparable = [
                    (token, alias_token)
                    for token, alias_token in zip(name_tokens, alias_tokens, strict=False)
                    if len(token) >= 4 and len(alias_token) >= 4
                ]
                if comparable and all(
                    token[:4] == alias_token[:4] for token, alias_token in comparable
                ):
                    return canonical
        return None

    @staticmethod
    def _organization_kind(entity: Entity) -> str:
        normalized = entity.normalized_name.lower()
        if normalized in {"kowr", "wfosi gw", "wfośigw", "nfośigw", "nfosigw"}:
            return "public_institution"
        if "fundusz" in normalized or "minister" in normalized or "sejm" in normalized:
            return "public_institution"
        if "spół" in normalized or "holding" in normalized or "wodoci" in normalized:
            return "company"
        return "organization"

    @staticmethod
    def _is_weak_person_name(text: str) -> bool:
        cleaned = normalize_entity_name(text).replace(".", "")
        return len(cleaned) <= 1

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
        entity_type: str,
        canonical_name: str,
        alias: str,
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
            return existing

        entity = Entity(
            entity_id=stable_id(entity_type.lower(), document.document_id, canonical_name),
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name,
            aliases=[alias],
        )
        document.entities.append(entity)
        return entity
