# Scored Secondary Facts Benchmark - 2026-04-15

This snapshot records the benchmark subset after adding confidence metadata for
secondary fact extractors.

Command:

```powershell
uv run python main.py --input-dir tmp_benchmark_inputs --glob "*.html" --output-dir output\benchmark_subset_20260415_scored
```

Runtime:

- `148.84s` for 4 HTML inputs.
- Repeated Stanza coref loading is expected under the current memory strategy
  documented in `reports/runtime_memory_findings_2026-04-14.md`.

## Summary

The secondary extractors now attach filterable metadata:

- `source_extractor`
- `extraction_signal`
- `evidence_scope`
- `overlaps_governance`
- `score_reason`

This makes overgeneration easier to tolerate because downstream filtering can
separate high-confidence direct facts from broad contextual facts.

## Results

### WP / Lubczyk dalej ciągnie kasę z Sejmu

Output:

- file: `output/benchmark_subset_20260415_scored/2024-02-26T04_52_53.000Z_local-document.json`
- `relevant = true`
- `facts = 10`
- `high_confidence_facts >= 0.7 = 5`
- `secondary_facts = 9`
- `relations = 4`
- `events = 1`

Secondary facts by source:

- `compensation = 3`
- `political_profile = 6`

What changed:

- The article now produces compensation facts, which is directionally correct for
  salary/public-money articles.
- Some compensation facts are deliberately low confidence:
  - `same_sentence / amount_person`
  - `same_paragraph / amount_public_org`

Remaining issue:

- The article still contains an appointment-like false positive.
- Compensation coverage is now higher recall, but needs downstream filtering and
  later remuneration-frame work.

### Radomszczańska / Rząsowski

Output:

- file: `output/benchmark_subset_20260415_scored/2024-06-29T10_15_00+00_00_local-document.json`
- `relevant = true`
- `facts = 5`
- `high_confidence_facts >= 0.7 = 4`
- `secondary_facts = 4`
- `relations = 5`
- `events = 3`

Secondary facts by source:

- `compensation = 1`
- `political_profile = 3`

What changed:

- Duplicate governance appointment is gone in this run:
  - current `APPOINTMENT = 1`
- Compensation is scored as `0.72` with reason `amount_person_org`.
- Party/profile facts now carry scoring metadata.

Remaining issue:

- Person and organization normalization remain inflected/noisy.

### Onet / Totalizator Sportowy

Output:

- file: `output/benchmark_subset_20260415_scored/2024-09-30T05_39_00+0200_local-document.json`
- `relevant = true`
- `facts = 23`
- `high_confidence_facts >= 0.7 = 12`
- `secondary_facts = 20`
- `relations = 10`
- `events = 3`

Secondary facts by source:

- `compensation = 1`
- `political_profile = 19`

What changed:

- Secondary profile coverage increased, which is expected under the high-recall
  approach.
- A compensation fact is now emitted where the earlier run missed salary/public-money
  information.
- High-confidence filtering is now meaningful: 12 of 23 facts are at least `0.7`.

Remaining issue:

- The article is still underextracted for appointment/network structure.
- Many new profile facts are contextual and should be filtered downstream unless
  high confidence.
- Entity normalization remains a major quality bottleneck.

### Olsztyn / Plac Roosevelta negative

Output:

- file: `output/benchmark_subset_20260415_scored/2026-04-15_local-document.json`
- `relevant = false`
- `facts = 0`
- `relations = 0`
- `events = 0`

Status:

- The negative case stayed clean.

## Current Conclusion

The scored-secondary-facts pass behaves as intended:

- raw fact counts can increase
- low-confidence facts are explicitly marked
- high-confidence counts can now be compared separately
- the negative article remains clean
- governance target quality did not visibly regress in the subset

Next likely focus:

1. Normalize entities after extraction, especially inflected person and organization names.
2. Add a real remuneration/public-money frame so salary facts become structured rather than incidental.
3. Improve repeated/list-style governance extraction for Totalizator-style articles.
