from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_v2.document import PipelineInput
from pipeline_v2.output import JsonOutputWriter
from pipeline_v2.runtime import CoreferenceMode, V2PipelineConfig, build_v2_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the v2 extraction pipeline")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--glob", default="*.html")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--spacy-model", default="pl_core_news_lg")
    parser.add_argument("--sentence-transformer-model", default=None)
    parser.add_argument(
        "--coreference-mode",
        choices=[mode.value for mode in CoreferenceMode],
        default=CoreferenceMode.OFF.value,
    )
    parser.add_argument("--enable-syntax", action="store_true")
    args = parser.parse_args(argv)

    pipeline = build_v2_pipeline(
        V2PipelineConfig(
            spacy_model=args.spacy_model,
            sentence_transformer_model=args.sentence_transformer_model,
            coreference_mode=CoreferenceMode(args.coreference_mode),
            enable_syntax=args.enable_syntax,
        )
    )
    writer = JsonOutputWriter()
    for input_path in sorted(args.input_dir.glob(args.glob)):
        document = pipeline.run_document(
            PipelineInput(raw_html=input_path.read_text(encoding="utf-8"))
        )
        writer.write(document, args.output_dir / f"{document.document_id}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
