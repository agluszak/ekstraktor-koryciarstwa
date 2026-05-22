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

---

## Descriptor-resolution rerun — after inference update

After the descriptor-preserving inference slice, I reran the most relevant
descriptor/proxy samples:

- `tp.com.pl__...__nowy-zarzad-inwestycji-miejskich...`
- `zona-posla-pis.html`
- `pleszew24...stadnina...`
- `interwencja.polsatnews.pl__...__bardzo-rodzinne-starostwo...`

### What improved

- **`tp.com.pl__...__nowy-zarzad-inwestycji-miejskich...`**
  - earlier run: a false descriptor-only governance fact materialized as
    `person=prezesa`
  - rerun: that artifact no longer appears literally; the strongest dismissal now
    materializes as `person=Kamil Rybacki`
  - interpretation: descriptor-only person hypotheses are still being produced, but
    inference/projection is now able to resolve at least some of them to a named
    person instead of exposing the raw descriptor in final output.

### What did not improve yet

- **`zona-posla-pis.html`**
  - party/employer leakage is still present, now as
    `public_employment person=Dariusza Stefaniuka; organization=PiS`
  - this confirms the remaining issue is role compatibility and spouse/person
    selection, not only descriptor projection.

- **`pleszew24...stadnina...`**
  - still shows a thin dismissal fact with `role=prezesa`
  - the owner/controller context behavior remains good, but descriptor resolution is
    still incomplete when there is not enough nearby named evidence.

- **`interwencja.polsatnews.pl__...__bardzo-rodzinne-starostwo...`**
  - proxy-family duplication is largely unchanged
  - this slice helped descriptor-person resolution, not the broader family proxy
    linking problem.

### Updated takeaway

The descriptor change is a real architectural improvement:

- descriptor-only people remain valid hypotheses,
- they are no longer hard-suppressed in materialization,
- and when local evidence is strong enough, output can now project a named person
  instead of the raw descriptor.

The next remaining gaps are still:

1. party/employer compatibility,
2. broader proxy-family resolution,
3. descriptor resolution in thinner articles where the nearby named evidence is
   weaker than in the `tp.com.pl` case.

---

## E2E rerun after proxy-family inference update (late 2026-05-22)

Rerun inputs:

- `zona-posla-pis.html`
- `interwencja.polsatnews.pl__...__bardzo-rodzinne-starostwo...`
- `pleszew24...stadnina...`

Also rerun fixture-style E2E regression tests:

- `uv run pytest -c pytest-v2.ini -q tests_v2/test_article_regression_fixtures.py`
- result: **17 passed**

Observed rerun summary:

- `zona-posla-pis.html`
  - relevance: `true`
  - materialized facts: `3` (governance only)
  - `public_employment`: `0` (**pass** for the previous party/employer leak symptom)
- `bardzo-rodzinne-starostwo`
  - relevance: `true`
  - materialized facts: `7` (`5` ties, `1` public employment, `1` governance)
  - still proxy-heavy with repeated tie variants (**not fully passed**; consolidation still incomplete)
- `pleszew24...stadnina...`
  - relevance: `true`
  - materialized facts: `2` (appointment + dismissal)
  - still sparse/thin governance completion (**not fully passed**; destination-role completion still needed)

---

## E2E rerun after sparse-governance + tie-consolidation follow-up (late 2026-05-22)

Rerun inputs:

- `interwencja.polsatnews.pl__...__bardzo-rodzinne-starostwo...`
- `pleszew24...stadnina...`

Observed changes vs previous rerun:

- `bardzo-rodzinne-starostwo`
  - materialized facts: `7 -> 6`
  - tie count: `5 -> 4`
  - the lower-confidence inverse `child` duplicate was suppressed in projection.
  - still not fully solved: proxy-heavy tie variants remain, but duplicate pressure is reduced.

- `pleszew24...stadnina...`
  - still `2` governance facts, but appointment completion improved:
    - appointment now materializes with explicit `organization` (stadnina mention),
    - `Skarb Państwa` remains in `context`, not as target organization.
  - dismissal remains relatively thin (`person + role`) and is still a follow-up target.

---

## Fresh mini-batch (late 2026-05-22)

Inputs:

- `wiadomosci.onet.pl__kraj__...__ezt8y9t.html`
- `onet_trzaskowski_kopania_phn.html`
- `dziennikzachodni.pl__nepotyzm-w-bytomiu...cba...html`
- `businessinsider_kadrowa_czystka_panstwowa_spolka.html`
- `niezalezna_polski2050_synekury.html`

Observed summary:

- `onet_trzaskowski_kopania_phn`:
  - relevance `true`, 12 facts, broad mixed extraction (governance/employment/tie/contract).
  - still noisy with several parallel high-confidence employment/governance outputs.
- `businessinsider_kadrowa_czystka_panstwowa_spolka`:
  - relevance `true`, 2 governance dismissal facts.
  - sparse but plausible; still one thin role-heavy dismissal.
- `niezalezna_polski2050_synekury`:
  - relevance `true`, 17 facts.
  - strong compensation/governance recall, but likely overproduction in mixed governance+employment surface.
- `onet ... ezt8y9t`:
  - relevance `true`, 18 facts.
  - high recall (party + governance + ties), but candidate volume indicates overfire risk.
- `dziennikzachodni ... cba`:
  - relevance `true`, 6 facts, including 3 `anti_corruption_referral`.
  - anti-corruption coverage is working; still multiple near-duplicate referrals.

Takeaway from this fresh batch:

- recall remains strong for governance/network-heavy articles,
- anti-corruption referrals are reliably detected,
- remaining precision pressure is mostly duplicate/parallel fact surfaces rather than missing extraction.

---

## Additional fresh mini-batch (late 2026-05-22)

Inputs:

- `ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm.html`
- `tvn24.pl__polska__kolesiostwo-i-rozdawanie-posad...html`
- `wiadomosci.wp.pl__odpartyjnienie-rad-nadzorczych...html`
- `wp_lubczyk.html`
- `natemat_giermasinska.html`

Observed summary:

- `ai42 ... czy-wojt-ukrywa-nepotyzm`:
  - relevance `true`, 4 facts (`2` employment, `2` ties),
  - good local nepotism recovery with one remaining proxy tie alternative.
- `tvn24 ... kolesiostwo-i-rozdawanie-posad`:
  - relevance `true`, 3 facts, all `party_affiliation`,
  - likely underextracts governance/employment despite relevant framing.
- `wp ... odpartyjnienie-rad-nadzorczych`:
  - relevance `true`, 8 facts (governance + compensation + affiliation),
  - good mixed extraction; still multiple governance variants around the same person/org.
- `wp_lubczyk`:
  - relevance `true`, 2 facts (compensation + affiliation),
  - sparse but consistent with salary-focused article framing.
- `natemat_giermasinska`:
  - relevance `true`, 9 facts, tie-heavy (`6` ties) plus governance/employment overlap,
  - still duplicate pressure between employment/governance surfaces for the same role.

Takeaway:

- V2 keeps strong recall on nepotism/network content,
- precision pressure remains visible as duplicate role surfaces (especially tie-heavy articles),
- some politically framed articles still collapse mostly to party-affiliation output.

---

## Rerun after patronage-complaint slice (late 2026-05-22)

Command:

```bash
uv run extractor-v2 --input-dir inputs --glob "tvn24.pl__polska__kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831__webarchive_20250427191848.html" --output-dir /tmp/v2-rerun-20260522
uv run extractor-v2 --input-dir inputs --glob "rp_klich.html" --output-dir /tmp/v2-rerun-20260522
```

### `tvn24 ... kolesiostwo-i-rozdawanie-posad`

Before (earlier in this report):
- relevance `true`, `3` facts, all `party_affiliation`.

Now:
- relevance `true`, `5` facts:
  - `3` `party_affiliation`,
  - `2` `public_procurement_abuse` (new complaint-level patronage kind).

Delta:
- no longer pure party-affiliation collapse,
- still weak argument grounding in complaint facts (one complaint fact currently carries only `context=kolesiostwo`; one is argument-sparse).

### `rp_klich`

Before (earlier in this report):
- relevance `true`, `2` facts with shallow appointment/employment coverage.

Now:
- relevance `true`, `5` facts:
  - `3` `public_procurement_abuse`,
  - `1` `public_employment`,
  - `1` `governance_appointment`.

Representative recovered facts:
- `public_procurement_abuse`: `actor=Marcin Dulian`, `target=Bogdana Klicha` (`0.688`),
- `governance_appointment`: `person=Jarosław Hodura`, `organization=Grupy Hoteli WAM`, `role=zarządu` (`0.664`),
- `public_employment`: `person=Bogdana Klicha`, `organization=Wojskowej Agencji Mieszkaniowej` (`0.665`).

Delta:
- meaningful depth increase vs prior underextracting output,
- complaint-level patronage signals are now present and materially scored.

### Follow-up scope (deferred): list-level extraction

Deferred to the next slice:
- enumeration/list-aware tuple extraction for repeated appointment records (comma/bullet/list patterns),
- list item-local role/org anchoring with shared article-level context propagation,
- post-inference duplicate control tuned for list articles so high recall does not explode parallel near-duplicates.

---

## TVN24 rerun after adjacent-sentence grounding + sentence-evidence fix (late 2026-05-22)

Command:

```bash
uv run extractor-v2 --input-dir inputs --glob "tvn24.pl__polska__kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831__webarchive_20250427191848.html" --output-dir /tmp/v2-tvn24-grounding-rerun
```

Observed:
- relevance `true`,
- `6` materialized facts total:
  - `3` `party_affiliation`,
  - `3` `public_procurement_abuse`.
- complaint facts now include grounded actors in two records:
  - `actor=Donalda Tuska`, `context=kolesiostwo` (`0.588`),
  - `actor=Bolesław Piecha`, `context=baron` (`0.526`),
  - one context-only `kolesiostwo` alternative remains (`0.557`).
- all complaint candidates now have sentence trigger evidence (`evidence_count=1` each), instead of empty evidence IDs.

Delta vs previous rerun:
- improved from mostly argument-sparse complaint outputs to mixed grounded + context-only alternatives,
- recall-first behavior remains (context-only complaint still visible as an uncertainty branch).

---

## Two-layer patronage schema rerun (2026-05-23)

Schema change in this slice:
- split complaint modeling into:
  - `patronage_allegation` (complaint/reporting frame),
  - `patronage_network_tie` (underlying alleged patronage relation).

### TVN24 `kolesiostwo-i-rozdawanie-posad`

Observed:
- `9` facts total:
  - `3` `party_affiliation`,
  - `3` `patronage_allegation`,
  - `3` `patronage_network_tie`.

Representative outputs:
- `patronage_network_tie`: `subject=Donalda Tuska`, `context=kolesiostwo` (`0.576`),
- `patronage_network_tie`: `subject=Bolesław Piecha`, `context=baron` (`0.576`),
- `patronage_allegation`: `complainant=Donalda Tuska`, `context=kolesiostwo` (`0.559`),
- `patronage_allegation`: `complainant=Bolesław Piecha`, `context=baron` (`0.559`),
- one argument-sparse pair of allegation/network alternatives remains (`0.639`).

Delta:
- clear separation between allegation frame and underlying relation hypotheses,
- higher network coverage than single-layer `public_procurement_abuse`,
- still imperfect local salience (national actor can still dominate local actors).

### RP `rp_klich`

Observed:
- `8` facts total:
  - `3` `patronage_allegation`,
  - `3` `patronage_network_tie`,
  - `1` `public_employment`,
  - `1` `governance_appointment`.

Representative outputs:
- `patronage_network_tie`: `subject=Marcin Dulian`, `object=Bogdana Klicha`, `institution=Grupy Hoteli` (`0.704`),
- `patronage_network_tie`: `subject=Krzysztof Kuczmański`, `object=Bogdana Klicha`, `institution=MON` (`0.694`),
- `patronage_allegation`: `complainant=Marcin Dulian`, `target=Bogdana Klicha`, `institution=Grupy Hoteli` (`0.685`).

Delta:
- richer two-layer patronage output while preserving governance/employment facts.

### Complaint-control: Bytom CBA nepotism article

Observed:
- anti-corruption output remains present (`3` `anti_corruption_referral`),
- two-layer patronage output appears in parallel (`1` allegation + `1` network tie),
- no regression where anti-corruption extraction disappears.

### Remaining issues after two-layer split

- locality bias is still not strong enough in some TVN24-style cases (nationally salient
  actors may still outrank local city actors),
- occasional argument-sparse two-layer alternatives remain visible under recall-first output,
- list-level network articles remain a separate follow-up.
