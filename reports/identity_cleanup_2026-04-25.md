# Identity Cleanup - 2026-04-25

## Scope

This step completed the planned family/proxy identity cleanup centered on
`pipeline/identity.py`.

The goal was to remove a remaining heuristic hub by splitting signal extraction
from mutation, making resolver stages explicit, and adding direct regression
coverage without changing the public JSON schema, CLI behavior, fact types, or
model shapes.

## Implemented

### 1. Shared identity-signal layer

- Added `pipeline/identity_signals.py`.
- Moved non-mutating family/proxy signal logic there:
  - family mention collection
  - honorific mention collection
  - possessive/public-role anchor detection
  - speaker/subject anchor resolution
  - surname compatibility helpers
- Kept the extracted layer typed with dataclasses instead of loose dictionaries.

### 2. Explicit resolver stages

- Refactored `PolishFamilyIdentityResolver.run(...)` into explicit phases:
  1. collect and resolve family mentions
  2. collect honorific mentions
  3. materialize family proxies
  4. materialize honorific hypotheses
  5. emit proxy facts / identity hypotheses
  6. refresh clause mentions
- Added typed intermediate records in `pipeline/identity.py` so collection and
  mutation are no longer coupled only by call order.

### 3. Regression coverage

- Added `tests/test_identity_signals.py` for direct signal-layer coverage.
- Extended architectural guardrails so `pipeline/identity_signals.py` is covered
  by import-boundary checks.
- Kept existing family/kinship resolver tests green against the refactor.

## Debt removed

- Removed family/honorific mention detection from the mutating resolver class.
- Removed anchor-resolution helpers from `pipeline/identity.py`.
- Removed duplicated surname/anchor utility logic from the resolver in favor of
  the shared signal layer.

## Benchmark / regression impact

Benchmark-sensitive identity checks remained green for the articles most
exposed to this cleanup:

- `tvnwarszawa_fundacja_bielskiego_20260425`
  - no bogus family tie introduced around Karol Bielski / fundacja context
- `wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`
  - keeps cross-office family resolution
- `dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-...`
  - keeps partner/proxy employment resolution

Focused identity protections that remained green:

- possessive family mentions
- public-role fallback anchors
- split-quote speaker anchors
- `pani + surname` honorific references
- proxy fact/hypothesis emission
- clause refresh after proxy creation

## Validation

Commands run during this cleanup:

```bash
uv run ruff format pipeline/identity.py pipeline/identity_signals.py \
  tests/test_identity_signals.py tests/test_import_boundaries.py
uv run ruff check pipeline/identity.py pipeline/identity_signals.py \
  tests/test_identity_signals.py tests/test_import_boundaries.py
uv run pytest tests/test_identity_signals.py tests/test_family_identity.py \
  tests/test_kinship_resolution.py tests/test_import_boundaries.py

uv run ruff format .
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest tests/test_relations.py tests/test_governance.py \
  tests/integration/test_benchmark.py -k \
  'tvnwarszawa_fundacja_bielskiego_public_contract or wp_opole_cross_office_family or charsznica'
uv run pytest
```

Results:

- focused identity + signal tests: `20 passed`
- benchmark-sensitive slice: `3 passed, 92 deselected`
- full suite: `173 passed, 1 xfailed`
