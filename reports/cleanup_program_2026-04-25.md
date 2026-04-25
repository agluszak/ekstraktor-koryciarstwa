# Cleanup Program - 2026-04-25

## Scope

This step completed the three planned cleanup phases after the slot-grounding
refactor:

1. split canonicalization policy from normalization and linking
2. consolidate shared secondary-fact helpers and remove the stale split module
3. unify shared sentence-level relation signals used by candidate graph and
   secondary fact extraction

The goal was to remove bad abstractions and duplicated heuristics without
changing the public JSON schema, CLI behavior, frame dataclasses, or fact
types.

## Implemented

### 1. Canonicalization / linking boundary cleanup

- Added `pipeline/entity_naming.py` as the shared naming-policy layer for:
  - organization canonical selection
  - public-institution canonical selection
  - acronym-based organization alias repair
  - organization alias normalization
  - shared organization token/acronym helpers
- Refactored `pipeline/normalization.py` to use the shared naming policy instead
  of owning the organization/public-institution naming logic directly.
- Refactored `pipeline/linking/service.py` to use the shared naming policy and
  shared org-token helper instead of calling canonicalizer private methods.

### 2. Secondary-fact helper consolidation

- Replaced `pipeline/secondary_fact_utils.py` with
  `pipeline/secondary_fact_helpers.py`.
- Moved `pipeline/domains/political_profile.py` to the new shared module.
- Removed duplicated scorer/building/helper definitions from
  `pipeline/domains/secondary_facts.py`.
- Updated `tests/test_import_boundaries.py` to point at the new shared module.

### 3. Shared relation-signal layer

- Added `pipeline/relation_signals.py` for shared sentence-level helpers:
  - candidate span word lookup
  - candidate head-word selection
  - between-candidate text windows
  - quote-speaker risk
  - party syntactic signal
  - party context-window support
  - candidate-graph `supports_party_link(...)`
- Refactored:
  - `pipeline/secondary_fact_helpers.py`
  - `pipeline/relations/candidate_graph.py`
  to consume the same relation-signal helpers.

## Debt removed

- deleted the stale `pipeline/secondary_fact_utils.py` abstraction
- removed duplicated secondary-fact scorer/building logic from
  `pipeline/domains/secondary_facts.py`
- removed duplicated sentence-level party-signal primitives from the
  secondary-fact layer in favor of `pipeline/relation_signals.py`
- removed linker dependence on canonicalizer private organization naming helpers

## Benchmark / regression impact

Benchmark-sensitive checks remained green for the articles most exposed to these
cleanups:

- `tvnwarszawa_fundacja_bielskiego_20260425`
  - keeps `Fundacja Karola Bielskiego`
  - keeps `Urząd Marszałkowski`
  - keeps paid-promotion `PUBLIC_CONTRACT`
- `wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`
  - keeps marshal-office and OUW context
- `wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie__7273798906222848a`
  - keeps `Lubelskie Koleje`
- `oko_miliony_pajeczyna_rydzyka`
  - keeps funding extraction rooted in the expected organizations

Additional focused protections that remained green:

- `Wp` alias deduplication in linking
- no party cross-attachment across multiple people in one sentence
- import-boundary enforcement for shared helper modules

## Validation

Commands run during this cleanup:

```bash
uv run ruff check pipeline/entity_naming.py pipeline/normalization.py pipeline/linking/service.py \
  tests/test_entity_normalization.py tests/test_identity_linking.py
uv run ty check pipeline/entity_naming.py pipeline/normalization.py pipeline/linking/service.py
uv run pytest tests/test_entity_normalization.py tests/test_identity_linking.py -q

uv run ruff check pipeline/secondary_fact_helpers.py pipeline/relation_signals.py \
  pipeline/domains/secondary_facts.py pipeline/domains/political_profile.py \
  pipeline/relations/candidate_graph.py tests/test_import_boundaries.py
uv run ty check pipeline/secondary_fact_helpers.py pipeline/relation_signals.py \
  pipeline/domains/secondary_facts.py pipeline/domains/political_profile.py \
  pipeline/relations/candidate_graph.py
uv run pytest tests/test_import_boundaries.py tests/test_relations.py tests/test_family_identity.py -q

uv run pytest tests/test_identity_linking.py tests/test_import_boundaries.py \
  tests/test_relations.py tests/test_family_identity.py tests/test_governance.py \
  tests/test_extraction_context.py -q

uv run pytest tests/integration/test_benchmark.py -k \
  'tvnwarszawa_fundacja_bielskiego_public_contract or wp_opole_cross_office_family or wp_zona_posla_pis_lubelskie_koleje or oko_rydzyk_funding' -q

uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Results:

- focused normalization/linking tests: `26 passed`
- focused helper/relation cleanup tests: `65 passed`
- expanded focused regression suite: `94 passed`
- benchmark-sensitive cleanup slice: `4 passed, 1 xfailed`
- final full validation: `170 passed, 1 xfailed`

The final benchmark and full-suite validation were run on a warmed benchmark
batch.
