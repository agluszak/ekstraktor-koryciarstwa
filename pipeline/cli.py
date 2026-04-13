from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.config import PipelineConfig
from pipeline.coref import StanzaCoreferenceResolver
from pipeline.events import PolishEventExtractor
from pipeline.filtering import KeywordRelevanceFilter
from pipeline.linking import SQLiteEntityLinker
from pipeline.models import PipelineInput
from pipeline.ner import SpacyPolishNERExtractor
from pipeline.orchestrator import NepotismPipeline
from pipeline.output import JsonOutputBuilder, write_outputs
from pipeline.preprocessing import TrafilaturaPreprocessor
from pipeline.relations import PolishRuleBasedRelationExtractor
from pipeline.scoring import RuleBasedNepotismScorer
from pipeline.segmentation import ParagraphSentenceSegmenter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Political nepotism extraction pipeline for Polish articles."
    )
    parser.add_argument("--html-path", type=Path, help="Path to a local HTML file.")
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
    return parser


def build_pipeline(config: PipelineConfig) -> NepotismPipeline:
    return NepotismPipeline(
        preprocessor=TrafilaturaPreprocessor(),
        relevance_filter=KeywordRelevanceFilter(config),
        segmenter=ParagraphSentenceSegmenter(config),
        ner_extractor=SpacyPolishNERExtractor(config),
        coreference_resolver=StanzaCoreferenceResolver(config),
        relation_extractor=PolishRuleBasedRelationExtractor(config),
        event_extractor=PolishEventExtractor(config),
        entity_linker=SQLiteEntityLinker(config),
        scorer=RuleBasedNepotismScorer(config),
        output_builder=JsonOutputBuilder(),
    )


def read_html(args: argparse.Namespace) -> str:
    if args.html_path:
        return args.html_path.read_text(encoding="utf-8")
    return sys.stdin.read()


def main() -> int:
    args = build_parser().parse_args()
    raw_html = read_html(args)
    if not raw_html.strip():
        raise ValueError("No HTML input provided. Use --html-path or pipe HTML through stdin.")

    config = PipelineConfig.from_file(args.config)
    pipeline = build_pipeline(config)
    result = pipeline.run(
        PipelineInput(
            raw_html=raw_html,
            source_url=args.source_url,
            publication_date=args.publication_date,
            document_id=args.document_id,
        )
    )
    result_path, graph_path = write_outputs(result, args.output_dir)
    if args.stdout:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {"result_path": str(result_path), "graph_path": str(graph_path)},
                ensure_ascii=False,
            )
        )
    return 0
