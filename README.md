# Political Nepotism Extraction Pipeline

This repository houses an information extraction pipeline ("ekstraktor-koryciarstwa") focused on analyzing Polish news articles. Its primary domain is monitoring "koryciarstwo" / public money extraction: nepotism, patronage, appointments to state-owned companies, and the flow of public funds.

## Setup

The project uses `uv` as the package manager and requires specific NLP models to be downloaded and patched before use.

```bash
uv sync
uv run python scripts/setup_models.py
```

> **Important**: You must run `uv run python scripts/setup_models.py` in the current `.venv` before running the pipeline or the test suite. `uv sync` alone is not enough, as the pipeline depends on specific spaCy and Stanza models, as well as a patched coreference artifact.

## Usage

### Single File Processing

To process a single local HTML file or download one directly from a URL:

```bash
uv run python main.py --html-path article.html --source-url https://example.com/article --stdout
```

### Batch Processing

For processing multiple articles efficiently (keeping NLP models loaded in a warm process), use the batch mode:

```bash
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
```

This will read all matching HTML files in `inputs/` and write `.json` extraction results and an `entity_registry.sqlite3` database to `output/`.

### Persistent Worker (stdin/stdout)

For repeated ad hoc requests from another application, use the persistent JSON-lines worker:

```bash
uv run python main.py --worker
```

Send one JSON object per line on `stdin`, for example:

```json
{"html_path":"inputs/article.html","source_url":"https://example.com/article"}
```

## Integration Tests and Benchmarks

The project includes an automated benchmark and integration test suite based on a manually curated set of expected findings (`reports/expected_article_findings.md`).

To run the full suite, which automatically executes the pipeline in batch mode over all benchmark articles and validates the expected extractions:

```bash
uv run pytest tests/test_benchmark.py -v -s
```

The test runner will evaluate whether the pipeline successfully identifies the required target entities and governance/compensation facts, logging soft warnings for currently unmet but desired extraction capabilities, while strictly failing on any regressions from established baselines.

## Output Structure

The pipeline generates structured JSON output for each document processed, containing:
- Relevance decisions and scores
- Extracted entities (People, Organizations, Roles, etc.)
- Identified facts (Governance, Compensation, Funding, etc.)
- Execution times for individual pipeline stages

See `examples/example_output.json` for a complete reference.
