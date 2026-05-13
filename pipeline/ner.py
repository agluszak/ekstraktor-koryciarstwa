from __future__ import annotations

import re

from pipeline.base import NERExtractor
from pipeline.config import PipelineConfig
from pipeline.document_graph import sync_entity_mentions
from pipeline.domain_lexicons import KINSHIP_LEMMAS
from pipeline.domain_types import EntityType, MentionKind, NERLabel
from pipeline.entity_classifiers import is_employer_like_name
from pipeline.entity_naming import is_acronym_like
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Mention, TemporalExpression
from pipeline.nlp_services import MorphologyAnalyzer, StanzaPolishMorphologyAnalyzer
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime
from pipeline.utils import (
    extract_local_event_date,
    join_hyphenated_parts,
    normalize_entity_name,
    stable_id,
)

LOWERCASE_COMMON_PARTY_ALIASES = frozenset({"razem"})
ORG_COORDINATION_SEPARATOR = re.compile(r"(?:,\s*|\s+(?:i|oraz)\s+)", re.IGNORECASE)


class SpacyPolishNERExtractor(NERExtractor):
    def __init__(
        self,
        config: PipelineConfig,
        runtime: PipelineRuntime | None = None,
        morphology: MorphologyAnalyzer | None = None,
    ) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)

        self.morphology = morphology or StanzaPolishMorphologyAnalyzer(self.runtime)
        self.canonicalizer = DocumentEntityCanonicalizer(config, self.morphology)

    def name(self) -> str:
        return "spacy_polish_ner_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        parsed = self.runtime.get_spacy_model()(document.cleaned_text)
        entity_index: dict[tuple[str, str], Entity] = {}
        entity_display_score: dict[tuple[str, str], int] = {}

        # Build lookup from config: party alias keys/values (case-insensitive)
        party_keys_lower = {k.lower() for k in self.config.party_aliases}
        party_values_lower = {v.lower() for v in self.config.party_aliases.values()}

        for ent in parsed.ents:
            ner_label = self._ner_label(ent.label_)
            if ner_label in {NERLabel.DATE, NERLabel.TIME}:
                sentence = self._sentence_for_offset(document, ent.start_char)
                document.temporal_expressions.append(
                    TemporalExpression(
                        text=ent.text,
                        label=ner_label,
                        normalized_value=extract_local_event_date(
                            ent.text, document.publication_date
                        )
                        if ner_label == NERLabel.DATE
                        else None,
                        start_char=ent.start_char,
                        end_char=ent.end_char,
                        sentence_index=sentence.sentence_index if sentence is not None else 0,
                        paragraph_index=sentence.paragraph_index if sentence is not None else 0,
                    )
                )
                continue
            entity_type = self._map_label(ent.label_)
            if not entity_type:
                continue
            if entity_type == EntityType.PERSON and self._person_span_looks_like_org(
                ent,
                document.cleaned_text,
            ):
                entity_type = EntityType.ORGANIZATION
            spans = (
                self._split_coordinated_organization_spans(ent.text, ent.start_char)
                if entity_type == EntityType.ORGANIZATION
                else []
            )
            if not spans:
                spans = [(ent.text, ent.start_char, ent.end_char)]

            for span_text, span_start, span_end in spans:
                if (
                    span_text == ent.text
                    and span_start == ent.start_char
                    and span_end == ent.end_char
                ):
                    segment_type = entity_type
                    merge_key, display_name, display_score, lemmas = self._entity_forms(
                        ent, segment_type
                    )

                    # Use spaCy's morphology to filter: single-token PERSON entities
                    # where no token has PROPN POS are misclassifications (media names,
                    # common nouns, abbreviations).
                    if segment_type == EntityType.PERSON:
                        lexical = [t for t in ent if t.text.strip()]
                        if lexical and not any(t.pos_ == "PROPN" for t in lexical):
                            continue
                        if self._person_span_is_kinship_phrase(lexical):
                            continue
                else:
                    segment_type = EntityType.ORGANIZATION
                    merge_key, display_name, display_score, lemmas = self._surface_entity_forms(
                        span_text, segment_type
                    )

                # Reclassify: if spaCy labeled an ORG that matches a known party
                # alias from config, retype it to PoliticalParty.
                if segment_type == EntityType.ORGANIZATION:
                    surface_lower = span_text.strip().lower()
                    if surface_lower in party_keys_lower or surface_lower in party_values_lower:
                        if (
                            surface_lower in LOWERCASE_COMMON_PARTY_ALIASES
                            and span_text.strip() == surface_lower
                        ):
                            continue
                        canonical_party = self._canonical_party_name(span_text)
                        segment_type = EntityType.POLITICAL_PARTY
                        merge_key = canonical_party
                        display_name = canonical_party
                        display_score = 100
                        lemmas = [token.lower() for token in canonical_party.split()]

                from pipeline.domain_types import EntityID

                key = (segment_type, merge_key)
                if key not in entity_index:
                    entity_index[key] = Entity(
                        entity_id=EntityID(
                            stable_id(segment_type.lower(), document.document_id, merge_key)
                        ),
                        entity_type=segment_type,
                        canonical_name=display_name,
                        normalized_name=display_name,
                        lemmas=lemmas,
                    )
                    entity_display_score[key] = display_score
                entity = entity_index[key]

                if len(lemmas) > len(entity.lemmas):
                    entity.lemmas = lemmas

                if display_score > entity_display_score[key]:
                    entity.canonical_name = display_name
                    entity.normalized_name = display_name
                    entity_display_score[key] = display_score
                entity.aliases = list(dict.fromkeys([*entity.aliases, span_text]))
                sentence = self._sentence_for_offset(document, span_start)
                entity.evidence.append(
                    EvidenceSpan(
                        text=span_text,
                        start_char=span_start,
                        end_char=span_end,
                        sentence_index=sentence.sentence_index if sentence is not None else 0,
                        paragraph_index=sentence.paragraph_index if sentence is not None else 0,
                    )
                )
                document.mentions.append(
                    Mention(
                        text=span_text,
                        normalized_text=display_name,
                        entity_type=segment_type,
                        mention_kind=MentionKind.NAMED_ENTITY,
                        sentence_index=sentence.sentence_index if sentence is not None else 0,
                        paragraph_index=sentence.paragraph_index if sentence is not None else 0,
                        start_char=span_start,
                        end_char=span_end,
                        entity_id=entity.entity_id,
                        lemmas=lemmas,
                        ner_label=ner_label,
                    )
                )

        document.entities = list(entity_index.values())
        document = self.canonicalizer.run(document)
        sync_entity_mentions(document)
        return document

    @staticmethod
    def _map_label(label: str) -> EntityType | None:
        ner_label = SpacyPolishNERExtractor._ner_label(label)
        if ner_label == NERLabel.PERSON:
            return EntityType.PERSON
        if ner_label in {NERLabel.GEOGRAPHY, NERLabel.PLACE}:
            return EntityType.LOCATION
        if ner_label == NERLabel.ORGANIZATION:
            return EntityType.ORGANIZATION
        return None

    @staticmethod
    def _ner_label(label: str) -> NERLabel | None:
        lowered = label.lower()
        if lowered in {"date", "time"}:
            return NERLabel(lowered)
        if "pers" in lowered or lowered == "person":
            return NERLabel.PERSON
        if lowered in {"loc", "gpe", "location"} or "place" in lowered:
            return NERLabel.PLACE
        if "geog" in lowered:
            return NERLabel.GEOGRAPHY
        if "org" in lowered:
            return NERLabel.ORGANIZATION
        return None

    @staticmethod
    def _person_span_looks_like_org(ent, cleaned_text: str) -> bool:
        surface = ent.text.strip()
        lowered = surface.lower()
        business_terms = {
            "consulting",
            "group",
            "holding",
            "spółka",
            "spółka z o.o.",
            "sp.",
            "firma",
            "fundacja",
            "stowarzyszenie",
            "przedsiębiorstwo",
        }
        if any(term in lowered for term in business_terms):
            return True

        right_context = cleaned_text[ent.end_char : ent.end_char + 18].lower()
        org_context_after = {" sp. z o.o.", " spółka", " firma"}
        return any(right_context.startswith(term) for term in org_context_after)

    @staticmethod
    def _person_span_is_kinship_phrase(lexical_tokens) -> bool:
        if len(lexical_tokens) < 2:
            return False
        first = lexical_tokens[0]
        if first.pos_ != "NOUN":
            return False
        if first.lemma_.casefold() not in KINSHIP_LEMMAS:
            return False
        return any(token.pos_ == "PROPN" for token in lexical_tokens[1:])

    @staticmethod
    def _entity_forms(ent, entity_type: EntityType) -> tuple[str, str, int, list[str]]:
        lemmas = [t.lemma_.lower() for t in ent if t.text.strip()]
        if entity_type == EntityType.PERSON:
            merge_key = SpacyPolishNERExtractor._person_merge_key(ent)
            display_name, display_score = SpacyPolishNERExtractor._person_display_name(ent)
            return merge_key, display_name, display_score, lemmas
        normalized = normalize_entity_name(ent.text)
        return normalized, normalized, 0, lemmas

    @staticmethod
    def _surface_entity_forms(
        text: str,
        entity_type: EntityType,
    ) -> tuple[str, str, int, list[str]]:
        normalized = normalize_entity_name(text)
        lemmas = [token.casefold() for token in normalized.split()]
        return normalized, normalized, 0 if entity_type == EntityType.ORGANIZATION else -1, lemmas

    @staticmethod
    def _split_coordinated_organization_spans(
        text: str,
        start_char: int,
    ) -> list[tuple[str, int, int]]:
        if not any(marker in text.lower() for marker in (",", " i ", " oraz ")):
            return []

        pieces = [
            piece.strip(" ,")
            for piece in ORG_COORDINATION_SEPARATOR.split(text)
            if piece.strip(" ,")
        ]
        if len(pieces) < 2 or not all(
            is_employer_like_name(piece) and (len(piece.split()) >= 2 or is_acronym_like(piece))
            for piece in pieces
        ):
            return []

        spans: list[tuple[str, int, int]] = []
        cursor = 0
        for piece in pieces:
            relative_start = text.find(piece, cursor)
            if relative_start < 0:
                return []
            relative_end = relative_start + len(piece)
            spans.append((piece, start_char + relative_start, start_char + relative_end))
            cursor = relative_end
        return spans

    @staticmethod
    def _person_merge_key(ent) -> str:
        parts = [
            (
                token.text.strip()
                if "-" in token.text and "-" not in token.lemma_.strip()
                else token.lemma_.strip()
                if token.lemma_.strip()
                else token.text.strip()
            )
            for token in ent
            if token.text.strip()
        ]
        return normalize_entity_name(join_hyphenated_parts(parts))

    @staticmethod
    def _person_display_name(ent) -> tuple[str, int]:
        lexical_tokens = [token for token in ent if token.pos_ != "PUNCT" and token.text.strip()]
        if not lexical_tokens:
            normalized = normalize_entity_name(ent.text)
            return normalized, 0

        all_propn = all(token.pos_ == "PROPN" for token in lexical_tokens)
        has_nom = any("Case=Nom" in token.morph for token in lexical_tokens)
        unchanged_lemma = any(
            token.lemma_.strip() == token.text.strip() for token in lexical_tokens
        )
        single_token = len(lexical_tokens) == 1

        if all_propn and (has_nom or unchanged_lemma or single_token):
            display = SpacyPolishNERExtractor._person_merge_key(ent)
            score = 10
            if has_nom:
                score += 5
            if unchanged_lemma:
                score += 2
            if single_token:
                score += 1
            return display, score

        display = SpacyPolishNERExtractor._person_merge_key(ent)
        surface = normalize_entity_name(ent.text)
        if SpacyPolishNERExtractor._surface_repairs_broken_person_lemma(surface, display):
            return surface, 8
        if all_propn:
            return display, 5

        return surface, -5

    @staticmethod
    def _surface_repairs_broken_person_lemma(surface: str, display: str) -> bool:
        surface_tokens = surface.split()
        display_tokens = display.split()
        if len(surface_tokens) != len(display_tokens) or len(surface_tokens) < 2:
            return False
        repaired = False
        for surface_token, display_token in zip(surface_tokens, display_tokens, strict=True):
            surface_lower = surface_token.lower()
            display_lower = display_token.lower()
            if surface_lower == display_lower:
                continue
            if (
                surface_lower.startswith(display_lower)
                and len(surface_lower) - len(display_lower) <= 2
            ):
                repaired = True
                continue
            return False
        return repaired

    @staticmethod
    def _sentence_index(document: ArticleDocument, start_char: int) -> int:
        sentence = SpacyPolishNERExtractor._sentence_for_offset(document, start_char)
        return sentence.sentence_index if sentence is not None else 0

    @staticmethod
    def _sentence_for_offset(document: ArticleDocument, start_char: int):
        for sentence in document.sentences:
            if sentence.start_char <= start_char <= sentence.end_char:
                return sentence
        return None

    def _canonical_party_name(self, text: str) -> str:
        normalized = normalize_entity_name(text)
        lookup = {
            alias.lower(): canonical for alias, canonical in self.config.party_aliases.items()
        }
        return lookup.get(text.lower(), lookup.get(normalized.lower(), normalized))
