# Funding Frames Progress - 2026-04-15

## Implementation

- Added `FundingFrame` as a first-class frame type alongside governance and compensation frames.
- Added `PolishFundingFrameExtractor` and `FundingFactBuilder`.
- Routed funding facts through the frame-first relation service instead of the older broad funding fact extractor.
- Kept funding amounts out of `CompensationFrame`; public grants and subsidies now produce `FUNDING`, not `COMPENSATION`.
- Fixed a general offset bug in funding role resolution: parsed token offsets are sentence-relative, while entity mentions use document-global offsets. The trigger position is now converted before comparing against entity spans.

## Checks

Commands run:

- `uv run ruff check . --fix`
- `uv run ruff format .`
- `uv run ruff check .`
- `uv run ty check`
- `uv run pytest tests/test_governance.py -q`

Focused test result:

- `11 passed in 0.23s`

Earlier full-suite result after the funding frame implementation, before the final offset fix:

- `66 passed in 101.65s`

## Focused OKO/Rydzyk Result

Command:

```powershell
uv run python main.py --input-dir tmp_funding_oko --glob "*.html" --output-dir output\funding_oko_20260415
```

Result:

- `relevant=true`
- `facts=4`
- `relations=3`
- `events=0`

Funding facts now extracted:

- Funded side: `Ministerstwo Kultury i Dziedzictwa Narodowego Fundacja Lux Veritatis`; funder: `Wojewodzki Fundusz Ochrony Srodowiska i Gospodarki Wodnej w Toruniu`; amount: `300 tys. zl`; confidence: `0.82`.
- Funded side: `Ministerstwo Kultury i Dziedzictwa Narodowego Fundacja Lux Veritatis`; funder: `Jastrzebskie Zaklady Remontowe`; amount: `100 tys. zl`; confidence: `0.82`.

The second fact is directionally improved after the offset fix. The sentence says the money was laid out by Jastrzebskie Zaklady Remontowe, and the output now uses that organization as the funder.

Remaining issue:

- The funded-side entity is over-merged with a later footer-like or structured-text mention: `Ministerstwo Kultury i Dziedzictwa Narodowego Fundacja Lux Veritatis`. This is a clustering/canonicalization problem, not a funding-role problem.

## Five-Article Subset

Command:

```powershell
uv run python main.py --input-dir tmp_funding_benchmark --glob "*.html" --output-dir output\funding_subset_20260415
```

Runtime:

- About 2m19s for 5 HTML inputs.
- Coref still reloads multiple times. This matches the earlier stability decision; syntax and relation extraction continue to run in one process.

Results:

- `niezalezna_polski2050_synekury`: relevant true, 12 facts, 2 relations, 0 events. Compensation facts for KZN salaries are still detected.
- `oko_miliony_pajeczyna_rydzyka`: relevant true, 4 facts, 3 relations, 0 events. Funding facts are now emitted for the public-money transfer examples.
- `olsztyn_roosevelta_negative`: relevant false, 0 facts, 0 relations, 0 events. Negative case stays clean.
- `olsztyn_wodkan`: relevant true, 5 facts, 1 relation, 0 events. Salary/compensation facts remain active.
- `radomszczanska_nowy_zaciag`: relevant true, 5 facts, 5 relations, 3 events. Governance extraction remains active.

## Current Takeaways

- Funding is now represented as its own scored fact family instead of being confused with compensation.
- Public grants/subsidies are in scope as koryciarstwo signals, but they should be scored and filtered downstream rather than forced into salary semantics.
- Directionality is better for postposed-funder constructions like `wylozyly takze <ORG>`.
- The next high-value quality issue is entity clustering hygiene: adjacent or footer-derived organization names can still merge into noisy canonical entities and then contaminate otherwise correct frames.
