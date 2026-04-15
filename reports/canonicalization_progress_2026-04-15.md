# Canonicalization Progress - 2026-04-15

This snapshot records the entity canonicalization pass after strengthening the
single document canonicalizer and applying it again after registry linking.

## Command

```powershell
uv run python main.py --input-dir tmp_canonicalization_benchmark --glob "*.html" --output-dir output\canonicalization_subset_20260415
```

The temporary benchmark directory contained:

- `radomszczanska_nowy_zaciag.html`
- `onet_totalizator.html`
- `onet_wfosigw_lublin.html`
- `olsztyn_roosevelta_negative.html`

## Results

### Radomszczanska / Rzasowski

- `relevant = true`
- `facts = 5`
- `relations = 5`
- `events = 3`

What improved:

- `Marku` now resolves to `Marek Rząsowski`.
- `Amw Rewita` now resolves to `AMW Rewita`.
- `AMW Rewita` no longer collapses to the parent institution
  `Agencja Mienia Wojskowego`.
- `Prawo I Sprawiedliwość` now resolves to `Prawo i Sprawiedliwość`.

### Onet / Totalizator Sportowy

- `relevant = true`
- `facts = 24`
- `relations = 11`
- `events = 3`

What improved:

- `PSL` resolves to `Polskie Stronnictwo Ludowe`.
- `PO` resolves to `Platforma Obywatelska`.

Remaining issues:

- Some organization mentions remain inflected when no cleaner observed alias is
  available, for example `Totalizatora Sportowego w Lublinie`.
- Some noisy person spans remain, for example glued names from article text.
- The article still needs better repeated/list-style governance extraction.

### Onet / WFOSiGW Lublin

- `relevant = true`
- `facts = 15`
- `relations = 13`
- `events = 2`

What improved:

- Party names normalize to configured canonical names:
  `Polskie Stronnictwo Ludowe`, `Prawo i Sprawiedliwość`,
  `Platforma Obywatelska`.
- `NFOŚiGW` keeps acronym casing.
- `Rada Nadzorcza` no longer becomes an ungrammatical lemma phrase.

Remaining issues:

- Long public-institution names can remain inflected, because generated lemma
  display names were deliberately rejected after they produced ungrammatical
  Polish.

### Olsztyn / Plac Roosevelta negative

- `relevant = false`
- `facts = 0`
- `relations = 0`
- `events = 0`

The negative case stayed clean.

## Conclusion

The canonicalization pass improves high-impact output names without changing the
CLI or JSON contract. The implementation deliberately avoids generating
organization display names from multi-token lemmas, because that created bad
forms such as `Ministerstw Obrona Narodowy`. Lemmas are still useful for matching
and scoring, but observed aliases remain the source of display names unless a
configured party/institution alias applies.

Next quality focus:

1. Better noisy-span rejection for glued person names and article UI artifacts.
2. A structured remuneration/public-money frame.
3. Repeated/list-style governance extraction for Totalizator-style articles.
