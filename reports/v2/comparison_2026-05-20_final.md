# Pipeline Comparison Report — V1 vs V2
**Date:** 2026-05-20  
**Run label:** `new`  
**V1 outputs:** `scratch/comparison_v1_new/`  
**V2 outputs:** `scratch/comparison_v2_new/`  

---

## Summary of Articles

| Article key | Title |
|---|---|
| ai42 | Czy wójt ukrywa nepotyzm? |
| dziennikpolski24 | Kontrowersje wokół wójta Charsznicy. Tak pracę dostała jego partnerka. |
| dziennikzachodni | Nepotyzm w Bytomiu? Radni reprezentujący PIS zapowiedzieli zawiadomienie do CBA |
| radomszczanska | Hotelarz Rząsowski: Robota w spółce podległej MON dla radnego powiatowego |

---

## Article 1 — ai42

**Filename:** `ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`  
**Title:** Czy wójt ukrywa nepotyzm?  
**Source:** https://ai42.pl/2024/08/04/czy-wojt-ukrywa-nepotyzm/

### Relevance

| | Relevant? |
|---|---|
| V1 | ✅ Yes (score 0.65) |
| V2 | ✅ Yes |

### V1 Facts

| fact_type | subject | object | role | evidence (≤80 chars) |
|---|---|---|---|---|
| PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny (proxy) | Sosna | cousin | kuzyn wójta Sosny |
| PERSONAL_OR_POLITICAL_TIE | Rafał Dobosz | Sosna | cousin | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy… |
| PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny (proxy) | Sosna | cousin | Rafał Dobosz, kuzyn wójta Sosny… |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | Pomoc Administracyjnej | Na początku lipca, w samorządzie zatrudniono Rafała Dobosza |
| APPOINTMENT | Dobosz | Gminy Poczesna | — | Z relacji osób zatrudnionych w urzędzie wynika… |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | — | Na pytania o zakres obowiązków i kryteria zatrudnienia… |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | — | „informacje dotyczące pana Rafała Dobosza nie podlegają… |
| APPOINTMENT | Dobosz | Gminy Poczesna | — | Jak się okazuje, nowy pracownik jest blisko spokrewniony… |
| POLITICAL_OFFICE | Artur Sosna | Wójt | — | …z wójtem Arturem Sosną, co wywołało… |
| POLITICAL_OFFICE | Sosna | Wójt | — | Rafał Dobosz, kuzyn wójta Sosny… |
| POLITICAL_OFFICE | Sosna | Wójt | — | Mimo rosnącej liczby pytań i wątpliwości, wójt Sosna… |
| POLITICAL_OFFICE | Sosna | Wójt | — | Czy wójt Sosna rzeczywiście ukrywa nepotyzm… |

V1 proxy entity: **Kuzyn Wójta Sosny** (`is_proxy_person=true`, `kinship_detail=cousin`, anchor=`Sosna`)  
Also created a direct kinship tie: **Rafał Dobosz → Sosna** (cousin, conf=0.88)

### V2 Facts (score ≥ 0.5)

| kind | score | arguments | evidence (≤80 chars) |
|---|---|---|---|
| personal_or_political_tie | 0.80 | subject=Rafał Dobosz, object=Sosny, context=family | Rafał Dobosz |

**V2 proxy entities (grounding=proxy):**  
- `proxy-14`: kind=person, hint=`kuzyn of Sosna`

### Gap Analysis

| Direction | What? |
|---|---|
| V1 has, V2 misses | Multiple APPOINTMENT / PUBLIC_EMPLOYMENT facts for Rafał Dobosz → Gminy Poczesna |
| V1 has, V2 misses | POLITICAL_OFFICE role facts for Artur Sosna/Sosna as wójt |
| V2 has, V1 misses | — (V2 subset of V1) |

**Key observations:**
- Both pipelines correctly identify the core kinship tie (Dobosz=cousin of Sosna/wójt).
- V2 emits only **1 high-confidence fact** vs V1's 12 (including 5 APPOINTMENTs). V2 is under-extracting here: the employment of Dobosz at the municipal office (`Gminy Poczesna`) is clearly stated but not scored ≥ 0.5.
- V2 correctly creates a **proxy entity** (`kuzyn of Sosna`) — this is the expected behavior for the new family proxy detection feature.
- The personal_or_political_tie is linked to named entities: subject=Rafał Dobosz (observed), object=Sosny (observed surname). No unnamed proxy is the subject — ✅ correct.
- V1 also creates a proxy entity `Kuzyn Wójta Sosny`, and a separate direct tie Rafał Dobosz → Sosna. V2 consolidates this into one fact with a proxy entity separately registered.
- **Missing in V2:** The public employment fact (Dobosz hired at gmina as "pomoc administracyjna") was the core nepotism event.

---

## Article 2 — dziennikpolski24

**Filename:** `dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-…__webarchive_20260422220715`  
**Title:** Kontrowersje wokół wójta Charsznicy. Tak pracę dostała jego partnerka. Tomasz Kościelniak zaprzecza zarzutom  
**Source:** https://dziennikpolski24.pl/ (webarchive 2026-04-22)

### Relevance

| | Relevant? |
|---|---|
| V1 | ✅ Yes (score 1.0) |
| V2 | ✅ Yes |

### V1 Facts

| fact_type | subject | object | role / kinship | evidence (≤80 chars) |
|---|---|---|---|---|
| PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę (proxy) | Tomasz Kościelniak | partner | swoją „dziewczynę |
| PERSONAL_OR_POLITICAL_TIE | Partnerka Wójta (proxy) | Tomasz Kościelniak | partner | partnerka wójta |
| PERSONAL_OR_POLITICAL_TIE | Swojego Przyszłego Teścia (proxy) | Tomasz Kościelniak | father_in_law | swojego przyszłego teścia |
| PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę (proxy) | Tomasz Kościelniak | partner | …sprawujący funkcję wójta…miał zatrudnić…swoją „dziewczynę… |
| APPOINTMENT | Swoją „dziewczynę (proxy) | Urzędu Gminy | Ekodoradcy | …miał zatrudnić w urzędzie swoją „dziewczynę na stanowisko eko |
| APPOINTMENT | Swojego Przyszłego Teścia (proxy) | Urzędzie Stanu Cywilnego | Pracownika Gospodarczego | …wójt zatrudnił swojego przyszłego teścia na stanowisko prac |
| POLITICAL_OFFICE | Kościelniak | Wójt | — | Ostatnim z przedstawionych zarzutów wobec wójta Kościelniaka… |
| PARTY_MEMBERSHIP | Szymon Kubit | Prawo i Sprawiedliwość | — | …startujący z listy PiS członek zarządu… |
| ELECTION_CANDIDACY | Szymon Kubit | — | — | …dyrektor Gminnego Ośrodka Kultury Szymon Kubit… |
| ELECTION_CANDIDACY | Tomasz Kościelniak | — | — | Zwycięzcą I tury głosowania… Tomasz Kościelniak… |

V1 proxy entities: **Swoją „dziewczynę** (partner, anchor=Kościelniak), **Partnerka Wójta** (partner, anchor=Kościelniak), **Swojego Przyszłego Teścia** (father_in_law, anchor=Kościelniak)

### V2 Facts (score ≥ 0.5)

| kind | score | arguments | evidence (≤80 chars) |
|---|---|---|---|
| governance_appointment | 0.87 | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=dyrektor | Zwycięzcą I tury głosowania…Tomasz Kościelniak… |
| governance_appointment | 0.87 | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=członek zarządu | Zwycięzcą I tury głosowania… |
| governance_appointment | 0.87 | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=dyrektor | Tymczasem stało się inaczej: Tomasz Kościelniak…wójtem |
| governance_appointment | 0.87 | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=członek zarządu | Tymczasem stało się inaczej: Tomasz Kościelniak…wójtem |
| public_employment | 0.78 | person=Tomasz Kościelniak, org=Urzędzie Stanu Cywilnego | …wójt zatrudnił swojego przyszłego teścia na stanowisku |

**V2 proxy entities (grounding=proxy):**  
- `proxy-32`: kind=person, hint=`teść of Tomasz Kościelniak`

### Gap Analysis

| Direction | What? |
|---|---|
| V1 has, V2 misses | Kinship ties: partnerka, „dziewczyna", teść — only the teść proxy is in V2, and it scores 0.35 (below threshold) |
| V1 has, V2 misses | Employment fact for the wójt's girlfriend (ekodoradca) |
| V1 has, V2 misses | PARTY_MEMBERSHIP for Szymon Kubit (PiS) |
| V2 has, V1 misses | — (overlap at governance/employment level) |

**Key observations and false positive flags:**

> ⚠️ **False positives in V2 governance_appointment:** The 4 `governance_appointment` facts all point to **Tomasz Kościelniak** being "appointed" to **Gminnego Ośrodka Kultury** as `dyrektor` or `członek zarządu`. This is wrong — Kościelniak is the *wójt*; the article says he *hired family members* at the town hall. The evidence sentences are about his election win, not a governance board appointment. V2 is confusing the wójt (the appointing authority) with the appointee.

> ℹ️ **Partner kinship detection:** V1 correctly detects 2 proxy entities for the wójt's girlfriend ("dziewczyna" / "partnerka"), while V2 only creates a proxy for "teść" (father-in-law), and even that scored only 0.35 (below threshold). The main finding — that the wójt hired his *partner* — is missed by V2.

> ✅ **Proxy entity creation:** V2 correctly creates proxy-32 (`teść of Tomasz Kościelniak`) with grounding=proxy, demonstrating the new proxy infrastructure works. However it's not surfaced as a fact.

---

## Article 3 — dziennikzachodni

**Filename:** `dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383`  
**Title:** Nepotyzm w Bytomiu? Radni reprezentujący PIS zapowiedzieli, że złożą zawiadomienie do CBA o możliwości popełnienia przestępstwa  
**Source:** https://dziennikzachodni.pl/ (webarchive 2023-09-23)

### Relevance

| | Relevant? |
|---|---|
| V1 | ✅ Yes (score 1.0) |
| V2 | ✅ Yes |

### V1 Facts

| fact_type | subject | object | evidence (≤80 chars) |
|---|---|---|---|
| DISMISSAL | Waldemar Gawron | Wnuk Consulting | Przypomnijmy, że w bytomskiej Radzie Miasta… |
| PUBLIC_CONTRACT | Urzędzie Miejskim w Bytomiu | Gminę Bytom | Informacja dotycząca umów zawieranych przez gminę Bytom… |
| PUBLIC_CONTRACT | Wnuk Consulting | PEC | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom… |
| PUBLIC_CONTRACT | Wnuk Consulting | BPK | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom… |
| ANTI_CORRUPTION_REFERRAL | Prawo i Sprawiedliwość | Centralne Biuro Antykorupcyjne | Konferencja bytomskich radnych reprezentujących Prawo i Sp… |
| ANTI_CORRUPTION_REFERRAL | Maciej Bartków | Centralne Biuro Antykorupcyjne | Jak podkreśla radny Maciej Bartków, zdecydował się on złożyć… |
| POLITICAL_OFFICE | Maciej Bartków | Radny | (×4) various sentences |
| PERSONAL_OR_POLITICAL_TIE | Mariusz Wołosze | Bartkowa | – W naszym przekonaniu doszło do ewidentnego konfliktu interesów… |

### V2 Facts (score ≥ 0.5)

| kind | score | arguments | evidence (≤80 chars) |
|---|---|---|---|
| anti_corruption_referral | 1.00 | complainant=Maciej Bartków, target=Przedsiębiorstwie Energetyki Cieplnej Sp., institution=CBA | Jak podkreśla radny Maciej Bartków…złożyć zawiadomienie do CBA |
| anti_corruption_referral | 0.90 | complainant=Prawo i Sprawiedliwość, institution=CBA, context=w sprawie złożenia zawiadomienia… | Konferencja bytomskich radnych reprezentujących Prawo i Sprawiedliwość… |
| public_contract | 0.85 | counterparty=Wnuk Consulting, contractor=PEC, amount=397 496,95 zł | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC |
| anti_corruption_referral | 0.80 | institution=CBA | Zawiadomienie do CBA to nie wszystko. |
| personal_or_political_tie | 0.80 | subject=Mariusza Wołosza, object=Bartków, context=spouse | Mariusza Wołosza |
| personal_or_political_tie | 0.75 | subject=Bartków, object=Wołosza, context=związany | Bartków |

**V2 proxy entities (grounding=proxy):** None

### Gap Analysis

| Direction | What? |
|---|---|
| V1 has, V2 misses | DISMISSAL fact for Waldemar Gawron / Wnuk Consulting |
| V1 has, V2 misses | Multiple POLITICAL_OFFICE facts for radni |
| V2 has, V1 misses | PUBLIC_CONTRACT with explicit monetary amount (397 496,95 zł) — V2 correctly extracts the amount |
| V2 has, V1 misses | Better structured ANTI_CORRUPTION_REFERRAL with complainant, target, institution |

**Key observations:**

> ✅ **PKW false positive check:** V1 had a concern about `zostać zgłoszone do PKW` generating a false governance appointment. Checking V2: there is **no governance_appointment or governance_dismissal fact with score ≥ 0.5**. The 6 governance_dismissal candidates (Waldemar Gawron, Mariusz Wołosz → PiS/Rada Miasta) all scored 0.23 — correctly suppressed. The PKW scenario does not appear to have fired. ✅

> ✅ **Spouse/kinship tie detected:** V2 correctly identifies a `personal_or_political_tie` between Mariusz Wołosz and Bartków (context=spouse, score=0.80). This is the key finding of possible conflict of interest.

> ✅ **Anti-corruption referral correctly surfaced:** V2 emits 3 `anti_corruption_referral` facts, all well-scored. The top one (score=1.00) correctly identifies Maciej Bartków as complainant, PEC as target, and CBA as institution.

> ✅ **Public contract with money amount:** V2 correctly extracts the Wnuk Consulting–PEC contract with amount 397 496,95 zł (V1 also found it, but without the amount).

---

## Article 4 — radomszczanska

**Filename:** `radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470`  
**Title:** Hotelarz Rząsowski: Robota w spółce podległej MON dla radnego powiatowego. Nowy zaciąg tłustych kotów?  
**Source:** https://radomszczanska.pl/artykul/nowy-zaciag-tlustych-n1256470

### Relevance

| | Relevant? |
|---|---|
| V1 | ✅ Yes |
| V2 | ✅ Yes |

### V1 Facts

| fact_type | subject | object | evidence (≤80 chars) |
|---|---|---|---|
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja (proxy) | Mirella Zugaj | żona Radka Zugaja |
| APPOINTMENT | Rząsowski | AMW Rewita | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem… |
| COMPENSATION | Rząsowski | AMW Rewita | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| APPOINTMENT | Rząsowski | Ministerstwu Obrony Narodowej | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| FORMER_PARTY_MEMBERSHIP | Marek Rząsowski | Platforma Obywatelska | Marek Rząsowski, radny powiatowy PO, został wiceprezesem… |
| POLITICAL_OFFICE | Marek Rząsowski | Radny | Marek Rząsowski, radny powiatowy PO… |
| POLITICAL_OFFICE | Cezary Tomczyk | Wiek / Zastępca Minister | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem… |
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja (proxy) | Mirella Zugaj | Ciekawe kto jeszcze okaże się super fachowcem w spółkach… |
| ELECTION_CANDIDACY | Jacek Łęski | — | Zaczynał w kampanii wyborczej Jacka Łęskiego… |

V1 proxy entity: **Żona Radka Zugaja** (spouse, anchor=Mirella Zugaj) — ⚠️ NOTE: the anchor should be Radek Zugaj, not Mirella Zugaj; V1 has inverted the anchor.

### V2 Facts (score ≥ 0.5)

| kind | score | arguments | evidence (≤80 chars) |
|---|---|---|---|
| compensation | 0.93 | funder=AMW Rewita, recipient=Rząsowskiego, amount=24 tys. zł | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| compensation | 0.93 | funder=Ministerstwu Obrony Narodowej, recipient=Rząsowskiego, amount=24 tys. zł | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| governance_appointment | 0.90 | person=Rząsowski, org=AMW Rewita, role=radę nadzorczą | Rząsowski został nominowany przez radę nadzorczą na wiceprezesa AMW Rewita |
| governance_appointment | 0.82 | person=Rząsowski, org=AMW Rewita, role=radę nadzorczą | Nie objął jeszcze stanowiska, poprosił o przesunięcie terminu… |
| party_affiliation | 0.80 | subject=Marek Rząsowski, object=Platforma Obywatelska | Marek Rząsowski, radny powiatowy PO, został wiceprezesem… |
| personal_or_political_tie | 0.80 | subject=Mirella Zugaj, object=Radka Zugaja, context=spouse | Mirella Zugaj |

**V2 proxy entities (grounding=proxy):** None (the Zugaj spouse relationship is between two named entities)

### Gap Analysis

| Direction | What? |
|---|---|
| V1 has, V2 misses | ELECTION_CANDIDACY for Jacek Łęski |
| V1 has, V2 misses | POLITICAL_OFFICE for Cezary Tomczyk (wiceminister) |
| V2 has, V1 misses | Explicit party_affiliation fact type (V1 uses FORMER_PARTY_MEMBERSHIP) |
| Both agree | APPOINTMENT/governance_appointment for Rząsowski → AMW Rewita |
| Both agree | COMPENSATION fact (24 tys. zł) |
| Both agree | Spouse/kinship tie: Mirella Zugaj ↔ Radka Zugaj |

**Key observations:**

> ✅ **Funder identification check:** V2 correctly identifies **AMW Rewita** as the compensation funder (score=0.93) — not a political party. The low-score candidates for PO, Platformy, PiS as funders all score 0.33 and are correctly filtered out. ✅

> ✅ **Governance appointment correctly extracts organization:** Both governance_appointment facts point to `AMW Rewita` as the organization (the defense-sector state company), which is the correct target. The `Ministerstwu Obrony Narodowej` funder in one compensation fact is a bit ambiguous (it's the parent ministry, not the direct employer), but it scores identically to the AMW Rewita version.

> ℹ️ **Spouse tie: named entities, no proxy needed.** Both Mirella Zugaj and Radek Zugaj are named individuals, so V2 correctly does **not** create a proxy entity — the tie is between two observed entities. V1 incorrectly used Mirella Zugaj as the anchor entity (the proxy was "Żona Radka Zugaja" anchored to Mirella Zugaj, which is backwards: the wording implies Mirella is the wife of Radek). V2 correctly models it as `subject=Mirella Zugaj, object=Radka Zugaja, context=spouse`.

> ⚠️ **Duplicate compensation facts:** The same salary sentence generates two compensation facts — one with funder=AMW Rewita and one with funder=Ministerstwu Obrony Narodowej. This is a mild redundancy; the AMW Rewita one is the more accurate funder.

---

## Overall Gap Analysis & Conclusions

### Improvements Visible in V2

| Feature | Status |
|---|---|
| Proxy entity creation for kinship | ✅ Working — proxy-14 (`kuzyn of Sosna`), proxy-32 (`teść of Tomasz Kościelniak`) are created |
| ANTI_CORRUPTION_REFERRAL extraction | ✅ Strong — top-scored facts in dziennikzachodni |
| PUBLIC_CONTRACT with amounts | ✅ Improved — 397 496,95 zł correctly extracted |
| Party affiliation (PARTY_AFFILIATION) | ✅ Correctly fires for radomszczanska |
| Spouse tie between named entities | ✅ Correctly identified without creating a proxy |
| PKW false positive governance avoidance | ✅ No governance facts fired for PKW mention in dziennikzachodni |
| Low-score filtering of party-as-funder | ✅ PO/PiS as funders score 0.33 and are correctly suppressed |

### Gaps Remaining in V2

| Gap | Article | Severity |
|---|---|---|
| Public employment of nepotism beneficiary (core fact) | ai42 | High — the actual hiring event is not scored ≥ 0.5 |
| Partner/girlfriend detection ("dziewczyna", "partnerka") | dziennikpolski24 | High — proxy created but personal_or_political_tie scores only 0.35 |
| Employment of family members at specific institutions | dziennikpolski24 | Medium — the girlfriend ekodoradca fact is missed |
| False positive governance: wójt as appointee, not appointer | dziennikpolski24 | Medium-High — 4 governance_appointment facts wrongly point to Kościelniak being appointed to Gminnego Ośrodka Kultury |
| Duplicate governance/compensation facts | radomszczanska | Low — same event generates 2 nearly identical candidates |
| Spouse proxy kinship when both parties are named | radomszczanska | Minor — V2 correctly avoids proxy here; V1 got anchor inverted |

### False Positive Flags (V2 facts ≥ 0.5 that look wrong)

| Article | Fact | Problem |
|---|---|---|
| dziennikpolski24 | `governance_appointment`: Tomasz Kościelniak → Gminnego Ośrodka Kultury (dyrektor/członek zarządu, ×4, score=0.87) | The wójt is not being appointed to this org; Szymon Kubit is the dyrektor. The sentence context is about other people in the same paragraph. This is a classic false positive from discourse-window organization/role matching. |

### Proxy Entity Summary

| Article | Proxy entity | Kinship | Anchor | Linked to named fact? |
|---|---|---|---|---|
| ai42 | `kuzyn of Sosna` | cousin | Sosna (Artur Sosna) | ✅ Indirectly via personal_or_political_tie subject=Rafał Dobosz |
| dziennikpolski24 | `teść of Tomasz Kościelniak` | father_in_law | Tomasz Kościelniak | ⚠️ Proxy exists but personal_or_political_tie scores 0.35 (below threshold) |
| dziennikzachodni | None | — | — | N/A |
| radomszczanska | None | — | — | N/A (spouse is between two named entities) |

---

*Report generated 2026-05-20 by comparison agent. Clean registry run — this is a fresh process batch.*
