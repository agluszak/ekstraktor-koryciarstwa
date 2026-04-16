# Political Nepotism Extraction Pipeline

## Setup

Use `uv` as the only package manager.

```powershell
uv sync
uv run python scripts/setup_models.py
```

You must run `uv run python scripts/setup_models.py` in the current `.venv` before
running the pipeline or the test suite. `uv sync` alone is not enough.

The setup script installs `pl_core_news_lg` and `pl_core_news_md`, downloads the Stanza Polish
`tokenize,mwt,pos,lemma,depparse` models, and downloads plus patches the pinned
Polish coref model artifact.

## Run

```powershell
uv run python main.py --html-path article.html --source-url https://example.com/article --stdout
```

For batch runs, keep one process warm and process a directory sequentially:

```powershell
uv run python main.py --input-dir inputs --stdout
```

For repeated ad hoc requests, use the persistent worker:

```powershell
uv run python main.py --worker
```

Then send one JSON object per line on stdin, for example:

```json
{"html_path":"inputs/article.html","source_url":"https://example.com/article"}
```

The pipeline writes:

- `output/<document>.json`
- `output/entity_registry.sqlite3`

## Example output

See [examples/example_output.json](examples/example_output.json).
