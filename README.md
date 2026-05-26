# Political Nepotism Extraction Pipeline

An information extraction pipeline ("ekstraktor-koryciarstwa") for analysing Polish
news articles about "koryciarstwo" — public money extraction, nepotism, patronage,
appointments to state-owned companies, and the flow of public funds.

The pipeline is event-first: it produces typed hypothesis graphs with probabilistic
inference, preserving competing candidates and posterior confidence scores rather than
collapsing to a single answer early.

## Setup

```bash
uv sync
uv run python scripts/setup_models.py
```

`uv sync` installs Python dependencies. `scripts/setup_models.py` downloads and patches
the spaCy and Stanza models that the pipeline requires. Both steps are needed before
running the pipeline or the test suite.

## Usage

### Single file or URL

```bash
uv run extractor --html-path inputs/article.html --stdout
uv run extractor --url https://example.com/article --stdout
```

### Batch processing

```bash
uv run extractor --input-dir inputs --glob "*.html" --output-dir output
```

Reads all matching HTML files from `inputs/` and writes `.json` results to `output/`.

### Output modes

**Slim (default)** — human-readable summary:
- `title`, `url`, `relevant`, `relevance_score`
- `facts`: list of materialized facts with resolved entity names and `confidence`

**Debug (`--debug`)** — full graph JSON including sentences, tokens, morphology, evidence
spans, inference marginals, resolution claims, and all internal IDs. Use this when
debugging extraction or inference behaviour.

Both modes work with all input sources. `--stdout` and `--output-dir` can be combined
with either mode.

## Development

### Validation

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check
uv run pytest -q
```

### Architecture

The pipeline stages run in this order (see `pipeline_v2/runtime.py`):

1. HTML preprocessing
2. Relevance filtering
3. Sentence/token segmentation
4. Morfeusz2 morphology
5. Dependency parsing
6. Named entity candidate production
7. Domain event/binding candidate production
8. Reference, coreference, proxy, and tie candidate production
9. Optional semantic enrichment
10. Probabilistic inference and materialized output projection

### Reports and benchmarks

Development notes and benchmark results are in `reports/` and `reports/v2/`. Before
significant extraction, inference, or architecture changes, read:

- `reports/expected_article_findings.md`
- `reports/v2/probabilistic_inference_plan_2026-05-21.md`

For article-specific work: read the article, write down expected findings, run the
pipeline, compare, then locate the gap in preprocessing / relevance / NER / morphology /
syntax / candidate production / retrieval / inference / materialization.
