# V2 article regression follow-up — 2026-05-20

## Scope

This note records the follow-up after the multi-input V2 batch that exposed:

- public-money / compensation articles falling out at relevance,
- a tribunal/legal article staying falsely relevant,
- malformed party-support / tie output,
- underspecified governance candidates on strong positives.

The changes in this slice were validated with:

- `uv run ruff check pipeline_v2 tests_v2 --fix`
- `uv run ruff format pipeline_v2 tests_v2`
- `uv run ruff check pipeline_v2 tests_v2`
- `uv run ty check pipeline_v2 tests_v2`
- `uv run pytest -c pytest-v2.ini -q`

Current full V2 test status after this slice:

- **93 passed**

## What changed

### 1. Relevance hardening

`pipeline_v2/relevance.py` now:

- separates **funding** and **compensation** term families instead of treating all money context the same;
- uses token-aware prefix/phrase matching instead of raw substring matching;
- narrows anti-corruption cues so generic political wording does not create anti-corruption relevance by itself;
- applies a stronger legal/procedural cap so tribunal / court-procedure articles do not survive on generic appointment or wage language alone.

### 2. Party/tie hardening

- candidacy-style `POLITICAL_SUPPORT` now resolves its supported target from **people only**, so the party entity can no longer self-link as both subject and object;
- explicit patronage ties now require **observed people**, which removes person→party, org→role, and other malformed tie output that had leaked through before.

### 3. Governance completeness hardening

`pipeline_v2/governance.py` is now more conservative:

- organization / role fallback no longer looks forward into the next sentence;
- party-like and role-like "organizations" are filtered out as governance targets;
- person-only appointments are dropped instead of surfacing as if they were complete governance facts.

## Article-derived regression fixtures added

New article-style behavior tests now cover:

1. compensation-positive article behavior (`olsztyn_wodkan`-style),
2. funding-positive article behavior (`oko_miliony_pajeczyna_rydzyka`-style),
3. tribunal/legal negative behavior (`rp_tk_negative`-style),
4. a strong governance-positive control (`onet_totalizator`-style).

These live alongside focused unit tests for:

- party support target selection,
- patronage ties requiring person/person structure,
- governance ignoring following-sentence background organizations,
- governance ignoring party-like organization arguments,
- governance dropping person-only appointments.

## Representative batch outcome

The representative five-input batch was rerun on:

- `onet_totalizator.html`
- `oko_miliony_pajeczyna_rydzyka.html`
- `olsztyn_wodkan.html`
- `wiadomosci.onet.pl__lublin__...__cpw9ltt.html`
- `rp_tk_negative.html`

### Improved

- **`olsztyn_wodkan`** stays relevant and now emits compensation output.
- **`oko_miliony_pajeczyna_rydzyka`** stays relevant and emits funding / contract output.
- **`rp_tk_negative`** now drops out at relevance and emits no downstream facts.
- malformed party self-links and non-person patronage ties observed in the earlier batch no longer survive.
- governance output on strong positives no longer uses party names or role-like NER spans as organization arguments.

### Remaining rough edges

- strong positives like `onet_totalizator` and the Lublin WFOŚiGW article are cleaner, but still somewhat **overproducing**:
  - weak collective `POLITICAL_SUPPORT` still appears,
  - some governance facts remain role-only rather than fully grounded with an organization.

## Practical status after this slice

Compared with the earlier batch, the main regression class is fixed:

- **false negatives on compensation/funding articles**: fixed in the checked batch,
- **tribunal/legal false positive**: fixed in the checked batch,
- **worst malformed party/tie/governance shapes**: reduced materially.

The next highest-value V2 work is no longer broad relevance triage. It is likely:

1. further reducing weak collective political-context output on strong positives,
2. improving organization grounding for role-only governance cases that are still directionally correct but incomplete.
