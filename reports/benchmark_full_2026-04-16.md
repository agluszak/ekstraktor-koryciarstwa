# Full Benchmark Snapshot - 2026-04-16

## Command

The benchmark was run from a clean generated SQLite registry:

```powershell
Remove-Item output\entity_registry.sqlite3*
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output\benchmark_20260416
```

Runtime: about 10m15s for 23 HTML inputs.

Note: Stanza coref still reloads per article by design, matching the earlier stability decision.

## Aggregate Result

- Inputs: 23
- Relevant outputs: 20
- Irrelevant outputs: 3
- Total facts: 177
- Total relations: 94
- Total events: 29

High-level fact families observed:

- `APPOINTMENT`: present in major appointment/patronage articles.
- `DISMISSAL`: present in `zona-posla-pis` and WFOŚiGW/Lublin-style governance examples where relevance allows processing.
- `COMPENSATION`: present in salary/public-money articles, including Wodkan and KZN.
- `FUNDING`: present in OKO/Rydzyk; also currently overfires on some `przekazać` communication contexts.

## Confirmed Improvements

### OKO/Rydzyk Funding

Both OKO copies now extract clean funding facts:

- `Fundacja Lux Veritatis` funded by `Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu`, amount `300 tys. zł`, confidence `0.82`.
- `Fundacja Lux Veritatis` funded by `Jastrzębskie Zakłady Remontowe`, amount `100 tys. zł`, confidence `0.82`.

The previous joined entity name `Ministerstwo Kultury i Dziedzictwa Narodowego Fundacja Lux Veritatis` no longer appears in this clean-registry benchmark output.

### Negative Cases

- `olsztyn_roosevelta_negative`: irrelevant, 0 facts, 0 relations, 0 events.
- `wp_meloni_negative`: irrelevant, 0 facts, 0 relations, 0 events.
- `rp_tk_negative`: still marked relevant, but emits 0 facts, 0 relations, 0 events.

The RP TK article remains a relevance false positive, but downstream extraction stays clean.

## Strong Positive Coverage

Examples with useful extraction:

- `onet_totalizator` / Onet Totalizator copy: 25 facts, 10 relations, 3 events.
- `onet_wfosigw_lublin`: 15 facts, 13 relations, 2 events.
- `radomszczanska_nowy_zaciag` / Radomszczańska copy: 5 facts, 5 relations, 3 events.
- `tvp_olsztyn_sloma_wodociagi` / TVP Olsztyn copy: 1 fact, 2 relations, 2 events.
- `zona-posla-pis`: 10 facts, 6 relations, 4 events.
- `wiadomosci.onet.pl__kraj__tak-psl-obsadzil...`: 15 facts, 6 relations, 2 events.

Salary/public-money coverage:

- `olsztyn_wodkan`: 5 compensation facts.
- `niezalezna_polski2050_synekury` and its duplicate: 2 compensation facts each for KZN salary amounts.

## Main Regressions Or Misses

### WFOŚiGW Lublin URL-Slug Copy Is Filtered Out

`wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt`

- Relevance: false.
- Score: `0.2`.
- Reason: only `contains person-like full name`.
- Facts/relations/events: all 0.

This is a strong positive article by expectation, so relevance filtering is too strict for this article variant. The shorter `onet_wfosigw_lublin` copy does extract useful facts, so this may be input-content extraction or boilerplate/cleaned-text differences rather than relation extraction itself.

### Pleszew Stadnina Article Emits Nothing

`pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni`

- Relevance: true.
- Facts/relations/events: all 0.

This is a strong appointment case by title and benchmark expectation. The failure is after relevance, likely in sentence segmentation, NER, clause parsing, or governance-frame target/person role resolution.

### Funding False Positives In Communication Contexts

Funding overfires on `przekazać` when it means "communicated/told us", not money transfer:

- `wiadomosci.wp.pl__odpartyjnienie...`: `Grupy Wirtualnej Polski -> Fundusz`, no amount.
- `wiadomosci.wp.pl__odpartyjnienie...`: `Społecznych Inicjatywach Mieszkaniowych -> Grupy Wirtualnej Polski`, no amount.
- `wp_lubczyk`: `Społecznych Inicjatywach Mieszkaniowych -> Konfederacja`, no amount.

This suggests funding frames should require stronger money-transfer evidence when no amount is present, and `przekazać` should be disambiguated by dependency/object context rather than treated as a generic funding trigger.

## Next Quality Targets

1. Relevance: debug why the URL-slug WFOŚiGW Lublin article is filtered out while the shorter duplicate passes.
2. Governance: debug the Pleszew Stadnina case, which is relevant but produces no facts.
3. Funding: add dependency/context disambiguation for `przekazać`, especially to suppress communication/reporting contexts with no amount.
4. Relevance: reduce false positive relevance for generic legal/TK articles like `rp_tk_negative`, while keeping salary and appointment articles in scope.
