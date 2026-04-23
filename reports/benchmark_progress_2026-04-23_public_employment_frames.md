# Benchmark Progress 2026-04-23: Public Employment Frames And Shared Enrichment

## Commands

```bash
uv run python scripts/setup_models.py
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --input-dir inputs --glob '*.html' --output-dir output/benchmark_20260423_public_employment_frames
```

The benchmark run below used a clean generated SQLite registry.

## Aggregate Result

- Inputs: 26
- Relevant: 23
- Facts: 414
- Output directory: `output/benchmark_20260423_public_employment_frames`

Fact-type totals in this run:

- `POLITICAL_OFFICE`: 209
- `APPOINTMENT`: 51
- `PERSONAL_OR_POLITICAL_TIE`: 49
- `PARTY_MEMBERSHIP`: 41
- `COMPENSATION`: 24
- `DISMISSAL`: 10
- `ELECTION_CANDIDACY`: 10
- `ROLE_HELD`: 5
- `FUNDING`: 5
- `FORMER_PARTY_MEMBERSHIP`: 2
- `PUBLIC_CONTRACT`: 2
- `ANTI_CORRUPTION_REFERRAL`: 2
- `PUBLIC_PROCUREMENT_ABUSE`: 2
- `ANTI_CORRUPTION_INVESTIGATION`: 2

## Confirmed Improvements

### Onet CBA/Ostrów

`wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe`

- Relevant: `true`
- Facts: `3`
- The run still emits the intended typed anti-corruption coverage:
  - `ANTI_CORRUPTION_INVESTIGATION`
  - `PUBLIC_PROCUREMENT_ABUSE`

### AI42/Poczesna

`ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`

- Relevant: `true`
- Facts: `19`
- Confirmed benchmark targets in the output:
  - `Rafał Dobosz`
  - `Artur Sosna`
  - cousin tie
  - `APPOINTMENT` for Dobosz with role `Pomoc Administracyjnej`
  - employer context on `Gminy Poczesna`

### Dziennik Polski/Charsznica

`dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715`

- Relevant: `true`
- Facts: `18`
- Confirmed benchmark targets in the output:
  - partner proxy facts
  - father-in-law proxy fact
  - public-office context on `Wójt`
  - `APPOINTMENT` for the partner proxy with role `Ekodoradcy`
- The previous bad direction where the public-office role itself became the employment target did not reappear in this run.

### WP/Opole

`wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`

- Relevant: `true`
- Facts: `31`
- Confirmed benchmark targets in the output:
  - partner and spouse ties
  - `Agnieszka Królikowska`
  - `Dariusz Jurek`
  - public-employment roles around `Dyrektor` / `Dyrektor Generalnym` / `Głównym Specjalista`
- The specific noisy label `Suwerenną Decyzja Wojewody Opolskiej` was not present in this run.

### Polsat/Ciechanów

`interwencja.polsatnews.pl__reportaz__2013-11-29__bardzo-rodzinne-starostwo_1329791`

- Relevant: `true`
- Facts: `23`
- Confirmed benchmark targets in the output:
  - `Sekretarz Powiatu`
  - `Starosta Ciechanowski`
  - named family context including `Joanna Pszczółkowska` and `Sławomir Morawski`
  - son / daughter-in-law proxy coverage
  - recovered public-employment-style facts for the sons

## Notable Side Effect Outside Planned Scope

Two WFOŚiGW Lublin fixtures now diverge in the batch benchmark:

- `onet_wfosigw_lublin`
  - Relevant: `true`
  - Facts: `21`
  - The run recovers governance facts including `Stanisław Mazur` and `Andrzej Kloc` with `Prezes` / `Rada Nadzorcza` style output.
- `wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt`
  - Relevant: `false`
  - Facts: `0`

This pass was not meant to fix WFOŚiGW relevance, so the important point is that the benchmark set now contains one improved fixture and one unchanged false negative for the same story family.

## Residual Issues

### WP/Opole Still Has Public-Employment Noise

The clean-registry benchmark no longer emits the exact rejected `Suwerenną Decyzja Wojewody Opolskiej` label, but the article still produces bad public-employment roles such as:

- `1 Luty 2024 Rok`
- `Partner Agnieszki Królikowska`
- `Szymon Ogłaz`
- `Agnieszka Królikowska`

This means the refactor fixed the worst visible label, but role-label boundary selection is still too permissive around nearby appositions and date/name spans.

### Charsznica Father-In-Law Employment Is Still Incomplete

The benchmark keeps the expected father-in-law proxy tie, but this run did not recover the expected `Pracownika Gospodarczego` employment fact for that proxy.

### Polsat/Ciechanów Still Has Noisy Role Labels

The article now recovers public-employment output for the family members, but some labels are still structurally wrong, for example:

- `Starszy Syn Sekretarz Pszczółkowskiej`
- `Potrzebna`

This remains a role-label extraction problem rather than a relevance or kinship problem.

### Known Relevance Problems Still Remain

- `rp_tk_negative` is still relevant with `0` facts.
- The canonical `wiadomosci.onet.pl__lublin__...__cpw9ltt` WFOŚiGW article remains irrelevant with `0` facts.

## Interpretation

The shared enrichment stage and frame-first public-employment path are doing the intended structural work:

- public-office role clusters are available earlier and reused across extractors,
- anti-corruption extraction still keeps its typed facts,
- public-employment facts now come from frames rather than the old fallback path,
- the benchmark recovers the intended Poczesna / Charsznica / Opole / Ciechanów article families at the document level.

The next bottleneck is not document routing anymore. It is role-label span control inside public-employment frames, especially where dates, names, partner phrases, or generic contextual nouns sit next to `stanowisko` / copular employment wording.
