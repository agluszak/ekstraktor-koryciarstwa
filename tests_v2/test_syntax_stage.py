from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.nlp import ParsedDependencySentence, ParsedDependencyToken
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.syntax import DependencyParseStage


@dataclass(frozen=True, slots=True)
class StaticDependencyProvider:
    parsed: tuple[ParsedDependencySentence, ...]

    def parse(self, text: str) -> tuple[ParsedDependencySentence, ...]:
        _ = text
        return self.parsed


def test_dependency_parse_stage_records_root_and_dependent_arcs() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Jan pracuje.",
        paragraphs=("Jan pracuje.",),
    )
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage().run(document)
    sentence = next(iter(document.store.sentences.values()))
    provider = StaticDependencyProvider(
        (
            ParsedDependencySentence(
                sentence_index=0,
                tokens=(
                    ParsedDependencyToken(
                        token_index=1,
                        text="Jan",
                        lemma="jan",
                        upos="PROPN",
                        head_index=2,
                        relation="nsubj",
                    ),
                    ParsedDependencyToken(
                        token_index=2,
                        text="pracuje",
                        lemma="pracować",
                        upos="VERB",
                        head_index=0,
                        relation="root",
                    ),
                ),
            ),
        )
    )

    DependencyParseStage(provider).run(document)
    arcs = document.store.dependency_arcs_for_sentence(sentence.id)
    tokens = document.store.tokens

    assert tuple(arc.relation for arc in arcs) == ("nsubj", "root")
    assert tokens[arcs[0].dependent_token_id].text == "Jan"
    assert arcs[0].head_token_id is not None
    assert tokens[arcs[0].head_token_id].text == "pracuje"
    assert arcs[1].head_token_id is None
