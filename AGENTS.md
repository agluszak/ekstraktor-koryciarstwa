# Repository Instructions

- Use uv in the repo root
- If a task starts needing environment or sandbox workarounds, stop and notify the user instead of adding a workaround.
- When lint or formatting tools support autofix, run the autofix path first and only do manual cleanup for remaining issues.
- `uv sync` does not install the spaCy/Stanza model assets required by this repo. In any fresh or rebuilt `.venv`, run `uv run python scripts/setup_models.py` before running the pipeline or tests. Do not skip model-dependent tests; provision the models instead.
- **Typing Hygiene**: Avoid "messy" weak typing like `dict[str, Any]` or broad unions in dictionaries. Prefer `NewType` for IDs and structured `TypedDict` or `dataclasses` for nested metadata.
- **ID Typing**: Preserve `NewType` ID aliases (`EntityID`, `ClusterID`, `FactID`, `DocumentID`, etc. in V1, and `EntityCandidateId`, `FactCandidateId`, `MentionId`, `SentenceId`, `EvidenceId`, etc. in V2) through local variables, helper signatures, sets, and return types. Do not weaken typed IDs to plain `str` just to satisfy type tooling; fix the annotations at the boundary instead.
- **Proper Logic**: Do not use `try-except` blocks for expected control flow (e.g., checking if a value is in an Enum). Use explicit checks or safe helper methods (e.g., `Enum.from_str()`) to handle optionality.
- Do not implement any kind of compatibility shims. We're not interested in backwards compatibility for now. When a test needs fixing, refactor it.

# Project Context

This repository houses an information extraction pipeline ("ekstraktor-koryciarstwa") focused on analyzing Polish news articles. Its primary domain is monitoring "koryciarstwo" / public money extraction: nepotism, patronage, appointments to state-owned companies, and the flow of public funds.

## Domain Model (V1 & V2)

### Entities
- **People**: Names of political appointees, relatives, or politicians.
- **Organizations**: State-owned enterprises, public institutions, municipal utilities, foundations, etc.
- **Political Parties**: Direct political affiliations (e.g., KO, PO, PSL, Lewica, Polska 2050, PiS).
- **Roles**: Public/corporate positions or titles.
- **Salary figures**: Monetary amounts corresponding to compensation or public funding.

### Fact Kinds
- **V1 (Legacy)**:
  - `APPOINTMENT`: Board/governance appointments.
  - `DISMISSAL`: Removals from management or supervisory boards.
  - `PARTY_MEMBERSHIP`: Political party affiliations.
  - `PERSONAL_OR_POLITICAL_TIE`: Acquaintances, family ties, and patronage networks.
- **V2 (Graph/Stage-Based)** (represented by `FactKind` enum):
  - `GOVERNANCE_APPOINTMENT` / `GOVERNANCE_DISMISSAL`: Governance changes.
  - `PARTY_AFFILIATION` / `POLITICAL_SUPPORT`: Political connections.
  - `PERSONAL_OR_POLITICAL_TIE`: Kinship and clientelism networks.
  - `PUBLIC_EMPLOYMENT`: Public-sector jobs.
  - `FUNDING` / `PUBLIC_CONTRACT` / `COMPENSATION`: Financial flows (grants, contracts, salaries).
  - `ANTI_CORRUPTION_REFERRAL` / `ANTI_CORRUPTION_INVESTIGATION`: External oversight events.

## Benchmarks and Evaluation
The `reports/` folder contains benchmark files (e.g., `expected_article_findings.md` and progress tracking reports) used to evaluate pipeline extraction quality. They document:
- Expected extraction scenarios for various high-signal articles (like appointments without competition, party-affiliated staffing in public trusts or utilities).
- True negative examples that should not trigger extraction (e.g., generic legal analysis or international news).
- Current parsing performance metrics, issues (like false-positive facts or noisy entity spans), and immediate focus areas for improvement.

Always consult the benchmark reports when modifying extraction rules or parsing logic to ensure changes align with expected outcomes and to avoid regressions.

## Pipeline Architectures (V1 vs V2)

### V1 Pipeline Architecture (Legacy Frame-First)

> [!NOTE]
> The V1 pipeline exists for reference only and must not be updated. Do not run V1 tests, only V2.

The legacy pipeline in `pipeline/` collapses frames early using dependency rules:
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

Orchestration is done in [pipeline/orchestrator.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline/orchestrator.py), and CLI entrypoint is [pipeline/cli.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline/cli.py) (run via `main.py`).

### V2 Pipeline Architecture (Active Modular Stage-Based)
The active V2 pipeline in `pipeline_v2/` is designed as a decoupled, stage-based hypothesis graph. It processes documents through `DocumentStage` implementations:
1. **HtmlArticlePreprocessor**: Normalizes raw HTML into clean text paragraphs.
2. **ProfileRelevanceFilter**: Filters out irrelevant articles early using keyword/structural heuristics.
3. **ParagraphSentenceSegmenter**: Segments paragraphs into sentences and tokens.
4. **MorfeuszMorphologyStage**: Runs Morfeusz2 to populate morphological tags and lemmas.
5. **DependencyParseStage** (optional): Computes token-level dependency trees.
6. **NamedEntityCandidateStage**: Runs spaCy/custom NER to produce named entity candidates.
7. **Domain Candidate Stages** (run sequentially to populate `document.store.fact_candidates`):
   - `PartyCandidateStage`: Detects party mentions and affiliations.
   - `RoleCandidateStage`: Detects public/corporate roles.
   - `GovernanceCandidateStage`: Extracts candidate appointments and dismissals.
   - `PublicEmploymentCandidateStage`: Extracts public-sector hiring events.
   - `PublicMoneyCandidateStage`: Extracts funding grants, public contracts, and compensations.
   - `AntiCorruptionCandidateStage`: Detects investigations and referrals.
8. **Coreference/Reference Stages** (optional):
   - `LightReferenceStage` or `CoreferenceReferenceStage`: Extracts and resolves reference mentions (pronouns, noun-phrase descriptors).
9. **Proxy & Tie Candidate Stages**:
   - `FamilyProxyCandidateStage` & `PersonalTieCandidateStage`: Extract familial and patronage networks.
10. **ResolutionScoringStage**: Scores candidate entity resolutions (merges, reference linkages) using explicit signals.
11. **FactScoringStage**: Scores fact candidates using positive/negative evidence signals and assigns final assessments.

Decoupled orchestration loop is implemented in `V2Pipeline` in [pipeline_v2/stages.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/stages.py), built using the factory `build_v2_pipeline` in [pipeline_v2/runtime.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/runtime.py). The CLI entrypoint is [pipeline_v2/cli.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/cli.py) (run via script command `extractor-v2`).

## V2 Knowledge Graph Design Principles

When working in `pipeline_v2/`, preserve the graph-like architecture and do not grow "god objects". Do not keep adding fields to `EntityCandidate`, fact candidates, `ArticleDocument`, or `ExtractionStore` just because a new producer needs state.

### Core Decoupled Rules
- **Entities are identity hypotheses only** (no fields like `entity.party`, `entity.role`, `entity.is_public`, etc. Instead, use explicit facts and claims).
- **Facts are event/relation hypotheses only**.
- **Evidence is text-grounding only**.
- **Scores are assessments only** (confidence/scores belong in separate `Assessment` records, not on candidates/facts).
- **Links between elements must be explicit typed records**, not hidden mutable fields.
- **Separation of Generation and Scoring**: Stages/producers only emit candidate hypotheses and local signals. The scoring stages (`ResolutionScoringStage`, `FactScoringStage`) compute the scores and assign assessments at the end.
- **Decoupled Retrieval**: Do not implement lookups in `ExtractionStore` directly. Implement search logic in specialized retriever classes (e.g. `SentenceEntityRetriever`, `EntityCandidateRetriever`) located in [pipeline_v2/retrieval.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/retrieval.py).

### Preferred V2 Graph Shape
- **Vertex-like records**:
  - `EvidenceSpan`: exact text span and source location.
  - `Mention`: observed named/entity-like span.
  - `ReferenceMention`: pronoun, surname-only, descriptor, omitted subject, or proxy phrase.
  - `EntityCandidate`: local hypothesis for a person, organization, party, role, etc.
  - `FactCandidate`: local hypothesis for a relation or event.
  - `Assessment`: score plus positive/negative signals.
  - `ResolutionClaim`: scored possible identity/reference link.
- **Edge-like records**:
  - `Mention -> EvidenceSpan` via `evidence_id`.
  - `EntityCandidate -> Mention` via `mention_ids`.
  - `EntityCandidate -> ReferenceMention` via `reference_ids`.
  - `FactCandidate -> EntityCandidate/Text` via typed fact arguments.
  - `FactCandidate -> EvidenceSpan` via `evidence_ids`.
  - `ResolutionClaim -> EntityCandidate/ReferenceMention` via explicit endpoint IDs.
  - `Assessment -> candidate/claim` through small wrapper records such as `FactAssessment`.

### V2 Candidate and Claim Guidance
- Candidate records should stay small and typed.
- If a new candidate family needs different arguments, prefer a new candidate dataclass with `to_fact_record()` over adding nullable fields to an existing one.
- If multiple candidate families share an output shape, convert them to a common `FactCandidateRecord` at the serialization/scoring boundary.
- Use explicit typed arguments instead of custom fields, for example:
  - `EntityFactArgument(FactArgumentRole.PERSON, person_id)`
  - `EntityFactArgument(FactArgumentRole.ORGANIZATION, org_id)`
  - `TextFactArgument(FactArgumentRole.CONTEXT, text)`
- Do not add "just in case" optional fields.

## V2 Extensibility & Development Guidelines

When extending the V2 pipeline with new domain logic (e.g., new fact kinds, signals, or entity types):

1. **Extend Domain Types**:
   - Add new fact kinds to the `FactKind` enum in [pipeline_v2/types.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/types.py).
   - Add new signal types by subclassing `Signal` (with `@dataclass(frozen=True, slots=True)`) in [pipeline_v2/types.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/types.py).

2. **Define Fact Candidates**:
   - Implement candidates using frozen dataclasses (e.g., implementing `FactCandidate` protocol) in [pipeline_v2/candidates.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/candidates.py).
   - Ensure the candidate class implements `to_fact_record()` to return a `FactCandidateRecord` with arguments wrapped in `EntityFactArgument` or `TextFactArgument` and associated signals.

3. **Implement Candidate Extraction (Stage)**:
   - Create a candidate stage implementing the `DocumentStage` protocol (e.g., must define `name(self) -> str` and `run(self, document: ArticleDocument) -> ArticleDocument`).
   - Locate sentence-local entities using `SentenceEntityRetriever` or token morphology.
   - Overwrite/populate the store using `document.store.add_fact_candidate()`.
   - Register the stage in `build_v2_pipeline` in [pipeline_v2/runtime.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/runtime.py).

4. **Add Scoring Logic**:
   - In `FactRecordScorer.score` inside [pipeline_v2/scoring.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/pipeline_v2/scoring.py), add signal evaluation logic.
   - Adjust the score (typically starting at a low baseline like 0.2, incrementing for positive signals, decrementing for negative signals, clamped to `[0.0, 1.0]`).

5. **Write Unit/Integration Tests**:
   - Create a test file in `tests_v2/` (e.g., `tests_v2/test_your_feature.py`).
   - Standardize tests by using `StaticPreprocessor` and `StaticEntityProvider` to avoid loading heavy models (spaCy/Stanza) and keep execution under 1 second.
   - Assert directly on `document.store` contents, candidate arguments, signals, and scoring thresholds.

## V2 Testability & Mocking Strategy

The modular design of V2 makes it highly testable and runs in milliseconds without initializing heavy neural pipelines:
- **Preprocessors**: Use a `StaticPreprocessor(document)` which directly returns a pre-formed `ArticleDocument` containing specific paragraphs.
- **Named Entities**: Inject static entity spans using `StaticEntityProvider(entities)` passed to `NamedEntityCandidateStage` instead of running full spacy models.
- **Morphology Adapter**: Use `Morfeusz2MorphologyAdapter` (fast dictionary lookup) for morphology tokenization.
- **Example Pattern**: See [tests_v2/test_public_money.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/tests_v2/test_public_money.py) and [tests_v2/test_article_regression_fixtures.py](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/tests_v2/test_article_regression_fixtures.py) for standard mocking templates.

## Regression Testing Workflow

When extraction, preprocessing, linking, scoring, or output logic changes:

1. Read [reports/expected_article_findings.md](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/reports/expected_article_findings.md) first.
   Use it as the manual oracle for what each benchmark article should and should not produce.

2. Run the automated checks first:
   - `uv run python scripts/setup_models.py`
   - `uv run ruff check . --fix`
   - `uv run ruff format .`
   - `uv run ruff check .`
   - `uv run ty check`
   - `uv run pytest tests_v2/`  # Do not run V1 tests (tests/), only V2 tests

3. Rerun the benchmark HTML inputs in one warm process:
   - **V2 CLI**: `uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir output`
   Prefer batch mode so spaCy/Stanza load once. (V1 CLI is deprecated).

4. Compare outputs against the benchmark report, especially for:
   - strong positives that should yield appointments / dismissals / funding / compensation
   - true negatives that should stay irrelevant or relation-empty
   - high-risk regressions such as party mentions becoming appointment destinations, bad person merges, or boilerplate/comment entities leaking in

5. If extraction behavior changed materially, update the progress snapshot in `reports/` with:
   - what improved
   - what regressed
   - which benchmark articles were checked
   - which bottleneck is next

Do not treat `pytest` success as sufficient for extraction changes. The checked-in benchmark report is part of regression testing and must be consulted after significant pipeline changes.

## Practical Model / Runtime Notes

- **Stanza coref reload**: Stanza coref is intentionally reloaded multiple times because earlier attempts to persist it caused instability. This is known and documented in `reports/`.
- **Batch mode**: Even with repeated coref loading, `--input-dir ... --glob "*.html"` is the correct benchmark path because the rest of the pipeline stays warm.
- **In-memory registry linking**: V1 linker maintains an in-memory registry during a warm process, so canonical-name pollution can persist within one batch run. Rerun the batch in a fresh process before judging extraction quality.

## V1/V2 Extraction Design Heuristics

### Governance
- Governance should come from clause-local frames, not broad document-level candidate pairing.
- Owner/controller entities and governing bodies are context, not usually the real appointment target.
- Common failure mode: confusing `owner`, `fundusz`, `rada`, `zarząd`, or a party with the actual company/institution being staffed.

### Compensation
- Salary / remuneration articles are in scope for this project.
- `COMPENSATION` is meant for remuneration/public-money facts, not for grants or subsidies.
- If a public-money article has no patronage network but does contain high public compensation, that is still relevant.

### Funding
- Public grants/subsidies are in scope and now use `FundingFrame` + `FUNDING`, not `COMPENSATION`.
- The funding path currently works well for direct money-transfer clauses like:
  - `przyznał ... dotację`
  - `przekazał ... 300 tys. zł`
  - `wyłożyły ... 100 tys. zł`
- Known weakness: `przekazać` is ambiguous and still overfires in communication/reporting contexts like "przekazała nam", "przekazał redakcji", etc.
- When changing funding extraction, prefer parser/dependency signals over adding more regexes or hardcoded lexical patches.

## Canonicalization / Entity Hygiene

- Entity cleanup is not just cosmetic. Bad canonical names poison linking, frames, and benchmark interpretation.
- Multiline organization names are split into line-level candidates for canonicalization.
- Compacted full-block names are excluded when the raw multiline alias exists.
- Multiline aliases are not inserted into registry alias matching.
- If you see a weird joined organization name in output, check both:
  - normalization behavior,
  - whether the current warm-process in-memory registry was already polluted earlier in the batch.

## Benchmark State As Of 2026-04-16

The latest full clean-registry benchmark is:
- [reports/benchmark_full_2026-04-16.md](file:///home/agluszak/code/aktywizm/ekstraktor-koryciarstwa/reports/benchmark_full_2026-04-16.md)

Important current truths:
- OKO / Rydzyk funding now looks correct:
  - `Fundacja Lux Veritatis` funded by `Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu`
  - `Fundacja Lux Veritatis` funded by `Jastrzębskie Zakłady Remontowe`
- Salary articles like `olsztyn_wodkan` and KZN still emit compensation facts.
- Strong appointment articles like Totalizator, Radomszczańska, TVP Olsztyn, and `zona-posla-pis` still emit governance output.

Current benchmark problems worth knowing before you start changing things:
1. `wiadomosci.onet.pl__lublin__...__cpw9ltt`: Strong positive article, but currently filtered out as irrelevant (content extraction or relevance issue).
2. `pleszew24.info__...stadniny-koni`: Relevant, but produces no facts (likely NER, parser, or governance-frame resolution issue).
3. `rp_tk_negative`: Still a relevance false positive, although downstream extraction stays empty.
4. Funding false positives: `przekazać` in "communicated/told us" contexts still sometimes creates weak `FUNDING` facts with no amount.

## Debugging Workflow That Saves Time

When an article behaves strangely, inspect it in this order:

1. **Relevance decision**: If relevance is wrong, nothing downstream matters.
2. **Cleaned text / content extraction quality**: Some article variants differ mainly because the extracted text is poorer or shorter.
3. **Entities and aliases**: Check whether the relevant person/org names even exist and whether they were over-merged.
4. **V1 Frames or V2 Candidates/Signals**:
   - For V1: "Did the right frame get built?" rather than "Why did the final relation look odd?".
   - For V2: "Did the domain stage emit the candidate with correct local signals?" and "How was it assessed by the scorer?".
5. **Warm-process linker contamination**: If names look stale or impossible, rerun once in a fresh process.

## Operational Guidance For Future Agents

- Do not add article-specific hardcoded patches unless the user explicitly asks for them.
- Prefer general NLP-backed fixes over word lists or regex expansions.
- But do not be dogmatic: small lexical lists are acceptable when they define a stable domain boundary. The problem is fragile article-specific patching, not every list.
- If a fix changes extraction quality materially, write a new dated progress note in `reports/`.
- If a benchmark run was done from a clean registry, say that explicitly in the report. It matters.
