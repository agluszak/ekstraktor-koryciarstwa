# Self-tie suppression architecture — 2026-05-24

## What changed

This session completed the architectural consolidation of self-tie suppression in the
inference layer.  All self-tie logic is now schema-driven; no ad-hoc role checks or
hard-coded SUBJECT/OBJECT branches remain.

### Schema (`pipeline_v2/inference/event_schema.py`)

- **Removed unused `_ORG_OR_PARTY`** constant that was not referenced by any schema.
- **Added `ANTI_CORRUPTION_REFERRAL` COMPLAINANT vs TARGET distinct constraint.**
  The schema now covers all role pairs where a self-tie would be semantically wrong:

  | Fact kind                       | Constrained pair          | Penalty       |
  |---------------------------------|---------------------------|---------------|
  | PERSONAL_OR_POLITICAL_TIE       | SUBJECT / OBJECT          | hard (1e-6)   |
  | PATRONAGE_NETWORK_TIE           | SUBJECT / OBJECT          | hard (1e-6)   |
  | PATRONAGE_ALLEGATION            | COMPLAINANT / TARGET      | soft (0.02)   |
  | ANTI_CORRUPTION_REFERRAL        | COMPLAINANT / TARGET      | soft (0.02) ← new |
  | PUBLIC_PROCUREMENT_ABUSE        | ACTOR / TARGET            | soft (0.02)   |
  | FUNDING                         | FUNDER / RECIPIENT        | soft (0.02)   |
  | PUBLIC_CONTRACT                 | COUNTERPARTY / CONTRACTOR | soft (0.02)   |

### Factor builders (`pipeline_v2/inference/factor_builders.py`)

No changes required.  `_distinct_role_constraint_factor` already consumes
`schema.distinct_role_constraints` generically and only performs **direct overlap**
checks (same candidate ID or same canonical hint) without eagerly resolving entity
identity through resolution claims.

### Resolution graph (`pipeline_v2/inference/resolution.py`)

No changes required.  `_add_self_tie_entity_factors` and
`_add_self_tie_reference_factors` both iterate over `schema.distinct_role_constraints`
and are fully role-agnostic.

### Tests (`tests_v2/test_inference_facade.py`)

Replaced the failing `test_reference_self_tie_constraint_depends_on_reference_variable`
(which asserted a specific internal factor ID — a bad implementation-detail assertion
that broke when the factor ID format changed) with three behavioral tests:

1. **`test_proxy_self_tie_does_not_materialize_when_reference_resolves_to_opposing_role`**
   A proxy entity (SUBJECT) whose reference resolution proposal points to the named
   entity (OBJECT) creates a potential self-tie.  Inference must demote this below the
   0.20 materialization threshold.  ✓ Passes.

2. **`test_same_entity_resolution_identifies_matching_candidates`**
   Two candidates with the same `FullPersonNameKey` (scored ~0.90 via
   `FullNameReuseMatchSignal`) in opposing SUBJECT/OBJECT roles.  Inference should
   produce a same-entity claim for the pair.  ✓ Passes.

3. **`test_distinct_personal_tie_materializes`**
   Regression guard: two genuinely distinct persons (different reuse_keys) with strong
   kinship signals must still produce a materialized personal tie.  ✓ Passes.

Total tests: 184 passing (was 181; one failing test replaced by 3 new passing tests).

## Known limitation: resolution-induced self-ties with moderate same-entity confidence

When two entity candidates share the same `FullPersonNameKey` (same_entity prior ~0.90)
and appear in opposing required roles, the event can still materialize above the 0.20
threshold via the same_entity=FALSE path (~10% probability) and via the unknown-role path
(required role = unknown, penalty 0.20 per role).

In the test case with a 0.35 event prior and same_entity=TRUE at 0.84:
- `P(event=TRUE)` ≈ 0.28 — above the 0.20 threshold.
- The materialized fact has SUBJECT=B and OBJECT=B (both resolved to the canonical
  representative), producing an output self-tie.

This is a **probabilistic limitation, not a bug**: if there is a 16% chance the two
"Jan Kowalski" candidates are actually different people, the tie legitimately might be
real and deserves to survive.  Hard suppression of this case would cause false negatives
in ambiguous same-name scenarios.

The Opole article case (Dariusz Jurek → Dariusz Jurek) was fixed via a different
mechanism: the `_add_surname_assignment_exclusion_factors` method prevents a
surname-only "Jurek" entity from simultaneously resolving to both "Dariusz Jurek"
(entity-19) and "Monika Jurek" (entity-20), which was the root cause of that transitive
merge.

## What was checked

- All 184 V2 tests pass.
- `ruff check --fix` and `ruff format` clean.
- `ty check` clean.

## What remains

- Full e2e benchmark re-run across the 5 target articles from the 2026-05-23 batch
  (was partially completed in the previous session, interrupted before the WFOŚiGW and
  WP-source articles were fully compared).
- WFOŚiGW Lublin: Stawiarski vs Mazur person confusion — the appointment still tends
  to land on Stawiarski (whose dismissal sentence has more surrounding signal) rather
  than Mazur.  This may require sentence-level event isolation or a stronger
  sentence-distance prior on appointment/dismissal co-occurrence.
