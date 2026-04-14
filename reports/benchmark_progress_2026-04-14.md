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
