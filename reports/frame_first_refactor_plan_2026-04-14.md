# Frame-First Refactor Plan - 2026-04-14

## Summary

The current extraction architecture does not scale well for the benchmark class this project cares about. The recurring failures are structural, not just heuristic:

- governance facts still confuse real targets with owners, supervisors, bodies, and parties
- canonicalization happens too late, after low-quality facts have already been emitted
- sentence-level fact extraction over a document-level candidate graph is too weak for clauses that contain appointee, role, target organization, owner context, governing body, and political context together

The next step should be a deeper refactor toward a **frame-first extraction architecture**. The new internal source of truth should be:

- entity clusters
- clause-local governance/funding/compensation frames

Facts, relations, and events should become derived outputs from those internal frames.

## Key Changes

### 1. Add an early entity-clustering stage

Insert a new document-level stage after NER/coref and before relation extraction.

This stage should build canonical clusters for:

- people:
  - nominative full name
  - inflected full name
  - surname-only mentions
  - initial + surname mentions
- organizations and public institutions:
  - acronym + expanded form
  - inflected forms
  - quoted/unquoted variants
  - owner/supervisor mentions linked but not merged into the same target
- political parties:
  - alias + canonical full name
  - inflected forms
  - coalition/committee phrases only when syntactically party-like
- positions:
  - role/title mentions that should be reused downstream

Cluster signals should come from:

- normalized surface form
- lemma signature
- acronym compatibility
- apposition/title structure
- paragraph-local compatibility
- person coref chains only for people

Important rule:

- owner/controller entities must not be merged with the actual target company/institution
- governing bodies like `rada nadzorcza` or `zarząd` must stay separate context clusters

This stage becomes the source of truth for downstream extraction. Downstream logic should work on cluster ids, not raw entity ids.

### 2. Replace direct governance fact extraction with clause-level governance frames

Keep whole-document parsing, but stop emitting `APPOINTMENT` / `DISMISSAL` directly from pooled sentence candidates.

Introduce:

- `ClauseUnit`
- `GovernanceFrame`

`ClauseUnit` should represent one parser-backed local extraction unit:

- a sentence may yield multiple clause units
- each clause keeps:
  - trigger head
  - local token span
  - cluster mentions inside the clause
  - sentence/paragraph indices

`GovernanceFrame` should resolve these slots explicitly:

- `person_cluster_id`
- `event_type`: appointment, dismissal, resignation, role_change
- `role_cluster_id | None`
- `target_org_cluster_id | None`
- `owner_context_cluster_id | None`
- `governing_body_cluster_id | None`
- `appointing_authority_cluster_id | None`
- `confidence`
- `evidence`

Frame construction rules:

- resolve appointee/removed person from dependency structure, not nearest person
- support object-appointee structures like `powołuje go`
- resolve role from apposition, predicative complement, or governed title phrase
- resolve target organization from the role-owned phrase first
- keep owner/controller context in a separate slot
- keep governing body in a separate slot
- allow paragraph carryover only when the next clause clearly continues the same person-role-target tuple

This is the general fix for the repeated benchmark failures:

- `AMW Rewita` vs `AMW`
- `Natura Tour` vs `PKP`
- `Stadnina Koni Iwno` vs `KOWR` / `Skarbu Państwa`
- `WFOŚiGW` vs `rada`
- `WTC Poznań` vs `PO`

### 3. Add an explicit organization target resolver

Replace the current pooled scoring approach with a dedicated target resolver for governance frames.

Target precedence:

1. organization cluster directly attached to the role phrase
2. organization cluster in the same clause as the trigger
3. organization cluster continued in the same paragraph
4. owner/controller context only as metadata, not as target

General penalties:

- parties as targets
- `Skarbu Państwa`
- ministries/supervisors when the supervised company is named
- umbrella parents when the subsidiary is named
- governing bodies as main targets
- location-only phrases
- publisher/media entities

General bonuses:

- company/institution cluster attached to the role phrase
- full expanded organization mention over a short generic alias
- cluster already attached to role context in the same clause
- specific subsidiary/company over umbrella parent

Owner/controller context and governing body should still be preserved on the frame, but never steal the main target slot when the real target is present.

### 4. Split governance extraction from profile extraction

Keep party/profile/funding coverage, but stop letting profile logic compete with governance resolution inside the same clause.

Refactor extractors into:

- primary frame extractors:
  - governance
  - funding
  - compensation
- secondary annotation extractors:
  - party membership
  - political office
  - candidacy
  - personal/political ties

Rules:

- governance frames run first
- profile facts are allowed only when they are syntactically tight to a person cluster
- if a strong governance frame exists in a clause, broad political context must not create extra party facts for nearby people
- candidacy requires explicit election context
- office facts should not be emitted as generic background spam unless they support governance or tie interpretation

This is the main fix for:

- `WFOŚiGW`
- `Totalizator`
- `WP / rady nadzorcze`
- `TVN24`
- `Niezależna`

### 5. Make facts, relations, and events derived views

Keep the top-level JSON output stable, but change internal truth ownership.

Internal source of truth:

- entity clusters
- governance/funding/compensation/tie frames

Derived outputs:

- `facts`
- `relations`
- `events`

Specific changes:

- `APPOINTMENT` / `DISMISSAL` facts should be derived from `GovernanceFrame`
- `EventExtractor` should derive events from governance frames instead of reinterpreting facts independently
- `APPOINTED_TO`, `DISMISSED_FROM`, `HOLDS_POSITION`, `MEMBER_OF_BOARD` should be generated from the same accepted frames
- owner/controller/body metadata should flow from the frame into facts/events as typed attributes

This removes the current semantic duplication between relation extraction and event derivation.

### 6. Restructure the pipeline around the new data flow

Target internal flow:

1. preprocess
2. relevance filter
3. segment
4. NER
5. coref
6. entity clustering
7. syntax parse -> clause units
8. frame extraction
9. derived facts / relations / events
10. entity linking
11. scoring
12. output

Important constraint:

- keep the current CLI and output contract stable
- keep the current runtime architecture stable for now:
  - whole-document spaCy NER
  - whole-document Stanza syntax
  - Stanza coref with per-article reset
- do not redesign runtime while doing the quality refactor

## Public Interfaces / Internal Types

Keep top-level JSON unchanged:

- `entities`
- `facts`
- `relations`
- `events`
- `graph`

Add internal models:

- `EntityCluster`
- `ClusterMention`
- `ClauseUnit`
- `GovernanceFrame`
- optionally `FundingFrame`
- optionally `CompensationFrame`

Keep typed metadata fields already introduced:

- `owner_context_entity_id`
- `appointing_authority_entity_id`
- `governing_body_entity_id`

These should be populated from frames rather than rediscovered later.

## Test Plan

### Structural tests

- inflected full-name + surname-only + initial forms collapse to one person cluster
- acronym + expanded institution collapse to one organization cluster
- owner/supervisor entities remain separate from target clusters
- governing bodies remain separate context clusters
- parties never become governance targets

### Governance-frame tests

- appositive role + company extraction
- object-appointee extraction for `powołuje go`
- appointment with target + owner context
- dismissal with governing body + target org
- umbrella parent loses to subsidiary when both are named
- `Skarbu Państwa` loses to named company target
- `KOWR` stays owner context when stadnina is the target

### Benchmark regression tests

- `Radomszczańska`: `Marek Rząsowski -> AMW Rewita -> Wiceprezes`
- `WFOŚiGW`: `Mazur -> WFOŚiGW -> prezes`, `Kloc -> WFOŚiGW -> wiceprezes`, `Kruk/Pokwapisz` dismissals
- `Natura Tour`: `Natura Tour` beats `PKP`
- `Pleszew24`: `Stadnina Koni Iwno` beats `KOWR` and `Skarbu Państwa`
- `TVP Olsztyn`: preserve the current `Jarosław Słoma` appointment
- `RP / Klich`: recover at least one governance frame into the WAM-related company path
- `Do Rzeczy / AMW`: preserve the `Dyrektor AMW` appointment, PSL affiliation, and Kosiniak-Kamysz tie
- `OKO.press`: preserve useful funding facts while reducing bogus political-profile noise

### Acceptance criteria

- hard benchmark cases stop failing for the same structural reason across different articles
- governance targets are mostly specific institutions/companies rather than owners/parties/bodies
- duplicate and inflected person/organization entities visibly decrease
- party/profile overfire no longer dominates governance-heavy articles
- current output contract and runtime behavior remain stable

## Assumptions

- This should be implemented as a staged refactor, not a big-bang rewrite.
- Recommended stage order:
  1. entity clustering + clause units
  2. governance frames + derived relations/events
  3. profile/funding extractors adapted to clusters/frames
- YAML should remain thin; extraction behavior stays in typed code.
- No site-specific extractors and no benchmark-specific hacks.
