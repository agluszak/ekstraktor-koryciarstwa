import spacy

from pipeline.ner import SpacyPolishNERExtractor


def test_bad_person_span_keeps_surface_display_name() -> None:
    nlp = spacy.load("pl_core_news_md")
    doc = nlp("Ruty Zaważyło")
    display_name, _score = SpacyPolishNERExtractor._person_display_name(doc[:])

    assert display_name == "Ruty Zaważyło"


def test_inflected_person_span_uses_lemma_display_name() -> None:
    nlp = spacy.load("pl_core_news_md")
    doc = nlp("Hanny Gronkiewicz-Waltz")
    display_name, _score = SpacyPolishNERExtractor._person_display_name(doc[:])

    assert display_name == "Hanna Gronkiewicz-Waltz"
