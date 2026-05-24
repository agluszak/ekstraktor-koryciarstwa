from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline_v2.document import PipelineInput
from pipeline_v2.output import JsonOutputWriter, document_to_json, document_to_slim_json
from pipeline_v2.runtime import CoreferenceMode, V2PipelineConfig, build_v2_pipeline


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


def emit_json(payload: object, *, indent: int | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    try:
        sys.stdout.write(f"{text}\n")
    except UnicodeEncodeError:
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=indent) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the v2 extraction pipeline")
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--html-path", type=Path, help="Path to a local HTML file.")
    input_group.add_argument("--url", help="URL to download and process.")
    input_group.add_argument(
        "--input-dir", type=Path, help="Directory with local HTML files (batch mode)."
    )
    parser.add_argument("--glob", default="*.html", help="Glob for batch input discovery.")
    parser.add_argument("--source-url", help="Source URL override (single-file mode).")
    parser.add_argument("--publication-date", help="Publication date override.")
    parser.add_argument("--document-id", help="Document identifier override.")
    parser.add_argument("--output-dir", type=Path, help="Directory for JSON outputs.")
    parser.add_argument("--stdout", action="store_true", help="Print result JSON to stdout.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Output full graph JSON instead of slim summary.",
    )
    parser.add_argument("--spacy-model", default="pl_core_news_lg")
    parser.add_argument("--sentence-transformer-model", default=None)
    parser.add_argument(
        "--coreference-mode",
        choices=[mode.value for mode in CoreferenceMode],
        default=CoreferenceMode.OFF.value,
    )
    parser.add_argument(
        "--stanza-coref-model-path",
        default="models/stanza/pl/coref/udcoref_xlm-roberta-lora-v1.12.0.patched.pt",
    )
    args = parser.parse_args(argv)

    if args.input_dir is None and args.html_path is None and args.url is None:
        parser.error("one of --html-path, --url, or --input-dir is required")
    if args.input_dir is not None and not args.stdout and args.output_dir is None:
        parser.error("--output-dir is required for batch mode unless --stdout is set")
    if (
        (args.html_path is not None or args.url is not None)
        and not args.stdout
        and args.output_dir is None
    ):
        parser.error("--output-dir is required unless --stdout is set")
    if args.input_dir is not None and args.document_id is not None:
        parser.error("--document-id cannot be used with --input-dir")

    coreference_mode = CoreferenceMode(args.coreference_mode)
    provider = None
    if coreference_mode == CoreferenceMode.STANZA:
        from pipeline_v2.coreference_provider import StanzaCoreferenceProvider

        provider = StanzaCoreferenceProvider(args.stanza_coref_model_path)

    pipeline = build_v2_pipeline(
        V2PipelineConfig(
            spacy_model=args.spacy_model,
            sentence_transformer_model=args.sentence_transformer_model,
            coreference_mode=coreference_mode,
            coreference_provider=provider,
        )
    )
    writer = JsonOutputWriter()
    debug: bool = args.debug

    def serialize(document: object) -> object:
        from pipeline_v2.document import ArticleDocument

        assert isinstance(document, ArticleDocument)
        return document_to_json(document) if debug else document_to_slim_json(document)

    if args.input_dir is not None:
        stdout_documents: list[object] = []
        for input_path in sorted(args.input_dir.glob(args.glob)):
            document = pipeline.run_document(
                PipelineInput(
                    raw_html=input_path.read_text(encoding="utf-8"),
                    source_url=args.source_url,
                    publication_date=args.publication_date,
                )
            )
            if args.stdout:
                stdout_documents.append(serialize(document))
            else:
                assert args.output_dir is not None
                out_path = args.output_dir / f"{document.document_id}.json"
                writer.write(document, out_path, debug=debug)
        if args.stdout:
            emit_json(stdout_documents, indent=2)
        return 0

    if args.url is not None:
        raw_html = fetch_html(args.url)
        source_url = args.source_url or args.url
    else:
        assert args.html_path is not None
        raw_html = args.html_path.read_text(encoding="utf-8")
        source_url = args.source_url

    document = pipeline.run_document(
        PipelineInput(
            raw_html=raw_html,
            source_url=source_url,
            publication_date=args.publication_date,
            document_id=args.document_id,
        )
    )
    if args.stdout:
        emit_json(serialize(document), indent=2)
    else:
        assert args.output_dir is not None
        writer.write(document, args.output_dir / f"{document.document_id}.json", debug=debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
