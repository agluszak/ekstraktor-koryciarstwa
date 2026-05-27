# Pipeline Comparison Report — 2026-05-27

Run after fixes for issues 5, 8, 9 (prior-role org demoting, initial-name NER merge,
kinship window fallback, `wskoczyć` appointment lemma).

## Articles present in inputs (33 HTML files)

Four expected articles are **not yet in inputs**: Demagog #2 ("Nie dostali się do
parlamentu"), Gazeta Krakowska #14 (Zapał/ZBK), Głos Wielkopolski #18 (WTC Poznań),
Do Rzeczy #19 (PSL/AMW). A new article `wp_zona_sekretarza_krasnik_20260513.html`
("Dwa dni i trzy umowy dla żony sekretarza") is present but not yet in
`expected_article_findings.md`.

Two articles exist in duplicate HTML form (TVP Olsztyn, WFOŚiGW Lublin); the
Onet WFOŚiGW file produces 30 facts while `onet_wfosigw_lublin.html` produces 4
— same article, different HTML source quality.

---

## Article-by-article status

### ✅ PASS

| # | Title | Key facts found |
|---|-------|-----------------|
| 1 | WP Lubczyk | relevant, compensation, people |
| 3 | Olsztyn zarobki | compensation (x2), public_role_holding |
| 4 | RP Klich | Hodura/Kuczmański/Dulian→Klich ties, Hodura→WAM appointment |
| 5 | Onet Totalizator Sportowy | 50 facts: appointments, party ties, compensation |
| 6 | Radomszczańska (Rząsowski) | Rząsowski→AMW Rewita appointment, PO membership, compensation |
| 7 | Onet WFOŚiGW Lublin | Mazur→WFOŚiGW (prezes), Kloc→WFOŚiGW (wiceprezes), Lewica/PSL |
| 8 | Niezależna KZN | Bałajewicz→KZN appointment, 12 political ties, compensation |
| 9 | OKO.press Rydzyk | 6 funding facts, public_contract, WFOŚiGW context |
| 10 | TVP Olsztyn (Słoma) | Słoma→PWiK appointment *(role=prezes, expected wiceprezes)* |
| 12 | WP Odpartyjnienie | Hołownia/Polska 2050, NFOŚiGW appointments |
| 13 | Onet PSL Natura Tour | 45 facts: Wojnarowski→Natura Tour, kinship, PSL ties |
| 20 | Bytom CBA | anti_corruption_referral, Wołosz-Bartków tie, public_contract |
| 22 | Charsznica wójt | partner employment, teść employment, kinship ties |
| 23 | Onet CBA wójt | anti_corruption_investigation (minimal, but correct) |
| 24 | AI42 wójt nepotyzm | Dobosz→samorząd employment, kuzyn kinship |
| 25 | WP Opole rodzina | Królikowska→OUW, Dariusz↔Monika Jurek, Królikowska↔Ogłaza |
| 26 | Polsat Starostwo | mąż/syn Pszczółkowskiej employments, starosta context |
| 29 | **Inwestycje Miejskie** | **Biernat→IM ✓, Rybacki→IM ✓, Stec/Śladowski dismissals ✓** *(Issue 5 fixed)* |
| 30 | Onet Totalizator leca głowy | Krzemień dismissal, Błaszkiewicz acting-role, political ties |
| 33 | WP pensja 30 tys | 9 compensation facts |

### ⚠️ PARTIAL

| # | Title | What works | Gap |
|---|-------|------------|-----|
| 11 | TVN24 Kolesiostwo | relevant, PO/PiS membership, Połedniok | No clean appointment; 5 facts only |
| 15 | **Stadnina Koni** | Entity split fixed ✓, Pacia dismissal ✓, A. Góralczyk appointment found | Org wrong: "Kościelnej Wsi" instead of "Stadnina Koni Iwno" (pre-existing — see note below) |
| 17 | WP Żona posła odnalazła się | Sobolewska kinship tie ✓, Sobolewska→Lubelskie Koleje holding ✓, compensation ✓ | Main fact is `public_role_holding` (0.62) not `public_role_appointment`; some low-conf noise |
| 27 | TVN Warszawa fundacja | Struzik PSL ✓, Zawisza Razem ✓, public_contract ✓, marszałek ✓ | Karol Bielski not found |
| 31 | Business Insider PZU | Kozłowska-Chyła (CEO), Olejniczak appointment, Górecki dismissal | Only 6 facts; expected >10 for full board turnover |
| 32 | Onet Kopania PHN | MPRI dismissal ✓ (0.73), Bartosz kinship ✓, Gawryszczak-Kropiwnicki tie ✓, public_contract ✓ | PHN appointment binds to **Wiesław Malicki** (wrong); Kopania→PHN only at low confidence as `public_employment` (0.54) |

### ❌ FAIL (main goal not met)

| # | Title | Issue |
|---|-------|-------|
| 16 | Żona posła PiS zrezygnowała | **Renata Stefaniuk not extracted**. Dariusz Stefaniuk (the MP) is found instead as the subject; kinship tie shows "Dariusz Stefaniuk @ Jacek Sasin (spouse)" which is wrong. |
| 21 | **Giermasińska** | **Main appointment still missing.** The appointment verb is "wskoczyła na fotel wiceprezesa" (added `wskoczyć`) but the sentence's subject (Giermasińska) is not a named entity in that sentence — implicit subject. Kinship tie to Klimczak also absent (cross-paragraph). Structural limitation. |

---

## True-negative status

| Label | Title | Result |
|-------|-------|--------|
| ✅ C | WP Meloni | relevant=False ✓ |
| ✅ D | Nowi sędziowie TK | relevant=False ✓ |
| ❌ A | **Olsztyn Plac Roosevelta** | **relevant=True (score=0.45)** — should be False. No facts produced but relevance filter triggers. |

The Roosevelt article is a borderline case (score 0.45). The relevance filter threshold
should be checked — at 0.45 exactly this classifies as relevant, which is a false positive
on a pure local-history article.

---

## Issue 5 / 8 / 9 post-fix summary

| Issue | Description | Status |
|-------|-------------|--------|
| **5** | Inwestycje Miejskie: Biernat/Rybacki bound to PKN Orlen | ✅ **FIXED** — both now bind to Inwestycji Miejskich (0.57) |
| **8a** | `wskoczyć` missing from appointment lemmas | ✅ Added — fires where person is named in the sentence |
| **8b** | Giermasińska appointment itself | ❌ **Still missing** — implicit subject, cross-paragraph kinship |
| **8c** | Kinship window fallback | ✅ Implemented — helps adjacent-sentence cases |
| **9** | A. Góralczyk entity split | ✅ **Fixed** — NER merge eliminates split, spurious tie gone. Org binding (Kościelnej Wsi) is pre-existing |

---

## Notable spurious facts

- **Rydzyk article**: Kinship facts for `córka Zbigniewa Ziobro @ Ziobro` and
  `Yad Vashem @ Rydzykowi` — noise from the longer article; Ziobro appears only in
  a comparison paragraph.
- **Giermasińska article**: 6 ties from historical PSL context section (Ograsiński,
  Bury, Żelichowski etc.) — all from a different generation, not the main subject.
- **WFOŚiGW dual duplicate**: `onet_wfosigw_lublin.html` produces only 4 facts
  (appointments labelled `rada nadzorczy` instead of `prezes`/`wiceprezes`); the
  full-quality file produces 30 facts with correct roles. HTML quality difference.

---

## New article (not yet in expected_article_findings.md)

**`wp_zona_sekretarza_krasnik_20260513.html`** — "Dwa dni i trzy umowy dla żony
sekretarza urzędu miasta" — 29 facts extracted including:
- Skokowski kinship and secretary appointments
- patronage_network_tie / patronage_allegation
- public_role_end, compensation
This should be added to expected_article_findings.md once reviewed.

---

## Recommended next investigations

1. **ART16 (Renata Stefaniuk)**: Check why NER produces "Dariusz Stefaniuk" but not
   "Renata Stefaniuk". The article has "Żona posła PiS … Renata Stefaniuk" — if NER
   is failing to tag "Renata Stefaniuk" as a PERSON entity, this is an NER-coverage gap.

2. **ART32 (Kopania → PHN)**: The appointment sentence "Od poniedziałku jest zastępcą
   dyrektora … w Polskim Holdingu Nieruchomości" contains `jest` (appointment trigger)
   but the local person is Wiesław Malicki (mentioned as the existing president). The
   subject "Kopania" is the implicit subject of the verb. This is the same implicit-
   subject problem as Giermasińska.

3. **Olsztyn Roosevelt false positive**: Relevance score 0.45 triggers `relevant=True`.
   Review relevance threshold or profile — this is a pure history/urban-planning article
   with no patronage signals.

4. **ART15 Stadnina org binding**: "Stadnina Koni Iwno" appears in the paragraph
   *after* the appointment trigger paragraph. Org window `after=1` might help but
   risks regressions. Lower priority.

5. **ART31 PZU board turnover**: Full board dismissal/appointment list-style articles
   produce only 6 facts. The pipeline may be missing list-level governance patterns.
