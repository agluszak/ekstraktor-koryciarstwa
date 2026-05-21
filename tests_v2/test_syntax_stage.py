from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId, EntityCandidateId, EvidenceId, MentionId, ProducerId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.nlp import (
    EvidenceSpan,
    Mention,
    ParsedDependencySentence,
    ParsedDependencyToken,
    Span,
)
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.syntax import DependencyParseStage
from pipeline_v2.syntax_view import SyntaxView
from pipeline_v2.types import (
    DependencyRelation,
    EntityKind,
    GroundingKind,
    MentionKind,
    SyntaxRelationClass,
)


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
                        relation=DependencyRelation.NSUBJ,
                    ),
                    ParsedDependencyToken(
                        token_index=2,
                        text="pracuje",
                        lemma="pracować",
                        upos="VERB",
                        head_index=0,
                        relation=DependencyRelation.ROOT,
                    ),
                ),
            ),
        )
    )

    DependencyParseStage(provider).run(document)
    arcs = document.store.dependency_arcs_for_sentence(sentence.id)
    tokens = document.store.tokens

    assert tuple(arc.relation for arc in arcs) == (
        DependencyRelation.NSUBJ,
        DependencyRelation.ROOT,
    )
    assert tokens[arcs[0].dependent_token_id].text == "Jan"
    assert arcs[0].head_token_id is not None
    assert tokens[arcs[0].head_token_id].text == "pracuje"
    assert arcs[1].head_token_id is None


def test_syntax_view_returns_typed_subject_binding() -> None:
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
                        relation=DependencyRelation.NSUBJ,
                    ),
                    ParsedDependencyToken(
                        token_index=2,
                        text="pracuje",
                        lemma="pracować",
                        upos="VERB",
                        head_index=0,
                        relation=DependencyRelation.ROOT,
                    ),
                ),
            ),
        )
    )
    DependencyParseStage(provider).run(document)
    token_ids = sentence.token_ids
    evidence = EvidenceSpan(
        id=EvidenceId("evidence-1"),
        text="Jan",
        span=Span(0, 3),
        sentence_id=sentence.id,
        paragraph_index=0,
        source=ProducerId("test"),
    )
    document.store.add_evidence(evidence)
    document.store.add_mention(
        Mention(
            id=MentionId("mention-1"),
            text="Jan",
            kind=MentionKind.NER,
            evidence_id=evidence.id,
            sentence_id=sentence.id,
            token_ids=(token_ids[0],),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("entity-1"),
            kind=EntityKind.PERSON,
            mention_ids=(MentionId("mention-1"),),
            canonical_hint="Jan",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    binding = SyntaxView(document.store).syntax_binding(
        sentence=sentence,
        trigger_token_id=token_ids[1],
        entity_id=EntityCandidateId("entity-1"),
    )

    assert binding is not None
    assert binding.relation is DependencyRelation.NSUBJ
    assert binding.relation_class is SyntaxRelationClass.SUBJECT
