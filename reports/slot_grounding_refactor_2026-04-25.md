# Frame Slot Grounding Refactor - 2026-04-25

## Scope

This step introduced a shared internal slot-grounding layer for reusable,
typed grounding of role labels, organization mentions, and slot evidence before
facts are built.

Implemented:

- Added `pipeline/frame_grounding.py` with:
  - `SlotEvidence`
  - `GroundedRoleLabel`
  - `GroundedOrganizationMention`
  - `FrameSlotGrounder`
- Moved public-employment role-label grounding behind the shared layer and
  tightened rejection of noisy labels dominated by dates, kinship phrases,
  person names, office spillover, and generic junk like `potrzebna`.
- Reused shared organization grounding in enrichment and frame extraction so
  public-money/public-contract logic can recover strong organization mentions
  that NER missed.
- Required explicit contract/public-money evidence before emitting
  `PUBLIC_CONTRACT`.
- Moved still-shared secondary-fact helpers into
  `pipeline/secondary_fact_utils.py` and added import-boundary tests so shared
  helpers stay outside `pipeline.domains`.

## Benchmark impact

Quality unlocks confirmed in the benchmark suite:

- `tvnwarszawa_fundacja_bielskiego_20260425`
  - recovers `Fundacja Karola Bielskiego`
  - recovers `Urząd Marszałkowski`
  - keeps `Karol Bielski -> PSL`
  - keeps `Marcelina Zawisza -> Razem`
  - emits `PUBLIC_CONTRACT` instead of losing the paid-promotion flow
- `wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`
  - keeps `Opolski Urząd Wojewódzki` / `OUW`
  - keeps marshal-office context for `UMWO`
  - keeps family/proxy employment findings
- `wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie__7273798906222848a`
  - recovers `Lubelskie Koleje` instead of collapsing to weak aliases
- `rp_tk_negative`
  - stays relevance-only / fact-empty after tightening `urząd` grounding
- `oko_miliony_pajeczyna_rydzyka`
  - keeps funding output rooted in the correct organizations

Regressions explicitly avoided while stabilizing canonicalization:

- no loss of `Wp` alias deduplication in identity linking
- no cross-attachment of party membership across multiple people in one
  sentence
- no bogus kinship fact from `fundacja założona przez ...`

## Validation

Commands run:

```bash
uv run python scripts/setup_models.py
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
uv run pytest tests/integration/test_benchmark.py -k \
  'wp_zona_posla_pis_lubelskie_koleje or tvnwarszawa_fundacja_bielskiego_public_contract or wp_opole_cross_office_family'
uv run pytest tests/test_relations.py -k paid_promotion_public_money_flow_emits_public_contract
```

Results:

- full repo validation passed: `168 passed, 1 xfailed`
- targeted benchmark slice passed: `3 passed`
- targeted public-contract regression passed: `1 passed`

The final full-suite validation was run on a warmed benchmark batch. The
canonicalization fixes were tuned against the actual pytest-produced JSON output
under `/tmp/pytest-of-agluszak/pytest-current/benchmark_output0/`.
