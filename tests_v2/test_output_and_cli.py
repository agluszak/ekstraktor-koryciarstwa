from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from pipeline_v2.candidates import (
    Assessment,
    EntityCandidate,
    EntityFactArgument,
    FactCandidateRecord,
    MaterializedFactAlternative,
)
from pipeline_v2.cli import main
from pipeline_v2.document import (
    ArticleDocument,
    FactAssessment,
    PipelineInput,
    RelevanceDecision,
    StageDiagnostic,
    StageDiagnosticStatus,
)
from pipeline_v2.ids import (
    DocumentId,
    EntityCandidateId,
    EvidenceId,
    FactCandidateId,
    InferenceStateId,
    InferenceVariableId,
    MentionId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
    SentenceId,
    TokenId,
)
from pipeline_v2.inference.graph_spec import InferenceDiagnostic, StateProbability, VariableMarginal
from pipeline_v2.nlp import EvidenceSpan, Mention, MorphAnalysis, Sentence, Span, Token
from pipeline_v2.output import document_to_json, document_to_slim_json
from pipeline_v2.types import (
    DependencyObjectSignal,
    DependencyRelation,
    EntityKind,
    FactArgumentRole,
    FactKind,
    GroundingKind,
    MentionKind,
    PublicMoneyRelevanceSignal,
    ResolutionRelation,
)


def test_document_output_includes_evidence_and_materialized_facts() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url="https://example.test",
        title="Title",
        publication_date="2026-05-15",
        cleaned_text="Text.",
        paragraphs=("Text.",),
        relevance=RelevanceDecision(
            is_relevant=True,
            score=0.8,
            reasons=(PublicMoneyRelevanceSignal(),),
        ),
    )
    document.store.add_sentence(
        Sentence(
            id=SentenceId("sentence-1"),
            sentence_index=0,
            paragraph_index=0,
            text="Text.",
            span=Span(0, 5),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("evidence-1"),
            text="Text",
            span=Span(0, 4),
            sentence_id=SentenceId("sentence-1"),
            paragraph_index=0,
            source=ProducerId("test"),
        )
    )
    document.fact_assessments.append(
        FactAssessment(
            materialized_fact_id=FactCandidateId("materialized-under-test"),
            assessment=Assessment(
                score=0.75,
                positive_signals=(),
                negative_signals=(),
                scorer_id=ScorerId("test_scorer"),
            ),
        )
    )
    document.stage_diagnostics.append(
        StageDiagnostic(
            stage_name="coreference_stage_v2",
            status=StageDiagnosticStatus.SKIPPED,
            reason="disabled by config",
        )
    )
    document.inference_marginals.append(
        VariableMarginal(
            variable_id=InferenceVariableId("variable-under-test"),
            probabilities=(
                StateProbability(InferenceStateId("false"), 0.25),
                StateProbability(InferenceStateId("true"), 0.75),
            ),
        )
    )
    document.inference_diagnostics.append(
        InferenceDiagnostic(message="pgmpy belief propagation completed")
    )

    rendered = document_to_json(document)

    assert rendered["document_id"] == "doc"
    assert rendered["relevance"] == {
        "is_relevant": True,
        "score": 0.8,
        "reasons": [
            {
                "name": "public-money context",
                "polarity": "positive",
                "weight": None,
            }
        ],
    }
    assert rendered["evidence"] == [
        {
            "id": "evidence-1",
            "text": "Text",
            "span": {"start_char": 0, "end_char": 4},
            "sentence_id": "sentence-1",
            "paragraph_index": 0,
            "source": "test",
            "scope": None,
        }
    ]
    assert rendered["stage_diagnostics"] == [
        {
            "stage_name": "coreference_stage_v2",
            "status": "skipped",
            "reason": "disabled by config",
        }
    ]
    assert rendered["materialized_fact_assessments"] == [
        {
            "materialized_fact_id": "materialized-under-test",
            "assessment": {
                "score": 0.75,
                "positive_signals": [],
                "negative_signals": [],
                "scorer_id": "test_scorer",
                "explanation": None,
            },
        }
    ]
    assert rendered["inference_marginals"] == [
        {
            "variable_id": "variable-under-test",
            "probabilities": [
                {"state_id": "false", "probability": 0.25},
                {"state_id": "true", "probability": 0.75},
            ],
        }
    ]
    assert rendered["inference_diagnostics"] == [{"message": "pgmpy belief propagation completed"}]


def test_document_output_serializes_signal_details_as_structured_json() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    document.fact_assessments.append(
        FactAssessment(
            materialized_fact_id=FactCandidateId("materialized-under-test"),
            assessment=Assessment(
                score=0.75,
                positive_signals=(DependencyObjectSignal(relation=DependencyRelation.OBJ),),
                negative_signals=(),
                scorer_id=ScorerId("test_scorer"),
            ),
        )
    )

    rendered = document_to_json(document)

    assert rendered["materialized_fact_assessments"] == [
        {
            "materialized_fact_id": "materialized-under-test",
            "assessment": {
                "score": 0.75,
                "positive_signals": [
                    {
                        "name": "dependency_object",
                        "polarity": "positive",
                        "weight": None,
                        "details": {"relation": "obj"},
                    }
                ],
                "negative_signals": [],
                "scorer_id": "test_scorer",
                "explanation": None,
            },
        }
    ]


def test_slim_output_normalizes_role_entities_to_lemmas() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Został prezesem.",
        paragraphs=("Został prezesem.",),
    )
    sentence_id = SentenceId("sentence-1")
    evidence_id = EvidenceId("evidence-1")
    token_id = TokenId("token-1")
    mention_id = MentionId("mention-1")
    role_id = EntityCandidateId("role-1")
    document.store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=0,
            paragraph_index=0,
            text="Został prezesem.",
            span=Span(0, 16),
            token_ids=(token_id,),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text="prezesem",
            span=Span(7, 15),
            sentence_id=sentence_id,
            paragraph_index=0,
            source=ProducerId("test"),
        )
    )
    document.store.add_token(
        Token(
            id=token_id,
            sentence_id=sentence_id,
            text="prezesem",
            span=Span(7, 15),
            morph=(MorphAnalysis(lemma="prezes", pos="subst"),),
        )
    )
    document.store.add_mention(
        Mention(
            id=mention_id,
            text="prezesem",
            kind=MentionKind.NER,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
            token_ids=(token_id,),
            head_lemma="prezes",
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=role_id,
            kind=EntityKind.ROLE,
            mention_ids=(mention_id,),
            canonical_hint="prezesem",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.materialized_fact_records.append(
        FactCandidateRecord(
            id=FactCandidateId("fact-1"),
            kind=FactKind.PUBLIC_ROLE_HOLDING,
            arguments=(EntityFactArgument(role=FactArgumentRole.ROLE, entity_id=role_id),),
            evidence_ids=(evidence_id,),
            source=ProducerId("test"),
        )
    )

    rendered = document_to_slim_json(document)

    assert rendered["facts"] == [{"kind": "public_role_holding", "role": "prezes"}]


def test_slim_output_dedupes_role_variants_by_normalized_content() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Był prezesem i później prezesowi zarzucono...",
        paragraphs=("Był prezesem i później prezesowi zarzucono...",),
    )
    sentence_id = SentenceId("sentence-1")
    document.store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=0,
            paragraph_index=0,
            text="Był prezesem i później prezesowi zarzucono...",
            span=Span(0, 43),
            token_ids=(TokenId("token-1"), TokenId("token-2")),
        )
    )
    role_specs = (
        ("1", "prezesem", Span(4, 12), 0.61),
        ("2", "prezesowi", Span(23, 32), 0.74),
    )
    for suffix, text, span, score in role_specs:
        evidence_id = EvidenceId(f"evidence-{suffix}")
        token_id = TokenId(f"token-{suffix}")
        mention_id = MentionId(f"mention-{suffix}")
        role_id = EntityCandidateId(f"role-{suffix}")
        document.store.add_evidence(
            EvidenceSpan(
                id=evidence_id,
                text=text,
                span=span,
                sentence_id=sentence_id,
                paragraph_index=0,
                source=ProducerId("test"),
            )
        )
        document.store.add_token(
            Token(
                id=token_id,
                sentence_id=sentence_id,
                text=text,
                span=span,
                morph=(MorphAnalysis(lemma="prezes", pos="subst"),),
            )
        )
        document.store.add_mention(
            Mention(
                id=mention_id,
                text=text,
                kind=MentionKind.NER,
                evidence_id=evidence_id,
                sentence_id=sentence_id,
                token_ids=(token_id,),
                head_lemma="prezes",
            )
        )
        document.store.add_entity_candidate(
            EntityCandidate(
                id=role_id,
                kind=EntityKind.ROLE,
                mention_ids=(mention_id,),
                canonical_hint=text,
                grounding=GroundingKind.OBSERVED,
                source=ProducerId("test"),
            )
        )
        fact_id = FactCandidateId(f"fact-{suffix}")
        document.materialized_fact_records.append(
            FactCandidateRecord(
                id=fact_id,
                kind=FactKind.PUBLIC_ROLE_HOLDING,
                arguments=(EntityFactArgument(role=FactArgumentRole.ROLE, entity_id=role_id),),
                evidence_ids=(evidence_id,),
                source=ProducerId("test"),
            )
        )
        document.fact_assessments.append(
            FactAssessment(
                materialized_fact_id=fact_id,
                assessment=Assessment(
                    score=score,
                    positive_signals=(),
                    negative_signals=(),
                    scorer_id=ScorerId("test_scorer"),
                ),
            )
        )

    rendered = document_to_slim_json(document)

    assert rendered["facts"] == [
        {"kind": "public_role_holding", "confidence": 0.74, "role": "prezes"}
    ]


@dataclass(slots=True)
class FakePipeline:
    document: ArticleDocument

    def run_document(self, data: PipelineInput) -> ArticleDocument:
        _ = data
        return self.document


@dataclass(slots=True)
class FakeBatchPipeline:
    def run_document(self, data: PipelineInput) -> ArticleDocument:
        document_id = DocumentId("first" if "First" in data.raw_html else "second")
        return ArticleDocument(
            document_id=document_id,
            source_url=data.source_url,
            title=str(document_id),
            publication_date=data.publication_date,
            cleaned_text="Text.",
            paragraphs=("Text.",),
        )


def test_v2_cli_writes_one_json_file_per_html_input(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    (input_dir / "article.html").write_text("<html><p>Text.</p></html>", encoding="utf-8")
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    monkeypatch.setattr(
        "pipeline_v2.cli.build_v2_pipeline",
        lambda _config: FakePipeline(document),
    )

    exit_code = main(
        [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    written = json.loads((output_dir / "doc.json").read_text(encoding="utf-8"))
    assert written["title"] == "Title"


def test_v2_cli_rejects_document_id_override_in_batch_mode(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "article.html").write_text("<html><p>Text.</p></html>", encoding="utf-8")

    with pytest.raises(SystemExit):
        main(
            [
                "--input-dir",
                str(input_dir),
                "--document-id",
                "same-id-for-every-file",
                "--stdout",
            ]
        )


def test_v2_cli_batch_stdout_is_single_json_array(tmp_path: Path, monkeypatch, capsys) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "a.html").write_text("<html><p>First.</p></html>", encoding="utf-8")
    (input_dir / "b.html").write_text("<html><p>Second.</p></html>", encoding="utf-8")
    monkeypatch.setattr(
        "pipeline_v2.cli.build_v2_pipeline",
        lambda _config: FakeBatchPipeline(),
    )

    exit_code = main(["--input-dir", str(input_dir), "--stdout"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["title"] for item in payload] == ["first", "second"]


def test_document_output_serializes_materialized_fact_alternatives() -> None:
    surviving_id = FactCandidateId("fact-surviving")
    suppressed_id = FactCandidateId("fact-suppressed")
    surviving_record = FactCandidateRecord(
        id=surviving_id,
        kind=FactKind.PUBLIC_EMPLOYMENT,
        arguments=(),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    suppressed_record = FactCandidateRecord(
        id=suppressed_id,
        kind=FactKind.PUBLIC_EMPLOYMENT,
        arguments=(),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    document.materialized_fact_records.append(surviving_record)
    document.materialized_fact_alternatives[surviving_id] = (
        MaterializedFactAlternative(
            record=suppressed_record,
            score=0.731,
            claim_id=ResolutionClaimId("claim-1"),
            relation=ResolutionRelation.SAME_FACT,
        ),
    )

    rendered = document_to_json(document)

    assert rendered["materialized_fact_alternatives"] == {
        str(surviving_id): [
            {
                "score": 0.731,
                "claim_id": "claim-1",
                "relation": "same_fact",
                "record": {
                    "id": str(suppressed_id),
                    "kind": FactKind.PUBLIC_EMPLOYMENT.value,
                    "arguments": [],
                    "evidence_ids": [],
                    "source": "test",
                    "signals": [],
                },
            }
        ]
    }
