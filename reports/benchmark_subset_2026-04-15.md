# Benchmark Subset - 2026-04-15

This snapshot records a small post-refactor benchmark run after the frame-first
pipeline cleanup.

Command:

```powershell
uv run python main.py --input-dir tmp_benchmark_inputs --glob "*.html" --output-dir output\benchmark_subset_20260415
```

Runtime:

- `163.84s` for 4 HTML inputs.
- The run used batch mode.
- `Stanza` coref loaded multiple times during the run. This is expected under the
  current memory strategy documented in `reports/runtime_memory_findings_2026-04-14.md`:
  keeping the same coref pipeline alive across multiple articles retains too much
  RAM, so repeated coref loading should not be treated as a new regression by itself.

## Articles Checked

### WP / Lubczyk dalej ciągnie kasę z Sejmu

Output:

- file: `output/benchmark_subset_20260415/2024-02-26T04_52_53.000Z_local-document.json`
- `relevant = true`
- `entities = 41`
- `facts = 6`
- `relations = 2`
- `events = 1`
- fact types:
  - `APPOINTMENT = 1`
  - `PARTY_MEMBERSHIP = 1`
  - `POLITICAL_OFFICE = 4`

What works:

- The article is treated as relevant, which matches the benchmark expectation for
  public-money / salary oversight articles.
- Some political-office and party information is extracted.

What fails:

- Salary/public-money extraction remains too weak for this type of article.
- There is a bad appointment-like extraction: `Wipler -> Sejmowych`.
- Person normalization is still inflected/noisy, for example `Radosław Lubczyka`.

Status:

- Correct relevance decision, weak domain extraction.
- This confirms that salary/remuneration articles still need a better public-money
  fact model rather than being forced into appointment semantics.

### Radomszczańska / Nowy zaciąg tłustych kotów

Output:

- file: `output/benchmark_subset_20260415/2024-06-29T10_15_00+00_00_local-document.json`
- `relevant = true`
- `entities = 20`
- `facts = 5`
- `relations = 5`
- `events = 3`
- score: `0.75`
- fact types:
  - `APPOINTMENT = 2`
  - `COMPENSATION = 1`
  - `FORMER_PARTY_MEMBERSHIP = 1`
  - `POLITICAL_OFFICE = 1`

What works:

- Main appointment shape is captured:
  - `Marku -> Amw Rewita`
  - role: `Wiceprezes`
- Board/management semantics are represented:
  - `APPOINTED_TO`
  - `MEMBER_OF_BOARD`
- Public-money compensation is captured:
  - `24 tys. zł brutto`
- Political affiliation is captured:
  - `Platforma Obywatelska`

What fails:

- Person normalization is still wrong: `Marek Rząsowski` appears as `Marku`.
- Organization normalization is still inflected/awkward: `Amw Rewita`.
- Duplicate appointment facts appear for the same person and organization, one with
  role and one without role.

Status:

- This is one of the better current benchmark results.
- Main remaining issues are normalization and duplicate governance-fact merging.

### Onet / Partyjny desant na Totalizator Sportowy

Output:

- file: `output/benchmark_subset_20260415/2024-09-30T05_39_00+0200_local-document.json`
- `relevant = true`
- `entities = 78`
- `facts = 17`
- `relations = 5`
- `events = 3`
- score: `0.4`
- fact types:
  - `APPOINTMENT = 3`
  - `PARTY_MEMBERSHIP = 2`
  - `POLITICAL_OFFICE = 12`

What works:

- The article is correctly treated as relevant.
- Some appointment extraction exists:
  - `Adam Sekuła -> Totalizatorze Sportowym`
  - `Anna Makarewicz -> Totalizatorze Sportowym`
- Director role extraction works in those examples:
  - role: `Dyrektor`
- Some party affiliation facts are extracted.

What fails:

- Coverage is far below the benchmark expectation for this article.
- Only 3 appointment facts are extracted, while the article should yield multiple
  regional-director / politically connected appointment findings.
- No compensation fact is extracted, despite the expected salary signal.
- No meaningful `RELATED_TO` political-network facts are extracted.
- One appointment target is wrong:
  - `Rafał Tyrcz -> Polska`
- Entity normalization is still noisy:
  - `Totalizatorze Sportowym`
  - `Prawa I Sprawiedliwości`
  - `Sławomir Czwalmateriały`
- Party extraction still produces weak or inflected party names in some cases.

Status:

- Relevant and non-empty, but still underperforming.
- Current bottlenecks are recall for repeated/list-style appointments, better
  compensation extraction, network/tie extraction, and stronger normalization.

### Olsztyn / Plac Roosevelta negative

Output:

- file: `output/benchmark_subset_20260415/2026-04-15_local-document.json`
- `relevant = false`
- `entities = 0`
- `facts = 0`
- `relations = 0`
- `events = 0`

What works:

- The negative example stays clean.
- No false appointment, party, or compensation facts were emitted.

Status:

- Correct negative behavior.

## Current Quality Summary

What improved or looks acceptable:

- The explicit frame-first pipeline still produces useful governance facts on a
  strong simple positive article (`Radomszczańska`).
- True-negative filtering remains good on the `Plac Roosevelta` article.
- Party-as-appointment-target failures are reduced compared with older snapshots,
  but not eliminated.

Main remaining issues:

- Entity normalization is now the most visible quality problem in the checked subset.
- Governance facts need better deduplication when the same appointment is emitted
  once with a role and once without one.
- List-style articles like `Totalizator` remain underextracted.
- Public-money salary/remuneration articles are relevant but do not yet have a
  dedicated fact model that captures the important money flow cleanly.
- Relationship/network extraction is still too weak for patronage articles.

## Suggested Next Focus

1. Improve normalization after extraction:
   person nominative restoration, organization casing, party canonicalization, and
   removal of boilerplate/token-glue artifacts.
2. Merge duplicate governance facts when subject and organization match and one fact
   has a role while the other lacks it.
3. Add a general public-money/remuneration fact model for salary articles instead of
   overloading appointment extraction.
4. Improve repeated appointment/list extraction for articles that enumerate many
   people and roles in parallel.
5. Revisit tie extraction once normalization and repeated appointment extraction are
   more stable.
