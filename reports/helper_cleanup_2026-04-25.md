# Helper Cleanup Refactor - 2026-04-25

## Scope

This was a behavior-preserving debt cleanup focused on modules that were already
half-split or carrying duplicated helper layers.

Implemented:

- Finished the canonicalizer decomposition in `pipeline/normalization.py`.
  - Added `pipeline/entity_name_policies.py` for person/party naming policy.
  - Added `pipeline/entity_graph_remapper.py` for mention/fact remapping after
    entity merges.
  - Reduced `DocumentEntityCanonicalizer` back toward an orchestration role.
- Finished the public-money helper split.
  - Added `pipeline/public_money_signals.py` for shared contractor,
    counterparty, and context-window predicates.
  - Updated `pipeline/domains/public_money.py` and
    `pipeline/domains/anti_corruption.py` to consume the shared layer directly.
- Consolidated repeated domain-context helpers.
  - Added `pipeline/domain_context_helpers.py` for `ExtractionContext` access,
    clause-distance sorting, paragraph-context lookup, and shared attribution
    speech lemmas.
  - Migrated `governance_frames.py`, `funding.py`, `compensation.py`,
    `public_money.py`, `anti_corruption.py`, and `identity_signals.py`.
- Tightened import-boundary coverage in `tests/test_import_boundaries.py`.

## Compatibility Notes

`pipeline/clustering.py` still uses a few canonicalizer-private helper names.
Those entrypoints were kept as thin delegates in `DocumentEntityCanonicalizer`
so the cleanup stays internal and does not leak a partial migration into
clustering.

The intent of this step was structural cleanup, not extraction-rule changes:

- no CLI changes
- no JSON schema changes
- no fact-type changes

## Validation

Commands run:

```bash
uv run python scripts/setup_models.py
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest tests/test_entity_normalization.py tests/test_identity_linking.py tests/test_import_boundaries.py tests/test_governance.py tests/test_relations.py
uv run pytest
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run pytest \
  tests/integration/test_benchmark.py::test_oko_rydzyk_funding \
  tests/integration/test_benchmark.py::test_dziennik_zachodni_bytom \
  tests/integration/test_benchmark.py::test_tvnwarszawa_fundacja_bielskiego_public_contract \
  tests/integration/test_benchmark.py::test_dziennik_polski_charsznica_nepotism \
  tests/integration/test_benchmark.py::test_wp_opole_cross_office_family \
  tests/integration/test_benchmark.py::test_polsat_ciechanow_family_starostwo
```

Results:

- Focused normalization / relations / governance slice: `99 passed`.
- Full test suite: `173 passed, 1 xfailed`.
- Clean-registry benchmark slice covering TVN Warszawa, OKO/Rydzyk, Bytom,
  Charsznica, Opole, and Ciechanow: `6 passed`.

## Follow-on Debt

The new helper boundaries are now explicit enough that the next cleanup can
target truly oversized heuristic hubs rather than repeated wrappers. The
remaining compatibility seam worth revisiting later is clustering's dependency
on canonicalizer-private helper names.
