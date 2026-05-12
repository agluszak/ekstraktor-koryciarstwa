from pipeline.domain_types import (
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FactID,
    FactType,
    IdentityHypothesisReason,
    IdentityHypothesisStatus,
    KinshipDetail,
    RelationshipType,
    TimeScope,
)
from pipeline.domains.kinship import KinshipTieBuilder
from pipeline.extraction_context import ExtractionContext
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    Fact,
    IdentityHypothesis,
    ParsedWord,
    SentenceFragment,
)


def _cluster(
    cluster_id: str,
    mentions: list[ClusterMention],
    *,
    primary_entity_id: EntityID | None = None,
    member_entity_ids: list[EntityID] | None = None,
) -> EntityCluster:
    resolved_primary = primary_entity_id or next(
        (mention.entity_id for mention in mentions if mention.entity_id is not None),
        None,
    )
    resolved_members = member_entity_ids
    if resolved_members is None:
        resolved_members = []
        if resolved_primary is not None:
            resolved_members.append(resolved_primary)
        for mention in mentions:
            if mention.entity_id is not None and mention.entity_id not in resolved_members:
                resolved_members.append(mention.entity_id)
    return EntityCluster(
        cluster_id=ClusterID(cluster_id),
        mentions=mentions,
        primary_entity_id=resolved_primary,
        member_entity_ids=resolved_members,
    )


def test_kinship_apposition_emits_spouse_tie() -> None:
    sentence_text = (
        "Marszałek powołał Sylwię Sobolewską, żonę byłego sekretarza Krzysztofa Sobolewskiego."
    )
    sentence = SentenceFragment(
        text=sentence_text,
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len(sentence_text),
    )
    sylwia_start = sentence_text.index("Sylwię")
    krzysztof_start = sentence_text.index("Krzysztofa")
    kinship_start = sentence_text.index("żonę")
    former_start = sentence_text.index("byłego")
    secretary_start = sentence_text.index("sekretarza")
    doc = ArticleDocument(
        document_id=DocumentID("doc-kinship"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-22",
        cleaned_text=sentence_text,
        paragraphs=[sentence_text],
        sentences=[sentence],
        parsed_sentences={
            0: [
                ParsedWord(1, "Marszałek", "marszałek", "NOUN", 2, "nsubj", 0, 9),
                ParsedWord(2, "powołał", "powołać", "VERB", 0, "root", 10, 17),
                ParsedWord(
                    3,
                    "Sylwię",
                    "Sylwia",
                    "PROPN",
                    2,
                    "obj",
                    sylwia_start,
                    sylwia_start + 6,
                ),
                ParsedWord(
                    4,
                    "Sobolewską",
                    "Sobolewska",
                    "PROPN",
                    3,
                    "flat",
                    sylwia_start + 7,
                    sylwia_start + 17,
                ),
                ParsedWord(5, "żonę", "żona", "NOUN", 3, "appos", kinship_start, kinship_start + 4),
                ParsedWord(6, "byłego", "były", "ADJ", 7, "amod", former_start, former_start + 6),
                ParsedWord(
                    7,
                    "sekretarza",
                    "sekretarz",
                    "NOUN",
                    5,
                    "nmod",
                    secretary_start,
                    secretary_start + 10,
                ),
                ParsedWord(
                    8,
                    "Krzysztofa",
                    "Krzysztof",
                    "PROPN",
                    7,
                    "flat",
                    krzysztof_start,
                    krzysztof_start + 10,
                ),
                ParsedWord(
                    9,
                    "Sobolewskiego",
                    "Sobolewski",
                    "PROPN",
                    8,
                    "flat",
                    krzysztof_start + 11,
                    krzysztof_start + 23,
                ),
            ]
        },
        clusters=[
            _cluster(
                "cluster-sylwia",
                [
                    ClusterMention(
                        text="Sylwię Sobolewską",
                        entity_id=EntityID("person-sylwia"),
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=sylwia_start,
                        end_char=sylwia_start + len("Sylwię Sobolewską"),
                    )
                ],
            ),
            _cluster(
                "cluster-krzysztof",
                [
                    ClusterMention(
                        text="Krzysztofa Sobolewskiego",
                        entity_id=EntityID("person-krzysztof"),
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=krzysztof_start,
                        end_char=krzysztof_start + len("Krzysztofa Sobolewskiego"),
                    )
                ],
            ),
        ],
    )

    facts = KinshipTieBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
    assert facts[0].subject_entity_id == "person-sylwia"
    assert facts[0].object_entity_id == "person-krzysztof"
    assert facts[0].kinship_detail == KinshipDetail.SPOUSE
    assert facts[0].relationship_type == "family"


def test_kinship_apposition_handles_sparse_dependency_indices() -> None:
    sentence_text = (
        "Marszałek powołał Sylwię Sobolewską, żonę byłego sekretarza Krzysztofa Sobolewskiego."
    )
    sentence = SentenceFragment(
        text=sentence_text,
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len(sentence_text),
    )
    sylwia_start = sentence_text.index("Sylwię")
    krzysztof_start = sentence_text.index("Krzysztofa")
    kinship_start = sentence_text.index("żonę")
    former_start = sentence_text.index("byłego")
    secretary_start = sentence_text.index("sekretarza")
    doc = ArticleDocument(
        document_id=DocumentID("doc-kinship-sparse-indices"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-22",
        cleaned_text=sentence_text,
        paragraphs=[sentence_text],
        sentences=[sentence],
        parsed_sentences={
            0: [
                ParsedWord(11, "Marszałek", "marszałek", "NOUN", 12, "nsubj", 0, 9),
                ParsedWord(12, "powołał", "powołać", "VERB", 0, "root", 10, 17),
                ParsedWord(
                    13,
                    "Sylwię",
                    "Sylwia",
                    "PROPN",
                    12,
                    "obj",
                    sylwia_start,
                    sylwia_start + 6,
                ),
                ParsedWord(
                    14,
                    "Sobolewską",
                    "Sobolewska",
                    "PROPN",
                    13,
                    "flat",
                    sylwia_start + 7,
                    sylwia_start + 17,
                ),
                ParsedWord(
                    15,
                    "żonę",
                    "żona",
                    "NOUN",
                    13,
                    "appos",
                    kinship_start,
                    kinship_start + 4,
                ),
                ParsedWord(16, "byłego", "były", "ADJ", 17, "amod", former_start, former_start + 6),
                ParsedWord(
                    17,
                    "sekretarza",
                    "sekretarz",
                    "NOUN",
                    15,
                    "nmod",
                    secretary_start,
                    secretary_start + 10,
                ),
                ParsedWord(
                    18,
                    "Krzysztofa",
                    "Krzysztof",
                    "PROPN",
                    17,
                    "flat",
                    krzysztof_start,
                    krzysztof_start + 10,
                ),
                ParsedWord(
                    19,
                    "Sobolewskiego",
                    "Sobolewski",
                    "PROPN",
                    18,
                    "flat",
                    krzysztof_start + 11,
                    krzysztof_start + 23,
                ),
            ]
        },
        clusters=[
            _cluster(
                "cluster-sylwia-sparse",
                [
                    ClusterMention(
                        text="Sylwię Sobolewską",
                        entity_id=EntityID("person-sylwia-sparse"),
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=sylwia_start,
                        end_char=sylwia_start + len("Sylwię Sobolewską"),
                    )
                ],
            ),
            _cluster(
                "cluster-krzysztof-sparse",
                [
                    ClusterMention(
                        text="Krzysztofa Sobolewskiego",
                        entity_id=EntityID("person-krzysztof-sparse"),
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=krzysztof_start,
                        end_char=krzysztof_start + len("Krzysztofa Sobolewskiego"),
                    )
                ],
            ),
        ],
    )

    facts = KinshipTieBuilder().build(doc, ExtractionContext.build(doc))

    assert len(facts) == 1
    assert facts[0].subject_entity_id == "person-sylwia-sparse"
    assert facts[0].object_entity_id == "person-krzysztof-sparse"
    assert facts[0].kinship_detail == KinshipDetail.SPOUSE


def test_kinship_builder_does_not_pair_nearest_previous_people_without_evidence() -> None:
    sentence = SentenceFragment(
        text="Jego żona później zrezygnowała.",
        paragraph_index=0,
        sentence_index=1,
        start_char=36,
        end_char=66,
    )
    doc = ArticleDocument(
        document_id=DocumentID("doc-negative-kinship"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Jan Kowalski spotkał Adama Nowaka. Jego żona później zrezygnowała.",
        paragraphs=["Jan Kowalski spotkał Adama Nowaka. Jego żona później zrezygnowała."],
        sentences=[
            SentenceFragment(
                text="Jan Kowalski spotkał Adama Nowaka.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=34,
            ),
            sentence,
        ],
        parsed_sentences={
            1: [
                ParsedWord(1, "Jego", "jego", "DET", 2, "det:poss", 0, 4),
                ParsedWord(2, "żona", "żona", "NOUN", 4, "nsubj", 5, 9),
                ParsedWord(3, "później", "późno", "ADV", 4, "advmod", 10, 17),
                ParsedWord(4, "zrezygnowała", "zrezygnować", "VERB", 0, "root", 18, 30),
            ]
        },
        clusters=[
            _cluster(
                "cluster-jan",
                [
                    ClusterMention(
                        text="Jan Kowalski",
                        entity_id=EntityID("person-jan"),
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=0,
                        end_char=12,
                    )
                ],
            ),
            _cluster(
                "cluster-adam",
                [
                    ClusterMention(
                        text="Adam Nowak",
                        entity_id=EntityID("person-adam"),
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=21,
                        end_char=32,
                    )
                ],
            ),
        ],
    )

    assert KinshipTieBuilder().build(doc, ExtractionContext.build(doc)) == []


def test_identity_backed_proxy_tie_uses_entity_backed_views_with_stale_cluster_metadata() -> None:
    sentence_text = "Anna Nowak jest opisywana jako możliwa żona Jana Kowalskiego."
    proxy_id = EntityID("entity-proxy-spouse")
    anchor_id = EntityID("entity-jan")
    matched_id = EntityID("entity-anna")
    sentence = SentenceFragment(
        text=sentence_text,
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len(sentence_text),
    )
    evidence = EvidenceSpan(
        text=sentence_text,
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
        end_char=len(sentence_text),
    )
    document = ArticleDocument(
        document_id=DocumentID("doc-identity-backed-proxy-stale-view"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-22",
        cleaned_text=sentence_text,
        paragraphs=[sentence_text],
        sentences=[sentence],
        entities=[
            Entity(
                entity_id=proxy_id,
                entity_type=EntityType.PERSON,
                canonical_name="proxy spouse",
                normalized_name="proxy spouse",
                is_proxy_person=True,
                kinship_detail=KinshipDetail.SPOUSE,
                proxy_anchor_entity_id=anchor_id,
            ),
            Entity(
                entity_id=anchor_id,
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            ),
            Entity(
                entity_id=matched_id,
                entity_type=EntityType.PERSON,
                canonical_name="Anna Nowak",
                normalized_name="Anna Nowak",
            ),
        ],
        clusters=[
            _cluster(
                "cluster-proxy-stale",
                [
                    ClusterMention(
                        text="żona",
                        entity_type=EntityType.POSITION,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=sentence_text.index("żona"),
                        end_char=sentence_text.index("żona") + len("żona"),
                        entity_id=proxy_id,
                    )
                ],
                primary_entity_id=proxy_id,
                member_entity_ids=[proxy_id],
            ),
            _cluster(
                "cluster-jan-stale",
                [
                    ClusterMention(
                        text="Jana Kowalskiego",
                        entity_type=EntityType.POSITION,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=sentence_text.index("Jana"),
                        end_char=sentence_text.index("Jana") + len("Jana Kowalskiego"),
                        entity_id=anchor_id,
                    )
                ],
                primary_entity_id=anchor_id,
                member_entity_ids=[anchor_id],
            ),
            _cluster(
                "cluster-anna-stale",
                [
                    ClusterMention(
                        text="Anna Nowak",
                        entity_type=EntityType.POSITION,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=0,
                        end_char=len("Anna Nowak"),
                        entity_id=matched_id,
                    )
                ],
                primary_entity_id=matched_id,
                member_entity_ids=[matched_id],
            ),
        ],
        facts=[
            Fact(
                fact_id=FactID("fact-proxy-family"),
                fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                subject_entity_id=proxy_id,
                object_entity_id=anchor_id,
                value_text=KinshipDetail.SPOUSE.value,
                value_normalized=KinshipDetail.SPOUSE.value,
                time_scope=TimeScope.CURRENT,
                event_date="2026-04-22",
                confidence=0.8,
                evidence=evidence,
                relationship_type=RelationshipType.FAMILY,
                kinship_detail=KinshipDetail.SPOUSE,
            )
        ],
        identity_hypotheses=[
            IdentityHypothesis(
                left_entity_id=proxy_id,
                right_entity_id=matched_id,
                confidence=0.72,
                reason=IdentityHypothesisReason.SAME_ANCHOR_COMPATIBLE_FAMILY_PROXY,
                evidence=[evidence],
                status=IdentityHypothesisStatus.PROBABLE,
            )
        ],
    )

    facts = KinshipTieBuilder().build(document, ExtractionContext.build(document))

    assert len(facts) == 1
    assert facts[0].subject_entity_id == proxy_id
    assert facts[0].object_entity_id == anchor_id
    assert facts[0].possible_identity_matches == [matched_id]
