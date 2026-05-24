# Repository Instructions

This repository is the V2 implementation of a Polish public-interest extraction
pipeline. The active code is `pipeline_v2/` and the active tests are `tests_v2/`.

The legacy `pipeline/` and `tests/` trees are reference material only. Do not modify
V1, do not run V1 tests as part of normal validation, and do not preserve backwards
compatibility with V1 APIs.

## Operating Rules

- Use `uv` from the repository root.
- If a task starts needing environment or sandbox workarounds, stop and notify the
  user instead of adding a workaround.
- `uv sync` does not install the spaCy/Stanza model assets required by this repo. In
  any fresh or rebuilt `.venv`, run `uv run python scripts/setup_models.py` before
  running model-dependent tests or the pipeline.
- When lint or formatting tools support autofix, run the autofix path first and do
  manual cleanup only for remaining issues.
- Do not add compatibility shims. We are not preserving old internal APIs. If tests
  depend on obsolete structure, refactor the tests.
- Do not use JSON-like dictionaries as internal graph data. JSON belongs at the final
  output boundary only.
- Do not add source-code scan tests that assert implementation strings, constructors,
  or imports.

Recommended validation commands:

```bash
uv run python scripts/setup_models.py
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check
uv run pytest -c pytest-v2.ini -q
uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir output
uv run extractor-v2 --html-path inputs/article.html --stdout
uv run extractor-v2 --url https://example.com/article --stdout
```

## CLI Output Modes

`extractor-v2` has two output modes:

**Slim (default)** — human-readable summary written to `<output-dir>/<doc-id>.json` or
stdout with `--stdout`. Contains only:
- `title`, `url`, `relevant`, `relevance_score`
- `facts`: list of materialized facts with resolved entity names and `confidence`

**Debug (`--debug`)** — full graph JSON with sentences, tokens, morphology, evidence
spans, inference marginals, resolution claims, proposals, and all internal IDs. Use
this when debugging extraction or inference behaviour. The debug format is what the
test suite and benchmark scripts read when they need internal graph state.

Both modes are available for all input sources (`--html-path`, `--url`, `--input-dir`).
`--stdout` and `--output-dir` can be combined with either mode.

For small changes, run the narrowest relevant subset first, then broaden if behavior
or shared contracts changed.

## Project Goal

The project extracts inspectable evidence about public-money and patronage cases from
Polish news articles: governance appointments, public employment, public contracts,
funding, compensation, political ties, family/proxy ties, and anti-corruption
referrals.

The goal is not to produce one prematurely cleaned final answer. The goal is to
overproduce plausible typed hypotheses, preserve alternatives, and attach posterior
confidence to candidates, role bindings, entity/reference resolution, and materialized
facts.

False positives are acceptable when they remain visible as low-confidence hypotheses.
Silent early collapse is not acceptable.

## Active Architecture

V2 is an event-first, typed hypothesis graph with probabilistic inference.

The active runtime is built in `pipeline_v2/runtime.py`. Stage order is explicit
there and should remain explicit. A normal run is:

1. HTML preprocessing.
2. Relevance filtering.
3. Sentence/token segmentation.
4. Morfeusz2 morphology.
5. Dependency parsing.
6. Named entity candidate production.
7. Domain event/binding candidate production.
8. Reference, coreference, proxy, and tie candidate production.
9. Optional semantic enrichment.
10. Probabilistic inference and materialized output projection.

Producers emit hypotheses. Inference scores hypotheses. Materialization projects
selected posterior states into output records.

## Core Graph Records

Keep these concepts separate:

- `EvidenceSpan`: exact text grounding and source location.
- `Mention`: observed named/entity-like span.
- `ReferenceMention`: pronoun, surname-only mention, descriptor, omitted subject, or
  proxy phrase.
- `EntityCandidate`: identity hypothesis only.
- `EventCandidate`: relation/event trigger hypothesis.
- `ArgumentBindingCandidate`: possible filler for a typed event role.
- `InferenceVariable`: backend-neutral variable, such as event activity, role filler,
  reference target, same-entity, or same-event.
- `InferenceFactor`: backend-neutral evidence, compatibility, or constraint factor.
- `Assessment`: posterior score and traceable supporting/opposing signals.
- `ResolutionClaim`: explicit identity, reference, or same-event claim.
- `FactCandidateRecord`: materialized output projection only.

Do not grow god objects. In particular:

- Do not add `party`, `role`, `employer`, `is_public`, `canonical_org`, or similar
  domain state to `EntityCandidate`.
- Do not add many nullable domain fields to `EventCandidate`, `ArticleDocument`, or
  `ExtractionStore`.
- Do not hide graph edges as mutable fields when a typed record or typed relation is
  the real model.
- Do not put confidence scores directly on candidates. Scores belong in assessments
  or inference marginals.

## Event And Role Model

Argument order matters, but it must be represented semantically through `EventRole`,
not tuple position.

For example, all of these should map to the same semantic roles where supported by
evidence:

```text
X zatrudnił Y w Z
Y został zatrudniony przez X w Z
zatrudniono Y w Z
```

Expected graph shape:

```text
EventCandidate(kind=PUBLIC_EMPLOYMENT, trigger=...)
ArgumentBindingCandidate(role=HIRING_AUTHORITY, filler=X)
ArgumentBindingCandidate(role=EMPLOYEE, filler=Y)
ArgumentBindingCandidate(role=WORKPLACE, filler=Z)
```

If several people or organizations are plausible, emit competing
`ArgumentBindingCandidate` records. Do not select "best" inside the producer.

`FactCandidateRecord` must not be the producer API or inference input. It is a final
projection for output, reports, and external consumers.

## Inference Rules

`pgmpy` is infrastructure. It must stay behind `pipeline_v2.inference.backend.InferenceBackend`.
No producer, domain stage, store, output module, or normal domain test should depend
on pgmpy APIs directly.

Inference should be represented with V2-owned typed records:

- event-active variables,
- categorical role-filler variables,
- reference-target variables,
- same-entity variables,
- same-event variables,
- typed evidence/compatibility/constraint factors.

Scoring should not regress to a god scorer with a central table of signal constants.
When a new scoring concern appears, prefer a composable factor family or domain-local
factor builder over adding another case to one central scoring function.

Posterior scores should come from inference. Do not compute a posterior and then
floor it back to an old producer prior in materialization.

Materialization is a projection step:

- It may write `document.materialized_fact_records`.
- It may write `document.fact_assessments`.
- It may add inferred resolution/reference/same-event claims when those claims are
  outputs of inference.
- It must not clear/repopulate producer hypotheses as a scoring side effect.
- It must not store materialized facts back into `ExtractionStore` as if they were
  producer candidates.

## Type Discipline

Preserve typed IDs end to end.

- Use existing `NewType` aliases such as `EntityCandidateId`, `EventCandidateId`,
  `ArgumentBindingCandidateId`, `FactCandidateId`, `MentionId`, `SentenceId`,
  `EvidenceId`, `InferenceVariableId`, and `ResolutionClaimId`.
- Do not weaken IDs to `str` for dict keys, sets, sorting, or pair tracking. Add a
  typed helper instead.
- Do not compare typed IDs through `str(...)` except at serialization boundaries.
- Avoid `dict[str, Any]`, broad unions, and unstructured metadata. Use dataclasses,
  typed aliases, `TypedDict`, or explicit domain records.
- Avoid `isinstance` for expected domain branching when structural pattern matching
  or typed variants are available.
- Do not use `try`/`except` for expected control flow, such as enum parsing. Use
  explicit checks or safe constructors.

Signals are strongly typed dataclasses. Signal names should normally be derived from
class names, for example `PartyOrganizationSignal` becomes `party_organization`.
Only override names when the output name is genuinely domain-specific.

## NLP-First Extraction

Prefer NLP-backed evidence over ad hoc string patches.

Use:

- Morfeusz2 lemmas and morphology for Polish inflection.
- Dependency relations and syntax paths for argument binding.
- spaCy/Stanza NER as evidence producers, not as final truth.
- Coreference/reference candidates for pronouns, omitted subjects, descriptors, and
  proxy phrases.
- Sentence-transformer embeddings and vector retrieval for semantic support where
  lexical/syntax evidence is insufficient.

Do not manually strip suffixes, hardcode article-specific names, or add one-off word
lists to fix a single report. Small lexical sets are acceptable only when they define
a stable domain boundary and are backed by tests.

NLP components must be wrapped behind V2-owned abstractions. Keep library-specific
details out of domain producers as much as practical so Stanza, spaCy, Morfeusz2, or
future providers can be swapped with limited churn.

## Domain Heuristics

Governance:

- Governance should come from clause-local syntax and typed role bindings.
- Appointee, organization, role, appointing authority, owner, controller, and board
  context are distinct roles or signals.
- Parties, owners, ministries, funds, boards, and supervisory bodies should not become
  appointment targets just because they are nearby.

Public employment:

- Employee, workplace, hiring authority, and public-office context are separate roles
  or factors.
- Do not materialize inferred organizations by mutating canonical strings. Represent
  "samorząd", office descriptors, and locations as evidence/context/claims.

Public money:

- `FUNDING`, `PUBLIC_CONTRACT`, and `COMPENSATION` are distinct fact kinds.
- Compensation is salary/remuneration, not grants.
- Public contracts should not be downgraded to generic funding.
- Controller/supervisor organizations should compete with direct payer/employer
  alternatives, not be removed by lexical post-filters.

Party and ties:

- Political parties are valid party-affiliation objects, but should not leak into
  generic organization/workplace/funder roles unless the event schema explicitly
  allows that.
- Kinship and proxy-person extraction must stay conservative. A foundation founded
  by a person is not a family tie.
- Same-name, same-surname, father/son, and "nie mylić z" cases must be represented as
  resolution uncertainty, not forced merges.

## Tests

Tests should assert behavior, not implementation details.

Good assertions:

- A sentence produces an event of the expected kind.
- Semantic roles are correct regardless of surface word order.
- Competing role fillers remain visible.
- A correct filler has a higher posterior than a weak/context filler.
- A party context is demoted for workplace/organization roles.
- A reference target is propagated into materialized facts when resolution is strong.
- Same-name contradiction lowers same-entity probability.
- A benchmark article produces or does not produce the expected high-level facts.

Bad assertions:

- Exact generated entity IDs such as `entity-3`.
- Exact generated fact IDs such as `fact-1`, unless the ID is hand-authored input to
  the specific unit under test.
- Exact argument tuple order when semantic role lookup is what matters.
- Exact signal order.
- Exact factor order or internal variable names, except in focused backend/facade
  tests.
- Source-code string scans.

Use static providers for fast unit tests:

- Static preprocessed `ArticleDocument` where preprocessing is not under test.
- Static NER spans via test providers where model behavior is not under test.
- Morfeusz2 morphology for realistic Polish lemmas.
- Fake `InferenceBackend` for facade tests.

Backend tests may import backend implementations directly. Domain tests should not.

## Reports And Benchmarks

The `reports/` and `reports/v2/` directories are part of the development context.
Before significant extraction, inference, or architecture changes, read the relevant
current report, especially:

- `reports/expected_article_findings.md`
- `reports/v2/probabilistic_inference_plan_2026-05-21.md`
- `reports/v2/probabilistic_inference_review_notes_2026-05-21.md`
- `reports/v2/v1_to_v2_architecture_2026-05-20.md`

For article-specific work, follow this workflow:

1. Read the article or fixture.
2. Write down expected findings before running the pipeline.
3. Run the smallest useful V2 pipeline/fixture check.
4. Compare expected vs actual.
5. Decide whether the gap belongs to preprocessing, relevance, NER, morphology,
   syntax, candidate production, retrieval, inference, materialization, or tests.

Do not treat `pytest` success as sufficient for extraction-quality changes. If
behavior changes materially, run benchmark inputs and add a dated note in `reports/`
or `reports/v2/` describing what improved, what regressed, what was checked, and
what remains.

## Output Boundary

Output serialization should expose enough graph state to debug extraction:

- event candidates,
- argument bindings,
- evidence,
- entities,
- references,
- inference marginals,
- resolution claims,
- materialized facts,
- fact assessments.

Serialization may convert typed IDs and enum values to strings. Internal pipeline
code should not.

## Review Checklist

When reviewing or changing code, check for these regressions:

- V1 code or V1 tests were modified.
- Producers emit final facts instead of events and role bindings.
- A producer silently chooses one best entity/organization/person when alternatives
  should remain visible.
- A new optional field was added to a central object instead of a typed candidate,
  role, signal, factor, or claim.
- IDs were weakened to strings.
- JSON/dicts were used as internal graph payloads.
- pgmpy or another backend leaked outside the inference backend adapter.
- Scoring logic grew as a central additive table.
- Materialization mutated producer hypotheses.
- Tests assert generated IDs, ordering, or implementation internals instead of
  behavior.
