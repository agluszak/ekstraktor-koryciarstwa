from pipeline.config import PipelineConfig
from pipeline.models import (
    ArticleDocument,
    CoreferenceResult,
    Entity,
    Mention,
    SentenceFragment,
)
from pipeline.relations import PolishRuleBasedRelationExtractor


def test_party_aliases_match_whole_tokens_only() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    document = ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Jan Kowalski, polityk PiS, został powołany.",
        paragraphs=["Jan Kowalski, polityk PiS, został powołany."],
        sentences=[
            SentenceFragment(
                text="Jan Kowalski, polityk PiS, został powołany.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=43,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type="Person",
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            )
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            )
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )
    party_names = sorted(
        entity.canonical_name
        for entity in extracted.entities
        if entity.entity_type == "PoliticalParty"
    )

    assert party_names == ["Prawo i Sprawiedliwość"]
