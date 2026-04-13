# Political Nepotism Extraction Pipeline

## Setup

Use `uv` as the only package manager.

```powershell
uv sync
uv run python scripts/setup_models.py
```

The setup script installs `pl_core_news_lg`, downloads the Stanza Polish
`tokenize,mwt,pos,lemma,depparse` models, and downloads plus patches the pinned
Polish coref model artifact.

## Run

```powershell
uv run python main.py --html-path article.html --source-url https://example.com/article --stdout
```

The pipeline writes:

- `output/<document>.json`
- `output/<document>.graph.json`
- `output/entity_registry.sqlite3`

## Example output

See [examples/example_output.json](examples/example_output.json).
