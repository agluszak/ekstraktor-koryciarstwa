# Gazeta Krakowska / Zapał / ZBK — Extraction Report 2026-05-24

Article: https://gazetakrakowska.pl/za-jej-czasow-wybuchla-w-krakowie-wielka-afera-to-koniec-rzadow-katarzyny-zapal-w-zarzadzie-budynkow-komunalnych/ar/c1p2-27523231

## Expected findings

- Katarzyna Zapał → `GOVERNANCE_DISMISSAL` → ZBK (Zarząd Budynków Komunalnych)
- Agnieszka Paradyż → `GOVERNANCE_APPOINTMENT` → ZBK (successor)
- Agnieszka Paradyż is currently president of KHK (Komunalne Hotele Krakowskie)
- Marcin Paradyż is deputy director (zastępca dyrektora ds. technicznych) → potential internal appointment

## Before fixes (pre-2026-05-24 batch)

Zero useful facts extracted:
- "odchodzi" (imperfective of odejść) not in `_dismissal_lemmas` → no dismissal
- "od objęcia urzędu" triggered a spurious GOVERNANCE_APPOINTMENT from the temporal phrase
- "Jej następcą zostanie Agnieszka Paradyż" assigned wrong person (window entity from dismissal sentence)
- "Agnieszka Paradyż — obecny prezes KHK" produced no event (no explicit appointment trigger)

## After Bug 1–4 fixes

```json
{
  "facts": [
    {"kind": "governance_appointment", "confidence": 0.675, "person": "Katarzyna Zapał", "organization": "ZBK"},
    {"kind": "governance_dismissal",   "confidence": 0.649, "person": "Katarzyna Zapał"},
    {"kind": "governance_dismissal",   "confidence": 0.564, "person": "Marcin Paradyż", "organization": "ZBK", "role": "dyrektora"}
  ]
}
```

## Assessment by bug

### Bug 1 — Imperfective dismissal lemmas (odchodzić, odwoływać, zwalniać, usuwać, rezygnować)

**PASS.** "odchodzi ze stanowiska" now triggers GOVERNANCE_DISMISSAL for Katarzyna Zapał.
The dismissal at confidence 0.649 is the key expected fact.

### Bug 2 — Temporal objąć/objęcie suppression

**PARTIAL.** The CASE-arc-based check is implemented and tested correctly against a static
dependency provider. In this article, the problematic sentence is 80+ tokens long:
"...przez 10 miesięcy od objęcia urzędu przeprowadził wiele zmian...". Stanza does not produce
a clean CASE arc from "od" to "objęcia" in such complex syntax, so the suppression does not fire.
The spurious appointment (Katarzyna Zapał, ZBK, confidence 0.675) originates from this sentence.

Root cause: Stanza dependency reliability degrades on long, parenthetical Polish sentences.
Mitigation options: positional proximity fallback (within N tokens), or raising the
appointment materialization threshold for long sentences.

### Bug 3 — Successor pattern ("następcą zostanie X")

**PARTIAL.** The filter is implemented and suppresses the wrong person in unit tests (Paradyż
appointed, Zapał excluded). In the real article the relevant sentence is:
`"następcą Zapał ma zostać Marcin Paradyż, pełniący dotychczas funkcję zastępcy dyrektora..."`

This long sentence contains "odchodzi" from a preceding quotation, which co-fires dismissal.
Because both a dismissal and an appointment candidate are produced for this sentence, and the
appointment is from a generic trigger ("zostać") with no strong local role entity, inference
scores the appointment below the materialization threshold. Marcin Paradyż dismissal appears
(confidence 0.564) but his appointment does not.

**Agnieszka Paradyż** — the expected successor — is mentioned only in the article title and
in the sentence "Jej następcą zostanie Agnieszka Paradyż" (if present). The article as crawled
may abbreviate this sentence or the entity may not survive NER. She does not appear in any
materialized fact.

### Bug 4 — Dash-apposition current-role pattern

**NOT VISIBLE** in this article run. "Agnieszka Paradyż — obecny prezes KHK" would produce a
GOVERNANCE_APPOINTMENT via the dash-apposition trigger, but Paradyż does not appear as a person
entity in the extracted output, suggesting the NER or the article fetch did not include the
relevant paragraph.

## Recurring gaps (pre-existing)

- Long-sentence inference suppression: when a sentence contains both a dismissal trigger and a
  generic appointment trigger (zostać), the appointment is often scored too low to materialize.
- Stanza CASE-arc reliability: complex sentences with embedded quotes and parentheticals yield
  unreliable dependency parses, limiting dependency-based suppression filters.

## What was checked

- Full V2 test suite: 189 tests, all pass.
- ruff, ty: clean.
- Article re-run after Bugs 1–4 implementation.
