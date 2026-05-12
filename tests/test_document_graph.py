from pipeline.document_graph import ensure_entity_view
from pipeline.domain_types import DocumentID, EntityID, EntityType, MentionKind
from pipeline.models import ArticleDocument, Entity, Mention


def test_ensure_entity_view_preserves_non_derived_mention_kind() -> None:
    entity_id = EntityID("entity-1")
    document = ArticleDocument(
        document_id=DocumentID("doc-graph"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="Jan Kowalski",
        paragraphs=["Jan Kowalski"],
        entities=[
            Entity(
                entity_id=entity_id,
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            )
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                entity_type=EntityType.PERSON,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=12,
                mention_kind=MentionKind.NAMED_ENTITY,
                entity_id=entity_id,
            )
        ],
    )

    ensure_entity_view(
        document,
        entity=document.entities[0],
        surface="Jan Kowalski",
        normalized_text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        mention_kind=MentionKind.DERIVED_ENTITY,
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=12,
    )

    assert len(document.mentions) == 1
    assert document.mentions[0].mention_kind == MentionKind.NAMED_ENTITY
