# Benchmark Progress 2026-04-21

Clean-registry batch run:

- Removed `output/entity_registry.sqlite3`, `output/entity_registry.sqlite3-shm`, and
  `output/entity_registry.sqlite3-wal` before running.
- Command: `uv run python main.py --input-dir inputs --glob "*.html" --output-dir output`
- Model assets were checked first with `uv run python scripts/setup_models.py`.

## What Changed

- Added document-level extraction context for bounded sentence-window lookup.
- Governance frame extraction now carries person, role, target organization, owner context, and
  evidence across adjacent sentences/paragraphs instead of relying only on one clause.
- Mention provenance now keeps `start_char`, `end_char`, and `paragraph_index` from NER through
  clustering, with a sentence-text fallback for coreference/manual mentions.
- Inflected party aliases such as `Polskiego Stronnictwa Ludowego` resolve to the canonical party.
- Added adjacent-sentence party-profile extraction for headline-style party context followed by a
  person sentence.
- Suppressed `przekazać` funding frames without an amount unless the clause has explicit grant or
  subsidy language.

## Checked Articles

- `pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni`
  now emits 3 facts:
  - `A. Góralczyk -> APPOINTMENT -> Stadnina Koni Iwno Sp.`, role `Prezes`
  - `Przemysław Pacie -> DISMISSAL -> Stadnina Koni Iwno Sp.`, role `Prezes`
  - `A. Góralczyk -> PARTY_MEMBERSHIP -> Polskie Stronnictwo Ludowe`
- Strong governance positives still emit governance output:
  - `onet_totalizator`: 31 facts, including appointment/dismissal facts
  - `radomszczanska`: 6 facts, including appointment and compensation
  - `olsztyn.tvp`: 1 appointment fact
  - `wiadomosci.onet.pl__...ezt8y9t`: 23 facts, including Natura Tour governance output
  - `zona-posla-pis`: 10 facts
- Salary/funding positives still emit:
  - `olsztyn_wodkan`: 5 compensation facts
  - `niezalezna_polski2050_synekury`: KZN compensation still present
  - `oko_miliony_pajeczyna_rydzyka`: 6 facts, including WFOŚiGW and JZR funding facts
- True negatives:
  - `olsztyn_roosevelta_negative`: irrelevant, 0 facts
  - `wp_meloni_negative`: irrelevant, 0 facts
  - `rp_tk_negative`: still relevance-positive, but 0 facts

## Regressions / Remaining Issues

- Pleszew person and organization normalization is still imperfect:
  `Przemysław Pacia` canonicalizes as `Przemysław Pacie`, and the target is
  `Stadnina Koni Iwno Sp.` rather than the cleaner `Stadnina Koni Iwno`.
- `KOWR` is no longer used as an appointment target, but owner/controller context for Pleszew is
  currently represented mainly through `Skarbu Państwa`; fuller KOWR owner context still depends on
  longer-range context modeling.
- Some older noisy governance/person merges remain visible outside this change, especially in
  Totalizator-style long articles.
- `wiadomosci.onet.pl__lublin__...cpw9ltt` remains filtered out as irrelevant, unchanged by this
  extraction-focused refactor.
- `oko_miliony_pajeczyna_rydzyka` still has two amountless funding facts from grant/subsidy or
  `wyłożyć` contexts; the communication-style `przekazać` no-amount false positives are gone from
  the final batch run.

## Next Bottleneck

The next useful step is entity hygiene in long articles: better canonicalization for inflected
person names and company suffix cleanup, followed by safer long-document person clustering.
