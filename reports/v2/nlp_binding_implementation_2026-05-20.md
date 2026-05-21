# V2 NLP Binding Implementation Snapshot - 2026-05-20

## Goal

Implement the first NLP-first V2 binding pass for the six known fresh-report failures:

- preserve entity/fact overproduction, but attach confidence-bearing signals;
- stop hidden entity merges and emit explicit resolution claims instead;
- make proxy family references available before public-employment extraction;
- use morphology/dependency/reference signals to bind event arguments more precisely;
- emit possible duplicate-fact merges explicitly.

## Implemented

- Entity candidates are no longer silently merged by `reuse_key`; same-name and inflected-name cases now remain separate candidates and are connected through resolution proposals/claims.
- Added typed fact-resolution records and `FactResolutionStage`; duplicate facts remain in output and receive `same_fact` claims with scored evidence.
- Added typed NLP/context signals for dependency subject/object bindings, possessive kinship, weak window binding, appointer context, controller context, pseudonymous source context, and duplicate facts.
- Added a `SyntaxView` helper so producers consume typed dependency/morphology views rather than raw parser records.
- Moved nominal/coreference proxy materialization before domain event extraction in the runtime, so unnamed relatives such as `teść of Tomasz Kościelniak` can be used as employment persons.
- Public employment now prefers proxy family entities for possessive kinship phrases and materializes inferred public organizations from morphology-backed heads such as `samorząd`, optionally enriched with nearby location context.
- Governance window-only person/org/role bleed is demoted when the local person looks like a public-office actor rather than the appointee.
- Compensation scoring demotes window organizations that look like supervising ministries/controllers instead of direct payers.
- Personal tie scoring demotes ties sourced from pseudonymous/commenter contexts.

## Smoke Result

Command:

```bash
uv run extractor-v2 --input-dir inputs_new --glob "*.html" --output-dir /tmp/ekstraktor-v2-nlp-check
```

Observed high-confidence output:

- AI42/Poczesna now emits `public_employment` for `Rafał Dobosz` with inferred public organization context and role where present.
- Charsznica emits public-employment candidates for proxy relatives (`dziewczyna`, `teść`) instead of only the named wójt.
- The previous high-confidence Charsznica `Tomasz Kościelniak -> Gminnego Ośrodka Kultury` governance false positive is not present in the high-score smoke output.
- Radomszczańska keeps `AMW Rewita` as the high-confidence compensation funder; `Ministerstwu Obrony Narodowej` is not high-confidence as direct funder.
- Duplicate fact candidates are represented through explicit `same_fact` claims rather than deleted.

## Validation

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check pipeline_v2 tests_v2
uv run pytest -c pytest-v2.ini -q
```

Result: `105 passed`.
