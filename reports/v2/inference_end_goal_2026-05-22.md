# V2 Inference End Goal And Implementation Plan

Date: 2026-05-22

## Purpose

This document describes the desired end state for V2 inference. It is stricter than
the first migration plan because the current implementation already has event-first
producers, a pgmpy backend facade, role variables, and materialized role
alternatives. The remaining risk is that V2 stops halfway and keeps old staged
scoring behavior behind newer names.

The end goal is joint probabilistic inference over a typed hypothesis graph. The
system should overproduce candidates, preserve competing alternatives, and assign
posterior confidence to events, role fillers, entity/reference resolution, and
same-event claims. Materialized facts are only a projection from those posterior
states.

## Current State

The current V2 runtime is already better than V1 in several important ways:

- Domain producers emit `EventCandidate` and `ArgumentBindingCandidate` records.
- Argument order is represented through semantic `EventRole` values.
- `pgmpy` is behind `InferenceBackend`.
- Role alternatives are visible in output.
- Typed semantic context signals can lower bad bindings such as party/media/owner
  leakage.
- Self-tie contradictions are visible and low-scored instead of silently deleted.

However, this is not the final architecture:

- Identity, reference, and same-event resolution are not yet fully joint with event
  and role inference.
- Some confidence behavior still happens during materialization, especially selected
  role caps from negative signals.
- Several factors are effectively unary priors derived from previous staged scorers.
- The graph does not yet let a strong event support a reference target, or a weak
  reference target lower an event role, inside one connected component.

Transitional caps and prior blending are acceptable short-term safeguards. They are
not the desired end state.

## End State

The authoritative internal object is a typed hypothesis graph, not a fact list.

The graph contains:

- evidence spans,
- mentions,
- reference mentions,
- entity candidates,
- event candidates,
- argument binding candidates,
- inference variables,
- inference factors,
- posterior assessments,
- inferred resolution/reference/same-event claims.

`FactCandidateRecord` is a final output projection only. It is not produced by domain
extractors, is not used as an inference input, and is not stored back into
`ExtractionStore` as a producer candidate.

Inference must be backend-neutral. `pgmpy` is the first backend implementation, not
the architecture. Domain code, output code, and normal tests should depend on V2-owned
records such as `InferenceGraphSpec`, `InferenceVariable`, `InferenceFactor`, and
`InferenceResult`.

## Variable Semantics

Use these variable families as the stable modeling surface:

- `EventActive(event_id) -> {false, true}`
- `RoleFiller(event_id, role) -> {candidate fillers..., unknown}`
- `SameEntity(entity_a, entity_b) -> {false, true}`
- `ReferenceTarget(reference_id) -> {candidate entities..., unknown}`
- `SameEvent(event_a, event_b) -> {false, true}`

Additional variable families are allowed only when they model a real graph question,
not when they are a convenient place to store domain fields. For example, an
`EntityContext(entity_id, context_kind)` variable may be reasonable if it represents
uncertain evidence such as "media outlet", "party organization", or "generic owner".
It should not become an entity god-object field.

Role variables are categorical. Competing fillers for one role belong in one
`RoleFiller` variable, with `unknown` as an explicit state. They should not become a
Cartesian product of separate flat facts.

Argument direction is modeled through roles, not tuple position:

```text
X zatrudnił Y w Z
Y został zatrudniony przez X w Z
zatrudniono Y w Z
```

All of these should bind the same semantic roles when the evidence supports them:

```text
EventActive(public_employment_event)
RoleFiller(event, HIRING_AUTHORITY) -> X or unknown
RoleFiller(event, EMPLOYEE) -> Y
RoleFiller(event, WORKPLACE) -> Z
```

## Factor Families

The implementation should grow by adding typed, composable factor families. It should
not grow by adding more cases to one central scorer.

Required factor families:

- Event evidence factors from trigger lemmas, morphology, dependency parses, amount
  spans, quote/reporting context, and domain cue evidence.
- Role evidence factors from direct dependency arcs, prepositional attachments,
  passive/active voice, apposition, paragraph locality, and trigger proximity.
- Role schema compatibility factors for allowed entity kinds and domain-specific
  semantic contexts.
- Directional syntax factors that distinguish subject, object, passive subject,
  oblique actor, possessive context, and prepositional role evidence.
- Reference-target factors from coreference, pronouns, omitted subjects, surname-only
  mentions, descriptors, and proxy phrases.
- Same-entity factors from lemma-normalized names, morphology, aliases, acronyms,
  context similarity, contradiction evidence, and "nie mylić z" evidence.
- Same-event factors from shared triggers, overlapping evidence, compatible role
  fillers, semantic similarity, and duplicate-report structure.
- Distinct-role constraint factors for relations where two roles must not resolve to
  the same entity, especially personal or political ties.
- Context contradiction factors for party organizations, media/reporting sources,
  generic owners, controllers, governing bodies, and supervisory bodies.
- Semantic support factors from sentence-transformer retrieval where syntax and
  lexical evidence are insufficient.
- Optional LLM/RAG factors with explicit provenance. They may propose or support
  hypotheses, but they must not bypass the typed graph schema.

Factors may be unary, binary, or higher-order. Unary factors are useful as priors, but
the end state should not be mostly independent unary scoring. The important gains
come from connected factors that let related hypotheses influence each other.

## Joint Inference Shape

Inference should run over bounded connected components.

Component construction should connect hypotheses through:

- shared evidence spans,
- sentence and paragraph windows,
- shared mentions or entity candidates,
- reference candidates that can target nearby entities,
- same-entity proposals,
- same-event proposals,
- role fillers that overlap with reference or identity candidates,
- semantic retrieval neighborhoods.

Components must be bounded so inference stays tractable:

- cap candidate fillers per role and keep `unknown`,
- cap reference targets per reference mention and keep `unknown`,
- cap same-entity and same-event neighbors by retrieval score and document locality,
- split very large documents into event-centered neighborhoods when needed,
- keep all dropped alternatives explainable as retrieval pruning, not silent truth
  decisions.

The key property is bidirectional support inside a component. For example:

- A low-confidence reference target should lower the posterior of event roles that
  depend on that target.
- A strongly supported event role should increase the posterior of a compatible
  reference target.
- A strong same-entity contradiction should lower facts that require those mentions
  to be the same person.
- A strong same-event relation should share support across duplicate event mentions
  instead of materializing duplicate-looking facts.

## Implementation Flow

The target runtime should use this flow:

1. Preprocessing, morphology, syntax, NER, references, and domain producers append
   typed hypotheses and evidence.
2. Candidate retrievers build bounded neighborhoods for roles, references,
   same-entity links, and same-event links.
3. A graph builder creates backend-neutral variables and factors for each connected
   component.
4. `InferenceBackend` runs inference per component and returns variable marginals.
5. A result mapper writes posterior assessments and inferred claims. It does not
   rewrite producer hypotheses.
6. A materializer projects high-level output facts and role alternatives from
   posterior states.
7. Output serialization converts typed IDs and enum values to JSON strings at the
   boundary only.

The materializer should eventually be mechanically simple. It should select the most
probable event and role states above configured thresholds, expose lower-probability
alternatives, and copy inference explanations. It should not contain domain truth
logic that should have been a factor.

## Desired Data Model Changes

The final model should make these distinctions explicit:

- `EntityCandidate` means identity hypothesis only.
- `ReferenceMention` means unresolved textual reference only.
- `ArgumentBindingCandidate` means possible event-role filler only.
- `ResolutionClaim` means inferred or proposed identity/reference/same-event relation.
- `Assessment` means posterior score plus traceable factor/signal provenance.
- `FactCandidateRecord` means output projection only.

Avoid these anti-patterns:

- adding `party`, `workplace`, `publicness`, `canonical_org`, `role`, or employer-like
  fields to entities,
- adding many nullable domain fields to events,
- storing graph edges as mutable fields on central objects,
- weakening typed IDs to strings for matching or sorting,
- using dictionaries as internal graph metadata,
- hiding resolution by mutating canonical names or silently merging candidates.

## Migration Plan

### Phase 1: Stabilize The Inference Core - Implemented 2026-05-22

- Keep `InferenceBackend` as the only backend facade.
- Add backend tests for disconnected components, zero/near-zero potentials, categorical
  role variables with `unknown`, and multi-variable connected components.
- Ensure factors have valid positive mass and deterministic normalization semantics.
- Remove or fix pgmpy warnings instead of treating them as harmless.

Implementation notes:

- `PgmpyInferenceBackend` now validates factor potential counts against variable
  cardinalities before compiling to pgmpy. Invalid backend specs fail with a clear
  `ValueError` instead of surfacing as an opaque pgmpy shape error.
- Non-finite, negative, and zero potentials are sanitized to a small positive minimum
  before backend execution.
- The pgmpy `StructureScore` deprecation warning is suppressed inside the backend
  adapter so V2 tests do not normalize backend-internal third-party warnings.
- `tests_v2/test_inference_facade.py` now covers disconnected unary components,
  factorless variables, zero/non-finite potentials, invalid factor shape, and one
  connected event-role component where event support changes a categorical role
  posterior.

Handoff:

- Phase 1 backend hardening is complete for the current facade.
- The next implementation slice should start at Phase 2 by introducing an explicit
  component builder outside the pgmpy backend. The backend can still split physical
  disconnected subgraphs internally, but semantic component construction should become
  V2-owned and inspectable before reference/entity/same-event variables are moved into
  the same graph.

### Phase 2: Introduce Explicit Component Building - Implemented 2026-05-22

- Add a typed component builder that groups events, bindings, references, identity
  proposals, and same-event proposals.
- Keep component-size limits explicit and tested through behavior, not exact internal
  component IDs.
- Make retrieval pruning visible in debug output where useful.

Implementation notes:

- Added `InferenceComponentId`, `InferenceComponent`, `BuiltInferenceComponents`, and
  `InferenceComponentBuilder`.
- `InferenceComponentBuilder` partitions a backend-neutral `InferenceGraphSpec` into
  connected components using variable/factor links. Factorless variables become their
  own components.
- The builder validates dangling factor references before backend execution, so
  unknown-variable bugs fail in V2 code instead of pgmpy internals.
- `ProbabilisticInferenceStage` now builds explicit components and runs the backend
  once per component, then merges marginals and diagnostics for the existing
  materializers.
- The pgmpy backend still keeps its internal physical partitioning as a defensive
  backend detail, but semantic component construction is now V2-owned and testable.
- `tests_v2/test_inference_facade.py` covers connected component grouping,
  factorless variables, dangling factor validation, and the existing stage facade.

Handoff:

- Phase 2 is complete for graph-spec connectivity. It does not yet build
  domain-semantic neighborhoods directly from document evidence.
- Phase 3 should move reference resolution further into these components. The first
  concrete step is to ensure `ReferenceTarget` variables and role variables that
  depend on reference-backed proxy entities are in the same explicit component, then
  add behavior tests where changing reference support changes the posterior of the
  event role and materialized fact.

### Phase 3: Move Reference Resolution Into The Graph

- Convert reference/coreference/proxy candidates into `ReferenceTarget` variables.
- Connect `ReferenceTarget` variables to role fillers that use those references.
- Add tests where event confidence changes when the reference target is strong or
  weak.

### Phase 4: Move Entity Resolution Into The Graph

- Convert same-person/same-organization proposals into `SameEntity` variables.
- Connect `SameEntity` variables to role fillers, distinct-role constraints, and
  contradiction evidence.
- Cover same-name/father-son/"nie mylić z" cases as graph uncertainty, not forced
  merge behavior.

### Phase 5: Move Same-Event Resolution Into The Graph

- Convert duplicate fact/event proposals into `SameEvent` variables over events.
- Let compatible roles and shared evidence support same-event links.
- Let incompatible roles or contradictory evidence oppose same-event links.
- Stop using post-materialization duplicate handling as the main resolution mechanism.

### Phase 6: Retire Transitional Scoring And Caps

- Delete old scorer-shaped code once its logic is represented by factors.
- Remove materialization-side contradiction caps after equivalent graph factors affect
  posteriors directly.
- Ensure no producer or inference stage writes materialized facts into
  `ExtractionStore` as candidates.
- Ensure no active code adapts flat fact candidates into events.

### Phase 7: Add Semantic And Optional RAG Support

- Use sentence-transformer retrieval to propose or support candidate neighbors for
  roles, references, and same-event links.
- Keep semantic evidence as typed factors with provenance.
- Add optional LLM/RAG producers or factor builders only behind explicit interfaces.
- Never let LLM/RAG output bypass typed candidates, factors, or evidence records.

### Phase 8: Calibrate And Evaluate

- Build calibration fixtures from real articles and negative controls.
- Track whether high-confidence outputs are useful, whether low-confidence
  alternatives remain inspectable, and whether false positives are visibly low.
- Evaluate by domain: governance, employment, contracts, funding, compensation,
  party/ties, proxy/family ties, and anti-corruption referrals.

## Acceptance Criteria

The inference refactor is complete only when all of these are true:

- Domain producers emit events and role bindings, not final facts.
- `FactCandidateRecord` exists only as output projection.
- Materialization does not mutate producer hypotheses or repopulate store candidates.
- `pgmpy` imports are confined to backend adapter code and backend-specific tests.
- Entity, reference, and same-event resolution are represented as variables/factors in
  the same bounded specs as connected event/role variables.
- Posterior fact confidence comes from inference marginals, not a central additive
  scorer or post-hoc materialization caps.
- Role alternatives remain visible in output with posterior scores and evidence.
- Bad party/media/owner/controller alternatives remain visible but low-confidence.
- Self-ties and same-name ambiguity are handled by graph constraints and resolution
  uncertainty.
- Tests assert behavior: semantic roles, relative posterior order, visible
  alternatives, and article-level expected facts. They do not assert generated IDs,
  signal order, factor order, or internal variable names outside backend tests.

## Validation Strategy

For implementation changes, start with focused tests for the touched graph behavior,
then broaden:

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check
uv run pytest -c pytest-v2.ini -q
uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir output
```

For article-quality changes, record expected findings before running the pipeline,
then compare expected versus actual. Passing tests alone is not enough if the change
affects extraction quality or inference semantics.
