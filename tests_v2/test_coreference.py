from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from pipeline_v2.coreference import CoreferenceReferenceStage, LightReferenceStage
from pipeline_v2.coreference_provider import StanzaCoreferenceProvider
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import CoreferenceSpanLink, Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.types import NerLabel, ReferenceKind
from tests_v2.helpers import StaticEntityProvider, setup_base_test_document


@dataclass(frozen=True, slots=True)
class StaticCoreferenceProvider:
    coreference_links: tuple[CoreferenceSpanLink, ...]

    def links(self, text: str) -> tuple[CoreferenceSpanLink, ...]:
        _ = text
        return self.coreference_links


def test_coreference_stage_proposes_reference_resolution_without_merging_entities() -> None:
    cleaned_text = "Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie."
    document = setup_base_test_document(cleaned_text)
    morphology = Morfeusz2MorphologyAdapter()
    antecedent_start = cleaned_text.index("Jan Kowalski")
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Jan Kowalski",
                    label=NerLabel.PERSON,
                    span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                ),
            )
        ),
        morphology=morphology,
    ).run(document)
    reference_start = cleaned_text.index("Jego")

    CoreferenceReferenceStage(
        provider=StaticCoreferenceProvider(
            (
                CoreferenceSpanLink(
                    antecedent_text="Jan Kowalski",
                    antecedent_span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                    reference_text="Jego",
                    reference_span=Span(reference_start, reference_start + len("Jego")),
                    reference_kind=ReferenceKind.POSSESSIVE_PRONOUN,
                ),
            )
        ),
        morphology=morphology,
    ).run(document)
    ProbabilisticInferenceStage().run(document)

    assert tuple(
        candidate.canonical_hint for candidate in document.store.entity_candidates.values()
    ) == ("Jan Kowalski",)
    assert tuple(reference.kind for reference in document.store.references.values()) == (
        ReferenceKind.POSSESSIVE_PRONOUN,
    )
    claims = tuple(document.store.reference_resolution_claims.values())
    assert len(claims) == 1
    assert claims[0].assessment.score >= 0.7


def test_light_reference_stage_emits_pronoun_reference_candidates_without_merging() -> None:
    cleaned_text = "Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie."
    document = setup_base_test_document(cleaned_text)
    morphology = Morfeusz2MorphologyAdapter()
    antecedent_start = cleaned_text.index("Jan Kowalski")
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(
            (
                NamedEntitySpan(
                    text="Jan Kowalski",
                    label=NerLabel.PERSON,
                    span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
                ),
            )
        ),
        morphology=morphology,
    ).run(document)

    LightReferenceStage().run(document)
    ProbabilisticInferenceStage().run(document)

    assert tuple(reference.text for reference in document.store.references.values()) == ("Jego",)
    assert tuple(
        candidate.canonical_hint for candidate in document.store.entity_candidates.values()
    ) == ("Jan Kowalski",)
    claims = tuple(document.store.reference_resolution_claims.values())
    assert len(claims) == 1
    assert claims[0].assessment.score >= 0.5


class MockWord:
    def __init__(self, text: str, start_char: int, end_char: int) -> None:
        self.text = text
        self.start_char = start_char
        self.end_char = end_char


class MockSentence:
    def __init__(self, words: list[MockWord]) -> None:
        self.words = words


class MockMention:
    def __init__(self, sentence: int, start_word: int, end_word: int) -> None:
        self.sentence = sentence
        self.start_word = start_word
        self.end_word = end_word


class MockChain:
    def __init__(self, representative_text: str, mentions: list[MockMention]) -> None:
        self.representative_text = representative_text
        self.mentions = mentions


class MockDocument:
    def __init__(self, sentences: list[MockSentence], coref: list[MockChain]) -> None:
        self.sentences = sentences
        self.coref = coref


@patch("stanza.Pipeline")
@patch("pipeline_v2.coreference_provider.extract_text")
def test_stanza_coreference_provider_links_and_filtering(
    mock_extract_text, mock_pipeline_class
) -> None:
    mock_nlp = MagicMock()
    mock_pipeline_class.return_value = mock_nlp

    # Sentence 0: "Jan Kowalski został burmistrzem."
    w1_1 = MockWord("Jan", 0, 3)
    w1_2 = MockWord("Kowalski", 4, 12)
    s0 = MockSentence([w1_1, w1_2])

    # Sentence 1: "Jego żona pracuje w urzędzie."
    w2_1 = MockWord("Jego", 33, 37)
    s1 = MockSentence([w2_1])

    # Sentence 2: "Ta spółka jest duża."
    w3_1 = MockWord("Ta", 50, 52)
    w3_2 = MockWord("spółka", 53, 59)
    s2 = MockSentence([w3_1, w3_2])

    # Chain 0: Jan Kowalski -> Jego
    m0_1 = MockMention(0, 0, 2)
    m0_2 = MockMention(1, 0, 1)
    chain0 = MockChain("Jan Kowalski", [m0_1, m0_2])

    # Chain 1: spółka -> Ta spółka (representative text "spółka" is a generic noun)
    m1_1 = MockMention(2, 0, 2)
    chain1 = MockChain("spółka", [m1_1])

    mock_doc = MockDocument([s0, s1, s2], [chain0, chain1])
    mock_nlp.return_value = mock_doc

    mock_extract_text.side_effect = lambda doc, sent, start, end: {
        (0, 0, 2): "Jan Kowalski",
        (1, 0, 1): "Jego",
        (2, 0, 2): "Ta spółka",
    }.get((sent, start, end), "")

    provider = StanzaCoreferenceProvider(model_path="dummy")
    links = provider.links("dummy text")

    # Verify that only Jan Kowalski -> Jego link is returned, and "spółka" chain is filtered out
    assert len(links) == 1
    link = links[0]
    assert link.antecedent_text == "Jan Kowalski"
    assert link.antecedent_span == Span(0, 12)
    assert link.reference_text == "Jego"
    assert link.reference_span == Span(33, 37)
    assert link.reference_kind == ReferenceKind.POSSESSIVE_PRONOUN
