# Tech Debt Cleanup Validation - 2026-05-05

## Scope

Cleanup items 4-8 removed stale compatibility shims and runtime role-regex
fallbacks while preserving the CLI contract and JSON output shape.

Implemented cleanup:

- added typed cluster/entity lookup helpers to `pipeline.extraction_context`
- preserved `ClusterID -> EntityID` and `EntityID -> EntityID` mappings through
  fact builders, clustering, normalization, linking, and graph remapping
- replaced clustering calls to canonicalizer-private methods with public methods
- deleted stale re-export shims:
  - `pipeline/compensation.py`
  - `pipeline/funding.py`
  - `pipeline/governance.py`
  - `pipeline/public_facts.py`
  - `pipeline/relations/fact_extractors.py`
- removed runtime `ROLE_PATTERNS` usage for role extraction
- kept `pipeline.frames` unchanged as the active CLI frame facade

## Commands Run

```bash
uv run python scripts/setup_models.py
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest tests/test_governance.py tests/test_relations.py tests/test_kinship_resolution.py tests/test_entity_normalization.py tests/test_identity_linking.py tests/test_import_boundaries.py
uv run pytest
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
```

## Results

- `uv run ruff check . --fix`: passed
- `uv run ruff format .`: passed
- `uv run ruff check .`: passed
- `uv run ty check`: passed
- focused regression slice: `126 passed`
- full test suite: `214 passed, 18 skipped`
- benchmark batch: completed successfully for all `inputs/*.html`

The benchmark output directory is generated state and did not create tracked
source diffs.

## Oracle Spot Check

Checked generated JSON against `reports/expected_article_findings.md` for the
high-risk cases affected by role/fact-builder cleanup:

- `wiadomosci.onet.pl__lublin__...__cpw9ltt`: relevant, emits appointment,
  dismissal, party/candidacy, and funding facts.
- `pleszew24.info__...stadniny-koni`: relevant, emits appointment and dismissal
  facts with parser-backed `Prezes` role labels.
- `oko_miliony_pajeczyna_rydzyka`: relevant, emits public-money facts for
  `Fundacja Lux Veritatis` and public funder/counterparty organizations.
- `tvnwarszawa_fundacja_bielskiego_20260425`: relevant, emits a
  `PUBLIC_CONTRACT` fact for `Fundacja Karola Bielskiego`.
- true negatives `olsztyn_roosevelta_negative` and `wp_meloni_negative`: remain
  irrelevant with zero facts.
- known `rp_tk_negative` issue remains a relevance false positive with zero
  downstream facts.

## Notes

The only test fixture adjustment was to provide `ParsedWord` role tokens in
governance tests that previously depended on regex role-text fallback. That
matches the new runtime contract: role extraction in the rules pipeline is
parser-backed through `match_role_mentions`.

Next bottleneck is unchanged by this cleanup: extraction quality work should
continue in frame slot grounding and target/role grounding, not in compatibility
import surfaces.
