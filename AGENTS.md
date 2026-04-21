# Repository Instructions

- Use direct execution now that full access is available.
- If a task starts needing environment or sandbox workarounds, stop and notify the user instead of adding a workaround.
- When lint or formatting tools support autofix, run the autofix path first and only do manual cleanup for remaining issues.
- `uv sync` does not install the spaCy/Stanza model assets required by this repo. In any fresh or rebuilt `.venv`, run `uv run python scripts/setup_models.py` before running the pipeline or tests. Do not skip model-dependent tests; provision the models instead.
- **Typing Hygiene**: Avoid "messy" weak typing like `dict[str, Any]` or broad unions in dictionaries. Prefer `NewType` for IDs and structured `TypedDict` or `dataclasses` for nested metadata.
- **ID Typing**: Preserve `NewType` ID aliases (`EntityID`, `ClusterID`, `FactID`, `DocumentID`, etc.) through local variables, helper signatures, sets, and return types. Do not weaken typed IDs to plain `str` just to satisfy type tooling; fix the annotations at the boundary instead.
- **Proper Logic**: Do not use `try-except` blocks for expected control flow (e.g., checking if a value is in an Enum). Use explicit checks or safe helper methods (e.g., `Enum.from_str()`) to handle optionality.

# Project Context

This repository houses an information extraction pipeline ("ekstraktor-koryciarstwa") focused on analyzing Polish news articles. Its primary domain is monitoring "koryciarstwo" / public money extraction: nepotism, patronage, appointments to state-owned companies, and the flow of public funds.

## Domain Model
The pipeline extracts specific entities and facts from text, using tools like spaCy NER and Stanza parsing. Key concepts include:
- **Entities**: People, Organizations (state-owned enterprises, public institutions, municipal utilities), Political Parties (e.g., KO, PO, PSL, Lewica, Polska 2050, PiS), Roles/Positions, and Salary figures.
- **Facts**:
  - `APPOINTMENT` / board-membership-style governance facts: Tracking governance changes and new board members.
  - `DISMISSAL`: Removals from management or supervisory boards.
  - `PARTY_MEMBERSHIP`: Direct political party affiliations.
  - `PERSONAL_OR_POLITICAL_TIE`: Acquaintances, family ties, and patronage networks.

## Benchmarks and Evaluation
The `reports/` folder contains benchmark files (e.g., `expected_article_findings.md` and progress tracking reports) used to evaluate pipeline extraction quality. They document:
- Expected extraction scenarios for various high-signal articles (like appointments without competition, party-affiliated staffing in public trusts or utilities).
- True negative examples that should not trigger extraction (e.g., generic legal analysis or international news).
- Current parsing performance metrics, issues (like false-positive facts or noisy entity spans), and immediate focus areas for improvement.

Always consult the benchmark reports when modifying extraction rules or parsing logic to ensure changes align with expected outcomes and to avoid regressions.

## Regression Testing Workflow

When extraction, preprocessing, linking, scoring, or output logic changes:

1. Read [reports/expected_article_findings.md](/D:/extractor/reports/expected_article_findings.md:1) first.
   Use it as the manual oracle for what each benchmark article should and should not produce.

2. Run the automated checks first:
   - `uv run python scripts/setup_models.py`
   - `uv run ruff check . --fix`
   - `uv run ruff format .`
   - `uv run ruff check .`
   - `uv run ty check`
   - `uv run pytest`

3. Rerun the benchmark HTML inputs in one warm process:
   - `uv run python main.py --input-dir inputs --glob "*.html" --output-dir output`
   Prefer batch mode so spaCy/Stanza load once.

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

## Current Architecture

The pipeline is no longer just "NER plus relation rules". The current internal shape is frame-first:

1. preprocessing
2. relevance filtering
3. segmentation
4. spaCy NER
5. Stanza coreference
6. entity clustering
7. clause parsing
8. frame extraction
9. fact extraction from frames
10. SQLite entity linking
11. scoring
12. JSON output

The practical entrypoint is [pipeline/cli.py](/D:/extractor/pipeline/cli.py:1), and the orchestration order is in [pipeline/orchestrator.py](/D:/extractor/pipeline/orchestrator.py:1).

### Important Modules

- [pipeline/ner/service.py](/D:/extractor/pipeline/ner/service.py:1)
  Owns initial spaCy entity extraction and creation of `document.entities`.
- [pipeline/normalization.py](/D:/extractor/pipeline/normalization.py:1)
  Owns canonicalization, deduplication, acronym/inflection handling, and alias cleanup.
- [pipeline/clustering.py](/D:/extractor/pipeline/clustering.py:1)
  Builds document-level `EntityCluster`s from normalized entities and mentions.
- [pipeline/syntax.py](/D:/extractor/pipeline/syntax.py:1)
  Produces parser-backed `ClauseUnit`s and aligned parsed token spans.
- [pipeline/frames.py](/D:/extractor/pipeline/frames.py:1)
  Builds `GovernanceFrame`, `CompensationFrame`, and `FundingFrame`.
- [pipeline/governance.py](/D:/extractor/pipeline/governance.py:1)
  Resolves governance targets and builds governance facts.
- [pipeline/compensation.py](/D:/extractor/pipeline/compensation.py:1)
  Builds compensation facts from compensation frames.
- [pipeline/funding.py](/D:/extractor/pipeline/funding.py:1)
  Builds funding facts from funding frames.
- [pipeline/relations/service.py](/D:/extractor/pipeline/relations/service.py:1)
  The frame-derived fact extraction path. This is the main extraction service now.
- [pipeline/linking/service.py](/D:/extractor/pipeline/linking/service.py:1)
  SQLite registry linking and post-extraction canonical name reuse.

## Practical Model / Runtime Notes

- There is a shared runtime for spaCy / sentence-transformers / parsing, but Stanza coref is intentionally reloaded multiple times because earlier attempts to persist it caused instability. This is known and documented in `reports/`.
- Batch mode still matters. Even with repeated coref loading, `--input-dir ... --glob "*.html"` is the correct benchmark path because the rest of the pipeline stays warm.
- The generated SQLite registry lives at `output/entity_registry.sqlite3`.
  This is a generated artifact, not a source of truth.
  If canonical names or aliases look polluted, it is valid to delete:
  - `output/entity_registry.sqlite3`
  - `output/entity_registry.sqlite3-shm`
  - `output/entity_registry.sqlite3-wal`
  and rerun from a clean registry before judging extraction quality.

## Current Extraction Design

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
- A recent concrete issue was multiline/block extraction like:
  `Ministerstwo Kultury i Dziedzictwa Narodowego\nFundacja Lux Veritatis\n`
  being compacted into a fake single entity.
- The current fix is:
  - multiline organization names are split into line-level candidates for canonicalization,
  - compacted full-block names are excluded when the raw multiline alias exists,
  - multiline aliases are not inserted into SQLite alias matching.
- If you see a weird joined organization name in output, check both:
  - normalization behavior,
  - whether the local generated SQLite registry still contains old polluted canonicals.

## Benchmark State As Of 2026-04-16

The latest full clean-registry benchmark is:
- [reports/benchmark_full_2026-04-16.md](/D:/extractor/reports/benchmark_full_2026-04-16.md:1)

Important current truths:

- OKO / Rydzyk funding now looks correct:
  - `Fundacja Lux Veritatis` funded by `Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu`
  - `Fundacja Lux Veritatis` funded by `Jastrzębskie Zakłady Remontowe`
- Salary articles like `olsztyn_wodkan` and KZN still emit compensation facts.
- Strong appointment articles like Totalizator, Radomszczańska, TVP Olsztyn, and `zona-posla-pis` still emit governance output.

Current benchmark problems worth knowing before you start changing things:

1. `wiadomosci.onet.pl__lublin__...__cpw9ltt`
   Strong positive article, but currently filtered out as irrelevant.
   This is probably a relevance/content-extraction issue, not just relation extraction.

2. `pleszew24.info__...stadniny-koni`
   Relevant, but produces no facts.
   Likely failure after relevance: NER, clause parsing, or governance-frame resolution.

3. `rp_tk_negative`
   Still a relevance false positive, although downstream extraction stays empty.

4. Funding false positives:
   `przekazać` in "communicated/told us" contexts still sometimes creates weak `FUNDING` facts with no amount.

## Debugging Workflow That Saves Time

When an article behaves strangely, inspect it in this order:

1. Relevance decision.
   If relevance is wrong, nothing downstream matters.

2. Cleaned text / content extraction quality.
   Some article variants differ mainly because the extracted text is poorer or shorter.

3. Entities and aliases.
   Check whether the relevant person/org names even exist and whether they were over-merged.

4. Clause units and frames.
   For governance/funding/compensation problems, the useful question is usually:
   "Did the right frame get built?"
   not
   "Why did the final relation look odd?"

5. SQLite registry contamination.
   If names look stale or impossible, clear the generated registry and rerun once before deeper surgery.

## Operational Guidance For Future Agents

- Do not add article-specific hardcoded patches unless the user explicitly asks for them.
- Prefer general NLP-backed fixes over word lists or regex expansions.
- But do not be dogmatic: small lexical lists are acceptable when they define a stable domain boundary. The problem is fragile article-specific patching, not every list.
- If a fix changes extraction quality materially, write a new dated progress note in `reports/`.
- If a benchmark run was done from a clean registry, say that explicitly in the report. It matters.
