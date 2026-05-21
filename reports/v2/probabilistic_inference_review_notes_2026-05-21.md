# Probabilistic Inference Migration Review Notes

Date: 2026-05-21

## Summary

The probabilistic-inference migration made real progress: active domain producers now
emit `EventCandidate` and `ArgumentBindingCandidate`, pgmpy is behind a backend
facade, the main runtime uses a single probabilistic scoring stage, and the V2 test
suite passes.

However, the implementation is not yet the intended end state. The most important
remaining issue is conceptual: materialized facts are still being written back into
`ExtractionStore.fact_candidates`, and old flat fact-candidate classes remain a
first-class code surface. That keeps the V1/V2 hybrid alive even though producers
mostly moved to event-first output.

## What The End State Must Look Like

The authoritative extraction graph should contain:

- evidence spans,
- mentions and references,
- entity candidates,
- event candidates,
- argument binding candidates,
- inference variables/factors,
- posterior assessments,
- resolution/reference/same-event claims.

`FactCandidateRecord` should be a final projection only. It should be created after
inference for output, reports, and compatibility with external consumers if needed.
It should not be stored as a candidate in `ExtractionStore`, and it should not be the
input to same-fact/entity/reference inference.

The store should not be cleared and repopulated during scoring. Scoring may add
assessments, inferred claims, and materialized output views, but it must not replace
producer hypotheses.

## Review Findings

### 1. Materialized facts are still stored as candidates

`FactAssessmentMaterializer` clears `document.store.fact_candidates` and then inserts
`MaterializedFactCandidate` records back into the same store.

Why this is a problem:

- It collapses the distinction between hypotheses and output projections.
- Downstream code sees final inferred facts as if they were producer candidates.
- Same-fact resolution currently runs over materialized facts, not event/binding
  hypotheses.
- Tests can keep asserting old `store.fact_candidates` behavior, hiding architecture
  drift.

Expected correction:

- Keep materialized fact records on `ArticleDocument.materialized_fact_records` or a
  dedicated `MaterializedFactStore`.
- Do not put `MaterializedFactCandidate` into `ExtractionStore.fact_candidates`.
- Remove `clear_fact_candidates()` from normal scoring flow.
- Rename old `fact_candidates` surfaces if they remain temporarily, so it is obvious
  whether a record is a producer hypothesis or an output projection.

### 2. Inference is still mostly staged unary scoring

The new runtime runs pgmpy, but many graph components are unary factors created from
old deterministic scorers:

- entity resolution: old `EntityResolutionScorer` score becomes a unary prior,
- reference resolution: old `ReferenceResolutionScorer` score becomes a categorical
  prior,
- fact resolution: old `FactResolutionScorer` score is multiplied by final fact
  scores,
- event scoring: event prior and role priors are mostly independent, connected only
  by simple event-role constraints.

This is better than a terminal scorer, but it is not yet the desired factor graph.
The desired model should let identity/reference/same-event variables and event/role
variables influence each other inside one connected graph where useful.

Expected correction:

- Build one inference spec per bounded connected component containing events,
  role fillers, entity resolution variables, reference target variables, and
  same-event variables together.
- Use factors to connect them, not post-hoc multiplication.
- Example: if a reference target is low confidence, facts using that reference should
  be lower confidence; if a strongly supported event depends on a reference, that
  should also support that reference target.

### 3. Role schemas are not enforced strongly enough

`RoleSpec.allowed_entity_kinds` exists, but current role-state building mostly trusts
whatever bindings producers emit and adjusts score from signals.

Why this matters:

- Party leakage into organization/workplace slots remains likely.
- Controller/ministry/direct-employer alternatives are still producer/scorer
  heuristics, not graph constraints.
- The graph cannot yet express "this filler is type-incompatible for this role" as a
  reusable typed factor.

Expected correction:

- Add role-schema compatibility factors for every entity filler.
- Penalize or disallow incompatible kinds unless an explicit role schema allows them.
- Keep political parties separate from ordinary organization/workplace slots unless a
  fact kind explicitly allows party-as-object.
- Add behavior tests where party entities are present in the same sentence but should
  not win workplace/organization roles.

### 4. Old flat fact candidate classes remain too prominent

`candidates.py` still contains old classes such as `GovernanceFactCandidate`,
`PublicEmploymentFactCandidate`, `MoneyTransferFactCandidate`, and `BinaryFactCandidate`.
Many tests still call `to_fact_record()` on `store.fact_candidates`.

Why this matters:

- It makes future agents think flat facts are still the producer API.
- It encourages bug fixes against materialized fact tuples instead of event/role
  binding hypotheses.
- It contradicts the "no compatibility shims" direction.

Expected correction:

- Move legacy flat candidates out of active `pipeline_v2` code or delete them once
  tests are migrated.
- Update tests to assert event candidates, role alternatives, inferred marginals, and
  materialized output records as separate things.
- Keep `FactCandidateRecord` only as output projection and report surface.

### 5. Old scorer classes and old standalone scoring stages still exist

The main runtime no longer uses `ResolutionScoringStage` / `FactResolutionStage`, but
tests still call them, and `FactRecordScorer` remains in `scoring.py`.

Expected correction:

- Delete `FactRecordScorer` after fact prior logic is fully represented as factor
  builders/policies.
- Delete or clearly quarantine old standalone stages if they are no longer active.
- Do not keep parallel old/new scoring APIs unless there is a very short-lived
  migration reason documented in the same PR.

### 6. pgmpy warnings should not be ignored

The current V2 suite passes but emits pgmpy warnings, including a divide-by-invalid
warning from `DiscreteFactor`.

Expected correction:

- Add backend-level tests for degenerate/zero-potential cases.
- Ensure every factor table has valid positive mass and normalized semantics where
  expected.
- Treat backend warnings as a correctness signal, not harmless noise.

## Assumptions Future Agents Must Preserve

- Passing tests is not sufficient if the architecture regresses to flat facts,
  hidden mutation, or scorer-shaped compatibility layers.
- Producers emit event and role-binding hypotheses. They do not emit final facts.
- Inference emits posterior assessments and inferred claims. It does not rewrite the
  producer graph.
- Materialization is a read/projection step. It may create output records, but it must
  not replace candidates in `ExtractionStore`.
- `pgmpy` is replaceable infrastructure. Keep it behind `InferenceBackend`.
- Role order is semantic, not tuple order. Use `EventRole` and typed role schemas.
- Alternatives should remain visible. Do not silently choose "best" people/orgs in
  producers or materializers when multiple plausible role fillers exist.
- Store records should be typed and append-oriented. Avoid clearing/rebuilding store
  collections during normal pipeline stages.
- JSON is only an output boundary. Do not use JSON-like dicts as internal graph data.
- Behavior tests should assert facts, roles, alternatives, scores, and claims; they
  should not assert exact generated IDs or implementation internals.

## Recommended Next Steps

1. Stop writing materialized facts into `ExtractionStore.fact_candidates`.
2. Split tests between producer graph assertions and output projection assertions.
3. Remove old flat candidate classes from active producer/test paths.
4. Move entity/reference/same-event variables into the same bounded inference specs
   as event/role variables.
5. Add role-schema compatibility factors and tests for party leakage.
6. Delete `FactRecordScorer` and old standalone scoring stages once no tests depend
   on them.
7. Add pgmpy backend tests for disconnected graphs, zero/near-zero potentials, and
   multi-variable connected components.

