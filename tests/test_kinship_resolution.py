from unittest.mock import MagicMock

import pytest

from pipeline.models import ArticleDocument, CandidateGraph, EntityCandidate
from pipeline.relations.fact_extractors import (
    CandidateType,
    GovernanceFactExtractor,
    SentenceContext,
)
from pipeline.relations.types import ParsedWord


@pytest.fixture
def extractor():
    return GovernanceFactExtractor()


def test_kinship_proxy_skips_speaker(extractor):
    # Setup:
    # Current sentence: "- Moja żona zrezygnowała - mówi Dariusz."
    # Speaker: Dariusz
    # Proxy: żona
    # Paragraph: Renata, Dariusz

    dariusz_candidate = EntityCandidate(
        candidate_id="p1",
        entity_id="p1",
        candidate_type=CandidateType.PERSON,
        canonical_name="Dariusz",
        normalized_name="Dariusz",
        sentence_index=0,
        paragraph_index=0,
        start_char=27,  # Start of 'mówi' (approx)
        end_char=39,
        source="text",
        attributes={},
    )

    renata_candidate = EntityCandidate(
        candidate_id="p0",
        entity_id="p0",
        candidate_type=CandidateType.PERSON,
        canonical_name="Renata",
        normalized_name="Renata",
        sentence_index=-1,  # Not in current sentence
        paragraph_index=0,
        start_char=0,
        end_char=6,
        source="text",
        attributes={},
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
    mock_doc.document_id = "test-doc"
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

    from pipeline.relations.fact_extractors import _subject_candidate

    res = _subject_candidate(context)

    # Should resolve to Renata (paragraph person) because Dariusz is identified as the speaker
    assert res is not None
    assert res.canonical_name == "Renata"
    assert res.candidate_id == "p0"
