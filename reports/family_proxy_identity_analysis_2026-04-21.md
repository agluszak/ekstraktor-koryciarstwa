# Family Proxy Identity Analysis - 2026-04-21

This note records the current behavior after tightening family-proxy identity,
person canonicalization, party/object linking, and quote-speaker attribution.

Commands run:

```bash
uv run python scripts/setup_models.py
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest

rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --html-path inputs/zona-posla-pis.html --document-id zona-posla-pis --output-dir output/zona_check

curl -L --fail --silent --show-error \
  'https://emkielce.pl/miasto-4/zarzuty-o-nepotyzm-i-ostre-personalne-spory-w-kieleckim-ratuszu-80925' \
  -o /tmp/koryciarstwo-analysis/emkielce-80925.html
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --html-path /tmp/koryciarstwo-analysis/emkielce-80925.html \
  --document-id emkielce-80925 \
  --source-url 'https://emkielce.pl/miasto-4/zarzuty-o-nepotyzm-i-ostre-personalne-spory-w-kieleckim-ratuszu-80925' \
  --output-dir output/emkielce_check

rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
```

All article checks and the full batch benchmark above were run from a clean generated
SQLite registry.

## `zona-posla-pis`

Output files:

- `output/zona_check/zona-posla-pis.json`
- `output/zona-posla-pis.json`

Headline result after the focused clean-registry run:

- relevant: `true`
- facts: `10`
- identity hypotheses: `1`

Fixed behavior:

- `Renata Stefaniuk`, `Dariusz Stefaniuk`, and surname-only `Stefaniuk` remain separate
  person entities.
- `Dariusz Stefaniuk` and `Dariusza Stefaniuka` still merge as one lemma-compatible full
  name.
- Ambiguous surname-only `Stefaniuk` does not hard-merge into either full-name person.
- The previous bad dismissal facts
  `Dariusz Stefaniuk -> Enea Połaniec/Jelcz` are gone.
- The output keeps a conservative proxy dismissal:
  `Moja Żona -> Enea Połaniec` with `DISMISSAL`.
- The resolver emits `Moja Żona -> Dariusz Stefaniuk` as a family tie and keeps
  `Moja Żona <-> Renata Stefaniuk` as a `possible` identity hypothesis rather than
  rewriting facts onto Renata.
- `Dariusz Stefaniuk -> Prawo i Sprawiedliwość` is present with a `PoliticalParty`
  object.

Remaining caveats:

- The direct Renata dismissal target still collapses the coordinated target wording to
  one organization entity in the JSON display (`Enea Połaniec`), so target splitting for
  `Enea Połaniec i Jelcz` remains a separate extraction-quality issue.
- A low-confidence `Renata Stefaniuk -> Prawo i Sprawiedliwość` party fact is still
  emitted from the sentence containing `żona posła PiS`; this is a party-support
  precision issue, not an identity merge.

## eM Kielce Article

Source:

- `https://emkielce.pl/miasto-4/zarzuty-o-nepotyzm-i-ostre-personalne-spory-w-kieleckim-ratuszu-80925`

Output file:

- `output/emkielce_check/emkielce-80925.json`

Headline result:

- title: `Zarzuty o nepotyzm i ostre personalne spory w kieleckim Ratuszu`
- relevant: `true`
- facts: `12`
- identity hypotheses: `1`

Recovered family proxy entities:

- `Żona Karola Wilczyńskiego`
  - `is_proxy_person: true`
  - `kinship_detail: spouse`
  - `proxy_anchor_entity_id`: `Karol Wilczyński`
- `Siostra Pana Przewodniczącego`
  - `is_proxy_person: true`
  - `kinship_detail: sibling_sister`
  - `proxy_anchor_entity_id`: `Karol Wilczyński`
- `Moja Partnerka`
  - `is_proxy_person: true`
  - `kinship_detail: partner`
  - `proxy_anchor_entity_id`: `Karol Wilczyński`

Identity hypothesis recovered:

- `Żona Karola Wilczyńskiego` <-> `Moja Partnerka`
- status: `probable`
- confidence: `0.78`
- reason: `same_anchor_compatible_family_proxy`

Fixed behavior:

- `Żona Karola Wilczyńskiego -> Radio Kielce` is now the appointment/employment subject,
  not `Karol Wilczyński`.
- `Siostra Pana Przewodniczącego -> Miejski Urząd Pracy` is the director appointment
  subject, not `Karol Wilczyński`.
- `Karol Wilczyński -> Koalicja Obywatelska` is present as `PARTY_MEMBERSHIP`, and the
  object resolves to a `PoliticalParty` entity.
- The previous bad party object contamination where the object displayed as
  `Muzeum Wsi Kieleckiej` is fixed.
- Possessive quote proxies are speaker-owned. The later `moja żona` proxy is anchored to
  the detected quote speaker `Marcin Stępniewski`, not to the nearest unrelated person.

Remaining caveats:

- The article is allegation/quote-heavy. Facts still need richer quoted/allegation
  metadata before they should be interpreted as clean confirmed appointment claims.
- The later `Marcin Stępniewski -> moja żona` proxy may be locally correct as quote
  ownership, but its downstream relevance should remain conservative.

## Full Clean-Registry Batch

Command:

```bash
rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
```

Batch result highlights:

- `zona-posla-pis`: relevant `true`, facts `10`.
- `pleszew24...stadniny-koni`: relevant `true`, facts `3`.
- `onet_totalizator`: relevant `true`, facts `31`.
- `radomszczanska...nowy-zaciag`: relevant `true`, facts `7`.
- `olsztyn_wodkan`: relevant `true`, facts `10`.
- `oko_miliony_pajeczyna_rydzyka`: relevant `true`, facts `7`.
- `olsztyn_roosevelta_negative`: relevant `false`, facts `0`.
- `wp_meloni_negative`: relevant `false`, facts `0`.

Known benchmark issues still present:

- `wiadomosci.onet.pl__lublin__...__cpw9ltt` remains filtered out as irrelevant.
- `rp_tk_negative` remains a relevance false positive, though downstream facts stay empty.
- Funding and party-support precision remain separate follow-up areas.
