from __future__ import annotations

from pipeline.config import PipelineConfig
from pipeline.coref import StanzaCoreferenceResolver
from pipeline.domain_types import DocumentID, EntityID, EntityType
from pipeline.models import ArticleDocument, Entity, SentenceFragment


class FakeWord:
    def __init__(self, start_char: int, end_char: int) -> None:
        self.start_char = start_char
        self.end_char = end_char


class FakeSentence:
    def __init__(self, words: list[FakeWord]) -> None:
        self.words = words


class FakeMention:
    def __init__(self, sentence: int, start_word: int, end_word: int) -> None:
        self.sentence = sentence
        self.start_word = start_word
        self.end_word = end_word


class FakeChain:
    def __init__(self, representative_text: str, mentions: list[FakeMention]) -> None:
        self.representative_text = representative_text
        self.mentions = mentions


class FakeCorefDoc:
    def __init__(self, sentences: list[FakeSentence], coref: list[FakeChain]) -> None:
        self.sentences = sentences
        self.coref = coref


def _fake_span(doc: FakeCorefDoc, sentence_index: int, start_word: int, end_word: int) -> slice:
    sentence = doc.sentences[sentence_index]
    start = sentence.words[start_word].start_char
    end = sentence.words[end_word - 1].end_char
    return slice(start, end)


def test_coref_resolved_mentions_preserve_exact_offsets(monkeypatch) -> None:
    config = PipelineConfig.from_file("config.yaml")
    cleaned_text = "Jan Kowalski wrócił. Potem on zadzwonił."
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=[cleaned_text],
        sentences=[
            SentenceFragment(
                text="Jan Kowalski wrócił.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=19,
            ),
            SentenceFragment(
                text="Potem on zadzwonił.",
                paragraph_index=0,
                sentence_index=1,
                start_char=21,
                end_char=len(cleaned_text),
            ),
        ],
        entities=[
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="Jan Kowalski",
            )
        ],
    )
    fake_doc = FakeCorefDoc(
        sentences=[
            FakeSentence(words=[FakeWord(0, 3), FakeWord(4, 12), FakeWord(13, 19)]),
            FakeSentence(words=[FakeWord(21, 26), FakeWord(27, 29), FakeWord(30, 40)]),
        ],
        coref=[
            FakeChain(
                representative_text="Jan Kowalski",
                mentions=[FakeMention(sentence=1, start_word=1, end_word=2)],
            )
        ],
    )
    monkeypatch.setattr(
        "pipeline.coref.extract_text",
        lambda doc, sentence_index, start_word, end_word: cleaned_text[
            _fake_span(doc, sentence_index, start_word, end_word)
        ],
    )

    resolver = StanzaCoreferenceResolver(config)
    monkeypatch.setattr(
        resolver.runtime,
        "get_stanza_coref_pipeline",
        lambda: lambda text: fake_doc,
    )
    monkeypatch.setattr(resolver.runtime, "reset_stanza_coref_pipeline", lambda: None)

    document = resolver.run(document)

    assert len(document.mentions) == 1
    m = document.mentions[0]
    assert m.text == "on"
    assert m.start_char == 27
    assert m.end_char == 29
    assert m.entity_id == "person-1"
    assert m.mention_type == "ResolvedPersonReference"
