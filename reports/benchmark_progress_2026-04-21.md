# Benchmark Progress 2026-04-21

Clean-registry batch run:

- Removed `output/entity_registry.sqlite3`, `output/entity_registry.sqlite3-shm`, and
  `output/entity_registry.sqlite3-wal` before running.
- Command: `uv run python main.py --input-dir inputs --glob "*.html" --output-dir output`
- Model assets were checked first with `uv run python scripts/setup_models.py`.

## What Changed

- Added document-level extraction context for bounded sentence-window lookup.
- Governance frame extraction now carries person, role, target organization, owner context, and
  evidence across adjacent sentences/paragraphs instead of relying only on one clause.
- Mention provenance now keeps `start_char`, `end_char`, and `paragraph_index` from NER through
  clustering, with a sentence-text fallback for coreference/manual mentions.
- Inflected party aliases such as `Polskiego Stronnictwa Ludowego` resolve to the canonical party.
- Added adjacent-sentence party-profile extraction for headline-style party context followed by a
  person sentence.
- Suppressed `przekazać` funding frames without an amount unless the clause has explicit grant or
  subsidy language.

## Checked Articles

- `pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni`
  now emits 3 facts:
  - `A. Góralczyk -> APPOINTMENT -> Stadnina Koni Iwno Sp.`, role `Prezes`
  - `Przemysław Pacie -> DISMISSAL -> Stadnina Koni Iwno Sp.`, role `Prezes`
  - `A. Góralczyk -> PARTY_MEMBERSHIP -> Polskie Stronnictwo Ludowe`
- Strong governance positives still emit governance output:
  - `onet_totalizator`: 31 facts, including appointment/dismissal facts
  - `radomszczanska`: 6 facts, including appointment and compensation
  - `olsztyn.tvp`: 1 appointment fact
  - `wiadomosci.onet.pl__...ezt8y9t`: 23 facts, including Natura Tour governance output
  - `zona-posla-pis`: 10 facts
- Salary/funding positives still emit:
  - `olsztyn_wodkan`: 5 compensation facts
  - `niezalezna_polski2050_synekury`: KZN compensation still present
  - `oko_miliony_pajeczyna_rydzyka`: 6 facts, including WFOŚiGW and JZR funding facts
- True negatives:
  - `olsztyn_roosevelta_negative`: irrelevant, 0 facts
  - `wp_meloni_negative`: irrelevant, 0 facts
  - `rp_tk_negative`: still relevance-positive, but 0 facts

## Regressions / Remaining Issues

- Pleszew person and organization normalization is still imperfect:
  `Przemysław Pacia` canonicalizes as `Przemysław Pacie`, and the target is
  `Stadnina Koni Iwno Sp.` rather than the cleaner `Stadnina Koni Iwno`.
- `KOWR` is no longer used as an appointment target, but owner/controller context for Pleszew is
  currently represented mainly through `Skarbu Państwa`; fuller KOWR owner context still depends on
  longer-range context modeling.
- Some older noisy governance/person merges remain visible outside this change, especially in
  Totalizator-style long articles.
- `wiadomosci.onet.pl__lublin__...cpw9ltt` remains filtered out as irrelevant, unchanged by this
  extraction-focused refactor.
- `oko_miliony_pajeczyna_rydzyka` still has two amountless funding facts from grant/subsidy or
  `wyłożyć` contexts; the communication-style `przekazać` no-amount false positives are gone from
  the final batch run.

## Dziennik Zachodni Bytom CBA Fixture

Added archived benchmark input:

- `inputs/dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383.html`
- Archived source:
  `https://web.archive.org/web/20230923073103/https://dziennikzachodni.pl/nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zapowiedzieli-ze-zloza-zawiadomienie-do-cba-o-mozliwosci-popelnienia-przestepstwa/ar/c1-16375383`

Single-article clean-registry check:

- Removed `output/entity_registry.sqlite3`, `output/entity_registry.sqlite3-shm`, and
  `output/entity_registry.sqlite3-wal` first.
- Command: `uv run python main.py --html-path inputs/dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383.html --document-id dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383 --source-url "https://web.archive.org/web/20230923073103/https://dziennikzachodni.pl/nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zapowiedzieli-ze-zloza-zawiadomienie-do-cba-o-mozliwosci-popelnienia-przestepstwa/ar/c1-16375383" --output-dir output/dziennikzachodni_bytom_check`
- Output:
  `output/dziennikzachodni_bytom_check/dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383.json`
- Relevance: `true`, score `1.0`.
- Relevance reasons include `CBA` and `Centralne Biuro Antykorupcyjne`.
- `Centralne Biuro Antykorupcyjne` is extracted as a `PublicInstitution`.
- Key entities present include `Maciej Bartków`, `Bartłomiej Wnuk`, `Mariusz Wołosz`,
  `Wnuk Consulting`, `Gminę Bytom`, `PEC Bytom`, `Bytomskim Przedsiębiorstwie
  Komunalnym Sp.`, `Prawo i Sprawiedliwość`, and `Centralne Biuro Antykorupcyjne`.
- Current facts after the public-contract/referral pass: 14 total.
- Newly recovered:
  - `ANTI_CORRUPTION_REFERRAL`: `Prawo i Sprawiedliwość` -> `Centralne Biuro Antykorupcyjne`
    from the bytomscy-radni/PiS CBA-notification sentence.
  - `ANTI_CORRUPTION_REFERRAL`: `Maciej Bartków` -> `Centralne Biuro Antykorupcyjne`
    from the "złożyć zawiadomienie do CBA" sentence.
  - `PUBLIC_CONTRACT`: `Wnuk Consulting` -> Bytom/city-context cluster and `PEC Bytom`,
    both carrying `397 496,95 zł`.
  - `PERSONAL_OR_POLITICAL_TIE`: `Mariusz Wołosz` -> `Bartłomiej Wnuk`, relationship
    `collaborator`, from the owner/operator context around the long quoted sentence.
- Remaining misses/weak spots:
  - The city counterparty is still canonically noisy as `Bytomski` because Bytom/BPK/city
    mentions are over-clustered.
  - The second contract amount `241 559,70 zł` for the employee-run firm and BPK is still not
    split into a separate contract frame.
  - `Wnuk Consulting` is still duplicated as a weak derived `Person` entity, though the recovered
    tie now points to `Bartłomiej Wnuk`, not the company-like person duplicate.

## Next Bottleneck

The next useful step is contract-clause splitting plus entity hygiene in long articles: separate
multiple contract/amount groups in one sentence, then clean Bytom/BPK city clustering and suppress
company-like derived person candidates.
