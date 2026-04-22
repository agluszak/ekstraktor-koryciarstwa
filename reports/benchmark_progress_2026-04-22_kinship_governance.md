# Benchmark Progress: Kinship And Governance Cleanup (2026-04-22)

## Scope

This snapshot records the cleanup of two extraction-quality issues:

- governance target selection now separates staffed entities from owner/controller/body context before choosing `target_org`
- kinship facts now use bounded apposition/proxy/identity evidence instead of unbounded cross-sentence person pairing

No new public fact types were added. The output contract still uses `APPOINTMENT`, `DISMISSAL`, `PARTY_MEMBERSHIP`, and `PERSONAL_OR_POLITICAL_TIE` with existing context fields.

## Implementation Notes

- `pipeline/governance.py`
  - Added `GovernanceOrgRoleEvidence` scoring for staffed target, owner context, governing body, and appointing authority evidence.
  - Staffed-target cues include local phrases such as `do rady nadzorczej spółki X`, role/org proximity, and target-like company names.
  - Owner/body/authority evidence is retained as context and penalized as a primary target when a staffed target is available.

- `pipeline/frames.py`
  - Stopped treating person `appos` mentions as appointing authorities.
  - Added an object-pronoun appointment branch so sentences like `Tusk powołuje go...` keep the previous appointee as subject rather than the current sentence speaker/authority.

- `pipeline/relations/service.py`
  - Replaced `_cross_sentence_kinship_ties` with `KinshipTieBuilder`.
  - Direct same-sentence kinship apposition now emits typed family facts, e.g. `Sylwia Sobolewska -> SPOUSE -> Krzysztof Sobolewski`.
  - Identity-hypothesis-backed proxy ties remain bounded to probable/confirmed hypotheses and same/adjacent paragraph evidence.

## Targeted Clean-Registry Check

Commands:

```bash
uv run python scripts/setup_models.py
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --input-dir output/target_kinship_inputs --glob "*.html" --output-dir output/target_kinship_governance
```

The temporary target input directory contained:

- `wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie__7273798906222848a.html`
- `zona-posla-pis.html`
- `pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni.html`

Observed results:

- WP Lubelskie Koleje:
  - `Sylwia Sobolewska -> APPOINTMENT -> Lubelskie Koleje`
  - `owner_context_entity_id -> Województwo Lubelskie`
  - `Sylwia Sobolewska -> PERSONAL_OR_POLITICAL_TIE/SPOUSE -> Krzysztof Sobolewski`
  - `Krzysztof Sobolewski -> PARTY_MEMBERSHIP -> Prawo i Sprawiedliwość`

- Old Onet `zona-posla-pis`:
  - `Renata Stefaniuk -> PERSONAL_OR_POLITICAL_TIE/SPOUSE -> Dariusz Stefaniuk`
  - dismissal output remains present; both named Renata and the existing `Moja Żona` proxy appear in dismissal evidence

- Pleszew Stadnina:
  - `A. Góralczyk -> APPOINTMENT -> Stadnina Koni Iwno Sp.`
  - `Przemysław Pacia -> DISMISSAL -> Stadnina Koni Iwno Sp.`
  - `A. Góralczyk -> PARTY_MEMBERSHIP -> Polskie Stronnictwo Ludowe`
  - `KOWR` / `Skarb Państwa` remain context rather than appointment targets

## Tests

Verification completed:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Final pytest result: `129 passed, 1 xfailed`.

## Remaining Notes

- WP still emits extra noisy governance facts later in the article, including historical/supporting appointments. The fixed hard benchmark assertions cover the core expected current Lubelskie Koleje finding, not the older Orlen / Port Lotniczy / remuneration TODOs.
- The old Onet `zona-posla-pis` article still carries both named and proxy dismissal evidence. That is acceptable for this pass because the spouse tie is now typed and the prior hard-merge issue is not reintroduced.
