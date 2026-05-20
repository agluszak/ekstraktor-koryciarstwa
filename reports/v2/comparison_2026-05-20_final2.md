# V1 vs V2 Comparison Report — 2026-05-20 (final2)

**Run label:** `new`  
**Date:** 2026-05-20  
**Articles compared:** 4  
**V1 output dir:** `scratch/comparison_v1_new/`  
**V2 output dir:** `scratch/comparison_v2_new/`

---

## Key Fix Tracker (summary at top)

| Question | Status |
|---|---|
| False positive governance: Tomasz Kościelniak → Gminnego Ośrodka Kultury gone? | ❌ **Still present** (score 0.87, x4 duplicates) |
| "teść of Tomasz Kościelniak" proxy tie score ≥ 0.5? | ✅ **Yes** (score 0.60) |
| "dziewczyna" kinship tie appears for charsznica? | ✅ **Yes** (score 0.60, proxy-32) |
| Public employment for Rafał Dobosz @ Gminy Poczesna score ≥ 0.5? | ❌ **Not present** — no `public_employment` candidate at all |

---

## Article 1: Czy wójt ukrywa nepotyzm?

**File:** `ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`

### Relevance

| | V1 | V2 |
|---|---|---|
| `is_relevant` | `null` (not set) | `true` |

### V2 Proxy Entities

| ID | Kind | Canonical Hint |
|---|---|---|
| proxy-14 | person | kuzyn of Sosna |

### V1 Facts

| Fact ID | Kind | Subject | Object | Role | Evidence |
|---|---|---|---|---|---|
| fact_45b1f11dba19573d | PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny | Sosna | — | kuzyn wójta Sosny |
| fact_a59d261904e85d37 | APPOINTMENT | Dobosz | Gminy Poczesna | — | Jak się okazuje, nowy pracownik jest blisko spokrewniony z wójtem Arturem Sosną… |
| fact_bfea4052871c58ab | APPOINTMENT | Rafał Dobosz | Gminy Poczesna | Pomoc Administracyjnej | Na początku lipca, w samorządzie zatrudniono Rafała Dobosza na stanowisku pomocy administracyjnej… |
| fact_30cd4ef69e555162 | APPOINTMENT | Dobosz | Gminy Poczesna | — | Z relacji osób zatrudnionych w urzędzie wynika… |
| fact_dbf78313f61551df | APPOINTMENT | Rafał Dobosz | Gminy Poczesna | — | Na pytania o zakres obowiązków i kryteria zatrudnienia Rafała Dobosza… |
| fact_206a2b77520f5412 | APPOINTMENT | Rafał Dobosz | Gminy Poczesna | — | informacje dotyczące pana Rafała Dobosza nie podlegają upublicznieniu… |
| fact_7b9a361a6a755edc | PERSONAL_OR_POLITICAL_TIE | Rafał Dobosz | Sosna | cousin | Rafał Dobosz, kuzyn wójta Sosny… |
| fact_5d6732f7672654e1 | PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny | Sosna | cousin | Rafał Dobosz, kuzyn wójta Sosny… |
| fact_f3f70d82fd1d53e3 | POLITICAL_OFFICE | Artur Sosna | Wójt | — | wójtem Arturem Sosną |
| fact_3c3cc0eca777589d | POLITICAL_OFFICE | Sosna | Wójt | — | wójt Sosny |
| fact_2355974e8f115a05 | POLITICAL_OFFICE | Sosna | Wójt | — | wójt Sosna unika |
| fact_87892a3e3ee6530e | POLITICAL_OFFICE | Sosna | Wójt | — | Czy wójt Sosna rzeczywiście ukrywa nepotyzm… |

### V2 Facts (all, with scores)

| ID | Kind | Score | Arguments | Signals (+) |
|---|---|---|---|---|
| fact-0 | personal_or_political_tie | **0.80** | subject=Rafał Dobosz, object=Sosny, context=family | named_kinship_lemma, sentence_local_subject, sentence_local_object |
| fact-1 | personal_or_political_tie | **0.60** | subject=Rafał Dobosz, object=Sosny, context=family/kuzyn | nominalkinship |
| fact-2 | personal_or_political_tie | **0.60** | subject=kuzyn of Sosna, object=Sosna, context=family/kuzyn | nominalkinship |

### Gap Analysis

**V1 has, V2 misses:**
- Multiple `APPOINTMENT` facts for Rafał Dobosz at Gminy Poczesna — V2 emits **zero** `public_employment` candidates for this article. The hiring of the wójt's cousin into a public position (the core nepotism story) is entirely absent from V2 output.
- `POLITICAL_OFFICE` role facts for Artur Sosna as Wójt.

**V2 has, V1 misses:**
- Proxy entity `kuzyn of Sosna` (proxy-14) is more structurally typed.
- Scores make confidence explicit.

### False Positive Flags

None (V2 score ≥ 0.5 facts all look correct — cousin tie is real).

### ❌ Open Issue

V2 has no `public_employment` candidate for Rafał Dobosz at Gminy Poczesna. The nepotism employment (hiring of cousin into public admin) is entirely undetected by the V2 domain stage. This is the primary gap for this article.

---

## Article 2: Kontrowersje wokół wójta Charsznicy

**File:** `dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715`

### Relevance

| | V1 | V2 |
|---|---|---|
| `is_relevant` | `null` (not set) | `true` |

### V2 Proxy Entities

| ID | Kind | Canonical Hint |
|---|---|---|
| proxy-32 | person | dziewczyna of Tomasz Kościelniak |
| proxy-33 | person | teść of Tomasz Kościelniak |

### V1 Facts

| Fact ID | Kind | Subject | Object | Role | Evidence |
|---|---|---|---|---|---|
| fact_ae0071c7260d538c | PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę | Tomasz Kościelniak | partner | swoją „dziewczynę |
| fact_14d06ee8a3a15a95 | PERSONAL_OR_POLITICAL_TIE | Partnerka Wójta | Tomasz Kościelniak | partner | partnerka wójta |
| fact_da1653cc372552eb | PERSONAL_OR_POLITICAL_TIE | Swojego Przyszłego Teścia | Tomasz Kościelniak | father_in_law | swojego przyszłego teścia |
| fact_5bbafa5867a85bda | APPOINTMENT | Swoją „dziewczynę | Urzędu Gminy | Ekodoradcy | wójt… zatrudnił swoją „dziewczynę" jako ekodoradcę… |
| fact_586fa765f93c575d | APPOINTMENT | Swojego Przyszłego Teścia | Urzędzie Stanu Cywilnego | Pracownika Gospodarczego | wójt zatrudnił swojego przyszłego teścia w Urzędzie Stanu Cywilnego… |
| fact_9ebf7eccfaae568e | POLITICAL_OFFICE | Kościelniak | Wójt | — | wójt Kościelniaka |
| fact_59420216ad645bfd | PARTY_MEMBERSHIP | Szymon Kubit | Prawo i Sprawiedliwość | — | dyrektor Gminnego Ośrodka Kultury Szymon Kubit oraz startujący z listy PiS… |
| fact_9b514d7612aa5a3a | PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę | Tomasz Kościelniak | partner | wójt… sprawujący funkcję wójta… zatrudnił swoją „dziewczynę"… |

### V2 Facts (score ≥ 0.5)

| ID | Kind | Score | Arguments | Signals (+) | Notes |
|---|---|---|---|---|---|
| fact-0 | governance_appointment | **0.87** | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=dyrektor | appointment_lemma, sentence_local_person, discourse_window_org, discourse_window_role | ⚠️ FALSE POSITIVE (see below) |
| fact-1 | governance_appointment | **0.87** | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=członek zarządu | appointment_lemma, sentence_local_person, discourse_window_org, discourse_window_role | ⚠️ FALSE POSITIVE |
| fact-4 | governance_appointment | **0.87** | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=dyrektor | appointment_lemma, sentence_local_person, discourse_window_org, discourse_window_role | ⚠️ FALSE POSITIVE (duplicate of fact-0) |
| fact-5 | governance_appointment | **0.87** | person=Tomasz Kościelniak, org=Gminnego Ośrodka Kultury, role=członek zarządu | appointment_lemma, sentence_local_person, discourse_window_org, discourse_window_role | ⚠️ FALSE POSITIVE (duplicate of fact-1) |
| fact-8 | public_employment | **0.78** | person=Tomasz Kościelniak, org=Urzędzie Stanu Cywilnego | public_employment_lemma, discourse_window_person, discourse_window_org | ✅ Partially correct (person misidentified — should be teść) |
| fact-9 | personal_or_political_tie | **0.80** | subject=Jan Kowalski, object=Tomasz Kościelniak, context=spouse | named_kinship_lemma, sentence_local_subject, sentence_local_object | ⚠️ Questionable (Jan Kowalski is a pseudonymous commenter, not a real person with tie) |
| fact-10 | personal_or_political_tie | **0.60** | subject=dziewczyna of Tomasz Kościelniak, object=Tomasz Kościelniak, context=spouse/dziewczyna | nominalkinship | ✅ **FIXED** — proxy dziewczyna tie now captured |
| fact-11 | personal_or_political_tie | **0.60** | subject=teść of Tomasz Kościelniak, object=Tomasz Kościelniak, context=family/teść | nominalkinship | ✅ **FIXED** — proxy teść tie now captured |

### V2 Facts (score < 0.5, for reference)

| ID | Kind | Score | Arguments |
|---|---|---|---|
| fact-2 | governance_appointment | 0.27 | person=Tomasz Kościelniak, org=PiS, role=dyrektor |
| fact-3 | governance_appointment | 0.27 | person=Tomasz Kościelniak, org=PiS, role=członek zarządu |
| fact-6 | governance_appointment | 0.27 | person=Tomasz Kościelniak, org=PiS, role=dyrektor |
| fact-7 | governance_appointment | 0.27 | person=Tomasz Kościelniak, org=PiS, role=członek zarządu |

### Gap Analysis

**V1 has, V2 misses:**
- Appointment/employment of **dziewczyna** at Urzędu Gminy as ekodoradca — V2 captures the tie but not the employment fact.
- Appointment/employment of **teść** at Urzędzie Stanu Cywilnego — V2 `public_employment` fires but attributes it to Tomasz Kościelniak (the wójt) rather than the teść (the actual hire).

**V2 has, V1 misses:**
- Explicit proxy entities with typed canonical hints.

### False Positive Flags

⚠️ **fact-0, fact-1, fact-4, fact-5**: `governance_appointment` for Tomasz Kościelniak → Gminnego Ośrodka Kultury with score **0.87** — **this is a false positive that was NOT fixed**. Kościelniak is the wójt; the article is about him appointing others, not about his own board-level appointment to GOK. The text mentions GOK in the context of the previous director (Szymon Kubit, a PiS candidate). The `discourse_window_organization` signal is bleeding the GOK entity into a window around Kościelniak. This is the main false positive to address.

⚠️ **fact-8**: `public_employment` Tomasz Kościelniak → Urzędzie Stanu Cywilnego (score 0.78): The actual hire was his future father-in-law, not Kościelniak himself. The proxy entity is correctly identified (`teść of Tomasz Kościelniak`), but the employment fact uses the wrong person.

⚠️ **fact-9**: Jan Kowalski appears as a named person tied to Kościelniak (spouse context) — Jan Kowalski is an anonymous pseudonymous commenter in the article and should not be extracted as a real person.

---

## Article 3: Nepotyzm w Bytomiu

**File:** `dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383`

### Relevance

| | V1 | V2 |
|---|---|---|
| `is_relevant` | `null` (not set) | `true` |

### V2 Proxy Entities

*(None detected)*

### V1 Facts

| Fact ID | Kind | Subject | Object | Role | Value | Evidence |
|---|---|---|---|---|---|---|
| fact_28d02339f92558f1 | DISMISSAL | Waldemar Gawron | Wnuk Consulting | — | — | Przypomnijmy, że w bytomskiej Radzie Miasta… |
| fact_ae3974cc4f4b5023 | PUBLIC_CONTRACT | Urzędzie Miejskim w Bytomiu | Gminę Bytom | — | — | Informacja dotycząca umów zawieranych przez gminę Bytom… |
| fact_d0f39d98589558c8 | PUBLIC_CONTRACT | Wnuk Consulting | PEC | — | 397 496,95 zł | Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC… |
| fact_04082ba042825486 | PUBLIC_CONTRACT | Wnuk Consulting | BPK | — | 397 496,95 zł | (same evidence) |
| fact_f83c210a8fd65aa0 | ANTI_CORRUPTION_REFERRAL | Prawo i Sprawiedliwość | CBA | — | CBA | Konferencja bytomskich radnych reprezentujących Prawo i Sprawiedliwość… |
| fact_8040ed309f34501c | ANTI_CORRUPTION_REFERRAL | Maciej Bartków | CBA | — | CBA | Maciej Bartków, zdecydował się on złożyć zawiadomienie do CBA… |
| fact_61fa074d5240504b | PERSONAL_OR_POLITICAL_TIE | Mariusz Wołosze | Bartkowa | spouse | — | W naszym przekonaniu doszło do ewidentnego konfliktu interesów… |
| (multiple) | POLITICAL_OFFICE | Maciej Bartków / Bartkowa / Janas / Rabus | Radny | — | — | Various |

### V2 Facts (score ≥ 0.5)

| ID | Kind | Score | Arguments | Signals (+) |
|---|---|---|---|---|
| fact-6 | public_contract | **0.85** | counterparty=Wnuk Consulting, contractor=PEC, amount=397 496,95 zł | money_amount, public_contract_lemma, sentence_local_contract_counterparty, sentence_local_contractor |
| fact-7 | anti_corruption_referral | **0.90** | complainant=Prawo i Sprawiedliwość, institution=CBA, context=(full clause) | anti_corruption_referral_lemma, oversight_institution, sentence_local_actor, sentence_local_institution |
| fact-8 | anti_corruption_referral | **1.00** | complainant=Maciej Bartków, target=Przedsiębiorstwie Energetyki Cieplnej Sp., institution=CBA | anti_corruption_referral_lemma, oversight_institution, sentence_local_actor, sentence_local_target, sentence_local_institution |
| fact-9 | anti_corruption_referral | **0.80** | institution=CBA | anti_corruption_referral_lemma, oversight_institution, sentence_local_institution |
| fact-10 | personal_or_political_tie | **0.80** | subject=Mariusza Wołosza, object=Bartków, context=spouse | named_kinship_lemma, sentence_local_subject, sentence_local_object |
| fact-11 | personal_or_political_tie | **0.75** | subject=Bartków, object=Wołosza, context=związany | explicit_patronage_lemma, sentence_local_subject, sentence_local_object |

### V2 Facts (score < 0.5, for reference)

| ID | Kind | Score | Arguments |
|---|---|---|---|
| fact-0 | governance_dismissal | 0.23 | person=Waldemar Gawron, organization=PiS |
| fact-1 | governance_dismissal | 0.23 | person=Waldemar Gawron, organization=Radzie Miasta |
| fact-2 | governance_dismissal | 0.23 | person=Waldemar Gawron, organization=PIS |
| fact-3 | governance_dismissal | 0.23 | person=Mariusza Wołosza, organization=PiS |
| fact-4 | governance_dismissal | 0.23 | person=Mariusza Wołosza, organization=Radzie Miasta |
| fact-5 | governance_dismissal | 0.23 | person=Mariusza Wołosza, organization=PIS |

### Gap Analysis

**V1 has, V2 misses:**
- No `DISMISSAL` scored ≥ 0.5 (Waldemar Gawron dismissed from Rada Miasta coalition — the low-score governance_dismissal facts correctly remain below threshold).
- V1 emits many `POLITICAL_OFFICE` facts for individual radni; V2 does not surface these (appropriately, they are noisy and low-value).

**V2 has, V1 misses:**
- Richer anti-corruption fact with target (`Przedsiębiorstwie Energetyki Cieplnej Sp.`) — V2 fact-8 scores 1.00 vs V1 having no target.
- Patronage tie (fact-11) via `związany` lemma not captured by V1.

### False Positive Flags

None at score ≥ 0.5.

---

## Article 4: Nowy zaciąg tłustych kotów? (Radomszczańska)

**File:** `radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470`

### Relevance

| | V1 | V2 |
|---|---|---|
| `is_relevant` | `null` (not set) | `true` |

### V2 Proxy Entities

*(None detected — Mirella Zugaj is named directly)*

### V1 Facts

| Fact ID | Kind | Subject | Object | Role | Value | Evidence |
|---|---|---|---|---|---|---|
| fact_24f05d1f27f4591e | PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj | spouse | — | żona Radka Zugaja |
| fact_186e9b62d32a5af0 | PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj | spouse | — | Ciekawe kto jeszcze okaże się super fachowcem… |
| fact_916f1960fdca5137 | APPOINTMENT | Rząsowski | AMW Rewita | Rada Nadzorcza | Rada Nadzorcza | Ta spółka podległa Ministerstwu Obrony Narodowej… |
| fact_09ebe23f133d5fa0 | COMPENSATION | Rząsowski | AMW Rewita | Rada Nadzorcza | 24 tys. zł brutto | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| fact_449b28a8b5f154c4 | APPOINTMENT | Rząsowski | Ministerstwu Obrony Narodowej | — | — | Poprzednik Rząsowskiego na tym stanowisku zarabiał… |
| fact_c9d116265e415f3c | FORMER_PARTY_MEMBERSHIP | Marek Rząsowski | Platforma Obywatelska | — | Platforma Obywatelska | Marek Rząsowski, radny powiatowy PO… |
| fact_e9d48980edef59ee | POLITICAL_OFFICE | Marek Rząsowski | Radny | — | Radny | Marek Rząsowski, radny powiatowy PO… |
| fact_4c744f6819c152ed | ELECTION_CANDIDACY | Jacek Łęski | — | — | — | Zaczynał w kampanii wyborczej Jacka Łęskiego… |

### V2 Facts (score ≥ 0.5)

| ID | Kind | Score | Arguments | Signals (+) |
|---|---|---|---|---|
| fact-0 | party_affiliation | **0.80** | subject=Marek Rząsowski, object=Platforma Obywatelska | party_alias_match, party_profile_lemma |
| fact-1 | governance_appointment | **0.90** | person=Rząsowski, org=AMW Rewita, role=radę nadzorczą | appointment_lemma, sentence_local_person, sentence_local_organization, sentence_local_role |
| fact-2 | governance_appointment | **0.82** | person=Rząsowski, org=AMW Rewita, role=radę nadzorczą | appointment_lemma, discourse_window_person, discourse_window_org, discourse_window_role |
| fact-5 | compensation | **0.93** | funder=AMW Rewita, recipient=Rząsowskiego, amount=24 tys. zł | money_amount, compensation_lemma, discourse_window_organization, sentence_local_compensation_recipient |
| fact-6 | compensation | **0.93** | funder=Ministerstwu Obrony Narodowej, recipient=Rząsowskiego, amount=24 tys. zł | money_amount, compensation_lemma, discourse_window_organization, sentence_local_compensation_recipient |
| fact-9 | personal_or_political_tie | **0.80** | subject=Mirella Zugaj, object=Radka Zugaja, context=spouse | named_kinship_lemma, sentence_local_subject, sentence_local_object |
| fact-10 | personal_or_political_tie | **0.60** | subject=Mirella Zugaj, object=Radka Zugaja, context=spouse/żona | nominalkinship |

### V2 Facts (score < 0.5, for reference)

| ID | Kind | Score | Arguments |
|---|---|---|---|
| fact-3 | governance_appointment | 0.29 | person=Marek Rząsowski, org=PO, role=radę nadzorczą |
| fact-4 | compensation | 0.33 | funder=PO, recipient=Rząsowskiego, amount=24 tys. zł |
| fact-7 | compensation | 0.33 | funder=Platformy, recipient=Rząsowskiego, amount=24 tys. zł |
| fact-8 | compensation | 0.33 | funder=PiS, recipient=Rząsowskiego, amount=24 tys. zł |

### Gap Analysis

**V1 has, V2 misses:**
- `ELECTION_CANDIDACY` for Jacek Łęski (V2 does not have this fact type).
- V1 distinguishes `FORMER_PARTY_MEMBERSHIP` — V2 uses the more general `party_affiliation`.

**V2 has, V1 misses:**
- Explicit `party_affiliation` fact (scored, explicit).
- `compensation` facts (V2 emits these with high confidence).
- Duplicate compensation with both `AMW Rewita` and `Ministerstwu Obrony Narodowej` as funder — minor false positive for MON (MON is the oversight ministry, not the direct payer; AMW Rewita is the correct funder).

### False Positive Flags

⚠️ **fact-6**: `compensation` funder=Ministerstwu Obrony Narodowej score 0.93 — MON is the supervising ministry, not the direct payer of Rząsowski's supervisory board fee. AMW Rewita (fact-5) is correct. Both fire because the discourse window captures the MON mention close to the salary clause.

---

## Cross-Article Summary

### Fix Verification Results

| Fix | Expected | Actual | Result |
|---|---|---|---|
| Charsznica: Kościelniak → GOK governance_appointment removed | Removed or scored < 0.5 | Still 0.87 (×4 deduplicated variants) | ❌ **NOT FIXED** |
| Charsznica: teść proxy tie ≥ 0.5 | score ≥ 0.5 | fact-11 score=0.60 | ✅ **FIXED** |
| Charsznica: dziewczyna tie ≥ 0.5 | score ≥ 0.5 | fact-10 score=0.60 | ✅ **FIXED** |
| AI42: public_employment for Rafał Dobosz @ Gminy Poczesna ≥ 0.5 | score ≥ 0.5 | No `public_employment` candidate emitted at all | ❌ **NOT FIXED** |

### Remaining Issues

1. **Charsznica governance false positive (HIGH PRIORITY)**: `governance_appointment` Tomasz Kościelniak → Gminnego Ośrodka Kultury (score 0.87) is a false positive. Kościelniak is the wójt who made appointments, not someone being appointed to GOK's board. The `discourse_window_organization` signal is firing across sentence boundaries when GOK is mentioned in context of the previous director. Consider: narrowing the discourse window for GOK, or adding a negative signal when the person is also detected as holding a `wójt` role.

2. **AI42 public employment gap (HIGH PRIORITY)**: The entire employment-of-cousin story (Rafał Dobosz hired at Gminy Poczesna) produces no `public_employment` candidate in V2. V1 correctly found multiple appointment facts. The sentence "Na początku lipca, w samorządzie zatrudniono Rafała Dobosza na stanowisku pomocy administracyjnej" should trigger `public_employment`. The verb `zatrudniono` (passive past of `zatrudnić`) may not be matching the current public employment lemma patterns.

3. **Charsznica: employment attributed to wrong person**: `public_employment` fact-8 (Tomasz Kościelniak → Urzędzie Stanu Cywilnego) should be teść → Urzędzie Stanu Cywilnego. The proxy entity was identified correctly, but the employment fact used the wójt's name instead of the proxy.

4. **Charsznica: Jan Kowalski false person tie**: fact-9 ties Jan Kowalski to Tomasz Kościelniak (spouse context). Jan Kowalski is a pseudonym used by an anonymous commenter, not a real person with a kinship relationship to the wójt.

5. **Radomszczańska: duplicate compensation funder**: MON fires as a funder (score 0.93) alongside AMW Rewita (score 0.93). MON is the supervising ministry, not the direct payer.

6. **Charsznica: duplicate governance facts**: fact-0 and fact-4 are identical (same kind, person, org, role, signals); similarly fact-1 and fact-5. De-duplication of identical fact candidates is needed.
