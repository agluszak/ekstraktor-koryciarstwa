from __future__ import annotations

from collections.abc import Mapping

from stanza.pipeline.coref_processor import extract_text

from pipeline.base import CoreferenceResolver
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType
from pipeline.models import ArticleDocument, CoreferenceResult, Entity, Mention
from pipeline.runtime import PipelineRuntime
from pipeline.utils import normalize_entity_name


class StanzaCoreferenceResolver(CoreferenceResolver):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime or PipelineRuntime(config)

    def name(self) -> str:
        return "stanza_coreference_resolver"

    def run(self, document: ArticleDocument) -> CoreferenceResult:
        mention_links: dict[int, str] = {}
        resolved_mentions = list(document.mentions)
        people = [entity for entity in document.entities if entity.entity_type == EntityType.PERSON]
        entity_by_name = {entity.normalized_name: entity for entity in people}
        nlp_doc = self.runtime.get_stanza_coref_pipeline()(document.cleaned_text)

        for chain in getattr(nlp_doc, "coref", []):
            representative_text = normalize_entity_name(chain.representative_text)
            representative_entity = entity_by_name.get(representative_text)
            if representative_entity is None:
                representative_entity = self._match_person_entity(
                    entity_by_name, representative_text
                )
            if representative_entity is None:
                continue

            for mention in chain.mentions:
                sentence_index = mention.sentence
                mention_text = extract_text(
                    nlp_doc,
                    mention.sentence,
                    mention.start_word,
                    mention.end_word,
                )
                resolved = Mention(
                    text=mention_text,
                    normalized_text=normalize_entity_name(mention_text),
                    mention_type="ResolvedPersonReference",
                    sentence_index=sentence_index,
                    entity_id=representative_entity.entity_id,
                    attributes={"representative_text": representative_text},
                )
                mention_links[id(resolved)] = representative_entity.entity_id
                resolved_mentions.append(resolved)

        for mention in document.mentions:
            if mention.entity_id:
                mention_links[id(mention)] = mention.entity_id

        return CoreferenceResult(mention_links=mention_links, resolved_mentions=resolved_mentions)

    @staticmethod
    def _match_person_entity(
        entity_by_name: Mapping[str, Entity],
        representative_text: str,
    ) -> Entity | None:
        if representative_text in entity_by_name:
            return entity_by_name[representative_text]
        rep_tokens = representative_text.split()
        for candidate_name, entity in entity_by_name.items():
            candidate_tokens = candidate_name.split()
            if rep_tokens == candidate_tokens:
                return entity
            if rep_tokens and candidate_tokens and rep_tokens[-1] == candidate_tokens[-1]:
                if len(rep_tokens) == len(candidate_tokens):
                    return entity
        return None
