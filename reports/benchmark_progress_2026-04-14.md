# Benchmark Progress - 2026-04-14

This snapshot records the current pipeline behavior on the main positive benchmark set after:

- warm runtime support
- batch and worker execution modes
- parser-driven fact extraction using spaCy NER plus Stanza parse/coref

## Summary

The pipeline is now materially better than the earlier entity-only state, but it is still not reliable enough on appointment target selection and political-party anchoring.

Current status by article:

- `Totalizator`: structurally improved, still noisy
- `Radomszczańska`: clear improvement, one of the best current results
- `WFOŚiGW Lublin`: partially improved, still misanchors some appointments
- `OKO.press / Rydzyk`: funding extraction now exists
- `TVP Olsztyn / Jarosław Słoma`: preprocessing works, extraction still fails
- `TVN24 archive`: fake kinship issue is gone, but real patronage structure is still underextracted

## Per-Article Snapshot

### Onet / Totalizator Sportowy

Output:
- file: [2024-09-30T05_39_00+0200_7nvq01b.json](/D:/extractor/output/2024-09-30T05_39_00+0200_7nvq01b.json:1)
- `relevant = true`
- `entities = 120`
- `facts = 22`
- `relations = 14`
- `events = 4`
- `score = 0.75`

What works:
- appointment events are no longer empty
- some appointment and political-network structure is extracted

What fails:
- party assignment is still noisy
- appointment targets are still partially wrong
- malformed entities still appear

Examples:
- good-ish: `Rafał Krzemień -> Polskim Holdingu Nieruchomości`
- wrong: `Donald Tusk -> Polskie Stronnictwo Ludowe`

### Radomszczańska / Nowy zaciąg tłustych

Output:
- file: [2024-06-29T10_15_00+00_00_nowy-zaciag-tlustych-n1256470.json](/D:/extractor/output/2024-06-29T10_15_00+00_00_nowy-zaciag-tlustych-n1256470.json:1)
- `relevant = true`
- `entities = 25`
- `facts = 5`
- `relations = 5`
- `events = 1`
- `score = 0.95`

What works:
- main appointment is extracted
- party tie is extracted
- this is currently one of the strongest benchmark results

Examples:
- `Marek Rząsowski -> AMW Rewita -> Wiceprezes`
- `Marek Rząsowski -> Platforma Obywatelska`

Remaining issue:
- still contains one unrelated personal tie from noisy article context

### Onet / WFOŚiGW Lublin

Output:
- file: [2024-03-13T18_46_40+0100_cpw9ltt.json](/D:/extractor/output/2024-03-13T18_46_40+0100_cpw9ltt.json:1)
- `relevant = true`
- `entities = 48`
- `facts = 8`
- `relations = 10`
- `events = 3`
- `score = 0.7`

What works:
- dismissal extraction improved
- some appointment structure is now present

What fails:
- one main appointment is still misanchored to a party
- board / institution targets are still inconsistent

Examples:
- good: `Agnieszka Kruk -> WFOŚiGW w Lublinie -> Prezes` as dismissal
- wrong: `Stanisław Mazur -> Lewicy -> Prezes`

### Niezależna / Synekury Polski 2050

Output:
- file: [2024-09-30T05_39_00+0200_local-document.json](/D:/extractor/output/2024-09-30T05_39_00+0200_local-document.json:1)
- this run reused the previous saved document id
- behavior is still in the same class as before: many facts, but semantics remain noisy

Status:
- not re-audited in detail in this pass
- still expected to be higher-recall than higher-precision

### OKO.press / Miliony, pajęczyna Rydzyka

Output:
- file: [25 września 2020_miliony-pajeczyna-rydzyka.json](</D:/extractor/output/25 września 2020_miliony-pajeczyna-rydzyka.json:1>)
- `relevant = true`
- `entities = 42`
- `facts = 5`
- `relations = 1`
- `events = 0`
- `score = 0.35`

What works:
- funding extraction now exists
- this article is no longer entity-only

Example:
- `Lux Veritatis -> Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu -> 300 tys. zł`

What fails:
- still very partial compared with the article complexity
- political-profile facts around Rydzyk are noisy and not yet useful

### TVP Olsztyn / Jarosław Słoma

Output:
- file: [2026-04-14_z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow.json](/D:/extractor/output/2026-04-14_z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow.json:1)
- `relevant = true`
- `entities = 4`
- `facts = 0`
- `relations = 0`
- `events = 0`
- `score = 0.0`

What works:
- preprocessing no longer crashes

What fails:
- extraction still produces nothing useful

### TVN24 archive / Kolesiostwo i rozdawanie posad

Output:
- file: [2013-05-06T20_18_00.000Z_kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831.json](/D:/extractor/output/2013-05-06T20_18_00.000Z_kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831.json:1)
- `relevant = true`
- `entities = 21`
- `facts = 11`
- `relations = 5`
- `events = 0`
- `score = 0.4`

What works:
- fake kinship issue from substring matching is gone
- some political-profile extraction exists

What fails:
- patronage structure is still underextracted
- party/office facts are too eager on broad context
- no dismissal or appointment event is extracted

Examples:
- extracted: `Doroda Połedniok -> Platforma Obywatelska`
- extracted: `Jacek Guzy -> Prezydent Miasta`
- still missing: actual municipal patronage / appointments described by the article

## Main Current Bottlenecks

1. Appointment target selection still confuses parties, offices, and organizations.
2. Party extraction is too eager and still fires from broad sentence context.
3. Political-profile extraction is often cleaner than before, but still overproduces facts.
4. `TVP Olsztyn` remains a hard downstream extraction miss.
5. Complex network articles like `OKO.press / Rydzyk` still need much better relation coverage.

## Immediate Next Focus

- tighten appointment target resolution so parties cannot become appointment destinations
- reduce over-eager party/profile extraction from long context sentences
- improve appositive and title-based appointment parsing for short local-news articles like `Jarosław Słoma`

## Update After Typing And Governance Pass

After the next generalization pass on 2026-04-14:

- sentence splitting no longer breaks `A. Góralczyk` into `A.` + surname fragments
- short local-news title/lead structures improved through longer role spans and paragraph-local governance carryover
- weak one-letter person mentions are suppressed from the candidate graph

Observed benchmark changes:

- `TVP Olsztyn / Jarosław Słoma`
  - improved from `Prezes` to `Zastępca Prezesa`
  - still only one core appointment fact, but it is now materially closer to the article

- `Pleszew24 / stadnina koni`
  - improved from `0` facts to:
    - `APPOINTMENT = 1`
    - `DISMISSAL = 1`
    - `PARTY_MEMBERSHIP = 1`
  - still noisy on organization targeting and person normalization, but no longer entity-only

- `WP / odpartyjnienie rad nadzorczych`
  - party overfire improved substantially
  - current snapshot:
    - `facts = 10`
    - `party_facts = 0`
    - `appointments = 1`

- `Onet / Natura Tour / PSL`
  - governance extraction improved materially
  - current snapshot:
    - `APPOINTMENT = 5`
    - `DISMISSAL = 2`
    - `PARTY_MEMBERSHIP = 1`
    - `events = 7`

- `WFOŚiGW Lublin`
  - governance count improved, but the biggest remaining problem is now obvious:
    - `PARTY_MEMBERSHIP = 11`
    - `APPOINTMENT = 2`
    - `DISMISSAL = 1`
  - this article is still dominated by party/profile overextraction

## Update After WTC Poznań Benchmark Addition

Article:
- `Głos Wielkopolski / Nowy prezes WTC Poznań...`
- canonical benchmark source is the Wayback snapshot:
  [webarchive 2025-01-20](https://web.archive.org/web/20250120123235/https://gloswielkopolski.pl/nowy-prezes-wtc-poznan-spolki-podleglej-mtp-wybrany-bez-konkursu-ma-dyplom-collegium-humanum/ar/c1p2-27186205)

Pipeline run result:
- live URL and archived URL produced materially the same extraction output
- `relevant = true`
- `score = 0.85`
- main appointee `Jarosław Nowak` was extracted correctly
- `Lena Bretes-Dorożała`, `Jacek Jaśkowiak`, and `Collegium Humanum` were also extracted as entities

What works:
- the article is correctly treated as in-scope
- the title and body are sufficient for non-empty governance extraction
- `Jarosław Nowak` gets appointment facts with role `Prezes`

What fails:
- the main appointment target is still misanchored:
  - one `APPOINTED_TO` goes to `Platformy Obywatelskiej`
  - another goes only to `WTC` instead of a cleaner `WTC Poznań` / `World Trade Center Poznań`
- no clean `Jarosław Nowak -> Platforma Obywatelska` party-affiliation fact is produced
- no dismissal / replacement fact is produced for `Lena Bretes-Dorożała`
- parent-company context is weak:
  - `MTP` is extracted, but canonicalization remains poor (`Międzynarodowym Targom Poznańskim`)
- entity noise remains substantial, including false people such as:
  - `World Trade`
  - `Center Poznań`
  - `Nominacja Nowaka`
  - `Zarówno Nowak`

Comparison against expectation:
- good:
  - relevance
  - main person
  - role extraction
  - some appointment signal
- still below benchmark:
  - target organization resolution
  - party affiliation
  - dismissal/change event for prior prezeska
  - clean WTC <-> MTP parent/company context

Current verdict:
- this article is now clearly detectable as a positive benchmark
- extraction quality is still below expectation because the core `Jarosław Nowak -> WTC Poznań` appointment is not cleanly anchored

## Update After Current Warm Benchmark Rerun

This rerun used a warm sequential process over a 10-article positive benchmark subset from `inputs/`.

Operational note:
- total wall time was about `316s`
- long articles are still expensive because the Stanza coref pipeline is rebuilt per article for memory safety

### Current Strength Ranking

Strongest current results:
- `TVP Olsztyn / Jarosław Słoma`
- `Do Rzeczy / AMW`
- `Radomszczańska`

Partial but still noisy:
- `Onet / Natura Tour / PSL`
- `Onet / Totalizator`
- `OKO.press / Rydzyk`

Weakest current positives:
- `WFOŚiGW Lublin`
- `Niezależna / KZN`
- `RP / Klich`
- `WP / rady nadzorcze`
- `Pleszew24`

### Current Warm Snapshot

#### Radomszczańska

- `relevant = true`
- `facts = 7`
- `relations = 7`
- `events = 1`
- `score = 0.75`
- runtime: `30.83s`

What improved:
- the core governance structure is present
- party/history signal exists
- compensation is extracted

What still fails:
- target anchoring is still not clean enough
- person/entity dedup is still weak

Examples:
- extracted: `Rząsowski -> Agencja Mienia Wojskowego -> Wiceprezes`
- expected benchmark target is still closer to `AMW Rewita`
- duplicates still appear as `Rząsowski` / `Rząsowskiego`

#### WFOŚiGW Lublin

- `relevant = true`
- `facts = 14`
- `relations = 17`
- `events = 3`
- `score = 0.7`
- runtime: `29.59s`

What works:
- the article is clearly in scope
- output is non-empty
- dismissals/appointments/events exist

What fails:
- party/profile overfire still dominates
- institution dedup is still poor
- clean Mazur/Kloc governance anchoring is still missing

Examples:
- duplicated institution forms:
  - `Wojewódzkim Funduszem Ochrony Środowiska i Gospodarki Wodnej w Lublinie`
  - `Wfośigw W Lublinie`
- bad party facts still appear for both Mazur and Kloc

#### Onet / Totalizator

- `relevant = true`
- `facts = 26`
- `relations = 21`
- `events = 7`
- `score = 0.7`
- runtime: `50.47s`

What works:
- structurally rich output
- appointments/dismissals/events are no longer missing

What fails:
- bogus subjects still appear
- target/subject normalization is still weak
- some party facts are still clearly wrong

Examples:
- extracted bad subject: `Janowa Lubelskiego -> Polskie Stronnictwo Ludowe`
- extracted bad office fact: `Janowa Lubelskiego -> Radny`

#### Onet / Natura Tour / PSL

- `relevant = true`
- `facts = 22`
- `relations = 20`
- `events = 8`
- `score = 0.9`
- runtime: `45.88s`

What works:
- many governance facts now exist
- `Jolanta Sobczyk` and `Natura Tour` are in the graph
- dismissal/change structure is present

What fails:
- one main appointment still points too broadly to `Polskie Koleje Państwowe`
- bogus location/ministry office facts still appear

Examples:
- good: `Jolanta Sobczyk -> Natura Tour -> Członek Zarządu`
- still bad: `Jolanta Sobczyk -> Polskie Koleje Państwowe -> Prezes`

#### Niezależna / KZN

- `relevant = true`
- `facts = 11`
- `relations = 9`
- `events = 3`
- `score = 0.7`
- runtime: `32.61s`

What works:
- article is not empty anymore
- some political-office and tie facts exist

What fails:
- benchmark core still missing
- clean `Łukasz Bałajewicz -> KZN -> prezes` extraction is still not there
- too many generic office facts, too few useful governance facts

Examples:
- extracted: `Katarzyna Pełczyńska-Nałęcz -> Ministerstwo Funduszy i Polityki Regionalnej -> Minister`
- still missing: clean KZN leadership appointment

#### OKO.press / Rydzyk

- `relevant = true`
- `facts = 13`
- `relations = 7`
- `events = 0`
- `score = 0.75`
- runtime: `38.02s`

What works:
- public-money/funding extraction exists
- money amounts are being recovered

What fails:
- malformed subjects remain
- irrelevant candidacy noise remains
- institution canonicalization is still poor

Examples:
- extracted: `Parku Pamięci -> Narodowego Instytutu Wolności -> 520 tys. zł`
- extracted: `Toruniu Parku -> Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu -> 300 tys. zł`

#### TVP Olsztyn / Jarosław Słoma

- `relevant = true`
- `facts = 1`
- `relations = 3`
- `events = 1`
- `score = 0.2`
- runtime: `11.77s`

What works:
- this is now one of the cleanest current positives
- the expected appointment is present

Example:
- `Jarosław Słoma -> Przedsiębiorstwa Wodociągów i Kanalizacji -> Zastępca Prezesa`

Remaining issue:
- organization canonicalization is still not ideal
- `Wodkan` is still misclassified as a person

#### Pleszew24

- `relevant = true`
- `facts = 2`
- `relations = 6`
- `events = 2`
- `score = 0.45`
- runtime: `23.5s`

What works:
- no longer empty
- appointment/dismissal structure now exists

What fails:
- both main targets are still wrong

Examples:
- extracted bad target: `A. Góralczyk -> Skarbu Państwa -> Prezes`
- extracted bad target: `Przemysław Pacie -> Krajowym Ośrodku Wsparcia Rolnictwa w Warszawie -> Prezes`
- expected benchmark target is still `Stadnina Koni Iwno`

#### RP / Klich

- `relevant = true`
- `facts = 2`
- `relations = 1`
- `events = 0`
- `score = 0.5`
- runtime: `13.02s`

What works:
- one collaborator/friend tie exists

What fails:
- main appointment graph is still almost entirely missing

Examples:
- extracted: `Marcin Dulian -> Klich -> friend`
- extracted: `Klich -> Minister`
- still missing: Hodura / Kuczmański / WAM governance structure

#### WP / rady nadzorcze

- `relevant = true`
- `facts = 7`
- `relations = 5`
- `events = 1`
- `score = 0.55`
- runtime: `26.66s`

What works:
- article is accepted
- some board/governance structure exists

What fails:
- still polluted by media/context artifacts
- expected clean NFOŚiGW board structure is not recovered well

Examples:
- extracted: `Ewa Patalas -> Radzie Nadzorczej Funduszu -> Rada Nadzorcza`
- bogus facts still appear:
  - `Grupy Wirtualnej Polski -> Funduszu`
  - `Biuro Prasowe Polski -> Sejmu`

## Current Main Bottlenecks After This Rerun

1. Governance target resolution is still the biggest quality problem.
2. Entity canonicalization and dedup are still too weak for inflected Polish names and institutions.
3. Party/profile extraction still overfires in dense political articles.
4. Local junk NER still creates bad subjects and weakens downstream facts.
5. Broad public-money articles are better than before, but funding/compensation subjects still need stronger normalization.

## Recommended Next Focus

- prioritize organization target resolution for governance facts
- add a stronger post-extraction entity clustering/dedup pass
- suppress weak political-profile facts when a stronger governance tuple exists in the same local context
