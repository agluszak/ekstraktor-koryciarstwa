from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline_v2.candidates import Assessment
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
    EvidenceId,
    FactCandidateId,
    InferenceStateId,
    InferenceVariableId,
    ProducerId,
    ScorerId,
    SentenceId,
)
from pipeline_v2.inference.graph_spec import InferenceDiagnostic, StateProbability, VariableMarginal
from pipeline_v2.nlp import EvidenceSpan, Sentence, Span
from pipeline_v2.output import document_to_json
from pipeline_v2.types import DependencyObjectSignal, DependencyRelation, PublicMoneyRelevanceSignal


def test_document_output_includes_evidence_and_fact_candidates() -> None:
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
            fact_candidate_id=FactCandidateId("fact-1"),
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
            variable_id=InferenceVariableId("event-active:fact-1"),
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
        }
    ]
    assert rendered["stage_diagnostics"] == [
        {
            "stage_name": "coreference_stage_v2",
            "status": "skipped",
            "reason": "disabled by config",
        }
    ]
    assert rendered["fact_assessments"] == [
        {
            "fact_candidate_id": "fact-1",
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
            "variable_id": "event-active:fact-1",
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
            fact_candidate_id=FactCandidateId("fact-1"),
            assessment=Assessment(
                score=0.75,
                positive_signals=(DependencyObjectSignal(relation=DependencyRelation.OBJ),),
                negative_signals=(),
                scorer_id=ScorerId("test_scorer"),
            ),
        )
    )

    rendered = document_to_json(document)

    assert rendered["fact_assessments"] == [
        {
            "fact_candidate_id": "fact-1",
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


@dataclass(slots=True)
class FakePipeline:
    document: ArticleDocument

    def run_document(self, data: PipelineInput) -> ArticleDocument:
        _ = data
        return self.document


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
    assert written["document_id"] == "doc"
