# V2 e2e sampled inputs — 2026-05-22

This is a V2-only end-to-end testing note for a small current batch of HTML
inputs from `inputs/`.

The goal is not exhaustive scoring. The goal is to keep a high-signal running
record of:

- what V2 currently recovers,
- where it still underextracts,
- where it still overfires,
- and which failures are inference/binding problems versus relevance or domain
  coverage problems.

## Command

```bash
uv run extractor-v2 --input-dir inputs --glob "<file>.html" --output-dir <out>
```

This note reflects a fresh run after the entity-context inference cleanup and
the funding distinctness follow-up.

Current validated baseline at the time of this run:

- `uv run ruff check pipeline_v2 tests_v2 --fix`
- `uv run ruff format pipeline_v2 tests_v2`
- `uv run ruff check pipeline_v2 tests_v2`
- `uv run ty check pipeline_v2 tests_v2`
- `uv run pytest -c pytest-v2.ini -q`
- suite state: **166 passed**

---

## 1. `onet_totalizator.html`

### Expected V2 outcome

- strongly relevant,
- multiple party-affiliation and network facts,
- multiple governance appointments/dismissals into `Totalizator Sportowy`,
- some salary / public-money context if the article states it clearly.

### Observed V2 output

- relevance: **true**
- materialized facts: **20**
- strong recovery of party affiliation:
  - `Sławomir Czwal -> Koalicja Obywatelska`
  - `Remigiusz Zagórski -> Lewica`
  - `Stanisław Gawłowski -> Platforma Obywatelska`
  - `Sławomir Nitras -> Platforma Obywatelska`
  - `Marcin Posadzy -> Prawo i Sprawiedliwość`
- governance output present, e.g.:
  - `Magdalena Sekuła -> Totalizatora -> dyrektorem`
  - `Olgierd Cieślik -> prezes` (appointment + dismissal)
  - `Rafał Krzemień -> zarząd`

### Current problems

- still noisy in governance:
  - some appointments lack destination organization,
  - some role-only governance facts remain too generic,
  - `partner of Donaldem Tuskiem` is still interpreted as a spouse-family tie,
    which is likely too aggressive for this article.

### Takeaway

Good breadth, but governance person-role interpretation and tie semantics still
need cleanup.

---

## 2. `rp_klich.html`

### Expected V2 outcome

- strongly relevant,
- several appointment/employment facts,
- at least some collaborator / political-network ties around Klich.

### Observed V2 output

- relevance: **true**
- materialized facts: **2**
- recovered:
  - `Jarosław Hodura -> Grupy Hoteli WAM -> zarząd`
  - `Bogdana Klicha -> Wojskowej Agencji Mieszkaniowej` as `public_employment`

### Current problems

- clearly underextracts this article:
  - too few appointments,
  - no explicit personal/political ties materialized,
  - missing richer role/organization coverage expected from the article.

### Takeaway

This remains a good high-value benchmark for relationship-heavy patronage
articles. Current output is too shallow.

---

## 3. `olsztyn_wodkan.html`

### Expected V2 outcome

- relevant public-money article,
- compensation extraction for municipal utility leadership,
- ideally correct person and employer/funder.

### Observed V2 output

- relevance: **true**
- materialized facts: **2**
- recovered compensation:
  - `Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie -> Wiesław Pancer -> 322 030,80 zł`
  - `Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie -> Wiesław Pancer -> 182 tys. zł`

### Current problems

- no major failure in this sample,
- still essentially compensation-only rather than richer role/governance output,
  but that is acceptable for this article.

### Takeaway

A good current V2 success case for public-money compensation extraction.

---

## 4. `dziennikpolski24...charsznica...`

### Expected V2 outcome

- relevant nepotism/employment article,
- partner/family proxy extraction,
- public-employment facts tied to the correct local institutions.

### Observed V2 output

- relevance: **true**
- materialized facts: **4**
- ties:
  - `dziewczyna of Tomasz Kościelniak -> Tomasz Kościelniak`
  - `teść of Tomasz Kościelniak -> Tomasz Kościelniak`
- employment:
  - `dziewczyna of Tomasz Kościelniak -> urzędzie`
  - `teść of Tomasz Kościelniak -> Urzędzie Stanu Cywilnego`

### Current problems

- still proxy-heavy rather than resolving named relatives where possible,
- likely organization drift remains for the `teść` employment fact,
- employment grounding is better than earlier, but still not fully robust in
  multi-relative local-government articles.

### Takeaway

Useful current test for the still-open proxy-family and organization-grounding
problems.

---

## 5. `wiadomosci.onet.pl__krakow__...__vdc04xe.html`

### Expected V2 outcome

- strongly relevant anti-corruption article,
- anti-corruption referral or investigation output,
- ideally a clear institution and a usable target.

### Observed V2 output

- relevance: **true**
- materialized facts: **1**
- recovered:
  - `anti_corruption_investigation`
  - `institution=Delegatura CBA`
  - target captured as a long prosecution-unit phrase

### Current problems

- target phrase is overly long and bureaucratic,
- extraction captures the oversight action but not yet a cleaner normalized
  target around the bribery / hiring allegations.

### Takeaway

The anti-corruption producer is functioning, but target normalization still
needs work.

---

## 6. `olsztyn_roosevelta_negative.html`

### Expected V2 outcome

- not relevant,
- zero materialized facts,
- ideally `relevance=false`.

### Observed V2 output

- relevance: **true**
- materialized facts: **0**

### Current problems

- this is a relevance false positive,
- downstream extraction is harmless here because it emits no facts, but the
  relevance layer is still too permissive for some local-history / city-topic
  articles.

### Takeaway

This should remain a negative control for the relevance filter.

---

## Batch summary

### Stronger current cases

- `olsztyn_wodkan.html` — compensation/public-money extraction is solid.
- `wiadomosci.onet...vdc04xe.html` — anti-corruption investigation extraction is
  present and useful.
- `onet_totalizator.html` — party/network surface is broad and clearly in scope.

### Weak / incomplete current cases

- `rp_klich.html` — underextracts both appointments and network ties.
- `dziennikpolski24...charsznica...` — still too proxy-heavy and not fully
  grounded.
- `onet_totalizator.html` — governance still overproduces generic role-only facts
  and some tie semantics are too loose.

### Clear control failure

- `olsztyn_roosevelta_negative.html` — still `relevance=true` despite zero facts.

## Most useful next follow-up after this e2e batch

1. **governance person-role binding and sentence filtering**
   - reduce role-only governance facts,
   - demote contextual/quoted participants,
   - tighten destination-organization selection.

2. **proxy-family / relative resolution**
   - better named-relative linking,
   - less proxy-only output in nepotism articles,
   - fewer cross-linked family ties.

3. **relevance tightening for local-history / non-patronage municipal articles**
   - preserve true positives,
   - reduce cases like `olsztyn_roosevelta_negative.html`.

---

## Additional batch — later on 2026-05-22

The same reporting format was reused for a second fresh batch.

## 7. `zona-posla-pis.html`

### Expected V2 outcome

- relevant nepotism/governance article,
- spouse tie around the MP,
- governance positions on state-company supervisory boards,
- no party-as-employer artifacts.

### Observed V2 output

- relevance: **true**
- materialized facts: **5**
- recovered:
  - spouse tie for `żona of Dariusz Stefaniuk`
  - governance board facts around `Dariusz Stefaniuk`
  - governance board fact around `Jacek Sasin -> Port Lotniczy Lublin`

### Current problems

- some governance facts bind the politician instead of the spouse more directly,
- `public_employment person=polityków; organization=PiS` is a clear bad binding,
- role-only board facts are still too permissive.

### Takeaway

This is still a good benchmark for separating spouse/relative targets from nearby
political context and party mentions.

---

## 8. `interwencja.polsatnews.pl__...__bardzo-rodzinne-starostwo...`

### Expected V2 outcome

- strongly relevant,
- several family ties,
- public-employment facts in county administration,
- limited governance noise.

### Observed V2 output

- relevance: **true**
- materialized facts: **7**
- recovered:
  - several family ties (`syn`, `mąż`, named child relation),
  - `public_employment` for `mąż of Joanna Pszczółkowska -> starostwu`,
  - one governance appointment around `Józef Borkowski`.

### Current problems

- still proxy-heavy rather than fully resolving named relatives,
- tie output duplicates the same local family cluster in multiple forms,
- governance appointment for `Józef Borkowski` is weak and generic.

### Takeaway

Family-tie coverage is present, but deduplication and name resolution remain
important gaps.

---

## 9. `pleszew24...stadnina...`

### Expected V2 outcome

- relevant governance article,
- appointment into the state stud farm,
- `Skarb Państwa` or similar owner/controller context should remain context, not
  the primary organization target.

### Observed V2 output

- relevance: **true**
- materialized facts: **2**
- recovered:
  - `governance_appointment person=Góralczyk; context=Skarbu Państwa`
  - `governance_dismissal person=Przemysław Pacia; role=prezesa`

### Current problems

- appointment output still lacks a clearly materialized destination organization,
- dismissal is still role-heavy and somewhat thin.

### Takeaway

This is a useful partial success: the owner/controller phrase stayed in
`CONTEXT`, which is the right architectural direction.

---

## 10. `radomszczanska.pl__...__nowy-zaciag-tlustych...`

### Expected V2 outcome

- relevant article about politically connected appointments,
- party affiliation,
- governance appointment into a state-related entity,
- ideally employment/compensation grounded to the same network.

### Observed V2 output

- relevance: **true**
- materialized facts: **4**
- recovered:
  - `Marek Rząsowski -> Platforma Obywatelska`
  - governance appointment into `AMW Rewita`
  - compensation for `Marek Rząsowski`
  - spouse tie `Mirella Zugaj -> Radek Zugaj`

### Current problems

- compensation is present but thinly attached,
- cross-person family/network facts may still be drifting across nearby article
  sections.

### Takeaway

A decent mixed success case: party, governance, compensation, and tie extraction
all appear, but the cross-section grouping still needs tightening.

---

## 11. `tp.com.pl__...__nowy-zarzad-inwestycji-miejskich...`

### Expected V2 outcome

- relevant municipal-governance article,
- clean appointment/dismissal events for the company leadership,
- no descriptor-only pseudo-person facts.

### Observed V2 output

- relevance: **true**
- materialized facts: **4**
- recovered:
  - `Mariusz Stec -> Inwestycji Miejskich` dismissal as president,
  - `Mirosław Milewski -> Inwestycje Miejskie` appointment,
  - one appointment involving `Artur Biernat -> PKN Orlen`.

### Current problems

- `governance_dismissal person=prezesa` is a clear descriptor-only false
  materialization,
- the `Artur Biernat -> PKN Orlen` appointment likely reflects contextual resume
  content rather than the main city-company event,
- municipal governance articles still need better quote/context filtering.

### Takeaway

This is a strong regression target for removing descriptor-person artifacts and
for demoting contextual career-history appointments.

---

## Updated cross-batch summary

### Stronger current cases across both batches

- `olsztyn_wodkan.html` — compensation/public-money extraction is solid.
- `wiadomosci.onet...vdc04xe.html` — anti-corruption investigation extraction is
  present and useful.
- `onet_totalizator.html` — party/network surface is broad and clearly in scope.
- `radomszczanska...nowy-zaciag-tlustych...` — mixed extraction across party,
  governance, compensation, and ties is reasonably good.

### Recurrent weaknesses across both batches

- **descriptor-only governance people**
  - e.g. `person=prezesa` in `tp.com.pl...nowy-zarzad-inwestycji-miejskich...`
- **proxy-heavy kinship output**
  - still common in `charsznica`, `bardzo-rodzinne-starostwo`, and
    `zona-posla-pis`
- **contextual political mentions leaking into core roles**
  - e.g. party/employer drift in `zona-posla-pis`
- **governance role-only facts without a good organization**
  - still visible in `onet_totalizator`, `pleszew24...stadnina...`, and
    `tp.com.pl...nowy-zarzad...`
- **relevance false positives**
  - still visible in `olsztyn_roosevelta_negative.html`

### Most useful next follow-up after the expanded e2e batch

1. **descriptor-person suppression in governance**
   - prevent role nouns like `prezes/prezesa` from materializing as people.

2. **better main-event versus contextual-resume separation**
   - demote background appointments and quoted context in municipal-governance
     articles.

3. **kinship/proxy consolidation**
   - keep family evidence, but reduce duplicate proxy-only materializations and
     improve linking to named people.

4. **party/employer role compatibility tightening**
   - continue preventing parties and broad political labels from winning
     employment or governance-organization slots.
