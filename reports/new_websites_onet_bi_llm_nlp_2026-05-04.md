# New Website Extraction Check - Onet Totalizator and Business Insider PZU

Date: 2026-05-04

## Inputs

- `inputs/onet_totalizator_leca_glowy.html`
  - URL: `https://wiadomosci.onet.pl/kraj/sa-skutki-afery-ujawnionej-przez-onet-leca-glowy-na-szczytach-totalizatora/v1x1k0e`
  - Title: `Trzęsienie ziemi w Totalizatorze Sportowym. Prezes odwołany ze stanowiska po publikacji Onetu`
- `inputs/businessinsider_kadrowa_czystka_panstwowa_spolka.html`
  - URL: `https://businessinsider.com.pl/biznes/kadrowa-czystka-objela-kolejna-panstwowa-spolke-nastepne-zmiany-niebawem/v75q3s4`
  - Title: `Kadrowa czystka objęła kolejną państwową spółkę. Następne zmiany niebawem`
- `inputs/onet_trzaskowski_kopania_phn.html`
  - URL: `https://wiadomosci.onet.pl/tylko-w-onecie/rafal-trzaskowski-wyrzucil-go-za-hejterstwo-marcin-kopania-odnalazl-sie-w-phn/3zp8m3y`
  - Title: `Rafał Trzaskowski wyrzucił go za hejterstwo. Teraz odnalazł się w spółce Skarbu Państwa`

## Expected Findings Written Before Execution

### Onet: Totalizator Sportowy - leca glowy

Expected relevance: relevant.

Expected core entities:

- `Totalizator Sportowy`
- `Rafał Krzemień`
- `Mariusz Błaszkiewicz`
- `Rada nadzorcza`
- `Jakub Jaworowski`
- `Ministerstwo Aktywów Państwowych`
- `Skarb Państwa`
- party/context entities: `PO`, `PSL`, `Lewica`
- political-context people: `Sławomir Nitras`, `Stanisław Gawłowski`, `Donald Tusk`, `Borys Budka`

Expected facts:

- `DISMISSAL`: `Rafał Krzemień` removed from president/CEO role at `Totalizator Sportowy`.
  Evidence: `Rada nadzorcza ... Totalizatora Sportowego odwołała ze stanowiska prezesa zarządu Rafała Krzemienia`.
- `APPOINTMENT` or equivalent acting-role fact: `Mariusz Błaszkiewicz` is to perform president duties at `Totalizator Sportowy`.
  Evidence: `obowiązki prezesa Totalizatora ma pełnić Mariusz Błaszkiewicz`.
- Governance/context: `Totalizator Sportowy` is a state-owned company, fully owned by `Skarb Państwa`.
- Political-context facts from the article's recap of the Onet scandal:
  - regional director roles in `Totalizator Sportowy` were filled by local `PO`, `PSL`, and `Lewica` activists and collaborators of `Sławomir Nitras` and `Stanisław Gawłowski`;
  - if represented, these should be party/political-tie context, not invented named appointments where the article only summarizes groups.

Expected negatives:

- Do not emit `APPOINTMENT` facts for all unnamed regional directors as if named people were present.
- Do not treat journalist/contact/footer text as entities or facts.
- Do not convert ministerial criticism by `Jakub Jaworowski` into an appointment/dismissal fact about him.

### Business Insider: PZU supervisory-board changes

Expected relevance: relevant.

Expected core entities:

- `PZU`
- `Skarb Państwa`
- `Ministerstwo Aktywów Państwowych`
- removed supervisory-board members: `Robert Jastrzębski`, `Paweł Górecki`, `Agata Górnicka`, `Marcin Chludziński`, `Krzysztof Opolski`, `Radosław Sierpiński`, `Józef Wierzbowski`, `Maciej Zaborowski`
- retained board member: `Marcin Kubicza`
- appointed supervisory-board members: `Wojciech Olejniczak`, `Michał Jonczynski`, `Adam Uszpolewicz`, `Anita Elżanowska`, `Michał Bernaczyk`, `Filip Gorczyca`, `Andrzej Kaleta`, `Małgorzata Kurzynoga`, `Anna Machnikowska`
- non-appointed candidate: `Andrzej Jarczyk`
- party/context entity: `SLD`
- current management context, not new facts: `Beata Kozłowska-Chyła`, `Tomasz Kulik`, `Maciej Rapkiewicz`, `Małgorzata Sadurska`, `Ernest Bejda`, `Małgorzata Kot`, `Krzysztof Kozłowski`, `Piotr Nowak`

Expected facts:

- `DISMISSAL`: most of the prior `PZU` supervisory board was removed, with `Marcin Kubicza` explicitly excepted.
  Evidence: `Spośród dotychczasowej rady nadzorczej odwołano w czwartek wszystkich z wyjątkiem Marcina Kubiczy`.
- `DISMISSAL`: `Paweł Górecki` had already been removed from the `PZU` supervisory board.
  Evidence: `Paweł Górecki został już odwołany`.
- Multiple `APPOINTMENT` facts: listed nominees from `Ministerstwo Aktywów Państwowych` were appointed to `PZU` supervision/rada nadzorcza, except `Andrzej Jarczyk`.
  Evidence: `Wszyscy kandydaci zostali powołani do nadzoru PZU z wyjątkiem nominata Allianza OFE`.
- `FORMER_PARTY_MEMBERSHIP` or political-context fact: `Wojciech Olejniczak` is former MP and former chairman/head of `SLD`.
  Evidence: `Wojciecha Olejniczaka (byłego posła i przewodniczącego SLD)`.
- Governance/context: `Skarb Państwa` controls `34,2 proc.` of PZU votes/shares; this explains state-control relevance.

Expected negatives:

- Do not emit appointment facts for `Andrzej Jarczyk`; his candidacy was not voted/appointed.
- Do not emit new appointment facts for current `PZU` management listed as existing board members.
- Do not emit future `Pekao`/`Alior` changes as completed facts; the article says they may follow later.

### Onet: Marcin Kopania in PHN

Expected relevance: relevant.

Expected core entities:

- `Marcin Kopania`
- `Polski Holding Nieruchomości` / `PHN`
- `Skarb Państwa`
- `Miejskie Przedsiębiorstwo Realizacji Inwestycji`
- `Rafał Trzaskowski`
- `Platforma Obywatelska` / `PO`
- `Bartosz Kopania`
- `Totalizator Sportowy`
- `Szymon Gawryszczak`
- `Robert Kropiwnicki`
- `Wiesław Malicki`

Expected facts:

- `APPOINTMENT` or public-employment/governance fact: `Marcin Kopania` became deputy director / deputy director of marketing at `Polski Holding Nieruchomości`.
  Evidence: `Marcin Kopania na początku czerwca został wicedyrektorem marketingu w ... Polskim Holdingu Nieruchomości`.
- More specific role/value detail: `zastępca dyrektora Biura Marketingu, Strategii, Relacji Inwestorskich i PR`.
  Evidence: `Od poniedziałku jest zastępcą dyrektora Biura Marketingu, Strategii, Relacji Inwestorskich i PR w Polskim Holdingu Nieruchomości (PHN)`.
- `DISMISSAL`: `Marcin Kopania` lost the president role at `Miejskie Przedsiębiorstwo Realizacji Inwestycji` after the Twitter/hejterstwo case.
  Evidence: `Marcin Kopania wkrótce potem stracił funkcję prezesa Miejskiego Przedsiębiorstwa Realizacji Inwestycji`.
- Governance/context: `PHN` is over 70 percent owned by `Skarb Państwa`.
  Evidence: `Spółka w ponad 70 proc. należy do Skarbu Państwa`.
- `PERSONAL_OR_POLITICAL_TIE`: `Marcin Kopania` is brother of `Bartosz Kopania`.
  Evidence: `Marcin Kopania prywatnie jest bratem Bartosza Kopani`.
- `PUBLIC_CONTRACT` or public-money/context fact if represented: `Bartosz Kopania` received Totalizator Sportowy marketing/text contracts worth over `100 tys. zł`.
  Evidence: `pracował dla Totalizatora Sportowego, od którego otrzymywał zlecenia ... warte ponad 100 tys. zł`.
- `PERSONAL_OR_POLITICAL_TIE`: `Szymon Gawryszczak` is an acquaintance of `Robert Kropiwnicki`.
  Evidence: `Zatrudnił go tam wiceprezes Totalizatora Szymon Gawryszczak, znajomy posła PO i wiceministra aktywów państwowych Roberta Kropiwnickiego`.
- Political context: `Robert Kropiwnicki` is a PO MP and deputy minister of state assets; both `Totalizator Sportowy` and `PHN` are under him.

Expected negatives:

- Do not treat `CasperVanDerHaag` / `Pablo Morales` social-media handles as primary people if the named person is present.
- Do not emit completed facts for earlier PHN allegations unless the evidence has concrete person-role-organization grounding.
- Do not turn insults/quoted tweets into relations.

## Commands

- `uv run python scripts/setup_models.py`
- `uv run python main.py --engine rules --html-path inputs/onet_totalizator_leca_glowy.html --document-id onet_totalizator_leca_glowy_rules --output-dir output/new_websites_rules`
- `uv run python main.py --engine rules --html-path inputs/businessinsider_kadrowa_czystka_panstwowa_spolka.html --document-id businessinsider_kadrowa_czystka_panstwowa_spolka_rules --output-dir output/new_websites_rules`
- `uv run python main.py --engine llm --llm-model gemma4:latest --html-path inputs/onet_totalizator_leca_glowy.html --document-id onet_totalizator_leca_glowy_llm --output-dir output/new_websites_llm`
- `uv run python main.py --engine llm --llm-model gemma4:latest --html-path inputs/businessinsider_kadrowa_czystka_panstwowa_spolka.html --document-id businessinsider_kadrowa_czystka_panstwowa_spolka_llm --output-dir output/new_websites_llm`
- `uv run python main.py --engine llm --llm-model gemma4:latest --html-path inputs/onet_trzaskowski_kopania_phn.html --document-id onet_trzaskowski_kopania_phn_llm --output-dir output/new_websites_llm`
- `ollama stop gemma4:latest`
- `uv run python main.py --engine rules --html-path inputs/onet_trzaskowski_kopania_phn.html --document-id onet_trzaskowski_kopania_phn_rules --output-dir output/new_websites_rules`

Operational note: the first attempted `rules` run for `onet_trzaskowski_kopania_phn` failed with CUDA OOM because the Ollama `gemma4:latest` model remained resident on the GPU. Unloading it with `ollama stop gemma4:latest` freed VRAM and the rules run succeeded.

## Actual Results

### Output Files

- Rules/NLP:
  - `output/new_websites_rules/onet_totalizator_leca_glowy_rules.json`
  - `output/new_websites_rules/businessinsider_kadrowa_czystka_panstwowa_spolka_rules.json`
  - `output/new_websites_rules/onet_trzaskowski_kopania_phn_rules.json`
- LLM:
  - `output/new_websites_llm/onet_totalizator_leca_glowy_llm.json`
  - `output/new_websites_llm/businessinsider_kadrowa_czystka_panstwowa_spolka_llm.json`
  - `output/new_websites_llm/onet_trzaskowski_kopania_phn_llm.json`

### Onet Totalizator - Rules/NLP

- Relevant: yes, score `1.0`.
- Entities: `21`.
- Facts: `11`.
- Good:
  - detects political-office context for `Jakub Jaworowski`, `Sławomir Nitras`, `Stanisław Gawłowski`, `Borys Budka`;
  - detects some party context.
- Bad:
  - misses the core `DISMISSAL` fact for `Rafał Krzemień -> Totalizator Sportowy`;
  - misses the acting-president fact for `Mariusz Błaszkiewicz -> Totalizator Sportowy`;
  - emits a bad governance `APPOINTMENT`: `Jakub Jaworowski -> Skarbu Państwa Totalizatora Sportowego` with role `Rada Nadzorcza`.

### Onet Totalizator - LLM

- Relevant: yes, score `1.0`.
- Entities: `7`.
- Facts: `7`.
- Good:
  - correctly emits `DISMISSAL`: `Rafał Krzemień -> Totalizator Sportowy`, value `prezes zarządu`;
  - correctly emits `APPOINTMENT`: `Mariusz Błaszkiewicz -> Totalizator Sportowy`, value `tymczasowy prezes`;
  - captures some political-network context around `PO` and `PSL`.
- Bad:
  - political-network facts are coarse party-to-company ties rather than named regional-director facts;
  - emits `Borys Budka -> Totalizator Sportowy` as a personal/political tie from a responsibility-denial quote, which is weak.
- Runtime: `llm_extractor` about `93.56s`.

### Business Insider PZU - Rules/NLP

- Relevant: yes, score `1.0`.
- Entities: `40`.
- Facts: `15`.
- Good:
  - identifies many candidate names from the PZU supervisory-board list;
  - marks the article as strongly relevant.
- Bad:
  - treats the appointment list mostly as `ELECTION_CANDIDACY`, not completed `APPOINTMENT` facts;
  - wrongly emits `APPOINTMENT` facts pointing to `SLD` as the object instead of `PZU`;
  - wrongly emits an `ELECTION_CANDIDACY` for `Andrzej Jarczyk`, even though this was explicitly the non-appointed candidate;
  - misses the broad prior-board `DISMISSAL` event and most specific PZU supervisory-board appointments.

### Business Insider PZU - LLM

- Relevant: yes, score `1.0`.
- Entities: `29`.
- Facts: `6`.
- Good:
  - emits `APPOINTMENT`: `Wojciech Olejniczak -> PZU`;
  - emits `DISMISSAL`: `Paweł Górecki -> PZU`;
  - recognizes PZU as the target instead of `SLD`.
- Bad:
  - collapses the whole appointment list onto `Wojciech Olejniczak` instead of emitting facts for all appointed candidates;
  - emits a false positive `APPOINTMENT` for current president `Beata Kozłowska-Chyła`, even though the article says this is an existing role since 2020;
  - does not emit the broad dismissal of the prior supervisory board except for `Paweł Górecki`;
  - misses `Wojciech Olejniczak`'s former `SLD` party/office context as a structured fact.
- Runtime: `llm_extractor` about `32.67s`.

### Onet Kopania/PHN - Rules/NLP

- Relevant: yes, score `1.0`.
- Entities: `39`.
- Facts: `7`.
- Good:
  - detects sibling/family signal between `Bartosz Kopania` and `Marcin Kopania`;
  - detects some party context and public-employment signals;
  - marks the article as strongly relevant.
- Bad:
  - misses the core `Marcin Kopania -> Polski Holding Nieruchomości` appointment as deputy marketing director;
  - emits a bad `APPOINTMENT`: `Marcin Kopani -> Warszawy`;
  - emits wrong public-employment targets around `Bartosz Kopani -> PHN` and `Szymon Gawryszczak -> PHN`;
  - misses the `PUBLIC_CONTRACT` / public-money fact for `Bartosz Kopania -> Totalizator Sportowy` worth over `100 tys. zł`;
  - person normalization degrades `Kopania` to `Kopani` in several entities.

### Onet Kopania/PHN - LLM

- Relevant: yes, score `1.0`.
- Entities: `11`.
- Facts: `10`.
- Good:
  - correctly emits `APPOINTMENT`: `Marcin Kopania -> Polski Holding Nieruchomości`, value `wicedyrektor marketingu`;
  - correctly emits the more specific role: `zastępca dyrektora Biura Marketingu, Strategii, Relacji Inwestorskich i PR`;
  - correctly emits `DISMISSAL`: `Marcin Kopania -> Miejskie Przedsiębiorstwo Realizacji Inwestycji`, value `prezes`, though the org canonical is noisy;
  - correctly emits `PUBLIC_CONTRACT`: `Bartosz Kopania -> Totalizator Sportowy`, value `ponad 100 tys. zł`;
  - captures some broader PHN/PO patronage context.
- Bad:
  - emits weak/false `PERSONAL_OR_POLITICAL_TIE` facts from anti-PO/PO social-media content;
  - emits a historical/background `APPOINTMENT` for `Wiesław Malicki -> Szpital Bródnowski`;
  - misses the explicit `Marcin Kopania` sibling tie to `Bartosz Kopania`;
  - misses the explicit `Szymon Gawryszczak` acquaintance tie to `Robert Kropiwnicki`.
- Runtime: `llm_extractor` about `42.95s`.

## Comparison

LLM currently gives better coverage on concise, named, sentence-local facts:

- `Rafał Krzemień` dismissal from `Totalizator Sportowy`;
- `Mariusz Błaszkiewicz` acting president role;
- `Marcin Kopania` appointment into `PHN`;
- `Marcin Kopania` dismissal from the municipal company;
- `Bartosz Kopania` public-money/contract relation with `Totalizator Sportowy`.

Rules/NLP still has useful relevance and broad entity coverage, but these three checks show recurring extraction issues:

- governance target resolution can attach roles to the wrong object (`SLD`, `Warszawy`, `Skarbu Państwa Totalizatora Sportowego`);
- list-level appointments are not cleanly converted into multiple completed `APPOINTMENT` facts;
- dismissal events are under-extracted when phrased as board/list changes;
- person normalization still damages some inflected Polish surnames (`Kopania` -> `Kopani`, `Kurzynoga` -> `Kurzynóg`, `Anita Elżanowska` -> `Anit Elżanowski`);
- public-money contracts embedded in employment/political-context paragraphs are better recovered by the LLM path than by rules.

Next improvement candidates:

1. Add a list-aware governance extractor for "wszyscy kandydaci zostali powołani ... z wyjątkiem X" and "odwołano wszystkich z wyjątkiem X".
2. Tighten governance target scoring so parties and place names cannot win over the article's company/institution target.
3. Improve person-name preservation for Polish inflection before clustering/linking.
4. Add a public-contract extractor for `otrzymywał zlecenia ... warte ponad <amount>` contexts.
5. For the LLM path, add post-validation rules that suppress existing-role background facts and social-media praise/insult ties unless they encode a concrete public-money, role, family, or political-office relation.
