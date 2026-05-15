from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter


def test_morphology_stage_populates_tokens_with_spans_and_lemmas() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Krzysztof Staruch rozmawiał ze Staruchem.",
        paragraphs=("Krzysztof Staruch rozmawiał ze Staruchem.",),
    )
    ParagraphSentenceSegmenter().run(document)

    MorfeuszMorphologyStage().run(document)
    sentence = next(iter(document.store.sentences.values()))
    tokens = tuple(document.store.tokens[token_id] for token_id in sentence.token_ids)
    surname_token = tokens[-2]

    assert tuple(token.text for token in tokens) == (
        "Krzysztof",
        "Staruch",
        "rozmawiał",
        "ze",
        "Staruchem",
        ".",
    )
    assert document.cleaned_text[surname_token.span.start_char : surname_token.span.end_char] == (
        "Staruchem"
    )
    assert any(
        analysis.lemma == "staruch" and "nazwisko" in analysis.labels
        for analysis in surname_token.morph
    )
