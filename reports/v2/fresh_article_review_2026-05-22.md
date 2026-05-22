# Fresh article review — 2026-05-22

## Scope

This note captures the current state after the recent inference/runtime cleanup,
the shared entity-tag slice, and one additional follow-up fix driven by fresh
article runs.

Work stayed in `pipeline_v2/` and `tests_v2/`.

## Changes landed so far

### 1. Inference/materialization cleanup

Recent work before this note tightened the probabilistic surface:

- materialized facts stay on `ArticleDocument`,
- optional weak roles move into `materialized_role_alternatives`,
- bare amount-only compensation facts are blocked,
- redundant descriptor-only governance facts are suppressed,
- `PUBLIC_CONTRACT` got a distinctness constraint so contractor and
  counterparty do not collapse to the same resolved entity/surface.

### 2. Entity-context first-class facts

The earlier ad-hoc `store.entity_tags` side dict has been replaced with a
first-class proposal/variable/claim chain that mirrors how entity, reference,
and same-event resolution are modeled:

- `EntityTag` enum (`pipeline_v2/types.py`) is unchanged in vocabulary
  (`public_institution`, `media_outlet`, `generic_owner`, `governing_body`).
- `EntityContextProposal` / `EntityContextClaim` typed records
  (`pipeline_v2/candidates.py`) carry `evidence_ids`, retrieval `signals`,
  and a scored `Assessment` — same shape as the other claim families.
- `LexicalEntityContextStage` (`pipeline_v2/entity_classification.py`)
  produces proposals from canonical-hint and lemma cues. Each rule emits a
  dedicated typed signal — `CanonicalHintMatchSignal`, `MinistryLemmaSignal`,
  `TreasuryLemmaSignal`, `MediaOutletLemmaSignal`,
  `PublicInstitutionLemmaSignal`, `GoverningBodyLemmaSignal` — carrying the
  specific trigger lemma/hint.
- `EntityContextScorer` (`pipeline_v2/scoring.py`) turns proposal signals
  into a prior `Assessment` (canonical hint → 0.95, 2+ lemma signals → 0.9,
  single lemma → 0.75).
- `ResolutionInferenceGraphBuilder._add_entity_context_variables` creates an
  `EntityContext(entity, tag) ∈ {false, true}` inference variable per
  proposal, with an `EVIDENCE_PRIOR` factor seeded by the scorer.
  `_add_entity_context_role_factors` then couples each
  `EntityContext(entity, tag)=TRUE` state to any `RoleFiller` state that
  binds that entity via a typed `CONSTRAINT` factor, with potentials taken
  from `EntityContextRolePolicy` keyed on `(tag, fact_kind, role)`.
- `ResolutionAssessmentMaterializer` writes an `EntityContextClaim` for
  every variable whose `TRUE` posterior is ≥ 0.5, with the assessment
  carrying the posterior, evidence, and trigger signals.

The legacy `ReportingSourceContextSignal`, `GenericOwnerContextSignal`, and
`GoverningBodyContextSignal` types are retired. The role-blind −0.85 case
in `BindingSignalWeightPolicy.contribution` is gone; tag-derived
suppression now lives in `EntityContextRolePolicy` as a per-(tag, fact_kind,
role) table that can express role-conditioned beliefs and **positive boosts**
(`PUBLIC_INSTITUTION` now boosts `public_employment.workplace` instead of
being dead).

`governance.py` and `public_money.py` no longer interpret tags: they read
`document.entity_context_proposals` directly when a producer-time routing
choice is needed (e.g. should an organization slot fill `ORGANIZATION` or
`CONTEXT`), and otherwise let the graph handle suppression.

JSON output exposes `entity_context_proposals` and `entity_context_claims`
arrays alongside the existing claim arrays. The flat `tags` field on each
entity is removed; consumers derive that view from the claims with
`claim.context_kind` and `claim.assessment.score`.

The `InferenceVariableKind.ENTITY_ATTRIBUTE` slot reserved on the inference
graph spec is finally load-bearing.

### 3. Funding distinctness follow-up

Fresh article runs exposed a generic failure mode:

- some `FUNDING` materializations still allowed the same resolved/same-surface
  organization to fill both `FUNDER` and `RECIPIENT`.

Fix:

- added a funding role-distinctness constraint in
  `pipeline_v2/inference/factor_builders.py`,
- generalized the previous contract-only distinctness helper into a shared
  entity-role overlap constraint,
- added a regression in `tests_v2/test_public_money.py`.

This is an inference-level fix rather than a post-hoc materialization filter.

## Fresh sampled articles

I reran the V2 pipeline on these inputs:

- `onet_totalizator_leca_glowy.html`
- `onet_wfosigw_lublin.html`
- `wp_zona_sekretarza_krasnik_20260513.html`
- `natemat_giermasinska.html`
- `wiadomosci.onet.pl__kraj__tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra__ezt8y9t.html`
- `oko_miliony_pajeczyna_rydzyka.html`
- `rp_tk_negative.html`
- `wp_meloni_negative.html`

## What improved

### Entity typing is now visible in output

The following classes now appear explicitly in JSON output instead of only
through stage-local lexical heuristics:

- `PAP`, `TVN`, `WP`, `Radio...` as `media_outlet`,
- `Skarbu Państwa`, ministries, and similar controller institutions as
  `generic_owner` and `public_institution`,
- `rada nadzorcza` as `governing_body`.

This is especially visible in:

- `...ezt8y9t.html`
- `onet_wfosigw_lublin.html`
- `wp_zona_sekretarza_krasnik_20260513.html`
- `onet_totalizator_leca_glowy.html`

### Controller/ministry handling is more principled

The governance stage no longer relies on scattered `"MAP"` /
`"ministerstwo ..."` string checks as its primary mechanism.

Inflected ministry mentions such as `Ministerstwa ...` are now handled through
token lemmas and shared classification, which is more robust for Polish case
variation.

### Self-funding noise dropped

In the Oko / Lux Veritatis article, the worst same-entity funder-recipient
artifact is gone.

The article still has other public-money issues, but the specific
`FUNDER == RECIPIENT` failure is now blocked at the inference level.

### Negative controls remain healthy

- `rp_tk_negative.html` stayed irrelevant / zero facts.
- `wp_meloni_negative.html` stayed irrelevant / zero facts.

## Remaining problems from the latest article runs

### 1. Governance still overfires on contextual people

This remains the largest open issue.

Examples:

- `...ezt8y9t.html`
  - `Dariusza Klimczaka` still appears as a weak governance appointee.
  - `Jan Grabiec` still appears as a weak dismissal target.
- `wp_zona_sekretarza_krasnik_20260513.html`
  - governance still mixes contextual office-holders with actual staffing
    targets in some clauses.

This is now mostly a **person-role binding** problem rather than an
organization-typing problem.

### 2. Governance still overfires in reporting/qualification sentences

Examples:

- `onet_totalizator_leca_glowy.html`
  - weak appointment/dismissal facts still appear around
    `Rafała Krzemienia` in discussion/reporting contexts.
- `...ezt8y9t.html`
  - tagged `PAP` is now visible as a media outlet, but the remaining weak
    governance noise is driven by sentence interpretation, not by missing org
    typing.

This suggests a next slice around **governance sentence filtering**:

- reporting verbs,
- commentary/qualification-process contexts,
- quoted or attributed discussion not describing the actual appointment event.

### 3. Parallel kinship remains broken

`natemat_giermasinska.html` still shows the classic parallel-kinship error:

- the sentence about `brata Eugeniusza Kłopotka oraz syna Stanisława
  Żelichowskiego` still cross-links the two politicians rather than anchoring
  two separate unnamed relatives.

This needs a dedicated nominal-kinship/proxy slice.

### 4. Governance vs public-employment boundary is still fuzzy

`natemat_giermasinska.html` still emits both:

- `governance_appointment`
- `public_employment`

for `Jacek Śmietanko`.

This points to a still-incomplete separation between:

- board/management appointment language,
- non-governance staffing language.

### 5. Public-money extraction still needs grouping cleanup

`oko_miliony_pajeczyna_rydzyka.html` still contains weaker artifacts such as:

- amount-only funding outputs,
- noisy public-money party pairing around `Lux Veritatis`,
- one remaining awkwardly grouped funder surface
  (`Fundacji Lux Veritatis, że 100 tys. zł`).

These are not the same bug as the removed self-funding artifact; they point to
party grouping and phrase-boundary issues upstream in `public_money.py`.

## Recommended next follow-up

The most valuable next slice is:

1. **sentence-internal person-role binding for governance**
   - distinguish appointee vs contextual minister / spokesperson / commentator,
   - use stronger trigger-local syntax and clause role checks,
   - demote quoted/reporting participants.

After that:

2. **governance sentence filtering**
   - suppress reporting / communication / qualification-process sentences.

Then:

3. **parallel kinship anchoring**
   - each kinship cue should anchor its own unnamed relative.

## Validation

The intended validation set for this slice is:

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check pipeline_v2 tests_v2
uv run pytest -c pytest-v2.ini -q
```

Final validation after this slice:

- `uv run ruff check pipeline_v2 tests_v2 --fix`
- `uv run ruff format pipeline_v2 tests_v2`
- `uv run ruff check pipeline_v2 tests_v2`
- `uv run ty check pipeline_v2 tests_v2`
- `uv run pytest -c pytest-v2.ini -q`

Current green state after the follow-up and report update:

- **162 passed**
