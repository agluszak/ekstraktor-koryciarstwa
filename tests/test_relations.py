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


def test_syndrom_does_not_trigger_fake_syn_relation() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = 'Jest to niestety prosta droga do "syndromu Rybnika" - pisze Dorota Połedniok.'
    document = ArticleDocument(
        document_id="doc-2",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=81,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type="Person",
                canonical_name="Dorota Połedniok",
                normalized_name="Dorota Połedniok",
            )
        ],
        mentions=[
            Mention(
                text="Dorota Połedniok",
                normalized_text="Dorota Połedniok",
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

    assert not any(relation.relation_type == "RELATED_TO" for relation in extracted.relations)


def test_compensation_relation_is_extracted() -> None:
    config = PipelineConfig.from_file("config.yaml")
    extractor = PolishRuleBasedRelationExtractor(config)
    text = "Łukasz Bałajewicz zarabia miesięcznie ponad 31 tys. zł brutto jako prezes KZN."
    document = ArticleDocument(
        document_id="doc-3",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=82,
            )
        ],
        entities=[
            Entity(
                entity_id="person-1",
                entity_type="Person",
                canonical_name="Łukasz Bałajewicz",
                normalized_name="Łukasz Bałajewicz",
            ),
            Entity(
                entity_id="org-1",
                entity_type="Organization",
                canonical_name="KZN",
                normalized_name="KZN",
            ),
        ],
        mentions=[
            Mention(
                text="Łukasz Bałajewicz",
                normalized_text="Łukasz Bałajewicz",
                mention_type="Person",
                sentence_index=0,
                entity_id="person-1",
            ),
            Mention(
                text="KZN",
                normalized_text="KZN",
                mention_type="Organization",
                sentence_index=0,
                entity_id="org-1",
            ),
        ],
    )

    extracted = extractor.run(
        document,
        coreference=CoreferenceResult(mention_links={}, resolved_mentions=[]),
    )

    compensation_relations = [
        relation
        for relation in extracted.relations
        if relation.relation_type == "RECEIVES_COMPENSATION"
    ]

    assert compensation_relations
    assert compensation_relations[0].attributes["amount_text"] == "31 Tys. Zł Brutto"
