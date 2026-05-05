# Dependency Frame Validation - 2026-05-05

## Scope

Added a shared dependency-frame layer for clause-local extraction arguments and
routed governance and funding extraction through it before existing discourse
fallbacks.

Implemented behavior:

- added `pipeline.dependency_frames` with typed argument, money-span, and
  trigger-frame dataclasses
- indexed dependency frames by `ClauseID` in `ExtractionContext`
- used dependency arguments to prefer appointee/dismissal-person and
  organization candidates in governance frames
- used dependency arguments and reporting-transfer checks in funding extraction
- exposed a shared `fact_time_scope` helper and applied it to governance and
  funding frame facts
- added unit coverage for active/passive governance arguments, funding transfer
  arguments, reporting `przekazac`, and imperfective aspect hints

## Commands Run

```bash
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest tests/test_governance.py tests/test_extraction_context.py
uv run pytest tests/test_dependency_frames.py
uv run python scripts/setup_models.py
uv run pytest
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
```

## Results

- `uv run ruff check . --fix`: passed
- `uv run ruff format .`: passed
- `uv run ruff check .`: passed
- `uv run ty check`: passed
- focused governance/context slice: `36 passed`
- dependency-frame unit tests: `5 passed`
- full test suite: `225 passed, 6 skipped`
- benchmark batch: completed successfully for all `inputs/*.html`

## Oracle Spot Check

Checked generated output against the high-risk cases in
`reports/expected_article_findings.md`:

- `pleszew24.info__...stadniny-koni`: relevant, emits:
  - `A. Goralczyk -> APPOINTMENT -> Stadnine Koni Iwno`, role `Prezes`
  - `Przemyslaw Pacia -> DISMISSAL -> Stadnine Koni Iwno`, role `Prezes`
- `oko_miliony_pajeczyna_rydzyka`: public-money facts remain present for
  `Fundacja Lux Veritatis` and public funder/counterparty organizations.
- reporting-style `przekazac` evidence:
  no `FUNDING` fact evidence matched explicit `redakcji`, `przekazala nam`, or
  `przekazal nam` reporting patterns.
- true negatives in the batch still include:
  - `olsztyn_roosevelta_negative`: irrelevant, zero facts
  - `wp_meloni_negative`: irrelevant, zero facts

## Notes

The dependency-frame layer is intentionally conservative. It now provides typed
clause-local grounding for domain builders, while the existing paragraph and
discourse-window recovery remains available for split-sentence benchmark cases.

The known `rp_tk_negative` issue remains a relevance false positive with zero
downstream facts.
