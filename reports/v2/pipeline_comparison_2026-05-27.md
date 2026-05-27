# Pipeline Benchmark Comparison — 2026-05-27

Pipeline run against all 34 inputs in `inputs/`. Output written to `output/run_20260527/`.
Changes in this session: MicroAmountSignal extended to PUBLIC_CONTRACT and FUNDING (penalty −0.95),
"Razem" party alias made case-sensitive, `span_of`/`last_span_of` test helpers added.

---

## Summary

| Category | Count |
|---|---|
| Outputs produced | 33 of 34 inputs |
| Expected negatives correctly False | 2 |
| Expected positives with correct facts | ~10 |
| Partial / degraded extractions | ~8 |
| Key regressions | 0 (no prior baseline to regress against) |

---

## Confirmed Passes

**ART9 — Rydzyk / Radio Maryja FUNDUSZ**
- FUNDING facts extracted correctly with amounts.

**ART20 — Bytom CBA**
- `anti_corruption_investigation` for Wołosz.
- `public_contract` for Bytom contracts.
- `kinship_tie` for Wołosz–Wnuk correctly emitted.

**ART26 — Ciechanów Pszczółkowski**
- Father/son appointments (Marek and Jakub Pszczółkowski) correctly extracted as `public_role_appointment`.
- `kinship_tie` between them present.

**ART32 — Kopania / PHN**
- MPRI dismissal + PHN appointment for Tomasz Kopania.
- `kinship_tie` for Bartosz Kopania sibling.
- `public_contract` for Bartosz Kopania's company.

**ART4 — Klich**
- `personal_or_political_tie` for Klich→Hodura, Klich→Dulian, Klich→Kuczmański.
- `public_role_appointment` for Hodura.

**ART7 — WFOŚiGW (long / full article)**
- Mazur and Kloc appointments present.
- Kruk and Pokwapisz dismissals present.
- Party ties for Mazur (Lewica) and Kloc (PSL) present.
- Compensation facts present.

**ART27 — TVN Bielski / Zawisza**
- Marcelina Zawisza → party Razem correctly matched (capital R).
- "razem" adverb in other articles no longer creates false party entity (case-sensitive fix verified).

**PSL / Natura Tour, KZN articles**
- Core facts extracted as expected.

**Negative articles (Meloni, TK legal analysis)**
- `relevant=false` correctly assigned.

---

## Issues and Gaps

### 1. Olsztyn Roosevelta — false positive relevance
- **Expected:** `relevant=false`
- **Actual:** `relevant=true, score=0.45, 0 facts`
- Score 0.45 is borderline; relevance threshold may need upward adjustment, or the relevance
  model is picking up incidental governance vocabulary.

### 2. ART10 — TVP Słoma / Wodkan — wrong role extracted
- **Expected:** `role="wiceprezes"` (vice-president)
- **Actual:** `role="prezes"` (president) — the text mentions "wiceprezes" but extraction picks
  the higher-salience title.
- `relevance_score=0.45` is borderline; only 1 fact extracted.

### 3. WFOŚiGW short version — organization and role errors
- Mazur and Kloc both shown as appointed to `rada nadzorcza` (supervisory board).
- **Correct:** Mazur = management board president; Kloc = management board vice-president.
- Missing Mazur→Lewica party tie in short version.
- False-positive `personal_or_political_tie` between Mazur and Kloc (co-occurrence artifact).

### 4. WFOŚiGW long version — overgeneration of personal_or_political_tie
- **Expected:** a handful of specific political ties.
- **Actual:** 21 `personal_or_political_tie` facts covering all pair combinations of co-board-members,
  with `context="człowiek"` (generic). These are false positives from the proximity/co-occurrence heuristic.
- False `public_role_end` for Stanisław Mazur — he is being *appointed*, not dismissed.
- Andrzej Kloc role shown as `"prezes"` instead of `"wiceprezes"`.

### 5. ART29 — Inwestycje Miejskie — organization resolution failure
- Biernat and Rybacki appointments attached to `"PKN Orlen"` instead of `"Inwestycje Miejskie"`.
- Dismissals for Stec and Śladowski from Inwestycje Miejskie are correct.
- Root cause: salience competition between PKN Orlen (high-profile org in article context) and
  the actual appointment target.

### 6. ART27 — TVN Bielski — wrong fact kind for money flow
- **Expected:** `public_contract` (Urząd Marszałkowski paid Fundacja Bielskiego for promotional services).
- **Actual:** `funding` (classified as a grant/subsidy).
- Amount "100 tysięcy złotych" extracted correctly.
- Root cause: `GrantTransactionSignal` triggered on the lexical context; the service-contract
  pattern is not strong enough to override it.

### 7. ART23 — CBA wójt — very sparse extraction
- Only 1 `anti_corruption_investigation` fact with no entity arguments.
- Subject (wójt name) and organization are not resolved into the fact.

### 8. ART21 — Giermasińska — main subject missed
- Missing `public_role_appointment` for Giermasińska → Energetyka Cieplna.
- Missing `personal_or_political_tie` between Giermasińska and Klimczak.
- Pipeline instead captures many historical PSL background facts from the article body.
- Root cause: appointment trigger sentence probably not matched by governance extractor patterns.

### 9. ART15 — Stadnina Koni Iwno — entity resolution failure
- `"A. Góralczyk"` split into `"A."` and `"Góralczyk"` as two separate entity candidates.
- Organization resolved as `"Kościelnej Wsi"` instead of `"Stadnina Koni Iwno"`.
- Missing PSL party membership for Góralczyk.

---

## What Was Checked

- All 34 input HTML files run with `uv run extractor --input-dir inputs --glob "*.html" --output-dir output/run_20260527`.
- Slim output JSON read per article and compared against `reports/expected_article_findings.md`.
- Fact kinds, entity names, role values, and signal lists spot-checked for key articles.

## What Remains

- Fix `personal_or_political_tie` overgeneration (issues 3, 4): likely needs a minimum evidence
  threshold beyond simple co-occurrence; `context="człowiek"` bindings should require stronger
  syntactic or reference evidence.
- Fix organization resolution for appointment targets (issue 5): salience-weighted disambiguation
  needed when article mentions high-profile orgs alongside the actual target.
- Fix fact-kind disambiguation between `funding` and `public_contract` (issue 6): service-transaction
  lexical patterns need higher weight or a dedicated contract-service signal.
- Fix `public_role_end` false positive on appointment sentences (issue 4): appointment and dismissal
  triggers must be mutually exclusive in inference.
- Fix role title extraction (issues 2, 3, 4): `wiceprezes` must not be superseded by `prezes` when
  both appear in the same passage; prefix "wice-" must be captured as part of the title.
- Improve sparse anti-corruption extraction (issue 7): argument binding for subject/org in
  CBA-referral sentences needs dedicated patterns.
- Improve governance patterns for appointment targets in `Giermasińska` and `Stadnina` articles (issues 8, 9).
- Investigate relevance false positive for Roosevelta (issue 1): may need threshold adjustment or
  negative-example fine-tuning.
