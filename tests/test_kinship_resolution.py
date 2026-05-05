from pipeline.domain_types import (
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    FactType,
    KinshipDetail,
)
from pipeline.domains.kinship import KinshipTieBuilder
from pipeline.extraction_context import ExtractionContext
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    EntityCluster,
    ParsedWord,
    SentenceFragment,
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
            EntityCluster(
                cluster_id=ClusterID("cluster-sylwia"),
                entity_type=EntityType.PERSON,
                canonical_name="Sylwia Sobolewska",
                normalized_name="sylwia sobolewska",
                mentions=[
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
            EntityCluster(
                cluster_id=ClusterID("cluster-krzysztof"),
                entity_type=EntityType.PERSON,
                canonical_name="Krzysztof Sobolewski",
                normalized_name="krzysztof sobolewski",
                mentions=[
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
            EntityCluster(
                cluster_id=ClusterID("cluster-jan"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
                mentions=[
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
            EntityCluster(
                cluster_id=ClusterID("cluster-adam"),
                entity_type=EntityType.PERSON,
                canonical_name="Adam Nowak",
                normalized_name="adam nowak",
                mentions=[
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
