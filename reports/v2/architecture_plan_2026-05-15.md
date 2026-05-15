# V2 Extraction Pipeline Design Plan

Date: 2026-05-15

This document captures the current V2 direction for the extraction pipeline. It is intentionally high level, but concrete enough to guide implementation slices and tests. V1 remains present for comparison, but new development should happen in `pipeline_v2/` and `tests_v2/`.

## Goals

V2 should be a candidate-producing, uncertainty-preserving extraction system rather than a pipeline that tries to collapse everything into one final answer too early.

Primary goals:

- Overproduce entity candidates, references, relation candidates, and fact candidates, then attach explicit scores and evidence.
- Preserve uncertainty in the output. Possible entity merges, pronoun/coreference links, and ambiguous references should be emitted as scored claims instead of being hidden inside transparent normalization or clustering.
- Make it easy to add new entity types, reference types, fact types, and scoring rules without modifying many unrelated modules.
- Keep NLP backends behind small adapter boundaries so spaCy, Stanza, Morfeusz2, sentence-transformers, and optional LLM/RAG producers can be changed or disabled with minimal domain-code churn.
- Prefer morphology, dependency parsing, NER, coreference, and semantic retrieval over article-specific regex patches or suffix stripping.
- Keep tests behavior-oriented. Tests should assert observable extraction behavior, evidence, scores, and output contracts, not internal implementation details.
- Keep V1 and V2 physically separate while V2 is immature. V1 tests should not be part of the V2 development loop unless we explicitly run cross-version comparison.

## What V2 Must Improve Over V1

V1 has accumulated useful behavior, but its architecture makes quality work too expensive.

Main V1 shortcomings to fix:

- Extensibility is poor. A new fact type or extraction fix often requires coordinated changes across models, frame code, normalization, scoring, output code, and tests.
- Identity handling is too eager. Normalization and clustering can silently collapse mentions, which hides uncertainty and makes later scoring/debugging harder.
- Tests often freeze implementation details. This creates churn when internals improve even if behavior remains correct.
- Lexical knowledge is scattered. Stable domain vocabulary, YAML config, ad hoc word lists, and one-off literals live in too many places.
- NLP tools are underused. We have spaCy, Stanza, sentence-transformers, and now Morfeusz2 available, but many decisions still rely on brittle string matching.
- Morphological handling is leaky. Inflection, surname forms, and role forms should be solved through analyzers and mention evidence, not manual suffix manipulation.
- The pipeline performs too many round-trip conversions. Several structures exist mostly because partial refactorings left stale mirrors of the same concept.
- Scoring is artificial. A single `0.0-1.0` number is still the right external shape, but it should be derived from explicit signals and evidence rather than opaque constants.
- Candidate retrieval is not first-class. V1 often pairs candidates broadly, then tries to repair mistakes downstream.
- Coreference is not cleanly optional. Expensive NLP stages should be optional producers/scorers that add evidence when enabled, not mandatory infrastructure for every test.
- Output hides too much provenance. Consumers need to see candidate facts, supporting evidence, scores, and alternative identity/reference hypotheses.
- Benchmark diagnostics are too final-output-oriented. We need to inspect whether preprocessing, relevance, NER, syntax, candidate production, scoring, or output serialization failed.

## Current V2 State

The current V2 skeleton already exists in `pipeline_v2/` with separate tests in `tests_v2/`.

Implemented foundations:

- A physically separate V2 package and pytest configuration.
- HTML preprocessing using `trafilatura` with a paragraph fallback.
- Paragraph and sentence segmentation with source spans.
- Typed IDs and typed domain enums for entities, facts, mentions, references, resolution relations, grounding kinds, and signal polarity.
- Morfeusz2-backed morphology stage with token lemmas and morphological analyses.
- spaCy NER adapter that creates mention-backed entity candidates.
- Optional sentence-transformer embedding support and an evidence vector index.
- Optional Stanza dependency parsing adapter and syntax stage.
- A typed append-only extraction store with indexes for sentences, tokens, evidence, mentions, references, candidates, facts, and resolution proposals.
- Candidate-owned conversion from fact candidates to fact records.
- Initial producers for NER entities, family proxies, party-affiliation candidates, and reference-resolution proposals.
- Initial scorers for entity resolution, party affiliation, and reference resolution.
- JSON output for entities, facts, evidence, resolution claims, and reference-resolution claims.
- A V2 CLI and runtime builder.

Recent validation before this report:

- `uv run ruff check pipeline_v2 tests_v2`
- `uv run ty check pipeline_v2 tests_v2`
- `uv run pytest -c pytest-v2.ini -q`

## Architecture Principles

### Pipeline Shape

V2 should keep a staged pipeline, but the stages should exchange typed records through a document-level store instead of passing partially normalized final objects around.

The intended phase order is:

1. Preprocess raw HTML and metadata into an `ArticleDocument`.
2. Segment text into paragraphs and sentences with stable spans.
3. Produce low-level NLP annotations: morphology, NER, dependency parses, embeddings, and optional coreference.
4. Produce mentions, references, entity candidates, and evidence records.
5. Retrieve plausible nearby or semantically related candidates for each producer.
6. Produce fact candidates and resolution proposals.
7. Score candidates and proposals from explicit signals.
8. Serialize candidates, scores, evidence, and uncertainty into the V2 output schema.

The important design rule is that producers add candidates and evidence; scorers assess candidates and attach scores/signals. Producers should not silently canonicalize away ambiguity.

### Store And Graph Model

V2 should not begin by adopting a full graph database. A graph database may be useful later for persistence, querying, or RAG, but the first implementation needs type safety and debuggable extraction behavior more than a general graph engine.

The near-term design is:

- Keep a typed append-only `ExtractionStore` as the source of truth inside one document run.
- Represent vertices as typed records: evidence spans, mentions, references, entity candidates, fact candidates, fact records, resolution proposals, and scored claims.
- Represent edges as typed records with explicit endpoints and relation enums: entity-resolution proposals, reference-resolution proposals, fact arguments, mention evidence, candidate evidence, and semantic-neighbor links.
- Maintain indexes as implementation details of the store and retrievers, not as domain state.
- Add graph-like traversal through typed query methods and retrievers rather than exposing a generic mutable graph API to producers.

This avoids hand-rolling a broad graph library while still giving us graph semantics where they matter. If we later need persistent graph queries, the typed records can be projected into NetworkX, SQLite tables, DuckDB, LanceDB/Qdrant, or a graph database without changing producer APIs.

### Entity Candidates And Identity

Entity candidates should be cheap and numerous. Creating another candidate is acceptable if it preserves uncertainty.

Identity policy:

- A candidate is a local hypothesis, not a canonical person or organization.
- Reuse is allowed only when the evidence is strong enough and local: exact mention reuse, same full-name mention, or an explicit resolver decision.
- Inflected forms should be linked through morphology-backed evidence and scored resolution proposals, not through manual string suffix logic.
- Ambiguous partial references such as surnames, pronouns, role descriptions, or paraphrases should create `ReferenceMention` records and scored reference-resolution proposals.
- Same-name collisions must remain representable. Two people with the same name, father/son cases, and explicit "not to be confused with" text should produce separate candidates plus low or negative resolution signals.

Candidate retrieval should be a service, not a hardcoded key:

- Name and lemma retrieval finds candidates sharing full-name lemmas, surname lemmas, or organization acronyms.
- Window retrieval finds candidates in the same sentence, adjacent sentences, paragraph, or bounded discourse window.
- Dependency retrieval finds candidates connected by apposition, subject/object, prepositional, possessive, or copular structures.
- Semantic retrieval uses embeddings to retrieve evidence spans or candidates near paraphrases like "ten lokalny polityk".
- Coreference retrieval uses optional coref links as another signal, not as a final merge.

Different entity types can have different retrieval strategies, but producers should depend on a common retriever interface rather than bespoke global indexes.

### Producer And Scorer Split

The producer/scorer split is still useful even though scorers need access to much of the same context as producers.

Producer responsibilities:

- Notice plausible evidence.
- Create typed candidates and proposals.
- Attach initial evidence spans and structured arguments.
- Avoid irreversible decisions.

Scorer responsibilities:

- Evaluate a candidate or proposal using available context.
- Attach a `0.0-1.0` score plus explicit positive and negative signals.
- Keep scoring logic comparable across producers.
- Allow multiple scoring implementations: deterministic rules, dependency-based scorers, semantic scorers, LLM scorers, or RAG-backed scorers.

The key difference is not context access; it is mutability and responsibility. Producers expand the hypothesis space. Scorers rank and explain that space. A scorer may read the same NLP annotations as a producer, but it should not be the component that invents a new party-affiliation or public-contract candidate.

### Fact Candidates

Fact candidates should be typed by fact family and should own their conversion to output records.

Current and planned fact families:

- `PARTY_MEMBERSHIP`: a person or organization is directly affiliated with a party.
- `POLITICAL_SUPPORT`: weaker political support, recommendation, candidacy, endorsement, or party-context evidence.
- `APPOINTMENT`: person appointed to a public or public-controlled role.
- `DISMISSAL`: person removed from a public or public-controlled role.
- `PUBLIC_EMPLOYMENT`: public-sector job or contract-like staffing fact that is not board governance.
- `FUNDING`: public grant, subsidy, or transfer.
- `PUBLIC_CONTRACT`: procurement or contract award, distinct from grants.
- `COMPENSATION`: salary, remuneration, severance, bonus, or other public-money personal compensation.
- `PERSONAL_OR_POLITICAL_TIE`: family, acquaintance, patronage, or other relevant tie.
- `ANTI_CORRUPTION_REFERRAL`: referral to CBA, prosecutor, audit body, or other oversight authority.

Adding a new fact type should require:

- A typed candidate record.
- A producer or LLM/RAG producer that emits it.
- One or more scorers.
- Output serialization for the shared fact-record shape.
- Behavior-level tests with realistic article snippets.

It should not require broad edits to unrelated candidate types.

### NLP Backend Boundary

V2 should expose our own domain-neutral NLP structures:

- `Sentence`
- `Token`
- `MorphToken`
- `MorphAnalysis`
- `Mention`
- `ReferenceMention`
- `NamedEntitySpan`
- `ParsedDependencySentence`
- `EvidenceSpan`

spaCy, Stanza, Morfeusz2, sentence-transformers, and LLM outputs should be adapters that populate these structures. Domain code should not depend on spaCy tokens, Stanza protobuf objects, or Morfeusz raw tuple shapes.

This will not make the system fully backend-agnostic, but it reduces switching cost and localizes backend-specific behavior.

### Optional LLM And RAG Producers

LLM/RAG should be optional, schema-constrained, and candidate-producing.

Appropriate uses:

- Propose difficult relation candidates from discourse-level context.
- Add weak evidence for paraphrases that deterministic producers miss.
- Score or explain ambiguous cases where deterministic signals conflict.

Boundaries:

- LLMs should not generate final entity IDs, offsets, timings, or canonical merges.
- LLM output should be parsed into the same typed candidate/proposal records as deterministic producers.
- LLM and RAG scorers should attach signals and confidence; they should not overwrite deterministic evidence.

### Output Schema Direction

The V2 output schema should expose:

- Document metadata and preprocessing diagnostics.
- Relevance decision with signals.
- Evidence spans with offsets, paragraph/sentence IDs, and optional embeddings metadata.
- Entity candidates with mentions, aliases, type, score, and evidence.
- Reference mentions and scored reference-resolution claims.
- Entity-resolution proposals and scored claims.
- Fact candidates/facts with typed arguments, evidence IDs, scores, and scorer signals.
- Optional debug diagnostics grouped by stage.

The schema can break V1 compatibility. The priority is preserving uncertainty and making extraction failures inspectable.

## Implementation Roadmap

### P0: Stabilize The Foundation

Before porting more domain behavior, harden the current V2 base:

- Tighten output serialization types so JSON conversion remains explicit and typed.
- Wire runtime coreference modes into actual provider selection.
- Add stage diagnostics for skipped optional NLP stages.
- Ensure every typed ID stays typed through local variables, helper signatures, sets, indexes, and JSON boundary conversion.
- Keep V2 test commands separate from V1 and documented in `pytest-v2.ini`.
- Remove or rewrite any tests that assert internal data structures instead of behavior.

Acceptance criteria:

- `uv run ruff check pipeline_v2 tests_v2`
- `uv run ty check pipeline_v2 tests_v2`
- `uv run pytest -c pytest-v2.ini`
- No compatibility shims for V1.

### P1: Port Core Domain Producers

Port V1 behavior as candidate producers, not as final normalizers.

Producer slices:

- Party and political context producer: direct party membership, candidacy, endorsement, campaign committee, and party-near apposition.
- Role and public-office producer: public roles, offices, boards, committees, municipal companies, state-controlled entities, and governing bodies.
- Governance producer: appointment and dismissal candidates from dependency frames and bounded discourse.
- Public-employment producer: hiring, job assignment, consultancy, mandate, and non-board public-sector staffing.
- Public-money producer: funding, public contract, procurement, subsidy, grant, and compensation candidates.
- Kinship and personal-tie producer: named and unnamed family/proxy persons, acquaintance, patronage, and "person connected to" patterns.
- Anti-corruption producer: CBA, prosecutor, audit, NIK, UOKiK, council-control, and formal referral facts.

Acceptance criteria:

- Each producer has behavior tests using realistic Polish snippets.
- Producers overproduce plausible candidates instead of silently dropping ambiguous ones.
- Producers attach evidence and typed arguments.
- Producers do not score themselves except for minimal source confidence if needed.

### P2: Build Scoring Layers

Scoring should become signal-based and explainable.

Scorer families:

- Entity-resolution scorer: exact full-name evidence, lemma match, dependency apposition, coreference, semantic proximity, contradiction, same-name disambiguation.
- Reference-resolution scorer: pronoun/coref links, role paraphrases, local discourse windows, grammatical agreement, semantic similarity.
- Party-affiliation scorer: direct syntactic relation, apposition, party context, indirect support, stale/historical modifiers.
- Governance scorer: action lemma, subject/object relation, target type, public-control evidence, appointment/dismissal polarity, negation.
- Public-money scorer: money amount, transfer/action lemma, payer/payee roles, public-source evidence, contract vs grant distinction.
- Tie scorer: kinship detail, named vs unnamed proxy, relation direction, negative contexts such as "not wife" or unrelated lexical collisions.

Acceptance criteria:

- Scores remain `0.0-1.0`.
- Every score has inspectable positive and negative signals.
- Scorers can be tested with candidates built from article snippets, not by checking private helper choices.

### P3: Migrate Benchmarks Into V2 Behavior Tests

The benchmark should become a mix of small behavioral fixtures and full-article integration checks.

Minimum V2 fixture groups:

- Split-sentence appointment where the appointee, role, and public entity appear across multiple nearby sentences.
- Dismissal/removal with public target separation from owner/controller context.
- Inflected person references such as full name followed by surname-only or pronoun references.
- Same-name contrast such as "Jan Kowalski from party A, not the Jan Kowalski from party B".
- Father/son or family members sharing names.
- Party affiliation vs weak party support.
- Public grant/funding vs public contract/procurement.
- Compensation/salary without explicit nepotism.
- Anti-corruption referral without forced appointment/funding facts.
- True negatives: generic legal analysis, foreign politics, and articles that mention parties but no relevant public-money extraction.

Acceptance criteria:

- Tests assert expected candidate/fact presence, evidence text, scores above/below thresholds, and explicit uncertainty claims.
- Tests do not assert exact internal index contents, dataclass field inventories, source-code strings, or producer ordering unless ordering is part of the public pipeline contract.

### P4: Add Retrieval, RAG, And Persistence Options

Once deterministic V2 behavior is usable, add retrieval and optional persistence:

- Use sentence-transformer vectors for evidence-span retrieval and paraphrase matching.
- Keep an in-memory vector index for tests and small batch runs.
- Add a persistent vector store only when cross-document retrieval or benchmark speed requires it.
- Consider graph projection for analysis, not as the first source of truth.
- Add optional RAG producers that retrieve similar evidence and propose candidates under schema constraints.

Acceptance criteria:

- Disabling embeddings, coreference, or LLM/RAG still leaves the deterministic pipeline usable.
- Optional producers add candidates/signals; they do not change the meaning of deterministic IDs or silently rewrite existing facts.

## Test And Command Discipline

V2-only development loop:

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check pipeline_v2 tests_v2
uv run pytest -c pytest-v2.ini
```

Full V1 benchmark runs remain useful for comparison, but they are not the default V2 loop. When V2 starts consuming benchmark HTML inputs, use a separate V2 benchmark command and separate report under `reports/v2/`.

## Immediate Next Slices

Recommended next implementation order:

1. Stabilize V2 output typing and diagnostics.
2. Add public-money candidate records for `FUNDING`, `PUBLIC_CONTRACT`, and `COMPENSATION`.
3. Add behavior fixtures for grant vs contract vs compensation.
4. Port governance appointment/dismissal as candidate producers backed by dependency and bounded discourse windows.
5. Add same-name and inflected-reference fixtures before expanding entity-resolution heuristics.
6. Add optional coreference provider wiring after deterministic reference resolution is behavior-tested.
7. Start a V2 benchmark report comparing a small set of articles against expected V2 candidates and uncertainty claims.

## Risks And Open Questions

- Real Stanza dependency spans and Morfeusz token spans may not always align cleanly. The adapter boundary should absorb this rather than leaking backend details into domain producers.
- The right amount of centralized domain vocabulary is still unresolved. Stable domain lexicons are acceptable, but scattered ad hoc lists are not.
- V2 output may become large because it intentionally overproduces. We will likely need output profiles: compact, default, and debug.
- A graph database might become useful for cross-document analysis, but adopting one too early could weaken type safety and obscure extraction behavior.
- LLM/RAG can improve recall, but only if they remain optional candidate/scoring layers with schema-constrained output.
- Benchmark migration must avoid turning V2 tests into frozen reimplementations of V1 internals.

