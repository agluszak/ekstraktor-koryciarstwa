from unittest.mock import MagicMock

from pipeline.domain_types import ClauseID, ClusterID, DocumentID, EntityID, EntityType, NERLabel
from pipeline.extraction_context import ExtractionContext, SentenceContext
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    ClauseUnit,
    ClusterMention,
    EntityCluster,
    ParsedWord,
    SentenceFragment,
    TemporalExpression,
)


def test_clusters_for_mentions_matches_span_before_text_fallback() -> None:
    person_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=10,
        end_char=22,
        entity_id=EntityID("entity-person"),
    )
    organization_mention = ClusterMention(
        text="Urząd Gminy",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        sentence_index=0,
        paragraph_index=0,
        start_char=40,
        end_char=51,
        entity_id=EntityID("entity-org"),
    )
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="",
        paragraphs=[],
        clusters=[
            EntityCluster(
                cluster_id=ClusterID("cluster-person"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
                mentions=[person_mention],
            ),
            EntityCluster(
                cluster_id=ClusterID("cluster-org"),
                entity_type=EntityType.PUBLIC_INSTITUTION,
                canonical_name="Urząd Gminy",
                normalized_name="urząd gminy",
                mentions=[organization_mention],
            ),
        ],
    )
    clause_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=11,
        end_char=23,
        entity_id=EntityID("entity-person"),
    )

    clusters = ExtractionContext.build(document).clusters_for_mentions(
        [clause_mention, organization_mention],
        {EntityType.PERSON},
    )

    assert [cluster.cluster_id for cluster in clusters] == [ClusterID("cluster-person")]


def test_paragraph_context_clusters_are_sorted_by_clause_distance() -> None:
    near = ClusterMention(
        text="Spółka",
        entity_type=EntityType.ORGANIZATION,
        sentence_index=2,
        paragraph_index=1,
        start_char=105,
        end_char=111,
    )
    far = ClusterMention(
        text="Fundusz",
        entity_type=EntityType.ORGANIZATION,
        sentence_index=0,
        paragraph_index=1,
        start_char=5,
        end_char=12,
    )
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="",
        paragraphs=[],
        clusters=[
            EntityCluster(
                cluster_id=ClusterID("far"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Fundusz",
                normalized_name="fundusz",
                mentions=[far],
            ),
            EntityCluster(
                cluster_id=ClusterID("near"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Spółka",
                normalized_name="spółka",
                mentions=[near],
            ),
        ],
    )
    clause = ClauseUnit(
        clause_id=ClauseID("clause"),
        text="",
        trigger_head_text="",
        trigger_head_lemma="",
        sentence_index=2,
        paragraph_index=1,
        start_char=100,
        end_char=140,
    )

    clusters = ExtractionContext.build(document).paragraph_context_clusters(
        clause,
        {EntityType.ORGANIZATION},
    )

    assert [cluster.cluster_id for cluster in clusters] == [ClusterID("near"), ClusterID("far")]


def test_sentence_context_event_date_prefers_local_polish_month_date() -> None:
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date="2019-03-22",
        cleaned_text="",
        paragraphs=[],
        sentences=[
            SentenceFragment(
                text="Jarosław Słoma od 25 lutego zajął nową funkcję.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=48,
            )
        ],
    )
    sentence = document.sentences[0]
    context = SentenceContext(
        document=document,
        sentence=sentence,
        parsed_words=[],
        graph=MagicMock(spec=CandidateGraph),
        candidates=[],
        paragraph_candidates=[],
        previous_candidates=[],
    )

    assert context.event_date == "2019-02-25"


def test_sentence_context_time_scope_detects_future_from_morphology() -> None:
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date="2019-03-22",
        cleaned_text="",
        paragraphs=[],
        sentences=[
            SentenceFragment(
                text="Anna będzie pełnić funkcję dyrektora.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=36,
            )
        ],
    )
    sentence = document.sentences[0]
    context = SentenceContext(
        document=document,
        sentence=sentence,
        parsed_words=[
            ParsedWord(1, "Anna", "Anna", "PROPN", 2, "nsubj", 0, 4),
            ParsedWord(
                2,
                "będzie",
                "być",
                "AUX",
                0,
                "root",
                5,
                11,
                feats={"Tense": "Fut"},
            ),
            ParsedWord(3, "pełnić", "pełnić", "VERB", 2, "xcomp", 12, 18),
        ],
        graph=MagicMock(spec=CandidateGraph),
        candidates=[],
        paragraph_candidates=[],
        previous_candidates=[],
    )

    assert context.time_scope.value == "future"


def test_sentence_context_event_date_prefers_preserved_ner_date_span() -> None:
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date="2019-03-22",
        cleaned_text="",
        paragraphs=[],
        temporal_expressions=[
            TemporalExpression(
                text="25 lut.",
                label=NERLabel.DATE,
                normalized_value="2019-02-25",
                sentence_index=0,
                paragraph_index=0,
                start_char=18,
                end_char=25,
            )
        ],
        sentences=[
            SentenceFragment(
                text="Jarosław Słoma od 25 lut. zajął nową funkcję.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=45,
            )
        ],
    )
    sentence = document.sentences[0]
    context = SentenceContext(
        document=document,
        sentence=sentence,
        parsed_words=[],
        graph=MagicMock(spec=CandidateGraph),
        candidates=[],
        paragraph_candidates=[],
        previous_candidates=[],
    )

    assert context.event_date == "2019-02-25"


def test_sentence_context_event_date_falls_back_to_publication_date() -> None:
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date="2019-03-22",
        cleaned_text="",
        paragraphs=[],
        sentences=[
            SentenceFragment(
                text="Jarosław Słoma zajął nową funkcję.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=34,
            )
        ],
    )
    sentence = document.sentences[0]
    context = SentenceContext(
        document=document,
        sentence=sentence,
        parsed_words=[],
        graph=MagicMock(spec=CandidateGraph),
        candidates=[],
        paragraph_candidates=[],
        previous_candidates=[],
    )

    assert context.event_date == "2019-03-22"
