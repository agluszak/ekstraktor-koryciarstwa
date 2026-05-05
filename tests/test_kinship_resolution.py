from unittest.mock import MagicMock

from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    DocumentID,
    EntityID,
    FactType,
    KinshipDetail,
)
from pipeline.domains.kinship import KinshipTieBuilder
from pipeline.extraction_context import ExtractionContext, FactExtractionContext, SentenceContext
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    EntityCandidate,
    ParsedWord,
    SentenceFragment,
)


def test_kinship_proxy_skips_speaker() -> None:
    # Setup:
    # Current sentence: "- Moja żona zrezygnowała - mówi Dariusz."
    # Speaker: Dariusz
    # Proxy: żona
    # Paragraph: Renata, Dariusz

    dariusz_candidate = EntityCandidate(
        candidate_id=CandidateID("p1"),
        entity_id=EntityID("p1"),
        candidate_type=CandidateType.PERSON,
        canonical_name="Dariusz",
        normalized_name="Dariusz",
        sentence_index=0,
        paragraph_index=0,
        start_char=27,  # Start of 'mówi' (approx)
        end_char=39,
        source="text",
    )

    renata_candidate = EntityCandidate(
        candidate_id=CandidateID("p0"),
        entity_id=EntityID("p0"),
        candidate_type=CandidateType.PERSON,
        canonical_name="Renata",
        normalized_name="Renata",
        sentence_index=-1,  # Not in current sentence
        paragraph_index=0,
        start_char=0,
        end_char=6,
        source="text",
    )

    # Words according to ParsedWord(index, text, lemma, upos, head, deprel, start, end)
    words = [
        ParsedWord(1, "-", "-", "PUNCT", 6, "punct", 0, 1),
        ParsedWord(2, "Moja", "mój", "DET", 3, "det:poss", 2, 6),
        ParsedWord(3, "żona", "żona", "NOUN", 4, "nsubj", 7, 11),
        ParsedWord(4, "zrezygnowała", "zrezygnować", "VERB", 6, "parataxis:obj", 12, 24),
        ParsedWord(5, "-", "-", "PUNCT", 6, "punct", 25, 26),
        ParsedWord(6, "mówi", "mówić", "VERB", 0, "root", 27, 31),
        ParsedWord(7, "Dariusz", "Dariusz", "PROPN", 6, "nsubj", 32, 39),
    ]

    mock_doc = MagicMock(spec=ArticleDocument)
    mock_doc.document_id = DocumentID("test-doc")
    mock_sentence = MagicMock()
    mock_sentence.text = "- Moja żona zrezygnowała - mówi Dariusz."
    mock_graph = MagicMock(spec=CandidateGraph)

    context = SentenceContext(
        document=mock_doc,
        sentence=mock_sentence,
        parsed_words=words,
        graph=mock_graph,
        candidates=[dariusz_candidate],
        paragraph_candidates=[renata_candidate, dariusz_candidate],
        previous_candidates=[],
    )

    from pipeline.domains.secondary_facts import _subject_candidate

    res = _subject_candidate(context)

    # Should resolve to Renata (paragraph person) because Dariusz is identified as the speaker
    assert res is not None
    assert res.canonical_name == "Renata"
    assert res.candidate_id == "p0"


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
    )
    graph = CandidateGraph(
        candidates=[
            EntityCandidate(
                candidate_id=CandidateID("candidate-sylwia"),
                entity_id=EntityID("person-sylwia"),
                candidate_type=CandidateType.PERSON,
                canonical_name="Sylwia Sobolewska",
                normalized_name="Sylwia Sobolewska",
                sentence_index=0,
                paragraph_index=0,
                start_char=sylwia_start,
                end_char=sylwia_start + len("Sylwię Sobolewską"),
                source="mention",
            ),
            EntityCandidate(
                candidate_id=CandidateID("candidate-krzysztof"),
                entity_id=EntityID("person-krzysztof"),
                candidate_type=CandidateType.PERSON,
                canonical_name="Krzysztof Sobolewski",
                normalized_name="Krzysztof Sobolewski",
                sentence_index=0,
                paragraph_index=0,
                start_char=krzysztof_start,
                end_char=krzysztof_start + len("Krzysztofa Sobolewskiego"),
                source="mention",
            ),
        ]
    )

    facts = KinshipTieBuilder().build(
        doc,
        ExtractionContext.build(doc),
        FactExtractionContext.build(graph),
    )

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
    )
    graph = CandidateGraph(
        candidates=[
            EntityCandidate(
                candidate_id=CandidateID("candidate-jan"),
                entity_id=EntityID("person-jan"),
                candidate_type=CandidateType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=12,
                source="mention",
            ),
            EntityCandidate(
                candidate_id=CandidateID("candidate-adam"),
                entity_id=EntityID("person-adam"),
                candidate_type=CandidateType.PERSON,
                canonical_name="Adam Nowak",
                normalized_name="Adam Nowak",
                sentence_index=0,
                paragraph_index=0,
                start_char=21,
                end_char=32,
                source="mention",
            ),
        ]
    )

    assert (
        KinshipTieBuilder().build(
            doc,
            ExtractionContext.build(doc),
            FactExtractionContext.build(graph),
        )
        == []
    )
