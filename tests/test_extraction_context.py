from unittest.mock import MagicMock

from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    ClauseID,
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    NERLabel,
)
from pipeline.extraction_context import ExtractionContext, FactExtractionContext, SentenceContext
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    ClauseUnit,
    ClusterMention,
    Entity,
    EntityCandidate,
    ParsedWord,
    ResolvedEntity,
    SentenceFragment,
    TemporalExpression,
)


def test_cluster_for_mention_does_not_fallback_when_exact_span_is_present() -> None:
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
        resolved_entities=[
            ResolvedEntity(
                entity_id=EntityID("cluster-person"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
                mentions=[person_mention],
            ),
            ResolvedEntity(
                entity_id=EntityID("cluster-org"),
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

    cluster = ExtractionContext.build(document).cluster_for_mention(clause_mention)

    assert cluster is None


def test_cluster_for_mention_uses_unique_text_fallback_for_anchorless_mentions() -> None:
    person_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=10,
        end_char=22,
        entity_id=EntityID("entity-person"),
    )
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="",
        paragraphs=[],
        resolved_entities=[
            ResolvedEntity(
                entity_id=EntityID("cluster-person"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
                mentions=[person_mention],
            )
        ],
    )
    anchorless_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=0,
        entity_id=EntityID("entity-person"),
    )

    cluster = ExtractionContext.build(document).cluster_for_mention(anchorless_mention)

    assert cluster is not None
    assert cluster.entity_id == ClusterID("cluster-person")


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
        resolved_entities=[
            ResolvedEntity(
                entity_id=EntityID("far"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Fundusz",
                normalized_name="fundusz",
                mentions=[far],
            ),
            ResolvedEntity(
                entity_id=EntityID("near"),
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

    assert [cluster.entity_id for cluster in clusters] == [ClusterID("near"), ClusterID("far")]


def test_extraction_context_precomputes_entity_cluster_sentence_and_paragraph_indexes() -> None:
    person_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=1,
        paragraph_index=1,
        start_char=20,
        end_char=32,
        entity_id=EntityID("entity-person"),
    )
    org_mention = ClusterMention(
        text="Urząd Miasta",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        sentence_index=2,
        paragraph_index=1,
        start_char=45,
        end_char=57,
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
        entities=[
            Entity(
                entity_id=EntityID("entity-person"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
            )
        ],
        resolved_entities=[
            ResolvedEntity(
                entity_id=EntityID("cluster-person"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
                mentions=[person_mention],
            ),
            ResolvedEntity(
                entity_id=EntityID("cluster-org"),
                entity_type=EntityType.PUBLIC_INSTITUTION,
                canonical_name="Urząd Miasta",
                normalized_name="urząd miasta",
                mentions=[org_mention],
            ),
        ],
    )
    context = ExtractionContext.build(document)

    mention_cluster = context.cluster_for_mention(person_mention)
    id_cluster = context.cluster_by_id(ClusterID("cluster-person"))
    entity = context.entity_by_id(EntityID("entity-person"))
    entity_cluster = context.cluster_by_entity_id(EntityID("entity-person"))

    assert mention_cluster is not None
    assert id_cluster is not None
    assert entity is not None
    assert entity_cluster is not None
    assert mention_cluster.entity_id == ClusterID("cluster-person")
    assert id_cluster.canonical_name == "Jan Kowalski"
    assert entity.canonical_name == "Jan Kowalski"
    assert entity_cluster.entity_id == ClusterID("cluster-person")
    sentence_cluster_ids = [
        cluster.entity_id for cluster in context.clusters_in_sentence(1, {EntityType.PERSON})
    ]
    assert sentence_cluster_ids == [ClusterID("cluster-person")]
    clause = ClauseUnit(
        clause_id=ClauseID("clause"),
        text="",
        trigger_head_text="",
        trigger_head_lemma="",
        sentence_index=2,
        paragraph_index=1,
        start_char=42,
        end_char=70,
    )
    assert [
        cluster.entity_id
        for cluster in context.paragraph_context_clusters(
            clause,
            {EntityType.PERSON, EntityType.PUBLIC_INSTITUTION},
        )
    ] == [ClusterID("cluster-org"), ClusterID("cluster-person")]


def test_fact_context_indexes_sentence_paragraph_and_previous_sentence_candidates() -> None:
    first = EntityCandidate(
        candidate_id=CandidateID("candidate-first"),
        entity_id=EntityID("person-1"),
        candidate_type=CandidateType.PERSON,
        canonical_name="Jan Kowalski",
        normalized_name="jan kowalski",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=12,
        source="mention",
    )
    second = EntityCandidate(
        candidate_id=CandidateID("candidate-second"),
        entity_id=EntityID("org-1"),
        candidate_type=CandidateType.PUBLIC_INSTITUTION,
        canonical_name="Urząd",
        normalized_name="urząd",
        sentence_index=1,
        paragraph_index=0,
        start_char=20,
        end_char=25,
        source="mention",
    )
    other_paragraph = EntityCandidate(
        candidate_id=CandidateID("candidate-other"),
        entity_id=EntityID("person-2"),
        candidate_type=CandidateType.PERSON,
        canonical_name="Anna Nowak",
        normalized_name="anna nowak",
        sentence_index=0,
        paragraph_index=1,
        start_char=0,
        end_char=10,
        source="mention",
    )
    context = FactExtractionContext.build(
        CandidateGraph(candidates=[first, second, other_paragraph])
    )

    assert context.sentence_candidates(0) == [first, other_paragraph]
    assert context.paragraph_candidates(0) == [first, second]
    assert context.previous_sentence_candidates(paragraph_index=0, sentence_index=1) == [first]


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


def test_sentence_context_time_scope_anchors_former_from_past_temporal_expression() -> None:
    """A sentence whose text gives no FORMER signal but contains a dated temporal
    expression older than the publication date should be tagged FORMER."""
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date="2024-06-01",
        cleaned_text="",
        paragraphs=[],
        temporal_expressions=[
            TemporalExpression(
                text="15 marca 2023",
                label=NERLabel.DATE,
                normalized_value="2023-03-15",
                sentence_index=0,
                paragraph_index=0,
                start_char=14,
                end_char=27,
            )
        ],
        sentences=[
            SentenceFragment(
                text="Powołano go 15 marca 2023 na stanowisko prezesa.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=47,
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

    assert context.time_scope.value == "former"


def test_sentence_context_time_scope_anchors_future_from_future_temporal_expression() -> None:
    """A sentence with a future temporal expression (after publication date) should
    be tagged FUTURE even without morphological future-tense markers."""
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date="2024-06-01",
        cleaned_text="",
        paragraphs=[],
        temporal_expressions=[
            TemporalExpression(
                text="1 września 2025",
                label=NERLabel.DATE,
                normalized_value="2025-09-01",
                sentence_index=0,
                paragraph_index=0,
                start_char=17,
                end_char=32,
            )
        ],
        sentences=[
            SentenceFragment(
                text="Objęcie funkcji nastąpi 1 września 2025.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=39,
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

    assert context.time_scope.value == "future"
