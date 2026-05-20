# V1 shortcomings and how V2 improves the architecture

Date: 2026-05-20

## Purpose

This document explains why the repository is moving toward `pipeline_v2/`, what is hard about the current V1 architecture, and how V2 is designed to improve both extraction quality and implementation velocity.

It is not a claim that V2 already surpasses V1 in every benchmark. The point is that V2 is built to make correctness, uncertainty handling, debugging, and future extension much cheaper.

## High-level goal

V1 is optimized around producing a best-effort final answer from a largely implicit pipeline.

V2 is optimized around producing a **typed, inspectable hypothesis graph**:

- candidate entities,
- candidate facts,
- explicit evidence,
- explicit scores and signals,
- explicit identity/reference uncertainty.

In short:

- **V1 collapses early**
- **V2 preserves uncertainty and scores it later**

## What V1 gets wrong architecturally

V1 has valuable behavior and domain knowledge, but the architecture makes many improvements expensive or fragile.

### 1. Too many irreversible decisions happen too early

In V1, normalization, clustering, frame extraction, linking, and downstream fact generation tend to compress multiple possibilities into one working interpretation too soon.

That causes problems:

- ambiguous names may be silently merged,
- party context may be mistaken for an organization target,
- a noisy organization span can pollute later linking,
- debugging becomes "why did the final answer look wrong?" instead of "which hypothesis was bad?"

### 2. Provenance and uncertainty are not first-class outputs

V1 produces useful final JSON, but many internal choices are only implicit:

- which span supported a conclusion,
- which competing identity interpretation existed,
- why one reading beat another,
- how much the output depended on sentence-local vs discourse-window recovery.

This makes review and benchmark diagnosis slower.

### 3. Domain logic is too cross-coupled

A new extraction behavior in V1 often affects several layers at once:

- models,
- normalization,
- clustering,
- syntax/frame logic,
- relation extraction,
- scoring,
- output,
- tests.

That increases the cost of adding new fact families or tightening boundaries.

### 4. The architecture hides graph structure inside mutable objects

V1 effectively works over a graph of mentions, entities, references, facts, and links, but much of that structure is encoded indirectly in larger document objects and intertwined stage logic.

This encourages "god object" growth and makes targeted retrieval harder.

### 5. NLP evidence is under-explained at decision boundaries

V1 uses strong NLP components, but many extraction decisions still feel like monolithic stage behavior rather than a clean progression from:

1. evidence,
2. hypothesis,
3. score,
4. serialized output.

That makes it harder to tell whether a miss is due to:

- preprocessing,
- relevance,
- NER,
- morphology,
- syntax,
- candidate production,
- linking,
- or scoring.

### 6. Optional NLP stages are awkward to reason about

Expensive features like coreference, parsing, and semantic retrieval are useful, but in V1 they are less cleanly isolated as optional evidence producers. That makes lightweight tests and controlled ablations harder.

## What V2 is trying to achieve instead

V2 is designed around a few explicit principles.

### 1. Preserve uncertainty

V2 should overproduce plausible candidates and then score them.

That means:

- multiple entity candidates can coexist,
- ambiguous references remain references until resolved,
- fact candidates can exist before confidence is final,
- same-name collisions and family overlaps stay representable.

### 2. Make graph structure explicit

V2 separates:

- `EvidenceSpan`
- `Mention`
- `ReferenceMention`
- `EntityCandidate`
- `FactCandidate`
- `Assessment`
- `ResolutionClaim`

This is the core architectural improvement over V1.

Instead of hiding relationships inside mutable entity/document state, V2 models them as explicit records and typed edges.

### 3. Split candidate production from scoring

V2 producers create hypotheses.

V2 scorers evaluate those hypotheses with explicit positive and negative signals.

This lets the system say:

- "this looks like a governance appointment candidate,"
- "this is only weak political support,"
- "this resolution claim is plausible but contradicted by same-name context."

That separation is much cleaner than V1-style early collapse.

### 4. Keep retrieval separate from candidate identity

If a producer needs nearby people, organizations, roles, or parties, it should use retrievers and stable indexes rather than adding more ad hoc fields to entity objects.

This prevents V2 from recreating V1-style state sprawl.

### 5. Make output inspectable

V2 output is meant to show:

- which candidates were produced,
- which evidence supports them,
- which links are uncertain,
- which scorer signals raised or lowered confidence.

This is a direct improvement over V1's more final-answer-oriented shape.

## Concrete implementation differences

## V1 pipeline shape

The current V1 orchestration is still a classic staged document pipeline:

1. preprocess HTML,
2. run stages in order,
3. stop if relevance is false,
4. return one extracted result.

Architecturally, V1 remains centered on a mutable document that accumulates interpretations as stages progress.

The practical extraction flow is frame-first:

1. preprocessing
2. relevance filtering
3. segmentation
4. spaCy NER
5. Stanza coreference
6. entity clustering
7. clause parsing
8. frame extraction
9. fact extraction from frames
10. in-memory entity linking
11. scoring
12. JSON output

This works, but it means the pipeline often commits to identity and relation interpretations before uncertainty is preserved as a first-class object.

## V2 pipeline shape

The V2 runtime in `pipeline_v2/runtime.py` is intentionally smaller and more modular:

1. relevance filter
2. sentence segmentation
3. morphology
4. optional syntax
5. NER candidate stage
6. candidate producers by domain
7. optional/light coreference
8. proxy and tie producers
9. resolution scoring
10. fact scoring

The important difference is not just stage order. It is what each stage is allowed to do:

- early stages add evidence and candidates,
- later stages score,
- output preserves the intermediate graph.

## V2 store vs V1 document-centric state

The biggest practical implementation change is `pipeline_v2/store.py`.

`ExtractionStore` is append-oriented and typed. It owns:

- sentences,
- tokens,
- evidence,
- mentions,
- references,
- entity candidates,
- fact candidates,
- resolution claims,
- structural indexes.

This gives V2 a graph-like core without introducing a graph database.

That is a major improvement over V1 because:

- traversal becomes explicit,
- indexes are stable and structural,
- producers can share retrieval logic,
- debugging can inspect each layer separately.

## Typed IDs and typed records

V2 uses `NewType` IDs and explicit dataclasses/enums throughout the pipeline.

That improves on V1 in two ways:

1. it reduces accidental mixing of entity/fact/evidence/reference identifiers,
2. it forces architectural boundaries to stay visible in code.

This matters because V1-style implicit state transitions are easy to write but hard to reason about.

## Entity identity handling

V1 relies heavily on normalization, clustering, and in-process linking to arrive at a stable interpretation.

V2 is stricter:

- entity candidates are local hypotheses,
- references are separate records,
- possible merges become `ResolutionClaim`s,
- confidence lives in `Assessment`s, not on entities.

This is the correct architectural choice for ambiguous political/news extraction because many errors are fundamentally identity-resolution errors.

## Fact modeling

V1 derives final relations mainly from frames and downstream logic.

V2 introduces typed fact families as candidates, including:

- `PARTY_AFFILIATION`
- `POLITICAL_SUPPORT`
- `GOVERNANCE_APPOINTMENT`
- `GOVERNANCE_DISMISSAL`
- `PUBLIC_EMPLOYMENT`
- `FUNDING`
- `PUBLIC_CONTRACT`
- `COMPENSATION`
- `ANTI_CORRUPTION_REFERRAL`
- `ANTI_CORRUPTION_INVESTIGATION`
- `PERSONAL_OR_POLITICAL_TIE`

This improves extensibility: adding a new fact family does not require reshaping the entire architecture.

## Scoring model

V1 has scoring, but V2 makes scoring a cleaner architectural layer.

In V2:

- candidate generation and scoring are separate,
- scores come with explicit signals,
- multiple scoring families can coexist,
- the system can keep weak but useful hypotheses instead of hiding them.

That is better for both debugging and benchmark-driven iteration.

## Optional NLP boundaries

V2 keeps adapters and optional stages smaller:

- spaCy behind the NER provider,
- Morfeusz2 behind morphology records,
- Stanza parsing behind a syntax stage,
- light vs full coreference behind explicit runtime configuration,
- embeddings as an optional evidence layer.

This is an architectural improvement because tests and development slices can run with only the components they actually need.

## Why this matters for day-to-day engineering

The V2 architecture is not only about cleaner theory. It directly improves implementation work.

### Faster debugging

When behavior is wrong, V2 makes it easier to ask:

- was the article relevant?
- were the right mentions created?
- did the right entity candidate exist?
- did the producer emit the fact candidate?
- did scoring suppress it?

In V1, those boundaries are blurrier.

### Safer iteration

Because V2 keeps uncertainty explicit, tightening one boundary is less likely to destroy unrelated behavior.

For example:

- party context can remain weak support instead of being forced into direct affiliation,
- surname-only references can stay unresolved until scoring,
- descriptive organization phrases can become inferred candidates instead of disappearing.

### Better tests

V2 supports behavior-oriented tests much more naturally:

- realistic Polish snippets,
- article-derived integration fixtures,
- assertions on emitted facts, evidence, and signals,
- fewer tests tied to internal object shape.

That is a major quality-of-life improvement over implementation-detail-heavy testing.

## Current V2 implementation status

V2 is no longer just a scaffold. It already has:

- separate runtime and CLI,
- HTML preprocessing,
- segmentation,
- Morfeusz morphology,
- spaCy NER adapter,
- typed append-only store,
- typed IDs and enums,
- optional syntax,
- optional embeddings,
- optional/light coreference,
- candidate producers for major current domains,
- explicit fact and resolution scoring,
- JSON output exposing candidates and claims.

Recent work also hardened:

- article-level regression coverage,
- relevance boundaries,
- party/tie malformed output,
- governance completeness guards.

So the architectural direction is already visible in running code, not only in plans.

## What V2 still does not solve yet

V2 is better structured, but it is still incomplete.

Current limits:

- some strong positives still overproduce weak collective political context,
- some governance outputs are still role-only rather than fully grounded,
- V1 still has more mature behavior in some article families,
- full benchmark migration is still in progress,
- retrieval/RAG/persistent analysis layers are still mostly future work.

So V2 should be understood as a better architecture with growing behavior coverage, not as a fully finished replacement today.

## Bottom line

The core problem with V1 is not that it lacks useful extraction logic. It is that the architecture makes ambiguity, provenance, and extension too expensive to manage.

V2 improves this by making the pipeline explicitly about:

- evidence,
- candidates,
- retrieval,
- scored claims,
- inspectable output.

That is the right long-term architecture for this repository because the domain is inherently ambiguous:

- names collide,
- affiliations are indirect,
- public-money arguments are often descriptive,
- articles mix strong facts with commentary and narrative context.

V1 can still be stronger in some mature paths.

But V2 is a better system to build on.
