# Project Consolidated Status Report - 2026-05-06

This report consolidates the most relevant architectural findings, refactor results, and benchmark progress from previous specialized reports.

## 0. Local Worktree Regression Fixes (2026-05-08)

Investigation focused on the current local worktree for PR #27-style extraction changes, not just the pushed branch state.

**What improved:**
- Fixed a real kinship-resolution bug where dependency `word.index` was treated as a list position in `pipeline/domains/kinship.py`.
- Fixed a broken local reference in `pipeline/attribution.py` and removed a shared-layer import from `pipeline.domains.kinship`, restoring the import boundary expected by `tests/test_import_boundaries.py`.
- Reduced party-profile overfitting by removing narrow office lemmas from `PARTY_CONTEXT_LEMMAS` and using public-office `role_kind` context in `pipeline/domains/political_profile.py` for cross-sentence party attribution.
- Added regression coverage for sparse dependency indices in kinship extraction and for cross-sentence party attribution driven by office-role context.

**What regressed:**
- No new regression was observed in the spot-checked benchmark outputs after the fixes.

**Benchmark / validation checked:**
- Full `uv run pytest -q`: passed.
- Clean-registry warm benchmark run: `uv run python main.py --input-dir inputs --glob "*.html" --output-dir output` after deleting `output/entity_registry.sqlite3*`: passed.
- Spot-checked benchmark outputs:
  - `zona-posla-pis`: spouse ties, PiS party links, and appointment output still present.
  - `dziennikpolski24...charsznicy...`: partner/father-in-law ties and local appointment output still present.
  - `dziennikzachodni...bytomiu...`: spouse tie still present.
  - `olsztyn.tvp.pl...jaroslaw-sloma...`: vice-president appointment plus party/office output still present.

**Next bottleneck:**
- Secondary-fact duplication remains visible in some outputs (notably repeated kinship and office/appointment facts in `zona-posla-pis` and the Jarosław Słoma article). The current fix preserved coverage but did not tackle deduplication quality.

## 1. Major Architectural Milestone: Dependency Frames (2026-05-05)

A shared dependency-frame layer was added for clause-local extraction arguments. Governance and funding extraction now route through this layer before discourse fallbacks.

**Key Improvements:**
- Typed argument, money-span, and trigger-frame dataclasses in `pipeline.dependency_frames`.
- Clauses index dependency frames in `ExtractionContext`.
- Preferred appointee/dismissal-person and organization candidates in governance frames based on dependency arguments.
- Shared `fact_time_scope` helper for temporal grounding.

**Current Coverage:**
- Full test suite: 225 passed.
- Benchmark batch: Success for all `inputs/*.html`.

## 2. Tech Debt Cleanup (2026-05-05)

Stale compatibility shims and runtime role-regex fallbacks were removed while preserving the CLI contract and JSON output shape.

**Cleaned Up Components:**
- Deleted stale re-export shims in `pipeline/compensation.py`, `funding.py`, `governance.py`, `public_facts.py`, and `relations/fact_extractors.py`.
- Removed runtime `ROLE_PATTERNS` usage for role extraction (now parser-backed).
- Preservation of `ClusterID -> EntityID` mappings through fact builders.

## 3. New Website Extraction Analysis (2026-05-04)

Evaluation of new articles (Onet Totalizator, Business Insider PZU, PHN) compared Rules/NLP vs. LLM engines.

**Comparative Findings:**
- **LLM Engine:** Better coverage on concise, named, sentence-local facts (e.g., dismissals, acting roles, specific salary amounts). Runtime is significantly higher (~30-90s per article).
- **Rules Engine:** Strong relevance and broad entity coverage but prone to target resolution issues (e.g., attaching roles to political parties instead of companies).

**Target Improvements for Rules Engine:**
1. List-aware governance extractor for broad board changes.
2. Tighten governance target scoring to avoid "party-as-employer" errors.
3. Improve person-name preservation for Polish inflection.
4. Add public-contract extractor for specific remuneration patterns.

## 4. Extraction Context & Domain Split (2026-04-25)

The pipeline was refactored into domain-oriented packages to improve maintainability.

**New Domain Packages:**
- `pipeline/domains/public_money.py`
- `pipeline/domains/funding.py`
- `pipeline/domains/public_employment.py`
- `pipeline/domains/anti_corruption.py`
- `pipeline/domains/compensation.py`
- `pipeline/domains/governance_frames.py`

Shared typed cluster and evidence helpers were moved to `pipeline/extraction_context.py`.

## 5. Summary of Recent Benchmark Results (2026-05-06)

**Aggregate Score:** 25 passed, 12 xfailed (target improvements), 29 subtests passed.

## 6. Refactor Plan Status (2026-05-06)

The **Frame-First Refactor Plan (2026-04-14)** has been fully executed and is now considered completed. 

**Achievements:**
- Implementation of `governance_frames`, `funding_frames`, and `dependency_frames`.
- Separation of concerns into domain-specific packages.
- Orchestration of the pipeline around frame-based extraction.
- Removal of legacy compatibility shims.

The original plan document has been removed from the active reports directory as it no longer contains pending tasks.
