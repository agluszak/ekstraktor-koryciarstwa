# New Article Benchmark Additions - 2026-04-23

## Scope

Added five new benchmark inputs requested on 2026-04-23:

- `inputs/dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715.html`
- `inputs/wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe.html`
- `inputs/ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm.html`
- `inputs/wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a.html`
- `inputs/interwencja.polsatnews.pl__reportaz__2013-11-29__bardzo-rodzinne-starostwo_1329791.html`

The Dziennik Polski live URL returned HTTP 403 in this environment, so the saved input uses:

- https://web.archive.org/web/20260422220715/https://dziennikpolski24.pl/kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom/ar/c1p2-28656825

Expected findings were added to `reports/expected_article_findings.md` before running the benchmark.

## Commands

Model setup and clean-registry benchmark:

```bash
uv run python scripts/setup_models.py
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
rm -rf output/benchmark_20260423_new_articles
uv run python main.py --input-dir inputs --glob '*.html' --output-dir output/benchmark_20260423_new_articles
```

Result:

- documents processed: 26
- relevant: 22
- facts: 285
- clean generated SQLite registry: yes, registry files were removed before the benchmark

False / expected-irrelevant outputs:

- `olsztyn_roosevelta_negative`: irrelevant, 0 facts
- `wp_meloni_negative`: irrelevant, 0 facts
- `rp_tk_negative`: still a relevance false positive, 0 facts

Known positive misses:

- `wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe`: false negative, 0 facts
- `wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt`: still false negative, 0 facts

## New Article Comparison

### Dziennik Polski / Charsznica

Output:

- relevance: true, score 1.0
- facts: 5
- recovered useful entities:
  - `Tomasz Kościelniak`
  - `Urzędzie Stanu Cywilnego`
  - `Urzędu Gminy`
  - `Klub Seniora`
  - `Rady Gminy`
  - `Prawo i Sprawiedliwość`
  - `Paweł Janicki`
- recovered useful facts:
  - `Paweł Janicki -> PARTY_MEMBERSHIP -> Prawo i Sprawiedliwość`
  - `Tomasz Kościelniak -> ELECTION_CANDIDACY`
  - `Tomasz Kościelniak -> APPOINTMENT -> Urzędzie Stanu Cywilnego`

Comparison:

- Correctly relevant.
- The `Urząd Stanu Cywilnego` fact is directionally related to the article, but target/subject assignment is wrong: the expected candidate is the unnamed partner of the wójt, not Tomasz Kościelniak or the letter writer `Jan Kowalski`.
- Missing the core partner/family proxy facts:
  - partner / girlfriend employment as `ekodoradca`
  - future father-in-law, sister-in-law, brother's wife, and sister-in-law's boyfriend employment contexts
  - partner relationship to Tomasz Kościelniak
- This is a strong regression target for unnamed kinship proxy extraction and employment facts outside company-board contexts.

### Onet / CBA Wójt Gminy Ostrów

Output:

- relevance: false, score 0.3
- facts: 0
- entities: none, because relevance filtering stopped the pipeline

Comparison:

- This is a clear false negative.
- The article contains strong in-scope cues:
  - `Centralne Biuro Antykorupcyjne`
  - `wójt gminy Ostrów`
  - `zamówienia publiczne`
  - `ustawiając zlecenia prac remontowych`
  - `przyjmował osoby do pracy w urzędzie w zamian za łapówki`
  - amounts `5 tys. zł`, `2 tys. zł`, and `20 tys. zł`
- The current relevance layer still misses anti-corruption / bribery / public-procurement stories when there is no named politician, family tie, or board appointment.
- This should be handled as a general relevance and fact-model gap, not as an article-specific regex patch.

### AI42 / Poczesna

Output:

- relevance: true, score 0.65
- facts: 0
- recovered useful entities:
  - `Gminy Poczesna`
  - `Rafał Dobosz`
  - `Artur Sosna`

Comparison:

- Correctly relevant and recovers the two main people plus municipality.
- Missing all expected facts:
  - `Rafał Dobosz -> employment/APPOINTMENT -> Urząd Gminy / Gmina Poczesna`
  - `Rafał Dobosz -> FAMILY/kuzyn -> Artur Sosna`
  - `Artur Sosna -> POLITICAL_OFFICE -> wójt`
- This is a clean small article for implementing non-board public-employment extraction plus cousin/family kinship detail.

### WP / Opole

Output:

- relevance: true, score 1.0
- facts: 14
- recovered useful entities:
  - `Agnieszk Królikowski` (normalization/lemmatization artifact)
  - `Monika Jurek`
  - `Szymon Ogłaz` (normalization/lemmatization artifact)
  - `Dariusz Jurek`
  - `Platforma Obywatelska`
  - `Generalnego Opolskiego Urzędu Wojewódzkiego`
  - `Biurze Bezpieczeństwa Urzędu Marszałkowskiego Województwa Opolskiego`
- recovered useful facts:
  - `Partner Królikowski -> PERSONAL_OR_POLITICAL_TIE/partner -> Agnieszk Królikowski`
  - `Szymon Ogłaz -> PARTY_MEMBERSHIP -> Platforma Obywatelska`
  - `Monika Jurek -> POLITICAL_OFFICE -> Wojewoda`
  - `Agnieszk Królikowski -> APPOINTMENT -> Generalnego Opolskiego Urzędu Wojewódzkiego`
  - `Pani Agnieszka -> APPOINTMENT -> Generalnego Opolskiego Urzędu Wojewódzkiego`

Comparison:

- Correctly relevant and partially useful.
- It recovers the broad Opole office structure and one partner proxy, but misses or misassigns key expected facts:
  - no direct `Agnieszka Królikowska -> partner -> Szymon Ogłaza`
  - no `Dariusz Jurek -> spouse -> Monika Jurek`
  - no `Dariusz Jurek -> employment/APPOINTMENT -> Urząd Marszałkowski / Biuro Bezpieczeństwa`
  - public-office extraction overattaches `Wojewoda` to several people, including Agnieszka Królikowska and Jarosław Draguć
  - one false appointment target appears as `Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie`, which is unrelated to the article and likely comes from registry/linking contamination or an over-broad canonical match
- This is the best new case for public-function target/context cleanup around `wojewoda` and `marszałek województwa`.

### Polsat Interwencja / Ciechanów

Output:

- relevance: true, score 0.7
- facts: 1
- recovered useful entities:
  - `Starostwo Powiatowe w Ciechanowie`
  - `Joann Pszczółkowski` (normalization/lemmatization artifact)
  - `Powiatowego Centrum Pomocy Rodzinie w Ciechanowie`
  - `Powiatowego Zarządu Dróg w Ciechanowie`
  - `Bartosz`
  - `Jakub Mieszko`
  - `Jakub Mieszko Pszczółkowski`
  - `Sławomir Morawski`
  - `Sekretarz Powiatu`
- recovered facts:
  - `Joann Pszczółkowski -> APPOINTMENT -> Powiatowego Centrum Pomocy Rodzinie w Ciechanowie`

Comparison:

- Correctly relevant and recovers many of the institutions and names.
- The only fact is wrong for the main expected relation: Joanna Pszczółkowska did not get the PCPR job; her husband did.
- Missing the key proxy-relative employment and kinship facts:
  - husband and brother-in-law at PCPR
  - Bartosz Pszczółkowski at Powiatowy Zarząd Dróg
  - Jakub Mieszko Pszczółkowski as coordinator of `e-Integracja`
  - daughter-in-law of Sławomir Morawski at Powiatowy Urząd Pracy
- Missing public-function facts:
  - `Joanna Pszczółkowska -> sekretarz powiatu`
  - `Sławomir Morawski -> starosta`
- This is the best new case for unnamed family proxy preservation in county-level institutions.

## Immediate Follow-Up Targets

1. Relevance: add general anti-corruption / bribery / public-procurement support so the Onet CBA/Ostrów article is not filtered out.
2. Public employment facts: support non-board public-office employment such as `pomoc administracyjna`, `ekodoradca`, `główny specjalista`, `koordynator projektu`, and county/municipal unit jobs.
3. Public-function recognition: add robust handling for `wójt`, `starosta`, `sekretarz powiatu`, `marszałek województwa`, and `wojewoda` as office/context facts rather than appointment targets.
4. Family/proxy kinship: extend proxy-relative handling to `partnerka`, `dziewczyna`, `kuzyn`, `mąż`, `szwagier`, `syn`, `synowa`, `teść`, `bratowa`, and related in-law forms, without rewriting uncertain proxies onto named people.
5. Entity normalization: reduce Polish-name lemmatization artifacts visible in new outputs (`Agnieszk Królikowski`, `Szymon Ogłaz`, `Joann Pszczółkowski`) before hard-promoting the new target assertions.
