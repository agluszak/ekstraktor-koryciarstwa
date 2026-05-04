---
name: add-extraction-website
description: "Use when adding or checking a new website/article in ekstraktor-koryciarstwa: read the article first, write expected extraction findings, run the pipeline on the exact input, compare actual JSON to the expectation, and identify the next extraction/relevance/preprocessing/linking improvement."
---

# Add Extraction Website

## Core Rule

Use the benchmark-first loop. Do not run the extractor first and then invent expected findings from the output. Read the article text, write what should be extracted, run the pipeline, compare, then decide what layer needs work.

This skill is repo-specific for `/home/agluszak/code/aktywizm/ekstraktor-koryciarstwa`.

## Workflow

1. Inspect the current benchmark context.
   - Read `reports/expected_article_findings.md` before deciding expected facts.
   - Skim recent relevant reports if the new article resembles existing cases, especially public-money, kinship, public-employment, governance, compensation, or anti-corruption reports.
   - Use `rg` to find similar fixture names, article domains, fact types, or person/org names.

2. Read the article input before running extraction.
   - If the user gives a local HTML path, inspect it through the repo preprocessor or direct text reads.
   - If the user gives a URL and asks for a live check, use the repo CLI URL path unless they ask to save a fixture.
   - If adding a durable benchmark article, save the fetched/raw HTML under `inputs/` with a clear source-derived filename.
   - Do not use temporary-directory/cache workarounds. If environment or sandbox behavior blocks normal repo execution, stop and report the blocker.

3. Write expected findings first.
   Include:
   - `relevance`: should the article be relevant?
   - expected facts by type, e.g. `APPOINTMENT`, `DISMISSAL`, `PUBLIC_CONTRACT`, `FUNDING`, `COMPENSATION`, `PARTY_MEMBERSHIP`, `PERSONAL_OR_POLITICAL_TIE`, `ANTI_CORRUPTION_REFERRAL`.
   - subject, object, role/amount/period/party/tie detail, and exact evidence sentence when available.
   - expected negatives: facts that should not be emitted, likely false-positive traps, boilerplate/comment risks, ambiguous `przekazać` uses, or family-trigger traps such as `założona` containing `żona`.

4. Run the narrow pipeline check.
   First ensure models are provisioned:

   ```bash
   uv run python scripts/setup_models.py
   ```

   For one local article:

   ```bash
   uv run python main.py --html-path inputs/<article>.html --document-id <article_id> --output-dir output --stdout
   ```

   For a URL-only check:

   ```bash
   uv run python main.py --url "<url>" --document-id <article_id> --output-dir output --stdout
   ```

   For benchmark batch checks, prefer one warm process:

   ```bash
   uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
   ```

5. Compare actual to expected.
   Check:
   - relevance decision and reasons
   - extracted entities and canonical names
   - facts, subject/object direction, type, amount/role/period, confidence, source extractor, and evidence spans
   - missing expected facts
   - false-positive facts
   - stale or polluted `output/entity_registry.sqlite3` effects

6. Identify the failing layer before proposing a fix.
   Use the smallest useful diagnosis:
   - Relevance wrong: inspect `pipeline/filtering/service.py` and cleaned text.
   - Text missing/bad: inspect `TrafilaturaPreprocessor` output and content quality flags.
   - Names bad: inspect NER, normalization, clustering, and SQLite linking.
   - Fact missing: inspect segmentation, clause parsing, frame extraction, then fact builders.
   - Wrong target/entity: inspect governance target resolution, owner/body context handling, identity/proxy evidence, and canonicalization.
   - Public-money confusion: distinguish `FUNDING`, `PUBLIC_CONTRACT`, and `COMPENSATION`; do not overload one fact type to cover another.

7. Preserve durable findings.
   If this is more than a quick chat check, write a fresh report in `reports/` with:
   - article/source and command run
   - expected findings written before execution
   - actual output summary
   - expected-vs-actual diff
   - likely failing layer
   - proposed next fix and regression scope

8. Add or update benchmark artifacts when appropriate.
   - Add an entry to `reports/expected_article_findings.md` for durable benchmark cases.
   - Add or update focused tests when changing extraction logic.
   - For material pipeline changes, run:

   ```bash
   uv run ruff check . --fix
   uv run ruff format .
   uv run ruff check .
   uv run ty check
   uv run pytest
   ```

## Fix Selection

Prefer general extraction improvements over article-specific patches. Small lexical lists are acceptable when they define a stable domain boundary; avoid hardcoded article/person/org hacks.

Use typed schema support when the missing behavior is a real fact category. For public-money cases, preserve semantic precision:

- `FUNDING`: grants/subsidies/direct public-money transfers.
- `PUBLIC_CONTRACT`: contracts, paid promotion, procurement-like money for services.
- `COMPENSATION`: salary/remuneration/public pay.

For family/proxy cases, preserve uncertainty. Do not hard-merge ambiguous surname or unnamed family-role mentions when the evidence only supports possible identity.

## Output Shape

When reporting back to the user, lead with the comparison:

```markdown
Expected:
- ...

Actual:
- ...

Gaps:
- Missing: ...
- False positives: ...
- Wrong attribution/canonicalization: ...

Likely failing layer:
- ...

Next improvement:
- ...
```
