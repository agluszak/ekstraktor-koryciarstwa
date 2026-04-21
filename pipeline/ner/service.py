from __future__ import annotations

from pipeline.base import NERExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Mention
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime
from pipeline.utils import join_hyphenated_parts, normalize_entity_name, stable_id


class SpacyPolishNERExtractor(NERExtractor):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)
        self.canonicalizer = DocumentEntityCanonicalizer(config)

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
            entity_type = self._map_label(ent.label_)
            if not entity_type:
                continue
            merge_key, display_name, display_score, lemmas = self._entity_forms(ent, entity_type)

            # Use spaCy's morphology to filter: single-token PERSON entities
            # where no token has PROPN POS are misclassifications (media names,
            # common nouns, abbreviations).
            if entity_type == EntityType.PERSON:
                lexical = [t for t in ent if t.text.strip()]
                if lexical and not any(t.pos_ == "PROPN" for t in lexical):
                    continue

            # Reclassify: if spaCy labeled an ORG that matches a known party
            # alias from config, retype it to PoliticalParty.
            if entity_type == EntityType.ORGANIZATION:
                surface_lower = ent.text.strip().lower()
                if surface_lower in party_keys_lower or surface_lower in party_values_lower:
                    canonical_party = self._canonical_party_name(ent.text)
                    entity_type = EntityType.POLITICAL_PARTY
                    merge_key = canonical_party
                    display_name = canonical_party
                    display_score = 100
                    lemmas = [token.lower() for token in canonical_party.split()]

            from pipeline.domain_types import EntityID

            key = (entity_type, merge_key)
            if key not in entity_index:
                entity_index[key] = Entity(
                    entity_id=EntityID(
                        stable_id(entity_type.lower(), document.document_id, merge_key)
                    ),
                    entity_type=entity_type,
                    canonical_name=display_name,
                    normalized_name=display_name,
                    lemmas=lemmas,
                )
                entity_display_score[key] = display_score
            entity = entity_index[key]

            # Update lemmas if we found a more "complete" version
            if len(lemmas) > len(entity.lemmas):
                entity.lemmas = lemmas

            if display_score > entity_display_score[key]:
                entity.canonical_name = display_name
                entity.normalized_name = display_name
                entity_display_score[key] = display_score
            entity.aliases = list(dict.fromkeys([*entity.aliases, ent.text]))
            sentence = self._sentence_for_offset(document, ent.start_char)
            entity.evidence.append(
                EvidenceSpan(
                    text=ent.text,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    sentence_index=sentence.sentence_index if sentence is not None else 0,
                    paragraph_index=sentence.paragraph_index if sentence is not None else 0,
                )
            )
            document.mentions.append(
                Mention(
                    text=ent.text,
                    normalized_text=display_name,
                    mention_type=entity_type,
                    sentence_index=sentence.sentence_index if sentence is not None else 0,
                    paragraph_index=sentence.paragraph_index if sentence is not None else 0,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    entity_id=entity.entity_id,
                    lemmas=lemmas,
                )
            )

        document.entities = list(entity_index.values())
        return self.canonicalizer.run(document)

    @staticmethod
    def _map_label(label: str) -> EntityType | None:
        lowered = label.lower()
        if "pers" in lowered or lowered == "person":
            return EntityType.PERSON
        if "org" in lowered or "geog" in lowered or "place" in lowered:
            return EntityType.ORGANIZATION
        return None

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
    def _person_merge_key(ent) -> str:
        parts = [
            token.lemma_.strip() if token.lemma_.strip() else token.text.strip()
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
        if all_propn:
            return display, 5

        surface = normalize_entity_name(ent.text)
        return surface, -5

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
