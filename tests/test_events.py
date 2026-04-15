from pipeline.clustering import PolishEntityClusterer
from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityType, EventType, RelationType
from pipeline.events import PolishEventExtractor
from pipeline.frames import PolishGovernanceFrameExtractor
from pipeline.models import (
    ArticleDocument,
    CoreferenceResult,
    Entity,
    Mention,
    SentenceFragment,
)
from pipeline.relations import PolishRuleBasedRelationExtractor
from pipeline.runtime import PipelineRuntime
from pipeline.syntax import StanzaClauseParser


def prepare_for_relation_extraction(
    config: PipelineConfig,
    document: ArticleDocument,
) -> ArticleDocument:
    runtime = PipelineRuntime(config)
    document = PolishEntityClusterer(config).run(document)
    document = StanzaClauseParser(config, runtime).run(document)
    return PolishGovernanceFrameExtractor(config).run(document)


def test_dismissal_sentence_produces_relation_and_event() -> None:
    config = PipelineConfig.from_file("config.yaml")
    relation_extractor = PolishRuleBasedRelationExtractor(config)
    event_extractor = PolishEventExtractor(config)
    document = ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Leszek Ruta został odwołany z zarządu Zarządu Transportu Miejskiego.",
        paragraphs=["Leszek Ruta został odwołany z zarządu Zarządu Transportu Miejskiego."],
        sentences=[
            SentenceFragment(
                text="Leszek Ruta został odwołany z zarządu Zarządu Transportu Miejskiego.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=68,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type=EntityType.PERSON,
                canonical_name="Leszek Ruta",
                normalized_name="Leszek Ruta",
            ),
            Entity(
                entity_id="org-1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Zarząd Transportu Miejskiego",
                normalized_name="Zarząd Transportu Miejskiego",
            ),
        ],
        mentions=[
            Mention(
                text="Leszek Ruta",
                normalized_text="Leszek Ruta",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="Zarząd Transportu Miejskiego",
                normalized_text="Zarząd Transportu Miejskiego",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    document = prepare_for_relation_extraction(config, document)
    document = relation_extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )
    document = event_extractor.run(document)

    assert any(
        relation.relation_type == RelationType.DISMISSED_FROM for relation in document.relations
    )
    assert any(event.event_type == EventType.DISMISSAL for event in document.events)
