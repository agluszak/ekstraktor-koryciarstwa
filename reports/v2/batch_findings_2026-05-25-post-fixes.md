# Post-fix batch findings — 2026-05-25

Run after implementing pipeline fixes from `batch_findings_2026-05-25.md` (issues 1–7).
Batch: `output/batch_2026-05-25-post-fixes/` (33 articles, same inputs as pre-fix run).

## Summary

| Metric | Pre-fix (2026-05-24) | Post-fix (2026-05-25) |
|--------|----------------------|------------------------|
| Total facts | ~270 | 455 |
| governance_appointment | ~50 | 84 |
| extended_kinship | ~25 | 42 |
| former_party_membership | ~0 | 4 |
| party_affiliation | ~20 | 34 |
| political_office* | varies | 96 |

*political_office count is high due to noise from low-confidence inference; suppression via
materialization gate (Fix 4) improved but did not fully eliminate no-subject cases.

## Fix-by-fix verification

### Fix 1 — Sentence splitter + CONJ expansion (was: list appointments not extracted)

**Root cause corrected:** "Do nadzoru powołano m.in." was fragmented into its own sentence
because the splitter treated "." after "m.in" as a sentence boundary.

**New approach:** `pipeline_v2/segmentation.py` now carries an `_ABBREVS` set of ~40 Polish
abbreviations (m.in, np, tj, dr, prof, etc.). `split_sentences` uses `finditer` instead of
`split`, skipping potential break-points where the left side ends with a known abbreviation.

**Result:** The PZU article (businessinsider_kadrowa_czystka) now produces:
- `governance_appointment` for Wojciecha Olejniczaka / radzie nadzorczej (conf 0.322) ✓
- CONJ expansion works for within-sentence lists like "powołano A, B i C" — verified by
  `test_governance_stage_list_appointments_via_conj` (was failing, now passes).

### Fix 2 — "narzeczona"/"narzeczony" kinship lemmas

Added to `_family_details_by_lemma` in both `ties.py` and `nominal_coreference.py`.

**Result:** PSL wiceminister article (Znajoma ministra, brat wiceministra):
- `extended_kinship` for Marta Giermasińska / Dariusz Klimczak, relationship_detail=spouse,
  context=narzeczony ✓

### Fix 3 + Fix 7 — SLD alias, profile lemmas, FORMER_PARTY_MEMBERSHIP

Added `SLD`, `Sojusz Lewicy Demokratycznej`, `TD`, `Trzecia Droga` to `_aliases`.
Added "szef", "przewodniczący", "wódz", "kierownik", "sekretarz", "współzałożyciel"
to `_profile_lemmas`.
Widened `_has_profile_context` window: before=3, after=5 tokens (was before=2, after=0).
Widened `_attached_profile_person` gap limit: >5 tokens (was >2).

**Result:**
- PZU article: `former_party_membership` for Wojciech Olejniczak / Sojusz Lewicy
  Demokratycznej (conf 0.7) ✓
- Test `test_former_party_membership_person_after_party` ("Do Platformy Obywatelskiej należał
  były poseł Jan Kowalski") now passes ✓
- No regression on `test_former_party_membership_context_does_not_leak_to_unrelated_party` ✓

### Fix 4 — POLITICAL_OFFICE / ELECTION_CANDIDACY materialization gate

Added case to `_meets_materialization_requirements` requiring `PERSON` role. Suppresses
zero-subject political_office and election_candidacy noise.

### Fix 5 — Reflexive "odwołać się" guard

Reflexive particle check via `SyntaxView.token_children` for "się" child of trigger token.

**Result:** Opole article (wiedza-doswiadczenie):
- Only 1 `governance_dismissal` (Monika Jurek / OUW / Wojewody) — a real dismissal ✓
- No spurious dismissal from "odwołała się od decyzji" pattern ✓

### Fix 6 — Symmetric kinship deduplication

Post-materialization dedup pass in `FactAssessmentMaterializer.materialize()`. For
`EXTENDED_KINSHIP` and `PERSONAL_OR_POLITICAL_TIE` facts where the same
frozenset({subject_entity_id, object_entity_id}) appears more than once under the same
`FactKind`, only the highest-scored record is kept (facts are already sorted descending).

## Remaining gaps (not addressed in this pass)

- `political_office` count is high (96) — many are low-confidence noise that passes the
  materialization threshold. A stricter prior or role-binding gate is needed.
- `election_candidacy` noise: "Allianza OFE" recognised as a person candidate (NER issue).
- Sentence fragmentation persists in some articles (e.g., lists separated by paragraph breaks
  in HTML rather than abbreviation boundaries).
- `governance_appointment` confidence for Olejniczak (0.322) is low because the person is in
  a window (next sentence) rather than the trigger sentence — the sentence splitter fix
  merged m.in. cases but not all paragraph-break cases.

## Test suite

212 tests, all passing (was 209 before this work; 3 new tests added in the previous session
were also fixed/unblocked by these changes).
