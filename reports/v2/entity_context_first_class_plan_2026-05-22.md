# Plan: Make Entity Tags First-Class Facts In V2 Inference

## Context

`store.entity_tags: dict[EntityCandidateId, frozenset[EntityTag]]` is an ad-hoc
side dict populated by `EntityClassificationStage` and consumed by hard-coded
`entity_has_tag(...)` checks in `governance.py` and `public_money.py`. Those
checks emit three pre-baked negative `Signal`s (`ReportingSourceContextSignal`,
`GenericOwnerContextSignal`, `GoverningBodyContextSignal`) that the inference
weight policy collapses into a single −0.85 case in
`BindingSignalWeightPolicy.contribution`.

This violates several V2 principles documented in
`reports/v2/inference_end_goal_2026-05-22.md`:

- The end-goal doc explicitly lists `EntityContext(entity_id, context_kind)` as
  the legitimate way to model "media outlet / party organization / generic
  owner" and warns it "should not become an entity god-object field" — the
  current dict is exactly that.
- "No post-hoc materialization": tag membership is decided categorically with no
  visible alternative claims, no provenance, no posterior.
- "Typed factors with provenance": tags carry neither evidence ids nor signals
  explaining why they fired.
- `InferenceVariableKind.ENTITY_ATTRIBUTE` is already declared in
  `graph_spec.py:13` — the slot was reserved for this work and is currently
  unused.
- Polarity is hard-coded and role-blind. `Skarb Państwa` as
  `PUBLIC_EMPLOYMENT.WORKPLACE` is legitimate; the −0.85 case can't express
  role-conditioned beliefs. `PUBLIC_INSTITUTION` is computed but never read.

The intended outcome: tags become typed proposals → graph variables → claims
that participate in joint inference, with role-aware potentials and full
provenance. The three legacy signals retire; the −0.85 weight-policy case
disappears; consumers read claims instead of dict membership.

User decisions (already made):

- **Single end-state PR** (no transitional dual-write).
- **Existing 4 tag kinds only** (`MEDIA_OUTLET`, `GENERIC_OWNER`,
  `GOVERNING_BODY`, `PUBLIC_INSTITUTION`); `PUBLIC_INSTITUTION` is activated.
- **Per-(tag, fact_kind, role) potential table** for the
  EntityContext↔RoleFiller factor.

---

## Design

The new layering mirrors the existing entity/reference resolution stack:

```
LexicalEntityContextProducer  →  EntityContextProposal     (typed candidate)
                                          ↓
EntityContextScorer           →  prior Assessment
                                          ↓
ResolutionInferenceGraphBuilder  →  EntityContext variable + factors
                                          ↓
inference (pgmpy)              →  posterior marginal
                                          ↓
ResolutionAssessmentMaterializer →  EntityContextClaim     (typed decision)
                                          ↓
governance.py / public_money.py  →  entity_has_context_claim(...)
```

This matches the existing `EntityResolutionProposal → EntityResolutionClaim`
shape exactly. No new architectural patterns; we're plugging tags into the
patterns that already exist.

---

## Implementation

### 1. New typed records (`pipeline_v2/candidates.py`)

Add proposal + claim parallel to the existing resolution pair:

```python
@dataclass(frozen=True, slots=True)
class EntityContextProposal:
    entity_id: EntityCandidateId
    context_kind: EntityTag
    evidence_ids: tuple[EvidenceId, ...]
    retrieval_signals: tuple[Signal, ...] = ()
    context_signals: tuple[Signal, ...] = ()

@dataclass(frozen=True, slots=True)
class EntityContextClaim:
    id: EntityContextClaimId   # new id family in ids.py
    entity_id: EntityCandidateId
    context_kind: EntityTag
    evidence_ids: tuple[EvidenceId, ...]
    assessment: Assessment
    source: ProducerId
```

`EntityTag` enum moves verbatim from `types.py` (no value churn). Add
`EntityContextClaimId` to `ids.py` next to `ResolutionClaimId`.

### 2. Producer (`pipeline_v2/entity_classification.py`)

Rename `EntityClassificationStage` → `LexicalEntityContextStage`. Replace dict
mutation with `EntityContextProposal` emission. Each rule fires its own typed
signal that explains *why*:

- New signals in `types.py` (positive, info-bearing — no role bias):
  `MinistryLemmaSignal`, `TreasuryLemmaSignal`, `PublicInstitutionLemmaSignal`,
  `MediaOutletLemmaSignal`, `GoverningBodyLemmaSignal`.
- Each rule carries the triggering mention's `evidence_id` and the matched
  lemma (signal field `lemma: str`).
- One proposal per (entity, tag) — multiple rules for the same tag merge their
  signals/evidence.

The stage writes `document.entity_context_proposals: list[EntityContextProposal]`
(new field on `ArticleDocument`, parallel to `reference_resolution_proposals`).

### 3. Scorer (`pipeline_v2/scoring.py`)

Add `EntityContextScorer` paralleling `ReferenceResolutionScorer`. Maps proposal
signals → prior `Assessment.score`. Initial calibration:

- 1 trigger lemma → 0.75
- 2+ trigger lemmas → 0.9
- Canonical-hint match (e.g. "MAP", "Skarb Państwa") → 0.95

Scorer id: `ScorerId("lexical_entity_context_scorer_v2")`.

### 4. Store (`pipeline_v2/store.py`)

- **Remove** `entity_tags` dict (line 48) and `add_entity_tags()` (line 117).
- **Add** `entity_context_claims: dict[EntityContextClaimId, EntityContextClaim]`
  plus `entity_context_claim_ids_by_entity_id` index, mirroring
  `resolution_claims` / `resolution_ids_by_entity_id`.
- Add `add_entity_context_claim()`, `entity_context_claims_for_entity()`.

### 5. Inference graph (`pipeline_v2/inference/resolution.py`)

Extend `ResolutionInferenceGraphBuilder.build()`. New method
`_add_entity_context_variables`:

- Iterate `document.entity_context_proposals`.
- For each, create an `InferenceVariable` of kind `ENTITY_ATTRIBUTE` with
  states `(FALSE_STATE, TRUE_STATE)`. Variable id pattern:
  `entity-context:{entity_id}:{context_kind}`.
- Attach an `EVIDENCE_PRIOR` factor with potentials `(1 - score, score)` from
  the scorer, carrying `evidence_ids` and `signals` from the proposal.
- Register in `BuiltResolutionInferenceGraph.entity_context_variable_id_by_pair:
  dict[tuple[EntityCandidateId, EntityTag], InferenceVariableId]`.

New method `_add_entity_context_role_factors`:

- For each role variable in `fact_graph` and each candidate entity that fills
  one of its `RoleFillerState`s, look up the `EntityContext(entity, tag)`
  variable for tags relevant to this `(fact_kind, role)` per the policy table
  (next item).
- Build a two-variable `CONSTRAINT` factor `(EntityContextVar, RoleFillerVar)`
  whose potential when `EntityContext=TRUE` and the role filler equals this
  entity is the table value; everywhere else 1.0.
- Factor id: `factor:entity-context-role:{entity_id}:{context_kind}:{role_variable_id}`.

### 6. Role policy table (`pipeline_v2/inference/entity_context_policy.py`, new file)

```python
@dataclass(frozen=True, slots=True)
class EntityContextRolePolicy:
    table: Mapping[tuple[EntityTag, FactKind, EventRole], float]

    def potential(self, *, tag, fact_kind, role) -> float:
        return self.table.get((tag, fact_kind, role), 1.0)
```

Default policy (`DEFAULT_ENTITY_CONTEXT_ROLE_POLICY`):

| tag | fact_kind | role | potential | reason |
| --- | --- | --- | --- | --- |
| MEDIA_OUTLET | FUNDING | FUNDER | 0.05 | media is rarely a funder |
| MEDIA_OUTLET | FUNDING | RECIPIENT | 0.05 | media is rarely a beneficiary |
| MEDIA_OUTLET | PUBLIC_CONTRACT | COUNTERPARTY | 0.1 | |
| MEDIA_OUTLET | PUBLIC_CONTRACT | CONTRACTOR | 0.1 | |
| MEDIA_OUTLET | COMPENSATION | FUNDER | 0.05 | |
| GENERIC_OWNER | GOVERNANCE_APPOINTMENT | ORGANIZATION | 0.05 | "Skarb Państwa" not the appointer |
| GENERIC_OWNER | GOVERNANCE_DISMISSAL | ORGANIZATION | 0.05 | |
| GENERIC_OWNER | PUBLIC_EMPLOYMENT | WORKPLACE | 1.0 | legitimate employer — neutral |
| GOVERNING_BODY | GOVERNANCE_APPOINTMENT | ORGANIZATION | 0.05 | "rada nadzorcza" isn't the org |
| GOVERNING_BODY | GOVERNANCE_DISMISSAL | ORGANIZATION | 0.05 | |
| PUBLIC_INSTITUTION | PUBLIC_EMPLOYMENT | WORKPLACE | 1.5 | positive boost — ministries ARE workplaces |
| PUBLIC_INSTITUTION | GOVERNANCE_APPOINTMENT | ORGANIZATION | 1.3 | mild positive boost |

Potentials > 1.0 are allowed (pgmpy normalizes); they up-weight rather than
suppress. The default for unlisted combinations is 1.0 (no opinion). Keep the
table inspectable and short.

### 7. Claim materialization (`pipeline_v2/inference/resolution.py`)

Extend `ResolutionAssessmentMaterializer.materialize()` to write
`EntityContextClaim`s from `ENTITY_ATTRIBUTE` posteriors:

- Threshold: `posterior(TRUE) >= 0.5` → claim emitted with
  `assessment.score = posterior`.
- Below threshold → no claim (the variable still exists in the graph; absence
  of claim means "no high-confidence context").
- Claim source: `ProducerId("probabilistic_inference_stage_v2")`.

### 8. Consumer migration

**`pipeline_v2/governance.py`** (lines 632–637, 771–785) and
**`pipeline_v2/public_money.py`** (lines 333–336, 374–378):

- Stop emitting `GoverningBodyContextSignal`, `GenericOwnerContextSignal`,
  `ReportingSourceContextSignal`. The graph constraint factor does that work
  now.
- Remove `entity_has_tag` calls. The producers no longer condition role
  selection on tag membership — the graph handles it during inference.
- If governance still needs to *skip* generic-owner orgs when synthesizing
  proxy persons (a producer-stage decision, not an inference signal),
  introduce a small helper `entity_has_lexical_context_proposal(document,
  entity_id, tag) -> bool` that reads
  `document.entity_context_proposals` directly. This preserves the
  producer-time gating while keeping the dict gone.

**Retire**:

- `ReportingSourceContextSignal`, `GenericOwnerContextSignal`,
  `GoverningBodyContextSignal` classes (`types.py:815–826`).
- The `-0.85` case in `BindingSignalWeightPolicy.contribution`
  (`factor_builders.py:163–173`) that bundled these three. Re-check the
  bundle: `WeakSyntacticBindingSignal`, `AppointerContextSignal`,
  `ControllerContextSignal`, `PartyOrganizationSignal`, and
  `SelfTieContradictionSignal` stay in their own case at −0.85.
- `_has_reporting_source_signal` / `_has_owner_context_signal` helpers in
  `factor_builders.py:716–732` — find callers and either delete them or have
  them read context claims. (Quick grep needed during implementation.)
- `entity_classification.entity_has_tag` / `entity_tags` helpers — replaced by
  `entity_classification.entity_has_context_claim(store, entity_id, tag)`.

### 9. Document + output

`pipeline_v2/document.py`:

- Add `entity_context_proposals: list[EntityContextProposal]`.
- Add `entity_context_claims: dict[EntityContextClaimId, EntityContextClaim]`
  is already inside the store, but `ExtractionResult` should expose the
  claims tuple for parity with `materialized_fact_alternatives`.

`pipeline_v2/output.py`:

- Add `entity_context_proposals` and `entity_context_claims` arrays to the
  JSON output, shaped like `entity_resolution_claims`.
- **Remove** the `"tags"` field from `entity_to_json` (line 237). Consumers
  that want the old view derive it from
  `[claim.context_kind for claim in entity_context_claims if claim.entity_id == ...]`.
  This is a JSON-shape break; the report `fresh_article_review_2026-05-22.md`
  is the only document referencing tags in output and will be updated.

### 10. Runtime (`pipeline_v2/runtime.py`)

- Rename `EntityClassificationStage` reference to `LexicalEntityContextStage`.
- Position unchanged: still in `V2StagePhase.ENTITY_CANDIDATES` after NER.

### 11. Tests

Update / add in `tests_v2/`:

- `test_entity_classification.py` → assert that `entity_context_proposals`
  contains the expected proposals with `evidence_ids` populated; assert
  appropriate `*LemmaSignal` carries the trigger lemma.
- `test_inference_facade.py` — add `test_media_outlet_funder_role_is_suppressed_by_entity_context`
  (PAP as FUNDER → low role posterior), and
  `test_public_institution_workplace_role_is_boosted` (ministerstwo as
  WORKPLACE → higher posterior than a generic ORGANIZATION).
- `test_output_and_cli.py` — assert `entity_context_claims` array shape;
  remove `tags` assertions.
- Update / delete tests asserting `store.entity_tags` content directly.
- `tests_v2/test_governance.py`, `tests_v2/test_public_money.py` — replace
  `entity_has_tag` assertions with claim presence checks.

### 12. Documentation

Update `reports/v2/fresh_article_review_2026-05-22.md` Section 2 ("Shared
entity-tag classification") to describe the new claim-based shape. Add a new
"Phase: Entity Context As First-Class Facts" subsection to
`reports/v2/inference_end_goal_2026-05-22.md` noting that the
`EntityContext` variable family mentioned on line 82 is now realised.

---

## Critical files

Modify:

- `pipeline_v2/candidates.py` — `EntityContextProposal`, `EntityContextClaim`
- `pipeline_v2/ids.py` — `EntityContextClaimId`
- `pipeline_v2/types.py` — new lemma signals; retire 3 context signals
- `pipeline_v2/store.py` — drop tag dict, add claim store
- `pipeline_v2/entity_classification.py` — proposal-emitting stage
- `pipeline_v2/scoring.py` — `EntityContextScorer`
- `pipeline_v2/document.py` — proposal list field
- `pipeline_v2/inference/resolution.py` — variables, role-coupling factors,
  claim materialization
- `pipeline_v2/inference/entity_context_policy.py` — **new**, role policy table
- `pipeline_v2/inference/factor_builders.py` — drop −0.85 case for retired
  signals; cleanup helpers
- `pipeline_v2/governance.py`, `pipeline_v2/public_money.py` — consumer
  migration
- `pipeline_v2/runtime.py` — stage rename
- `pipeline_v2/output.py` — JSON shape
- Tests as listed in §11

Pattern reuse:

- `EntityResolutionProposal` / `EntityResolutionClaim` shape
  (`candidates.py:171–196`).
- `_add_reference_resolution_variables` for the variable+prior-factor pattern
  (`resolution.py:208–269`).
- `_add_reference_role_factors` for the constraint-factor coupling pattern
  (`resolution.py:368–421`).
- `ResolutionAssessmentMaterializer` posterior→claim writeback (existing
  pattern for reference resolution claims).

---

## Verification

```bash
uv run ruff check pipeline_v2 tests_v2 --fix
uv run ruff format pipeline_v2 tests_v2
uv run ruff check pipeline_v2 tests_v2
uv run ty check pipeline_v2 tests_v2
uv run pytest -c pytest-v2.ini -q
```

End-to-end article check on a representative sample:

```bash
uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir output
```

Manual verification (use the articles from the fresh-article review):

- `...ezt8y9t.html`: `PAP` appears as `EntityContextClaim(context_kind=MEDIA_OUTLET)`
  with score > 0.7; if a funding event tries to bind `PAP` as FUNDER, the role
  posterior drops below 0.05.
- `onet_wfosigw_lublin.html`: `Ministerstwo …` produces a `PUBLIC_INSTITUTION`
  claim; `PUBLIC_EMPLOYMENT.WORKPLACE` binding to that ministry receives a
  higher posterior than a baseline (uncalibrated) ORGANIZATION competitor.
- `wp_zona_sekretarza_krasnik_20260513.html`: `Skarb Państwa` shows
  `GENERIC_OWNER` and `PUBLIC_INSTITUTION` claims simultaneously; appointment
  org binding is suppressed (governance-org constraint) while a hypothetical
  employment binding remains plausible.
- Negative controls (`rp_tk_negative.html`, `wp_meloni_negative.html`) stay
  zero-fact.

Inspect a few output JSONs to confirm:

- `entity_context_proposals` and `entity_context_claims` arrays appear.
- Each claim carries `assessment.score`, `evidence_ids`, and matching
  `signals`.
- The old `tags` field on each entity is gone.
- No `ReportingSourceContextSignal` / `GenericOwnerContextSignal` /
  `GoverningBodyContextSignal` remain on any binding.
