# Benchmark Full Report - 2026-05-13

## Commands

```bash
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
uv run python main.py --input-dir inputs --glob "*.html" --output-dir output
```

## Run context

- Date checked: 2026-05-13
- Batch mode: warm `inputs/*.html` run
- Output state: current pipeline writes per-document JSON files only; no SQLite registry artifact is produced.

## What improved

1. **WP Kraśnik uncertainty trail is now explicit and preserved in final output.**
   - `Michał Stawiarski -> child_son -> Stawiarski` now carries `possible_entity_matches: [Jarosław Stawiarski]`.
   - The output also includes `entity_resolution_hypotheses` for `Stawiarski <-> Jarosław Stawiarski` instead of hard-merging.
   - `MOPS` and `MOSiR w Kraśniku` remain separate entities.
   - The `10 189,50 Zł Brutto` compensation fact is attached to Magdalena Skokowska rather than Piotr Janczarek.
   - The lower-case `razem` / `PO` leakage called out in the article-specific report was not reproduced in the current output.
   - The main person canonical is now `Magdalena Skokowska`; the earlier `Magdalen Skokowski` / broken spouse proxy canonicals are gone.

2. **The previously weak Onet Lublin article is no longer filtered out.**
   - `wiadomosci.onet.pl__lublin__...__cpw9ltt` is now relevant and emits appointment/dismissal output.
   - This closes one of the most important known failures from the earlier benchmark notes.

3. **The previously empty Pleszew article now emits governance facts with readable names.**
   - `pleszew24.info__...stadniny-koni` is relevant and now produces `APPOINTMENT` plus `DISMISSAL`.
   - `Przemysław Pacia` now survives as the dismissal subject instead of degrading to `Przemysław Pata`.

4. **Political-profile noise is materially lower in one of the worst offenders.**
   - `businessinsider_kadrowa_czystka_panstwowa_spolka` no longer emits the earlier flood of supervisory-board `ELECTION_CANDIDACY` false positives.
   - Current output there is down to governance + office facts, which is much closer to the article shape.

5. **The Olsztyn salary article no longer leaks a fake funding fact.**
   - `olsztyn_wodkan` still emits `COMPENSATION`, but the weak `FUNDING` fact from the salary-burden clause is gone.
   - Role-only `Prezes` compensation subjects remain removed.

6. **Benchmark regressions introduced during the canonicalization pass were fixed before the final rerun.**
   - `ai42...czy-wojt-ukrywa-nepotyzm` again recovers `Artur Sosna`.
   - `tvnwarszawa_fundacja_bielskiego_20260425` now recovers `Karol Bielski` and a Bielsk-linked `Fundacja ...` entity.
   - `interwencja.polsatnews.pl__...bardzo-rodzinne-starostwo_1329791` now keeps `Syn Pszczółkowski`, `Synowa Morawska`, and `Jakub Mieszko Pszczółkowski`.

7. **Stable positives still look alive after the uncertainty changes.**
   - `oko_miliony_pajeczyna_rydzyka`: still emits `FUNDING` output.
   - `tvnwarszawa_fundacja_bielskiego_20260425`: still emits public-money output.
   - `zona-posla-pis`: still emits appointment/dismissal plus family/network facts.
   - `wp_lubczyk`: still stays relevant and emits compensation/public-money output.

## What regressed or still looks wrong

1. **WP Kraśnik still has political-profile noise.**
   - `ELECTION_CANDIDACY` facts for `Stawiarski` / `Staruch` are still overgenerated.
   - The critical relationship output is better, but candidacy extraction is still too loose around reference resolution.

2. **`rp_tk_negative` is still a relevance false positive.**
   - The article remains marked relevant while producing no facts.
   - This is still a benchmark mismatch and suggests the relevance gate remains too permissive for that pattern.

3. **`onet_totalizator_leca_glowy` still under-recovers network context.**
   - The article remains relevant and emits appointments/dismissals, but output is still thin relative to expectations.
   - Current facts are dominated by governance and office signals; party-network and compensation coverage still look weak.

4. **`wiadomosci.onet.pl__lublin__...__cpw9ltt` improved on relevance but remains noisy.**
   - The article now emits useful governance facts, but also overproduces party memberships and some implausible targets.
   - This looks like a precision problem after the relevance gate, not a relevance failure anymore.

5. **`onet_totalizator` is still the loudest remaining political-profile outlier.**
   - It still emits very high `PARTY_MEMBERSHIP`, `POLITICAL_OFFICE`, and `ELECTION_CANDIDACY` counts.
   - The new candidacy guard helped in board-candidate articles, but this broader political-profile inflation still needs a deeper precision pass.

## Batch totals

- Inputs processed: **33**
- Relevant: **31**
- Irrelevant: **2**
- Outputs with facts: **30**
- Outputs without facts: **3**
- Missing output JSONs for `inputs/*.html`: **0**

The three zero-fact outputs are:

- `olsztyn_roosevelta_negative` (expected negative)
- `wp_meloni_negative` (expected negative)
- `rp_tk_negative` (**still wrong**: relevant-but-empty false positive)

## Broader article-by-article snapshot

### Useful / mostly healthy outputs

- `ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`  
  Nepotism story stays relevant and again recovers `Artur Sosna`; it still repeats `Wójt` office facts and surname-only variants.
- `dziennikpolski24...charsznicy...`  
  Partner and father-in-law ties plus local appointments are present; proxy-style canonicals like `Swoją "dziewczynę` still look rough.
- `interwencja.polsatnews.pl__...bardzo-rodzinne-starostwo_1329791`  
  Family ties, appointments, and role-held output are all present; `Syn Pszczółkowski` / `Synowa Morawska` are now explicit, though office extraction is still a bit repetitive.
- `natemat_giermasinska`  
  Family-network and appointment coverage is non-empty with PSL context, though one kinship tie looks misattached.
- `niezalezna_polski2050_synekury`  
  Appointments and compensation survive well enough to keep the article useful, but some subjects/targets are still degraded.
- `oko_miliony_pajeczyna_rydzyka`  
  Funding output remains strong and concentrated: `FUNDING: 6`, `PUBLIC_CONTRACT: 1`.
- `olsztyn.tvp.pl__41863255__...wodociagow` and `...__downloaded_20260427`  
  Both variants still emit Jarosław Słoma's vice-president appointment plus party/office context, though the appointment is duplicated.
- `onet_trzaskowski_kopania_phn`  
  Appointments and sibling/associate ties are present; some target strings remain noisy.
- `pleszew24.info__...stadniny-koni`  
  Previously empty article is now non-empty and emits `APPOINTMENT` plus `DISMISSAL`.
- `radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470`  
  Appointment, spouse tie, and former-PO context remain visible; compensation modeling is still weak and partly role-shaped.
- `rp_klich`  
  Appointments and a friend/acquaintance tie are present, but overall coverage is still thin relative to article richness.
- `tp.com.pl__artykul__nowy-zarzad-inwestycji-miejskich-n684452__downloaded_20260427`  
  Minimal but non-empty governance output survives.
- `wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe`  
  The anti-corruption article looks relatively clean: two investigation facts plus one procurement-abuse fact.
- `wp_lubczyk`  
  The article stays relevant and emits compensation/public-money output, but the compensation subject is still too generic (`Poseł`) rather than clearly bound to a named person.
- `wp_zona_sekretarza_krasnik_20260513`  
  Major improvement: the child/parent uncertainty trail is explicit in final output, MOPS and MOSiR stay separate, and the compensation fact now points at Magdalena Skokowska.
- `zona-posla-pis`  
  Spouse/sister-in-law and board facts are still present; proxy duplication remains visible but core coverage survived.

### Useful but still noisy / partially under-modeled

- `businessinsider_kadrowa_czystka_panstwowa_spolka`  
  High-density output, but severe `ELECTION_CANDIDACY` overgeneration (`20`) and obviously wrong targets (`Wojciech Olejniczak -> SLD`, `Allianza OFE -> PZU`) make this output unreliable.
- `dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383`  
  Public-contract and anti-corruption output exists, but `Radny` is duplicated heavily and surname/person references are noisy.
- `olsztyn_wodkan`  
  Salary article stays relevant and now avoids the earlier false-positive `FUNDING` fact; compensation output is still a bit dense but cleaner than before.
- `onet_totalizator`  
  Coverage is broad (`52` facts) but precision is shaky: many long/noisy targets, party/office inflation, and duplicate/overstretched appointments.
- `onet_totalizator_leca_glowy`  
  Still under-recovers the political-network story; output is mostly governance + office and looks thin relative to the article.
- `onet_wfosigw_lublin`  
  Governance facts are present, but party/office output is inflated and the funding line remains weak/noisy.
- `tvn24.pl__polska__kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831__webarchive_20250427191848`  
  Party and associate-network output exists, but names and affiliations are still noisy enough to create contradictory-looking facts.
- `tvnwarszawa_fundacja_bielskiego_20260425`  
  The key public-contract fact is good (`100 tysięcy złotych`); `Karol Bielski` and a Bielsk-linked foundation entity are now recovered, though party-membership output is still inflated by duplicates.
- `wiadomosci.onet.pl__kraj__tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra__ezt8y9t`  
  Family/network and governance output is present, but the article is over-dense (`42` facts) with duplicated Natura Tour events and too many office facts.
- `wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt`  
  Important improvement on relevance, but still noisy after that: implausible targets (`Janów`, `Senatu`) and too many party/office/candidacy facts.
- `wiadomosci.wp.pl__odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle__6996280410176160a`  
  Board-appointment story is visible, but targets are long/noisy and office output is repetitive.
- `wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`  
  Family and appointment output survives, but targets are badly polluted (`Urzędu Wojewódzkiego Czuwa Nad Prawidłowym`) and partner proxies remain messy.
- `wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie__7273798906222848a`  
  Dense and useful article coverage remains, but role/board compensation output is overgenerated and still proxy-heavy.

### Negative controls and remaining outright failures

- `olsztyn_roosevelta_negative`  
  Correctly filtered out as irrelevant with no entities and no facts.
- `wp_meloni_negative`  
  Correctly filtered out as irrelevant with no entities and no facts.
- `rp_tk_negative`  
  Still the clearest unresolved benchmark failure: relevant `true`, `35` entities, and **zero facts**.

## Articles covered in this report

All `inputs/*.html` outputs were summarized. Representative facts were inspected directly for:

- `ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`
- `businessinsider_kadrowa_czystka_panstwowa_spolka`
- `dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715`
- `dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383`
- `interwencja.polsatnews.pl__reportaz__2013-11-29__bardzo-rodzinne-starostwo_1329791`
- `natemat_giermasinska`
- `niezalezna_polski2050_synekury`
- `oko_miliony_pajeczyna_rydzyka`
- `olsztyn.tvp.pl__41863255__z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow`
- `onet_totalizator`
- `onet_totalizator_leca_glowy`
- `onet_trzaskowski_kopania_phn`
- `onet_wfosigw_lublin`
- `pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni`
- `radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470`
- `rp_klich`
- `rp_tk_negative`
- `tvn24.pl__polska__kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831__webarchive_20250427191848`
- `tvnwarszawa_fundacja_bielskiego_20260425`
- `wiadomosci.onet.pl__kraj__tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra__ezt8y9t`
- `wiadomosci.onet.pl__krakow__cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow__vdc04xe`
- `wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt`
- `wiadomosci.wp.pl__odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle__6996280410176160a`
- `wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu__7147022691576352a`
- `wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie__7273798906222848a`
- `wp_lubczyk`
- `wp_meloni_negative`
- `wp_zona_sekretarza_krasnik_20260513`
- `zona-posla-pis`

## Next bottleneck

The next highest-leverage cleanup is **downstream political-profile precision**, not entity-resolution schema plumbing.

Concretely:

- reduce candidacy/party overgeneration around pronouns and surname-only mentions,
- keep deduplication uncertainty-aware so richer facts do not lose `possible_entity_matches` during merge.
