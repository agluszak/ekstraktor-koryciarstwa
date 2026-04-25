# Extraction Context Refactor - 2026-04-25

## Scope

This was a behavior-preserving structural step toward domain-oriented extraction.

Implemented:

- Added shared typed cluster/evidence helpers to `pipeline/extraction_context.py`.
- Migrated repeated frame-extractor lookup helpers to `ExtractionContext`:
  - cluster lookup by `ClusterMention`
  - cluster lookup by `ClusterID`
  - paragraph context cluster lookup
  - cluster merge/dedupe
  - clause-distance sorting primitive
  - single-clause evidence construction
- Added `pipeline/domains/public_money.py` and moved public-money frame extraction there:
  - `PolishFundingFrameExtractor`
  - `PolishPublicContractFrameExtractor`
  - public-money flow signal helpers
  - public-contract counterparty predicates
- Added focused unit coverage for `ExtractionContext` mention matching and paragraph-distance ordering.

Not implemented in this step:

- Full domain package split of the remaining `pipeline/frames.py` extractors.
- Full relation extractor split of `pipeline/relations/fact_extractors.py`.
- Any intentional extraction behavior change.

## Validation

Commands run:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest tests/test_extraction_context.py tests/test_governance.py tests/test_relations.py
uv run python scripts/setup_models.py
uv run pytest
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run pytest tests/integration/test_benchmark.py::test_oko_rydzyk_funding tests/integration/test_benchmark.py::test_dziennik_zachodni_bytom
```

Results:

- `ruff check --fix`: passed.
- `ruff format`: no files changed.
- `ruff check`: passed.
- `ty check`: passed.
- Targeted tests: `72 passed`.
- Public-money integration checks after the split: `2 passed`.
- Full pytest on the working tree: `159 passed, 1 xfailed, 2 failed`.

The two full-suite failures are benchmark assertions that also fail on a clean
`HEAD` worktree after model setup, so they are pre-existing benchmark gaps rather
than regressions from this refactor:

- `tests/integration/test_benchmark.py::test_tvnwarszawa_fundacja_bielskiego_public_contract`
  - Missing entity expectation: foundation tied to Karol Bielski.
- `tests/integration/test_benchmark.py::test_wp_opole_cross_office_family`
  - Missing entity expectation: Opolski Urząd Wojewódzki / OUW.

## Behavior Notes

No extraction behavior change is intended. The migrated methods preserve the
same matching rules:

- exact mention span match first,
- same text / sentence / entity type fallback,
- `ClusterID`-based dedupe.

The generated SQLite registry was cleared before rerunning the failing targeted
integration checks:

```bash
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
```

The same failures remained.

The public-money split also keeps `pipeline.frames` as the public compatibility
surface for now, so existing imports such as `from pipeline.frames import
PolishFundingFrameExtractor` continue to work.

## Next Step

The next safe structural increment is to move `PolishCompensationFrameExtractor`
into a domain module. It should first stop calling governance role-text helpers
through `PolishGovernanceFrameExtractor`, or those helpers should be extracted to
a neutral role-matching module.
