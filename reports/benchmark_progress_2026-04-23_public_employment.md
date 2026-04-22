# Benchmark Progress 2026-04-23: Public Employment, Kinship, and Anti-Corruption Coverage

## Run

- Command: `rm -f output/entity_registry.sqlite3 output/entity_registry.sqlite3-shm output/entity_registry.sqlite3-wal && uv run python main.py --input-dir inputs --glob '*.html' --output-dir output/benchmark_20260423_public_employment`
- Registry state: clean generated SQLite registry.
- Output directory: `output/benchmark_20260423_public_employment`
- Inputs processed: 26
- Relevant documents: 23
- Extracted facts: 334

## Improvements

- `wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe`
  is now relevant and reaches downstream extraction. It recovers `Centralne Biuro Antykorupcyjne`,
  `Gminy Ostrów`, and `Wójta`, but still emits `0` facts.
- Public-office role matching now covers `wójt`, `starosta`, `sekretarz powiatu`,
  `marszałek województwa`, and existing `wojewoda` variants.
- Public-employment extraction now emits frame-adjacent `APPOINTMENT` / `ROLE_HELD`
  facts for public institutions, using job labels in `role` and `value_text`.
- Kinship proxy coverage now includes `kuzyn`, `teść`, `szwagier`, `szwagierka`,
  `bratowa`, and `synowa`. Public-office anchor phrases like `mąż wojewody Moniki Jurek`
  now create a spouse proxy instead of rewriting employment directly onto the official.
- Person canonicalization now prefers observed proper-name surfaces over broken lemma stems for
  cases like `Agnieszka Królikowska`, `Szymon Ogłaza`, and `Joanna Pszczółkowska`.

## Target Article Notes

- AI42/Poczesna: relevant; recovers `Rafał Dobosz`, `Artur Sosna`, `Gminy Poczesna`,
  and cousin ties. It still lacks a hard public-employment fact for Dobosz.
- Dziennik Polski/Charsznica: relevant; emits `POLITICAL_OFFICE` for Tomasz Kościelniak as `Wójt`.
  Municipal employment remains incomplete.
- WP/Opole: relevant; public-employment facts now include:
  - `Agnieszka Królikowska -> Generalnego Opolskiego Urzędu Wojewódzkiego` as `Dyrektor`
  - `Mąż Wojewody Moniki Jurek -> Biurze Bezpieczeństwa Urzędu Marszałkowskiego Województwa Opolskiego`
    as `Główny Specjalista`
  The unrelated `Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie` target remains in a
  governance-frame fact, not the new public-employment path.
- Polsat/Ciechanów: relevant; recovers `Joanna Pszczółkowska`, `Sławomir Morawski`,
  `Sekretarz Powiatu`, `Starosta`, `Syn Pszczółkowski`, and `synowa` proxies.
  Public-employment facts for sons/daughter-in-law remain incomplete after suppressing noisy
  status clauses.

## Remaining Bottlenecks

- Anti-corruption investigation stories now pass relevance, but existing fact types still do not
  represent bribery/procurement investigation facts cleanly.
- Public-employment extraction is intentionally conservative after this pass; it avoids obvious
  quote/context overfires but misses some cross-clause and proxy employment statuses.
- Governance target resolution still sometimes confuses contextual organizations or role phrases
  with employment targets, notably in WP/Opole.
- `wiadomosci.onet.pl__lublin__...__cpw9ltt` remains filtered out as irrelevant.
- `rp_tk_negative` remains a relevance false positive with no downstream facts.
