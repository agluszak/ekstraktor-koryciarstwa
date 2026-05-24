# E2E Benchmark Run — 2026-05-24

Run after completing all four plan items from the 2026-05-23 batch.
All 184 V2 tests pass; ruff and ty checks clean.

## Articles benchmarked

Five articles from `reports/expected_article_findings.md` (§7, §10, §17, §25, §30):

| File | Article |
|---|---|
| `onet_totalizator_leca_glowy.html` | Totalizator — prezes odwołany (§30) |
| `onet_wfosigw_lublin.html` | WFOŚiGW Lublin — nowe władze (§7) |
| `wiadomosci.wp.pl__wiedza-doswiadczenie*.html` | Opole — rodzina na swoim (§25) |
| `wiadomosci.wp.pl__zona-posla-pis*.html` | Lublin — żona posła PiS (§17) |
| `olsztyn.tvp.pl__41863255__*downloaded*.html` | Olsztyn — Jarosław Słoma (§10) |

---

## Article-by-article results

### 1. Słoma / PWiK Olsztyn — IMPROVED (was 0 facts, now 1)

**Expected**: Jarosław Słoma → `APPOINTMENT` → Przedsiębiorstwo Wodociągów i Kanalizacji, role wiceprezes.

**Got**:
```
governance_appointment: person=Jarosław Słoma,
                        organization=Przedsiębiorstwa Wodociągów i Kanal,
                        role=prezesa
```

**Assessment**: PASS.  The title-prepend fix (already in preprocessing) allows the title
sentence "Z wiceprezydenta na wiceprezesa. Jarosław Słoma w zarządzie olsztyńskich
wodociągów" to be segmented and NER-processed, providing the key entity + appointment
signal.  Role lands on `prezesa` instead of the expected `wiceprezesa`; the lemma "zająć"
(generic appointment trigger) fires rather than a specific deputy-role lemma.  One-fact
recall is a clear improvement over the prior zero-fact result.

---

### 2. Opole / Królikowska–Jurek cross-employment — STABLE/IMPROVED

**Expected**: Królikowska appointment + Ogłaza–Królikowska partner tie + Jurek–Jurek
spouse tie (no self-tie).

**Got (relevant subset)**:
```
public_employment:         person=Agnieszki Królikowskiej, organization=Generalnego OUW, role=Dyrektora   ✓
governance_appointment:    person=Agnieszki Królikowskiej, organization=Generalnego OUW, role=Dyrektora   ✓
personal_or_political_tie: subject=Szymona Ogłazy, object=Agnieszki Królikowskiej, relationship_detail=?  ✓
personal_or_political_tie: subject=Dariusz Jurek, object=Moniki Jurek, relationship_detail=?              ✓  (spouse)
governance_dismissal:      person=Monika Jurek, organization=OUW, role=dyrektorów
governance_appointment:    person=Monika Jurek, organization=OUW, role=dyrektorów
```

**Assessment**: Core facts recovered.  Self-tie "Dariusz Jurek → Dariusz Jurek" (from the
previous session) is absent — the surname-assignment exclusion factor and resolution-graph
self-tie suppression are both working.  Monika Jurek produces a dismiss+appoint pair on
OUW; the article describes her as wojewoda who may have left and re-joined an OUW role —
co-production here is at worst a false duplicate, not outright wrong.

---

### 3. Lublin / Żona posła PiS (Sobolewska) — GOOD

**Expected**: Sylwia Sobolewska → APPOINTMENT → Lubelskie Koleje + spouse tie to Sobolewski
+ PiS affiliation.

**Got (relevant subset)**:
```
governance_appointment:    person=Sylwii Sobolewskiej, organization=Lubelskie Koleje, role=rady nadzorczej  ✓
governance_appointment:    person=Sylwii Sobolewskiej, organization=Spółka Lubelskie, role=rady nadzorczej  ✓ (alias)
governance_dismissal:      person=Sylwii Sobolewskiej, organization=Orlenie, role=radach nadzorczych        ✓
party_affiliation:         subject=Krzysztofa Sobolewskiego, object=Prawo i Sprawiedliwość                 ✓
personal_or_political_tie: subject=Sylwii Sobolewskiej, object=Krzysztofa Sobolewskiego (×3)              ✓
personal_or_political_tie: subject=żona of Sobolewskiego, object=Krzysztofa Sobolewskiego                 (proxy entity, relation OK)
```

**Assessment**: PASS.  All three headline expectations met.  Three personal-tie facts for
the same pair are duplicates from separate sentences; deduplication is a later concern.

---

### 4. Totalizator Sportowy (leca_glowy) — PARTIAL

**Expected**: Rafał Krzemień → `DISMISSAL` + Mariusz Błaszkiewicz → `APPOINTMENT` (acting).

**Got**:
```
governance_dismissal: person=Rafała Krzemienia, role=prezesa   ✓
governance_dismissal: person=Rafała Krzemienia, role=prezesa   (duplicate)
governance_dismissal: person=Jakub Jaworowski,  role=prezesa   ✗ (Jaworowski is NOT dismissed)
governance_dismissal: person=Prezes,            role=prezesa   ✗ (role entity leaked into person slot)
governance_appointment: person=Jaworowski, organization=Totalizatora, role=rady nadzorczej   ? (possibly his prior supervisory-board role)
governance_appointment: person=Sławomira Nitrasa, role=Dyrektorami                          ✗ (Nitras is a minister, not a director appointee)
```

Błaszkiewicz (the expected acting president) is not in the output.

**Assessment**: PARTIAL.  Krzemień dismissal is correct; Błaszkiewicz appointment is
missing.  Jaworowski dismissal is spurious — Jaworowski is contextual supervisory-board
context, not the dismissed president.  "Prezes" (a role/title) is being resolved as a
person entity and filling the person slot; this is a role-entity-kind classification
issue.  Issue 2 fix (dismissal+appointment co-production) prevented spurious Krzemień
appointment, which is a confirmed improvement.

---

### 5. WFOŚiGW Lublin — PARTIAL (known limitation remains)

**Expected**: Stanisław Mazur → `APPOINTMENT` (prezes), Andrzej Kloc → `APPOINTMENT`
(wiceprezes), Agnieszka Kruk → `DISMISSAL`.

**Got**:
```
governance_dismissal:   person=Jarosław Stawiarski, organization=WFOŚiGW, role=prezesem       ✓  (correct dismissal)
governance_dismissal:   person=Agnieszkę Kruk, organization=WFOŚiGW w Lublinie, role=radzie   ✓
governance_appointment: person=Jarosław Stawiarski, organization=WFOŚiGW w Lublinie, role=prezesem  ✗ (Mazur should be here)
governance_appointment: person=Jerzy Szwaj, role=rady nadzorczej                               ? (plausible)
governance_dismissal:   person=prezesem, organization=WFOŚiGW, role=prezesem                  ✗ (role entity as person)
```

**Assessment**: PARTIAL.  Mazur appointment still missing; Stawiarski wins that slot.
Root cause (from `self_tie_architecture_2026-05-24.md`): Stawiarski's dismissal sentence
has more local entity signal than the Mazur appointment sentence, so Stawiarski's
mentions dominate the appointment event's person role binding.  This requires either
sentence-level event isolation or a stronger sentence-distance prior on
appointment/dismissal co-occurrence.  Agnieszka Kruk dismissal is correctly recovered.
"prezesem" is again a role entity leaking into a person slot.

---

## Summary

| Article | Before | After | Notes |
|---|---|---|---|
| Słoma (§10) | 0 facts | 1 fact ✓ | Title-prepend fix worked |
| Opole (§25) | Self-tie present | Self-tie absent ✓ | Self-tie suppression working |
| Lublin WP (§17) | — | All 3 headline facts ✓ | Good baseline |
| Totalizator (§30) | Krzemień got spurious appt | No spurious appt ✓ | Issue 2 fix worked; Błaszkiewicz still missing |
| WFOŚiGW (§7) | Stawiarski/Mazur confusion | Stawiarski/Mazur confusion persists | Known limitation |

## Recurring problems observed

### A — Role entities leaking into person slots
"prezesem", "Prezes" etc. appear as `person` role fillers in governance facts.
These are role/title entities (EntityKind.ROLE) that should be excluded from the PERSON
role via the entity-kind constraint in the schema.  The `GOVERNANCE_APPOINTMENT` and
`GOVERNANCE_DISMISSAL` schemas restrict the person role to `_PERSON` (EntityKind.PERSON),
but role-entity resolution or NER mislabeling may be producing PERSON-kind candidates
for these strings.  Needs investigation: are "prezesem" / "prezes" being tagged PERSON
by NER, or is the kind constraint not firing?

### B — Stawiarski/Mazur appointment slot confusion
Documented in `self_tie_architecture_2026-05-24.md`.  Stawiarski's dismissal sentence
generates broader local entity context than the Mazur appointment sentence, causing
Stawiarski to win the appointment event's person binding.  Possible approaches:
- Sentence-level event isolation: an event's required roles should prefer fillers from
  the trigger sentence over fillers from adjacent sentences.
- Stronger sentence-distance prior: argument binding signals from the same sentence as
  the trigger should receive a stronger LocalPersonSignal boost vs. WindowPersonSignal.

### C — Duplicate facts from distinct sentences
Same fact (e.g., Krzemień dismissal, Sobolewska–Sobolewski tie) materializes multiple
times from different sentences.  This is by design for now (overproduction); deduplication
belongs in a downstream output layer.

## What remains from the plan

All four plan items are confirmed implemented and tested.  Remaining quality gaps not
covered by the plan:
- WFOŚiGW Stawiarski/Mazur: needs sentence-distance prior or event isolation.
- Role entities in person slots: needs investigation into NER or resolution mislabeling.
- Totalizator: Błaszkiewicz acting-appointment not recovered (thin signal — "pełniący
  obowiązki" rather than a strong appointment lemma).
