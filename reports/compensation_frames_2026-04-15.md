# Compensation Frames Benchmark - 2026-04-15

This snapshot records the first pass of frame-owned salary/remuneration
extraction.

## Command

```powershell
uv run python main.py --input-dir tmp_compensation_benchmark --glob "*.html" --output-dir output\compensation_subset_20260415
```

The temporary benchmark directory contained:

- `niezalezna_polski2050_synekury.html`
- `olsztyn_roosevelta_negative.html`
- `olsztyn_wodkan.html`
- `onet_totalizator.html`
- `radomszczanska_nowy_zaciag.html`

Batch mode now uses the local HTML filename stem as the default document id, so
local files without source URLs no longer overwrite each other.

## Summary

Compensation extraction now runs through internal `CompensationFrame` objects and
emits existing `COMPENSATION` facts / `RECEIVES_COMPENSATION` relations from
those frames. The JSON output contract is unchanged.

Funding-style amounts are not treated as compensation frames. They remain
public-money/koryciarstwo signals, but should be handled by the funding frame
refactor rather than by salary/remuneration extraction.

## Results

### Niezalezna / Polski 2050 synekury

- `relevant = true`
- `facts = 12`
- `relations = 2`
- `events = 0`

Compensation frames:

- `31 tys. zł brutto`, confidence `0.55`, subject `Krajowy Zasób Nieruchomości`
- `11 tys. zł brutto`, confidence `0.55`, subject `Krajowy Zasób Nieruchomości`

Remaining issue:

- The amounts are correctly detected as remuneration, but person carryover is
  still weak in this article. The subject falls back to `KZN` instead of the
  person discussed in prior context.

### Olsztyn / Wodkan salary article

- `relevant = true`
- `facts = 5`
- `relations = 1`
- `events = 0`

Compensation frames:

- `322 030,80 zł`, confidence `0.74`, subject `Wiesław Pancer`, object
  `Przedsiębiorstwo Wodociągów i Kanalizacji w Olsztynie`
- `330 tys. zł`, confidence `0.74`, same subject/object
- `315 tys. zł`, confidence `0.74`, same subject/object
- `1,88 zł`, confidence `0.55`, subject `Wiesław Pancer`
- `2,53 zł`, confidence `0.55`, subject `Henryk Milcarz`

What improved:

- The salary article now passes relevance filtering.
- Public/municipal salary figures are represented as compensation facts.

Remaining issue:

- Per-resident cost figures are treated as compensation context because the
  clause contains salary wording. They are low confidence, but a later pass
  should distinguish direct salary from derived cost-per-resident figures.

### Onet / Totalizator Sportowy

- `relevant = true`
- `facts = 25`
- `relations = 10`
- `events = 3`

Compensation frames:

- `345 tys. zł`, confidence `0.55`, subject
  `Totalizator Sportowy` context
- `29 tys. zł`, confidence `0.55`, period `Miesięcznie`, same context

What improved:

- The yearly and monthly director-pay figures are now captured as compensation
  frames.

Remaining issue:

- Person/role carryover is still weak for list-style articles, so these facts
  are organization-context facts rather than person-specific salary facts.

### Radomszczanska / Rzasowski

- `relevant = true`
- `facts = 5`
- `relations = 5`
- `events = 3`

Compensation frames:

- `24 tys. zł brutto`, confidence `0.66`, subject `Marek Rząsowski`, object
  `AMW Rewita`

Remaining issue:

- The evidence refers to the predecessor of Rząsowski, so this is useful public
  salary context but the current carryover attribution is imperfect.

### Olsztyn / Plac Roosevelta negative

- `relevant = false`
- `facts = 0`
- `relations = 0`
- `events = 0`

The negative case stayed clean.

## Next Focus

1. Improve person/role carryover for compensation frames using previous-sentence
   subjects and governance frames.
2. Add a funding/public-money frame so grants and subsidies are first-class
   koryciarstwo signals instead of being handled by the old sentence extractor.
3. Separate direct remuneration from derived cost metrics such as
   `1,88 zł na mieszkańca`.
