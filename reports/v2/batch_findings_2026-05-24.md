# Batch Findings — 2026-05-24

Fresh e2e run across 5 articles after Zapał/ZBK governance fixes.

## Status of previous plan (jazzy-painting-turtle.md Issues 1–4)

| Issue | Description | Status |
|-------|-------------|--------|
| 1 | Self-tie via proxy entity resolution | **PARTIAL** — proxy case is addressed by `resolution.py` `_add_self_tie_reference_factors`, but direct self-tie (subject=object with no alternatives) still materializes (Charsznica) |
| 2 | Dismissal+appointment co-production for same person | **DONE** — `_has_tight_generic_dismissal_cluster` in `governance.py` |
| 3 | Thin-article title stripping (Słoma, 0 facts) | **DONE** — title prepended as first paragraph in `preprocessing.py`; Słoma now produces 1 governance_appointment |
| 4 | News-outlet entities in employment/governance org roles | **DONE** — `entity_context_policy.py` suppression table extended |

---

## Articles run

### businessinsider_kadrowa_czystka_panstwowa_spolka.html (PZU kadry)

**Expected:** Dismissals of Górecki, Kubicza (only z wyjątkiem clause), 8 board appointments.

**Actual:**
```
governance_dismissal Paweł Górecki PZU           ✓
governance_dismissal Marcina Kubiczy             ✗ (spurious — "z wyjątkiem Marcina Kubiczy")
```
Zero appointments extracted. Eight named appointees in the article are missing.

**Bugs:** Bug C (wyjątek clause), Bug D (missing list appointments).

---

### dziennikpolski24 Charsznica (webarchive 20260422)

**Expected:** public_employment for partnerka of Kościelniak; patronage facts with Kościelniak as subject.

**Actual:**
```
public_employment  dziewczyna of Tomasz Kościelniak  urzędzie         ✓ (partial — "dziewczyna" not resolved to name)
public_employment  teść of Tomasz Kościelniak         Urząd Stanu Cywilnego  ✓
patronage_network_tie  subject=entity-13  object=entity-13  ✗ SELF-TIE
personal_or_political_tie  subject=proxy-36  object=entity-13       ✓
personal_or_political_tie  subject=entity-5  object=entity-13       ✗ entity-5 is "Jan Kowalski" (ghost entity)
patronage_allegation  subject=entity-13  target=proxy-37  ✓
```

Debug shows `entity-13 = Tomasza Kościelniaka`, `entity-5 = Jan Kowalski` (ghost entity, ref_ids=[]).

`patronage_network_tie { subject: entity-13, object: entity-13 }` — direct self-tie survives because entity-13 is the only candidate in both roles; the 0.000001 penalty fires but there are no alternatives to prefer.

`entity-5 = Jan Kowalski` appears in a personal_or_political_tie but is a phantom from HTML boilerplate (cookie notice or navigation).

**Bugs:** Bug A (self-tie), Bug F (ghost entity from HTML boilerplate).

---

### niezalezna_polski2050_synekury.html

**Expected:** Governance appointments for Bałajewicz (KZN), Filip Curyło (RN KZN), Emil Rojek (RN KZN); Waldemar Buda as political connection; multiple compensation facts.

**Actual (selection):**
```
governance_appointment  Łukasz Bałajewicz   KZN               ✓ (repeated 4×)
governance_appointment  Prezes              KZN               ✗ Bug B
governance_appointment  Emil Rojek          RN KZN            ✓
governance_appointment  Filip Curyło        (no org)          partial
governance_appointment  Łukasz Bałajewicz   Biuro Obsługi Medialnej Kancelarii Sejmu  ✗ wrong org
```

"Prezes" (the Polish title for CEO/president) is being extracted as a PERSON entity and landing in the person slot of a governance fact. NER is mislabeling the title word as a named person.

**Bug:** Bug B (governance role title as PERSON).

---

### wiadomosci.wp.pl Opole (wiedza-doswiadczenie)

**Expected:** Employment/ties for Kościelniak family, Agnieszki Królikowskiej appointment, Monika Jurek dismissal.

**Actual (governance subset):**
```
governance_appointment  Agnieszki Królikowskiej  Generalnego Opolskiego Urzędu Wojewódzkiego  ✓
governance_dismissal    Monika Jurek              OUW   ✓
governance_appointment  Monika Jurek              OUW   ✗ (dismissal+appointment co-produced for same person)
governance_appointment  Andrzej Buła              Urzędu Wojewódzkiego  ✓
```

The Monika Jurek dismissal+appointment co-production reappears. In this sentence "Jurek odwołała się od tej decyzji" — "odwołała" matches dismissal lemma (`odwoływać`), but the sentence also contains "zostać" or another appointment trigger. The `_has_tight_generic_dismissal_cluster` guard is not catching this case because the generic and dismissal tokens are not close enough (or "odwoływać" is being parsed differently).

**Bug:** Bug G (regression — dismissal+appointment co-production still occurring in edge case).

---

## Bugs summary

### Bug A — Direct self-tie in tie/patronage facts
**Symptom:** `patronage_network_tie { subject: entity-13, object: entity-13 }` in Charsznica.

**Root cause:** When the only candidate for both SUBJECT and OBJECT roles is the same entity, the 0.000001 self-tie penalty in the distinct-role constraint fires but there are no alternatives to prefer. The event is active, and inference marginalizes each role independently — both peak on entity-13. Materialization then selects entity-13 for both roles.

**Fix location:** `pipeline_v2/inference/materialize.py`  
Add a post-inference guard: after selecting role fillers, check all `distinct_role_constraints` whose `same_candidate_penalty == _SELF_TIE_DIRECT`. If the selected fillers for left_role and right_role resolve to the same entity, drop this fact entirely.

---

### Bug B — Governance role title ("Prezes") extracted as PERSON
**Symptom:** `governance_appointment { person: "Prezes", organization: "KZN" }`.

**Root cause:** The governance role word "Prezes" is being labeled as a named entity (PERSON) by NER. In Polish, "Prezes" can function as a title before a name ("Prezes Kowalski") but NER is not distinguishing this from a person's name.

**Fix location:** `pipeline_v2/entity_classification.py` or where person entities are filtered.  
After NER, demote any `EntityCandidate` of kind=PERSON whose canonical surface form's morph lemmas are entirely within `_governance_role_lemmas` (prezes, dyrektor, wiceprezes, etc.). Such tokens are titles, not names.

---

### Bug C — "z wyjątkiem X" exception clause triggers spurious dismissal
**Symptom:** `governance_dismissal { person: Marcin Kubicza }` from "z wyjątkiem Marcina Kubiczy pełniącego funkcję...".

**Root cause:** The governance producer finds dismissal lemmas in the sentence and produces a dismissal event. "Kubicza" is the nearest person entity. The exception clause structure ("with the exception of X who...") is not a dismissal.

**Fix location:** `pipeline_v2/governance.py`, `_candidate_kinds` or pre-filter.  
Detect sentences containing "wyjątek" / "z wyjątkiem" and suppress dismissal events where the person entity is syntactically local to the exception clause.

---

### Bug D — Missing list appointments ("powołano m.in. X, Y, Z")
**Symptom:** PZU article has 8 board appointees named in a list; 0 appointments extracted.

**Root cause:** The governance producer binds one person per event candidate. When a sentence has "powołano m.in. [NAME1], [NAME2], [NAME3]..." the event is created once but only the most prominent/closest person gets the binding. The other 7 are never bound.

**Fix location:** `pipeline_v2/governance.py`, argument binding section.  
For appointment events triggered by a single sentence containing multiple person entities in a conjoined list, emit one `ArgumentBindingCandidate` per person entity in the APPOINTEE role. Inference then selects the best; but all should compete so separate facts can be materialized for each.

Actually the right fix is that for a single "powołano" event, we need multiple events — one per person in the list. OR, the single event must have multiple APPOINTEE role candidates, one per person.

Given the architecture (one event per trigger, one person slot per event), the cleaner fix is: detect the list pattern and emit N appointment event candidates, one per person name in the conjunction.

---

### Bug E — FUNDING vs PUBLIC_CONTRACT misclassification
**Symptom:** Paid promotional services (e.g., 100k PLN for media promotion) labeled FUNDING instead of PUBLIC_CONTRACT.

**Root cause:** The public money producer uses paid-service triggers for both FUNDING and PUBLIC_CONTRACT. When the payment is for a service (reklama, promocja, obsługa), it should be a contract. When it is a grant (dotacja, subwencja), it should be FUNDING. The distinction may not be encoded.

**Fix location:** `pipeline_v2/public_money.py` — tighten the FUNDING trigger lemma set to exclude service/promotion words; add service-type triggers to PUBLIC_CONTRACT.

*(Requires dedicated article run to confirm; lower priority than A–D.)*

---

### Bug F — Ghost entities from HTML boilerplate (cookies, navigation)
**Symptom:** "Jan Kowalski" entity in Charsznica article; appears in a personal_or_political_tie with Kościelniak despite not being a subject of the article.

**Root cause:** The HTML preprocessor did not strip the specific boilerplate block containing "Jan Kowalski" (likely a cookie consent dialog or navigation element with a sample/placeholder name). The entity then competes in tie inference.

**Fix location:** `pipeline_v2/preprocessing.py` — inspect the webarchive HTML to identify the boilerplate block; add the relevant selectors to the CSS filter list.

*(Requires inspecting the raw HTML to identify the exact block.)*

---

### Bug G — Regression: Monika Jurek dismissal+appointment co-production (Opole article)
**Symptom:** `governance_dismissal Monika Jurek OUW` + `governance_appointment Monika Jurek OUW` in the same article.

**Root cause:** "Jurek odwołała się od tej decyzji" — "odwołała" matches `odwoływać` (dismissal lemma). But "odwołać się" (reflexive) means "to appeal a decision", not "to be dismissed". The reflexive construction is not distinguished from the transitive "odwołać kogoś".

**Fix location:** `pipeline_v2/governance.py`, dismissal detection.  
Detect the reflexive `odwołać się` pattern (REFL morph tag or "się" within N tokens of "odwołać") and suppress the dismissal event for that sentence.

---

## Prioritized fix order

1. **Bug G** — Regression; dismissal+appointment logic already had a fix; the reflexive "odwołać się" case is a clear gap. One new lemma exclusion pattern.
2. **Bug A** — Self-tie materialization guard; low-risk post-inference filter in `materialize.py`.
3. **Bug B** — "Prezes" as PERSON; needs entity classification guard on role-title lemmas.
4. **Bug C** — "z wyjątkiem" exception suppression; governance producer filter.
5. **Bug D** — List appointment expansion; governance producer structural change.
6. **Bug F** — Ghost entities; requires HTML inspection first.
7. **Bug E** — FUNDING/PUBLIC_CONTRACT; requires targeted article run to confirm.

---

## What was checked

- Full V2 test suite: 189 tests, all pass.
- ruff, ty: clean.
- 5 article e2e runs (PZU, Charsznica, Niezalezna, Opole, Słoma confirmation).
- Słoma confirmed working (1 governance_appointment) — Issue 3 from prior plan is resolved.
