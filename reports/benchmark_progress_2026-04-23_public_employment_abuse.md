# Benchmark Progress: Public Employment And Anti-Corruption Coverage

Date: 2026-04-23

## Commands

```bash
uv run python scripts/setup_models.py
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --input-dir inputs --glob '*.html' --output-dir output/benchmark_20260423_public_employment_abuse
```

The benchmark was run from a clean generated SQLite registry.

## Aggregate Result

- Inputs: 26
- Relevant: 23
- Facts: 349
- New typed facts emitted:
  - `ANTI_CORRUPTION_INVESTIGATION`: 2
  - `PUBLIC_PROCUREMENT_ABUSE`: 2

## Confirmed Improvements

### Onet CBA/Ostrów

`wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe`

- Relevant: true
- Facts: 3
- Extracted:
  - 2 `ANTI_CORRUPTION_INVESTIGATION` facts: CBA -> Wójt
  - 1 `PUBLIC_PROCUREMENT_ABUSE` fact: Wójt, evidence on ustawianie zamówień/zleceń remontowych

This unblocks the previous relevance/downstream gap for CBA/procurement abuse coverage.

### AI42/Poczesna

`ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`

- Relevant: true
- Facts: 18
- Extracted:
  - cousin tie for `Rafał Dobosz` / `Artur Sosna`
  - `APPOINTMENT` public-employment fact for `Rafał Dobosz` -> `Gminy Poczesna`
  - job label from the employment phrase: `Pomoc Administracyjnej`

The previous broad attachment to a generic resident was not present in this run.

### Dziennik Polski/Charsznica

`dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715`

- Relevant: true
- Facts: 19
- Extracted:
  - proxy partner facts for `swoją dziewczynę` and `partnerka wójta`
  - proxy father-in-law fact for `swojego przyszłego teścia`
  - `APPOINTMENT` public-employment fact for partner proxy with role `Ekodoradcy`
  - `APPOINTMENT` public-employment fact for father-in-law proxy with role `Pracownika Gospodarczego`

The governance path no longer emits public-office `Wójt` as an appointment role in this article.

### Polsat/Ciechanów

`interwencja.polsatnews.pl__reportaz__2013-11-29__bardzo-rodzinne-starostwo_1329791`

- Relevant: true
- Facts: 20
- Extracted family proxies include:
  - `syn sekretarz Pszczółkowskiej`
  - `Moja synowa`
  - `moją synową`

This confirms the expanded kinship/proxy vocabulary is active in the benchmark run.

## Residual Issues

### WP/Opole Public Employment Still Needs Work

`wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`

- Relevant: true
- Facts: 25
- Good:
  - partner tie: `partnerem Agnieszki Królikowskiej`
  - spouse tie: `Mąż wojewody Moniki Jurek`
- Still noisy:
  - public-employment emitted `Szymon Ogłaza` -> `Urząd Marszałkowski` with role `Suwerenną Decyzja Wojewody Opolskiej`

Next pass should tighten public-employment patient selection for clauses like `stanowisko dla swojej partnerki` and avoid treating official-response wording as the job label.

### Known Relevance Issues Remain

- `wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt` remains irrelevant with 0 facts.
- `rp_tk_negative` remains relevant but with 0 facts.

