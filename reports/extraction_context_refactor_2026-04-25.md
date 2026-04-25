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
  - `PolishPublicContractFrameExtractor`
  - public-money flow signal helpers
  - public-contract counterparty predicates
- Added `pipeline/domains/funding.py` and moved `PolishFundingFrameExtractor`
  there while keeping shared public-money flow/reporting guards in
  `pipeline/domains/public_money.py`.
- Added `pipeline/domains/public_employment.py` and moved
  `PolishPublicEmploymentFrameExtractor` there.
- Added `pipeline/domains/anti_corruption.py` and moved:
  - `PolishAntiCorruptionReferralFrameExtractor`
  - `PolishAntiCorruptionAbuseFrameExtractor`
- Added `pipeline/domains/compensation.py` and moved
  `PolishCompensationFrameExtractor` there.
- Added `pipeline/domains/governance_frames.py` and moved
  `PolishGovernanceFrameExtractor` there.
- Added `pipeline/role_text.py` for role-text lookup shared by governance and
  compensation.
- Reduced `pipeline/frames.py` to a compatibility orchestration facade.
- Added focused unit coverage for `ExtractionContext` mention matching and paragraph-distance ordering.

Not implemented in this step:

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
uv run pytest tests/test_extraction_context.py tests/test_governance.py tests/test_relations.py tests/test_family_identity.py
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run pytest \
  tests/integration/test_benchmark.py::test_oko_rydzyk_funding \
  tests/integration/test_benchmark.py::test_dziennik_zachodni_bytom \
  tests/integration/test_benchmark.py::test_pleszew24_stadnina \
  tests/integration/test_benchmark.py::test_olsztyn_wodkan \
  tests/integration/test_benchmark.py::test_onet_cba_ostrow_bribery \
  tests/integration/test_benchmark.py::test_dziennik_polski_charsznica_nepotism \
  tests/integration/test_benchmark.py::test_ai42_poczesna_nepotism \
  tests/integration/test_benchmark.py::test_polsat_ciechanow_family_starostwo
uv run pytest tests/test_extraction_context.py tests/test_governance.py tests/test_relations.py tests/test_family_identity.py \
  tests/integration/test_benchmark.py::test_oko_rydzyk_funding \
  tests/integration/test_benchmark.py::test_dziennik_zachodni_bytom \
  tests/integration/test_benchmark.py::test_onet_cba_ostrow_bribery
```

Results:

- `ruff check --fix`: passed.
- `ruff format`: passed.
- `ruff check`: passed.
- `ty check`: passed.
- First focused tests after domain moves: `83 passed`.
- Cross-domain clean-registry benchmark slice: `8 passed`.
- Final focused tests after the funding/public-money dedupe: `86 passed`.
- Full pytest was run earlier during this refactor before the final domain split:
  `159 passed, 1 xfailed, 2 failed`.

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

Current extraction module line counts:

```text
    37 pipeline/frames.py
   452 pipeline/domains/anti_corruption.py
   300 pipeline/domains/compensation.py
   344 pipeline/domains/funding.py
   693 pipeline/domains/governance_frames.py
   630 pipeline/domains/public_employment.py
   653 pipeline/domains/public_money.py
```

## Next Step

The next structural increment is to split
`pipeline/relations/fact_extractors.py` by the same domain package boundaries,
with `relations/service.py` left as the fixed-order facade.
