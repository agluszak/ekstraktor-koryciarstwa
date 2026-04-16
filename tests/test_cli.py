from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from pipeline.cli import emit_json, handle_worker_request, iter_batch_inputs, run_batch
from pipeline.domain_types import EntityType
from pipeline.models import (
    Entity,
    ExtractionResult,
    RelevanceDecision,
)


class StubPipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, data):  # noqa: ANN001
        self.calls.append(data.raw_html)
        document_id = data.document_id or f"doc-{len(self.calls)}"
        return ExtractionResult(
            document_id=document_id,
            source_url=data.source_url,
            title="Test",
            publication_date=None,
            relevance=RelevanceDecision(is_relevant=True, score=1.0, reasons=["test"]),
            entities=[
                Entity(
                    entity_id="person-1",
                    entity_type=EntityType.PERSON,
                    canonical_name="Jan Kowalski",
                    normalized_name="Jan Kowalski",
                )
            ],
            facts=[],
            events=[],
            score=None,
        )


def test_iter_batch_inputs_returns_sorted_html_files(tmp_path: Path) -> None:
    (tmp_path / "b.html").write_text("b", encoding="utf-8")
    (tmp_path / "a.html").write_text("a", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")

    paths = iter_batch_inputs(tmp_path, "*.html")

    assert [path.name for path in paths] == ["a.html", "b.html"]


def test_run_batch_reuses_single_pipeline_instance(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.html").write_text("<html>a</html>", encoding="utf-8")
    (tmp_path / "b.html").write_text("<html>b</html>", encoding="utf-8")
    pipeline = StubPipeline()
    args = argparse.Namespace(
        input_dir=tmp_path,
        glob="*.html",
        output_dir=tmp_path / "out",
        stdout=True,
        publication_date=None,
        document_id=None,
    )

    status = run_batch(args, pipeline)
    captured = capsys.readouterr().out

    assert status == 0
    assert len(pipeline.calls) == 2
    assert '"document_id": "a"' in captured
    assert '"document_id": "b"' in captured


def test_handle_worker_request_accepts_html_path(tmp_path: Path) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html>body</html>", encoding="utf-8")
    pipeline = StubPipeline()

    response = handle_worker_request(
        {"html_path": str(html_path), "source_url": "https://example.com/article"},
        pipeline=pipeline,
        output_dir=tmp_path / "out",
    )

    assert response["ok"] is True
    assert response["document_id"] == "doc-1"
    assert response["result"]["source_url"] == "https://example.com/article"


def test_emit_json_falls_back_to_ascii_when_stdout_encoding_cannot_encode(monkeypatch) -> None:
    sink = io.BytesIO()
    stdout = io.TextIOWrapper(sink, encoding="cp1250", errors="strict")
    original_stdout = sys.stdout
    monkeypatch.setattr(sys, "stdout", stdout)
    try:
        emit_json({"text": "Horyń � Rydzyk"})
        stdout.flush()
    finally:
        monkeypatch.setattr(sys, "stdout", original_stdout)

    output = sink.getvalue().decode("cp1250")
    assert "\\ufffd" in output
