# V2 Typed Binding Refactor - 2026-05-21

## Goal

Implement the non-scoring part of the architecture cleanup:

- make dependency relations typed at the adapter boundary,
- remove broad governance fallback binding,
- stop encoding public-employment location context in organization canonical names,
- reduce compensation Cartesian products,
- make fact-resolution signatures typed,
- keep signal details structured in final JSON output.

The broader scoring redesign is intentionally deferred. The current scorer still uses the existing score table, with only minimal updates needed for new typed signal fields.

## Changes Checked

- `DependencyRelation` now replaces raw dependency relation strings in parsed dependency tokens, stored dependency arcs, syntax bindings, and dependency signals.
- `SyntaxView` now exposes typed `SyntaxBinding` records with relation class, path length, and direction.
- Governance candidate binding no longer scans three-sentence windows or paragraph lead fallback organizations. The default weak discourse window is one previous sentence.
- Public employment inferred public organizations keep the observed head phrase as the canonical hint. Nearby location context is represented by explicit typed signals.
- Compensation candidate binding no longer emits a full person x organization Cartesian product.
- Fact resolution uses typed `FactSignature` values and typed `FactResolutionStrategy` values instead of repr/string signatures.
- Final output signal details are JSON objects, not stringified Python dictionaries.

## Validation

Commands run:

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ty check pipeline_v2 tests_v2
uv run pytest -c pytest-v2.ini -q
uv run extractor-v2 --input-dir inputs_new --glob "*.html" --output-dir /tmp/ekstraktor-v2-binding-check
```

Results:

- `ty`: passed.
- `pytest-v2`: 117 passed.
- `extractor-v2` smoke run completed for 4 `inputs_new` HTML files.

Smoke output counts:

| Document | Fact candidates | Fact resolution claims |
| --- | ---: | ---: |
| Czy wójt ukrywa nepotyzm? | 5 | 1 |
| Hotelarz Rząsowski / MON | 6 | 2 |
| Nepotyzm w Bytomiu / CBA | 10 | 0 |
| Kontrowersje wokół wójta Charsznicy | 5 | 0 |

## Deferred

Scoring still needs a deeper redesign. Do not keep extending `FactRecordScorer` with more global signal cases; the next refactor should introduce domain scoring policies or another composable scoring architecture.
