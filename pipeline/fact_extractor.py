from __future__ import annotations

from dataclasses import replace

from pipeline.base import FactExtractor
from pipeline.config import PipelineConfig
from pipeline.domain_registry import DomainRegistry, build_default_domain_registry
from pipeline.extraction_context import ExtractionContext
from pipeline.models import ArticleDocument, Fact
from pipeline.normalization import DocumentEntityCanonicalizer


class PolishFactExtractor(FactExtractor):
    def __init__(
        self,
        config: PipelineConfig,
        registry: DomainRegistry | None = None,
    ) -> None:
        self.config = config
        self.canonicalizer = DocumentEntityCanonicalizer(config)
        self.registry = registry or build_default_domain_registry(config)

    def name(self) -> str:
        return "polish_fact_extractor"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        extraction_context = ExtractionContext.build(document)
        facts: list[Fact] = list(document.facts)

        for builder in self.registry.document_fact_builders:
            facts.extend(builder.build(document, extraction_context))

        document.facts = self._deduplicate_facts(facts)
        canonicalized = self.canonicalizer.run(document)
        canonicalized.facts = self._deduplicate_facts(canonicalized.facts)
        return canonicalized

    @staticmethod
    def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str, str | None, str | None, str], Fact] = {}
        for fact in facts:
            key = (
                fact.fact_type,
                fact.subject_entity_id,
                fact.object_entity_id,
                fact.value_normalized,
                fact.evidence.text,
            )
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = fact
                continue
            preferred = fact if existing.confidence < fact.confidence else existing
            fallback = existing if preferred is fact else fact
            merged_matches = list(preferred.possible_entity_matches)
            for match in fallback.possible_entity_matches:
                if match not in merged_matches:
                    merged_matches.append(match)
            deduplicated[key] = replace(
                preferred,
                entity_resolution=preferred.entity_resolution or fallback.entity_resolution,
                possible_entity_matches=merged_matches,
            )
        return list(deduplicated.values())
