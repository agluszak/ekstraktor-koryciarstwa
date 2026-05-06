from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

from pipeline.base import DocumentStage
from pipeline.clustering import PolishEntityClusterer
from pipeline.config import PipelineConfig
from pipeline.coref import StanzaCoreferenceResolver
from pipeline.domain_registry import build_default_domain_registry
from pipeline.enrichment import SharedEntityEnricher
from pipeline.fact_extractor import PolishFactExtractor
from pipeline.filtering import KeywordRelevanceFilter
from pipeline.frames import PolishFrameExtractor
from pipeline.identity import PolishFamilyIdentityResolver
from pipeline.linking import InMemoryEntityLinker
from pipeline.llm import OllamaLLMEngine
from pipeline.models import ExtractionResult, PipelineInput
from pipeline.ner import SpacyPolishNERExtractor
from pipeline.nlp_services import StanzaPolishMorphologyAnalyzer
from pipeline.orchestrator import NepotismPipeline
from pipeline.preprocessing import TrafilaturaPreprocessor
from pipeline.custom_entities import CustomEntityExtractor
from pipeline.roles import PolishPositionExtractor
from pipeline.runtime import PipelineRuntime
from pipeline.scoring import RuleBasedNepotismScorer
from pipeline.segmentation import ParagraphSentenceSegmenter
from pipeline.syntax import StanzaClauseParser


class PipelineRunner(Protocol):
    def run(self, data: PipelineInput) -> ExtractionResult: ...


def emit_json(payload: object, *, indent: int | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    try:
        sys.stdout.write(f"{text}\n")
    except UnicodeEncodeError:
        fallback = json.dumps(payload, ensure_ascii=True, indent=indent)
        sys.stdout.write(f"{fallback}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Political nepotism extraction pipeline for Polish articles."
    )
    parser.add_argument("--html-path", type=Path, help="Path to a local HTML file.")
    parser.add_argument("--url", help="URL to download and process directly.")
    parser.add_argument("--input-dir", type=Path, help="Directory with local HTML files.")
    parser.add_argument("--glob", default="*.html", help="Glob for batch input discovery.")
    parser.add_argument("--source-url", help="Original article URL.")
    parser.add_argument("--publication-date", help="Publication date override.")
    parser.add_argument("--document-id", help="Document identifier override.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML configuration.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for JSON outputs.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the main JSON result to stdout.",
    )
    parser.add_argument(
        "--engine",
        choices=("rules", "llm"),
        default="rules",
        help="Extraction engine to use.",
    )
    parser.add_argument(
        "--llm-model",
        help="Ollama model name for --engine llm.",
    )
    parser.add_argument(
        "--llm-host",
        help="Ollama base URL for --engine llm.",
    )
    parser.add_argument(
        "--llm-model-path",
        help="Legacy alias for the Ollama model name.",
    )
    parser.add_argument(
        "--llm-context-size",
        type=int,
        help="Ollama context size for --engine llm.",
    )
    parser.add_argument(
        "--llm-max-output-tokens",
        type=int,
        help="Maximum generated tokens per LLM chunk.",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        help="LLM sampling temperature. Defaults to 0.0.",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help="Run a persistent JSON-lines worker on stdin/stdout.",
    )
    return parser


def build_pipeline(
    config: PipelineConfig,
    *,
    engine: str = "rules",
    runtime: PipelineRuntime | None = None,
) -> NepotismPipeline:
    shared_runtime = runtime or PipelineRuntime(config)
    morphology = StanzaPolishMorphologyAnalyzer(shared_runtime)

    stages: list[DocumentStage] = [
        ParagraphSentenceSegmenter(config),
        KeywordRelevanceFilter(config),
    ]

    if engine == "rules":
        domain_registry = build_default_domain_registry(config, runtime=shared_runtime)
        stages.extend(
            [
                SpacyPolishNERExtractor(
                    config,
                    runtime=shared_runtime,
                    morphology=morphology,
                ),
                StanzaClauseParser(config, runtime=shared_runtime),
                PolishPositionExtractor(config),
                CustomEntityExtractor(config),
                StanzaCoreferenceResolver(config, runtime=shared_runtime),
                PolishEntityClusterer(config, runtime=shared_runtime),
                PolishFamilyIdentityResolver(config),
                SharedEntityEnricher(config, runtime=shared_runtime),
                PolishFrameExtractor(config, runtime=shared_runtime, registry=domain_registry),
                PolishFactExtractor(config, registry=domain_registry),
                InMemoryEntityLinker(config, runtime=shared_runtime),
            ]
        )
    elif engine == "llm":
        stages.append(OllamaLLMEngine(config))

    stages.append(RuleBasedNepotismScorer(config))

    return NepotismPipeline(
        preprocessor=TrafilaturaPreprocessor(),
        stages=stages,
    )


def apply_cli_llm_overrides(args: argparse.Namespace, config: PipelineConfig) -> None:
    if args.llm_model is not None:
        config.llm.model = args.llm_model
    if args.llm_host is not None:
        config.llm.base_url = args.llm_host
    if args.llm_model_path is not None:
        config.llm.model = args.llm_model_path
    if args.llm_context_size is not None:
        config.llm.context_size = args.llm_context_size
    if args.llm_max_output_tokens is not None:
        config.llm.max_output_tokens = args.llm_max_output_tokens
    if args.llm_temperature is not None:
        config.llm.temperature = args.llm_temperature


def select_pipeline(args: argparse.Namespace, config: PipelineConfig) -> NepotismPipeline:
    if args.engine == "llm":
        apply_cli_llm_overrides(args, config)
    return build_pipeline(config, engine=args.engine)


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def read_html(path: Path | None, url: str | None) -> str:
    if path is not None:
        return path.read_text(encoding="utf-8")
    if url is not None:
        return fetch_html(url)
    return sys.stdin.read()


def run_single(args: argparse.Namespace, pipeline: PipelineRunner) -> int:
    raw_html = read_html(args.html_path, args.url)
    if not raw_html.strip():
        raise ValueError(
            "No HTML input provided. Use --html-path, --url, or pipe HTML through stdin."
        )

    result = pipeline.run(
        PipelineInput(
            raw_html=raw_html,
            source_url=args.source_url or args.url,
            publication_date=args.publication_date,
            document_id=args.document_id,
        )
    )
    if args.stdout:
        emit_json(result.to_dict(), indent=2)
    else:
        output_path = write_result(result, args.output_dir)
        emit_json({"result_path": str(output_path)})
    return 0


def iter_batch_inputs(input_dir: Path, pattern: str) -> list[Path]:
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def run_batch(args: argparse.Namespace, pipeline: PipelineRunner) -> int:
    if args.input_dir is None:
        raise ValueError("--input-dir is required for batch execution.")
    html_paths = iter_batch_inputs(args.input_dir, args.glob)
    if not html_paths:
        raise ValueError(f"No HTML files matched {args.glob!r} in {args.input_dir}.")

    rows: list[dict[str, Any]] = []
    for html_path in html_paths:
        result = pipeline.run(
            PipelineInput(
                raw_html=html_path.read_text(encoding="utf-8"),
                source_url=None,
                publication_date=args.publication_date,
                document_id=args.document_id or html_path.stem,
            )
        )
        result_path = write_result(result, args.output_dir)
        rows.append(
            {
                "input_path": str(html_path),
                "document_id": result.document_id,
                "result_path": str(result_path),
                "relevant": result.relevance.is_relevant,
                "facts": len(result.facts),
            }
        )

    if args.stdout:
        emit_json(rows, indent=2)
    else:
        emit_json(rows)
    return 0


def handle_worker_request(
    payload: dict[str, Any],
    *,
    pipeline: PipelineRunner,
    output_dir: Path,
) -> dict[str, Any]:
    html_path_value = payload.get("html_path")
    raw_html = payload.get("raw_html")
    if html_path_value is None and raw_html is None:
        raise ValueError("worker request must include either 'html_path' or 'raw_html'")
    if html_path_value is not None and raw_html is not None:
        raise ValueError("worker request must not include both 'html_path' and 'raw_html'")

    if html_path_value is not None:
        html_path = Path(str(html_path_value))
        raw_html = html_path.read_text(encoding="utf-8")
    assert raw_html is not None

    result = pipeline.run(
        PipelineInput(
            raw_html=raw_html,
            source_url=str(payload["source_url"]) if payload.get("source_url") else None,
            publication_date=str(payload["publication_date"])
            if payload.get("publication_date")
            else None,
            document_id=str(payload["document_id"]) if payload.get("document_id") else None,
        )
    )
    result_path = write_result(result, output_dir)
    return {
        "ok": True,
        "document_id": result.document_id,
        "result_path": str(result_path),
        "result": result.to_dict(),
    }


def write_result(result: ExtractionResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{result.document_id}.json"
    result_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result_path


def run_worker(args: argparse.Namespace, pipeline: PipelineRunner) -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("worker request must be a JSON object")
            response = handle_worker_request(
                payload,
                pipeline=pipeline,
                output_dir=args.output_dir,
            )
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        emit_json(response)
        sys.stdout.flush()
    return 0


def main() -> int:
    args = build_parser().parse_args()
    config = PipelineConfig.from_file(args.config)
    pipeline = select_pipeline(args, config)
    if args.worker:
        return run_worker(args, pipeline)
    if args.input_dir is not None:
        return run_batch(args, pipeline)
    return run_single(args, pipeline)
