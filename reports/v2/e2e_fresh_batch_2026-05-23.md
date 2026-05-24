# V2 e2e fresh batch — 2026-05-23

Six articles not covered by previous reports. Each compared against
`reports/expected_article_findings.md`.

Suite state at time of run: last known passing baseline (166 passed as of
2026-05-22 end-of-day).

Command pattern:
```bash
uv run extractor-v2 --input-dir inputs --glob "<file>.html" --output-dir /tmp/v2-fresh-20260523
```

---

## 1. TVN Warszawa: fundacja Bielskiego

Input: `tvnwarszawa_fundacja_bielskiego_20260425.html`

### Expected (article 27)

- `PUBLIC_CONTRACT` (not `FUNDING`) for 100 tys. from Urząd Marszałkowski to
  Fundacja Bielskiego.
- Adam Struzik -> PSL affiliation.
- Karol Bielski -> PSL affiliation.
- Marcelina Zawisza -> Razem affiliation.
- Adam Struzik -> marszałek województwa political-office context.
- No family tie from "fundacja założona przez" phrase.

### Observed

relevance `true` (score 1.0), `3` facts:

- `party_affiliation` Marcelina Zawisza -> Razem ✓
- `party_affiliation` Adam Struzik -> PSL ✓
- `funding` urzędu marszałkowskiego -> fundacja założona przez dyrektora
  warszawskiego pogotowia... -> 100 tysięcy złotych ✓ amount/parties, ✗ kind

### Problems

- Kind is `funding` instead of `public_contract`. This is the wrong category
  for a paid-promotion service agreement; expected notes it explicitly.
- Karol Bielski -> PSL affiliation missing.
- No spurious family tie from "założona przez" — that guard is working.

### Takeaway

Partial pass. The public-money signal and party affiliations are present. The
`funding` vs `public_contract` distinction is still not resolved for
service-agreement framing.

---

## 2. WFOŚiGW Lublin

Input: `onet_wfosigw_lublin.html`

### Expected (article 7)

- Stanisław Mazur -> APPOINTMENT -> WFOŚiGW w Lublinie, prezes.
- Andrzej Kloc -> APPOINTMENT -> WFOŚiGW w Lublinie, wiceprezes.
- Agnieszka Kruk -> DISMISSAL -> WFOŚiGW.
- Anna Pokwapisz -> DISMISSAL -> WFOŚiGW.
- Stanisław Mazur -> PARTY_MEMBERSHIP -> Lewica.
- Andrzej Kloc -> PARTY_MEMBERSHIP -> PSL.

### Observed

relevance `true` (score 1.0), `19` facts.

Hits:
- `party_affiliation` Andrzeja Kloca -> PSL ✓ (duplicated twice)
- `governance_dismissal` Agnieszkę Kruk -> WFOŚiGW -> radzie nadzorczej ✓
- `patronage_network_tie` / `patronage_allegation` pairs around
  Pauliny Hennig-Kloski / NFOŚiGW context ✓ (plausible)

Problems:
- Person confusion: `Jarosław Stawiarski` (a PiS politician) is being
  assigned both the new appointment role of `prezesem` and the Lewica
  affiliation. The expected new prezes is Stanisław Mazur. Stawiarski
  appears in article context as the outgoing or opposition figure.
- `governance_appointment` Jarosław Stawiarski -> WFOŚiGW -> prezesem is
  therefore wrong; it should be Stanisław Mazur.
- `governance_dismissal` prezesem -> WFOŚiGW -> prezesem: descriptor-only
  person still leaking through.
- Andrzej Kloc appointment as wiceprezes is missing (only affiliation present).
- Anna Pokwapisz dismissal is missing.
- Stanisław Mazur entity not materialized at all.

### Takeaway

High overproduction (19 facts), but the key new-president appointment is
attached to the wrong person (Stawiarski vs Mazur). This is the most
significant extraction error in this batch — a named-entity confusion between
a contextually mentioned PiS figure and the new incoming official. Also a
continuing gap on the second appointment (Kloc as wiceprezes) and second
dismissal (Pokwapisz).

---

## 3. Totalizator: Prezes odwołany (leca głowy)

Input: `onet_totalizator_leca_glowy.html`

### Expected (article 30)

- Rafał Krzemień -> DISMISSAL -> Totalizator Sportowy, prezes zarządu.
- Mariusz Błaszkiewicz -> APPOINTMENT -> Totalizator Sportowy, p.o. prezesa.
- No appointment fact for Jakub Jaworowski (supervisory board, not president).

### Observed

relevance `true` (score 1.0), `12` facts.

Hits:
- `governance_dismissal` Rafała Krzemienia -> prezesa ✓ (duplicated)
- `personal_or_political_tie` Sławomira Nitrasa -> Stanisława Gawłowskiego
  -> współpracownik ✓ (good political-network context)

Problems:
- `governance_dismissal` Jakub Jaworowski -> prezesa: false dismissal —
  Jaworowski appears in article as supervisory-board context, not as the
  person being removed from the presidency.
- `governance_appointment` Rafała Krzemienia -> prezesa: false appointment
  for the person being dismissed; appointment and dismissal co-materialized.
- Mariusz Błaszkiewicz (the actual acting p.o. prezes) does not appear in
  output.
- `governance_appointment` Sławomira Nitrasa -> Dyrektorami: false
  appointment — Nitras is a politician providing political context,
  not being appointed.
- `patronage_network_tie` / `patronage_allegation` Jaworowski ->
  Totalizatora Sportowego -> Dyrektorami: plausible patronage framing but
  actor is wrong.

### Takeaway

Correct Krzemień dismissal is present. Two critical errors: Jaworowski gets
a false dismissal as prezes, and Błaszkiewicz (acting president) is entirely
absent. The dismissal-plus-appointment co-production bug for the same person
remains.

---

## 4. WP: Żona posła PiS odnalazła się w Lublinie

Input: `wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie...html`

### Expected (article 17)

- Sylwia Sobolewska -> APPOINTMENT -> Lubelskie Koleje, rady nadzorczej.
- Sylwia Sobolewska -> PERSONAL_OR_POLITICAL_TIE -> Krzysztof Sobolewski,
  spouse.
- Krzysztof Sobolewski -> PARTY_MEMBERSHIP -> PiS.
- Sylwia Sobolewska prior dismissal from Orlen boards (historical context).
- Compensation: 2 tys. / 2,3 tys. zł monthly board remuneration.

### Observed

relevance `true` (score 1.0), `20` facts.

Hits:
- `party_affiliation` Krzysztofa Sobolewskiego -> PiS ✓
- `personal_or_political_tie` Sylwii Sobolewskiej -> Krzysztofa Sobolewskiego
  -> spouse ✓ (present via both direct and proxy route, but triplicated)
- `governance_dismissal` Sylwii Sobolewskiej -> Orlen -> radach nadzorczych
  ✓ (historical dismissal correctly captured)
- `governance_appointment` Sylwii Sobolewskiej -> Lubelskie Koleje -> rady
  nadzorczej ✓ KEY FACT present
- `compensation` Lubelskie Koleje -> 2,3 tys. zł ✓

Problems:
- Triple spouse-tie duplicate (entity-route + proxy-route + third variant).
- `public_employment` proxy-130 -> WP: news-outlet name ("WP") materialized
  as an employment organization — entity leaking from source attribution.
- `public_employment` Grzegorz Schreiber -> urzędzie: unexpected person in
  employment, likely contextual drift.
- `governance_dismissal` Krzysztofa Sobolewskiego -> sekretarza: wrong — he
  is not being dismissed as a secretary.
- `patronage_network_tie` / `patronage_allegation` Iwonie Koperskiej ->
  Iwonie Koperskiej -> WP: self-referential tie with news outlet as
  institution. Koperska is likely a journalist or editorial reference.
- `personal_or_political_tie` Krzysztofa Sobolewskiego -> Jarosława
  Kaczyńskiego -> współpracownik: plausible, not explicitly in expected but
  acceptable background signal.

### Takeaway

The core triple (appointment, spouse, party affiliation) is all present.
Key problem: triple-duplicate ties, source-attribution entity leaking into
employment facts, and self-referential patronage tie for what appears to be a
journalist byline.

---

## 5. TVP Olsztyn: Jarosław Słoma (wiceprezydent → wiceprezes)

Input: `olsztyn.tvp.pl__41863255__z-wiceprezydenta-na-wiceprezesa...html`

### Expected (article 10)

- Jarosław Słoma -> APPOINTMENT -> PWiK Olsztyn, wiceprezes.
- Even thin article should yield this from title + opening sentence.

### Observed

relevance `true` (score **0.45**), `0` facts.

### Problems

- Relevance score 0.45 is below the materialization threshold, so no facts
  are produced despite the article being strongly in scope.
- Zero facts is a complete miss for a named-appointment article.
- This was flagged in `expected_article_findings.md` as a case where "title
  and metadata alone should be enough."

### Takeaway

Clear double failure: relevance threshold not met for a thin but clearly
in-scope municipal-company appointment article, and extraction downstream
produces nothing. This is the most critical gap in this batch — thin articles
with strong title signals are currently invisible.

---

## 6. WP: Wiedza, doświadczenie i kompetencje (Opole)

Input: `wiadomosci.wp.pl__wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu...html`

### Expected (article 25)

- Agnieszka Królikowska -> APPOINTMENT -> Opolski Urząd Wojewódzki,
  dyrektor generalny.
- Agnieszka Królikowska -> PERSONAL_OR_POLITICAL_TIE -> Szymon Ogłaza,
  partner.
- Szymon Ogłaza -> marszałek województwa political-office context + PO
  affiliation.
- Monika Jurek -> wojewoda opolska political-office context + PO affiliation.
- Dariusz Jurek -> APPOINTMENT -> Urząd Marszałkowski, główny specjalista.
- Dariusz Jurek -> PERSONAL_OR_POLITICAL_TIE -> Monika Jurek, spouse.

### Observed

relevance `true` (score 1.0), `21` facts.

Hits:
- `public_employment` + `governance_appointment` Agnieszki Królikowskiej ->
  Generalnego Opolskiego Urzędu Wojewódzkiego -> Dyrektora ✓✓
- `personal_or_political_tie` Agnieszki Królikowskiej -> Szymona Ogłazy ->
  spouse -> partnerka ✓ (correct direction)
- `patronage_network_tie` / `patronage_allegation` Agnieszki Królikowskiej
  -> Generalnego Opolskiego Urzędu Wojewódzkiego ✓

Problems:
- `personal_or_political_tie` Dariusz Jurek -> **Dariusz Jurek** -> spouse ->
  mąż: self-referential. The phrase "mąż Moniki Jurek" is resolved with
  Dariusz Jurek as both subject and object. Monika Jurek is not surfaced as
  an entity in the tie.
- `patronage_network_tie` Dariusz Jurek -> **Dariusz Jurek** -> institution:
  same self-referential resolution propagated into patronage tie.
- `governance_dismissal` Dariusz Jurek -> OUW -> dyrektorów: wrong event
  kind (should be appointment, not dismissal) and wrong organization (OUW
  instead of Urząd Marszałkowski).
- `governance_appointment` Andrzej Buła -> Urzędu Wojewódzkiego: contextual
  historical figure, not a new appointment event in this article.
- Missing: Monika Jurek entity, her party affiliation, and her
  `provincial governor` political-office role.
- Missing: Szymon Ogłaza PO affiliation.
- `personal_or_political_tie` Dariusz Jurek -> Jarosław Draguć -> konkurs:
  unexpected link to unknown person.

### Takeaway

Good Królikowska appointment and partner tie. Critical failure: "mąż Moniki
Jurek" does not resolve to a distinct Monika Jurek entity — it collapses to a
self-referential Jurek-Jurek relation. This is the self-referential tie
problem recurring in a cross-institution spousal case. Monika Jurek's
political-office context is entirely absent.

---

## Cross-batch summary

### Strong results

- WP Opole: Królikowska appointment + partner tie working.
- WP zona PiS Lublin: core triple (appointment, spouse, party) present.
- All six articles correctly marked relevant (though Olsztyn TVP is marginal).

### Recurrent problems confirmed or newly observed

1. **Self-referential ties when spouse is the protagonist**
   - `Dariusz Jurek -> Dariusz Jurek (spouse)` in Opole article.
   - Proxy tie `proxy-130 -> WP` in zona PiS article.
   - Root cause: "mąż X" / "żona X" resolution produces X as both subject
     and object when the named reference can't be linked to a distinct entity.

2. **News-outlet entity leak into employment roles**
   - `proxy-130 -> WP` as a public-employment fact.
   - Source-attribution bylines ("WP", "Onet", journalist names) are being
     treated as organizations or persons in employment facts.

3. **Person confusion in appointment articles**
   - WFOŚiGW: Jarosław Stawiarski (opposition context) instead of Stanisław
     Mazur (new president). The correct new appointee is not materialized.

4. **Co-production of dismissal + appointment for the same person**
   - Totalizator: Rafał Krzemień gets both events despite only being
     dismissed.

5. **Thin-article relevance / extraction failure**
   - TVP Olsztyn Słoma: score 0.45, zero facts. Short named-appointment
     articles still need better signal boosting from title + short text.

6. **funding vs public_contract distinction**
   - Service-agreement / paid-promotion articles still produce `funding`
     instead of `public_contract`.

7. **Duplicate fact production**
   - Triple spouse ties in zona PiS Lublin.
   - Duplicate party affiliation entries in WFOŚiGW.

### Priority follow-up targets

1. **Self-referential tie suppression**
   - When inference resolves `mąż/żona X` and subject == object, that
     candidate should be suppressed or heavily penalized.

2. **Person confusion in multi-person appointment articles**
   - WFOŚiGW Lublin is a good focused benchmark for this: new-president
     Mazur must be separated from context-figure Stawiarski.

3. **Thin-article relevance / extraction**
   - TVP Olsztyn Słoma needs a regression fix: relevance threshold for
     short governance-appointment articles where the title carries the signal.

4. **News-outlet name filtering in employment extraction**
   - Prevent source bylines ("WP", "Onet", journalist names) from winning
     employment role slots.

5. **funding → public_contract for service-agreement framing**
   - TVN Warszawa fundacja case is the benchmark.
