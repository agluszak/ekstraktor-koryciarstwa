# V2 Probabilistic Inference Plan

Date: 2026-05-21

## Goal

V2 scoring should become probabilistic inference over a typed hypothesis graph, not a
central scorer that sums signal constants. Producers should overproduce hypotheses.
Inference should estimate posterior confidence for events, role bindings, entity
attributes, references, identity links, and duplicate/same-event claims.

`pgmpy` is the first inference backend, but it must remain behind a V2-owned facade.
No producer, store, materializer, output module, or domain test should depend on
pgmpy APIs directly.

## Desired End State

The final internal graph should be event-first:

- `EntityCandidate`: identity hypothesis grounded in observed mentions. It should not
  grow domain-state fields such as party, role, publicness, employer, etc.
- `ReferenceMention`: unresolved pronoun, surname-only mention, descriptor, omitted
  subject, or proxy phrase.
- `EventCandidate`: a typed event/relation hypothesis such as public employment,
  governance appointment, funding, compensation, tie, party affiliation, or referral.
- `ArgumentBindingCandidate`: a typed possible filler for an event role.
- `InferenceVariable`: backend-neutral variable over event activity, role fillers,
  entity attributes, reference targets, identity links, or same-event claims.
- `InferenceFactor`: backend-neutral evidence/constraint/compatibility factor.
- `Assessment`: posterior score for an inferred target/state, with traceable factor or
  signal provenance.

Flat `FactCandidateRecord` should become a materialized output projection only. It
should not be the primary candidate shape and should not be what domain producers
emit. The final pipeline should not contain an adapter from flat fact candidates to
events.

## Event And Role Model

Each domain producer emits an event trigger plus candidate role bindings. Direction
and argument order belong in roles, not in tuple ordering.

Example:

```text
X zatrudnił Y w Z
```

should produce:

```text
EventCandidate(kind=PUBLIC_EMPLOYMENT, trigger="zatrudnił")
ArgumentBindingCandidate(role=HIRING_AUTHORITY, filler=X)
ArgumentBindingCandidate(role=EMPLOYEE, filler=Y)
ArgumentBindingCandidate(role=WORKPLACE, filler=Z)
```

Passive and impersonal variants should bind the same semantic roles:

```text
Y został zatrudniony przez X w Z
zatrudniono Y w Z
```

The inference graph should use categorical role variables:

```text
RoleFiller(event, EMPLOYEE) -> {person_a, proxy_b, unknown}
RoleFiller(event, WORKPLACE) -> {org_a, org_b, unknown}
```

This is important. Competing organizations or competing people should be alternatives
inside one role variable, not multiple independent facts that are demoted later.

## Backend Facade

The public V2 inference API should stay in `pipeline_v2/inference/` and expose only
typed internal records:

```python
class InferenceBackend(Protocol):
    def run(self, spec: InferenceGraphSpec) -> InferenceResult: ...
```

`InferenceGraphSpec` owns typed variables and factors. Backend adapters compile that
spec into implementation-specific objects. The pgmpy backend may import:

- `pgmpy.models.FactorGraph`
- `pgmpy.factors.discrete.DiscreteFactor`
- `pgmpy.inference.BeliefPropagation`

No other V2 module should import pgmpy.

The backend is responsible for implementation constraints such as connected-component
partitioning and cardinality limits. Domain code should not know about pgmpy junction
trees, clique construction, or factor table layout.

## Factor Families

Start with these variable families:

- `EventActive(event_id) -> {false, true}`
- `RoleFiller(event_id, role) -> {candidate fillers..., unknown}`
- `EntityAttribute(entity_id, attribute) -> {false, true}`
- `SameEntity(entity_a, entity_b) -> {false, true}`
- `ReferenceTarget(reference_id) -> {candidate entities..., unknown}`
- `SameEvent(event_a, event_b) -> {false, true}`

Start with these factor families:

- Evidence priors from trigger lemmas, dependency arcs, morphology, amount spans, and
  explicit lexical/domain evidence.
- Directional syntax factors for active/passive/object/oblique/prepositional role
  assignment.
- Role-schema compatibility factors, such as employee should be person/proxy-person
  and workplace should be public organization.
- Competition factors for mutually exclusive alternatives in the same role.
- Contradiction factors for same-name contrast, "nie mylić z", negation, quoted
  allegations, controller-versus-direct-employer contexts, and pseudonymous sources.
- Support factors from reference/coreference, entity resolution, semantic similarity,
  and optional LLM/RAG evidence.

Scores exposed downstream are posterior probabilities from inference, not additive
constants.

## Current Transitional State

The current migration slice added:

- typed event/binding records,
- typed inference IDs,
- `InferenceBackend`,
- a pgmpy backend hidden behind that facade,
- a `ProbabilisticInferenceStage`,
- initial graph spec and materialization records,
- `pgmpy` as a project dependency.

There is also a temporary adapter that materializes events from existing flat fact
candidates. This is acceptable only as a migration bridge. It is not part of the
desired architecture and must be removed once domain producers emit events directly.

There is still a known implementation issue in the pgmpy backend/component execution
path from the initial migration pass. The next agent should rerun the targeted tests
and finish backend component partitioning before expanding producer migration.

## Migration Plan

1. Stabilize the backend facade.
   Ensure pgmpy execution works on disconnected unary-factor graphs by running each
   connected component independently inside the backend adapter. Keep this behavior
   hidden from domain code.

2. Make inference output inspectable.
   Add output sections for event candidates, argument bindings, inferred variable
   marginals, and materialized facts. Keep JSON serialization at the boundary only.

3. Migrate public employment producer first.
   It is the clearest role-ordering case. It should emit `EventCandidate` and
   `ArgumentBindingCandidate` directly for active, passive, impersonal, and proxy
   hiring cases. Remove its dependence on flat fact construction once tests pass.

4. Add real role competition.
   For public employment, compile all plausible employee/workplace/hiring-authority
   fillers into categorical `RoleFiller` variables. Do not emit one fact per
   Cartesian product.

5. Migrate governance producer.
   Governance needs appointee, organization, role, appointing authority, and
   controller/body context separated. Appointer/controller context should be modeled
   as competing/negative factors, not as selected final arguments.

6. Migrate public money producer.
   Funding, contract, and compensation should use event roles for payer, recipient,
   contractor, counterparty, amount, and controller context. Ministry/controller
   alternatives should compete with direct employer/funder alternatives.

7. Migrate identity/reference/fact resolution into inference.
   Existing resolution claims should become variables/factors first, then direct
   inference outputs. Identity and reference scores should influence fact/event
   confidence and vice versa where connected.

8. Remove transitional compatibility code.
   Delete the flat-fact-to-event adapter, remove `FactRecordScorer`, stop producing
   domain facts directly, and make `FactCandidateRecord` a pure materialized output
   view.

## Test Strategy

Tests should assert behavior, not implementation details:

- Active hiring: `X zatrudnił Y w Z` scores `Y` as employee, not `X`.
- Passive hiring: `Y został zatrudniony przez X w Z` scores the same semantic roles.
- Impersonal hiring: `zatrudniono Y w Z` supports employee and workplace even without
  explicit hiring authority.
- Same-name contrast lowers `SameEntity`.
- Competing organizations produce ordered probabilities, not hidden best-selection.
- Controller/ministry contexts score lower than direct employer/funder contexts.
- Role alternatives remain visible in output, including low-confidence alternatives.

Do not assert exact internal IDs, exact factor order, source-code strings, or signal
ordering.

## Validation Commands

Use V2-only validation:

```bash
uv sync
uv run python scripts/setup_models.py
uv run ruff check <touched files> --fix
uv run ruff format <touched files>
uv run ruff check <touched files>
uv run ty check
uv run pytest tests_v2/
uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir output
```

Global `ruff check .` may currently report unrelated pre-existing lint in scratch
report scripts. Do not mix that cleanup into the inference refactor unless explicitly
asked.

