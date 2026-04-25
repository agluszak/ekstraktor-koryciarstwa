# TVN Warszawa: fundacja dyrektora pogotowia article check (2026-04-25)

## Source

- Current article: `https://tvn24.pl/tvnwarszawa/srodmiescie/warszawa-100-tysiecy-z-urzedu-dla-fundacji-dyrektora-pogotowia-razem-chce-kontroli-st8987644`
- Linked background article: `https://tvn24.pl/tvnwarszawa/srodmiescie/pieniadze-dla-fundacji-dyrektora-pogotowia-100-tysiecy-za-wyswietlanie-logo-urzedu-st8973405`

## Commands

```bash
curl -L -A 'Mozilla/5.0' -s \
  'https://tvn24.pl/tvnwarszawa/srodmiescie/warszawa-100-tysiecy-z-urzedu-dla-fundacji-dyrektora-pogotowia-razem-chce-kontroli-st8987644' \
  > tmp/article_checks/tvnwarszawa_fundacja_bielskiego_20260425.html

uv run python scripts/setup_models.py

uv run python main.py \
  --html-path tmp/article_checks/tvnwarszawa_fundacja_bielskiego_20260425.html \
  --document-id tvnwarszawa_fundacja_bielskiego_20260425 \
  --source-url 'https://tvn24.pl/tvnwarszawa/srodmiescie/warszawa-100-tysiecy-z-urzedu-dla-fundacji-dyrektora-pogotowia-razem-chce-kontroli-st8987644' \
  --output-dir output/tvnwarszawa_fundacja_bielskiego_20260425
```

Result JSON:

- `output/tvnwarszawa_fundacja_bielskiego_20260425/tvnwarszawa_fundacja_bielskiego_20260425.json`

## What Should Be There

### Scope

- This article is clearly in scope.
- It is a public-money oversight story about money from a public institution flowing to a foundation connected to the director of a public rescue service, with additional party-network context.

### The article text directly supports

- `Karol Bielski` as a central `Person`.
- `Adam Struzik` as a central `Person`.
- `Polskie Stronnictwo Ludowe / PSL` as a central `PoliticalParty`.
- `Marcelina Zawisza` as a secondary `Person`.
- `Razem` as a `PoliticalParty`.
- `urząd marszałkowski` as the public institution providing the money.
- an unnamed `fundacja` founded by Karol Bielski as the recipient organization.
- a public-money transfer:
  - `urząd marszałkowski` -> `fundacja Karola Bielskiego`
  - amount: `100 tysięcy złotych`
  - stated purpose: promotion / promotional activities around the event organized by the ambulance service
- political-profile facts:
  - `Adam Struzik` -> `PARTY_MEMBERSHIP` -> `PSL`
  - `Karol Bielski` -> `PARTY_MEMBERSHIP` -> `PSL`
  - `Marcelina Zawisza` -> `PARTY_MEMBERSHIP` -> `Razem`
- public-office / public-employment context:
  - `Adam Struzik` holds the office of marshal of the voivodeship
  - `Karol Bielski` heads the Warsaw ambulance service / `Meditrans`

### Comparison standard

- Relevance should be `true`.
- The extractor should recover at least one money-flow / funding fact from the current article alone. The transfer is restated explicitly in paragraph 2 of the cleaned text.
- The extractor should recover both `PSL` memberships named in the article body.
- It should not invent kinship or family ties. The article is about political/public-money ties, not relatives.
- Organization coverage should be better than person-only extraction. Missing both the recipient foundation and the paying public institution is underperformance.

## Cleaned Input Seen By The Pipeline

Preprocessing result:

- title: `"Adam Struzik chroni swoich". Chcą kontroli umów w urzędzie`
- publication date: `2026-04-08T11:36:52.000Z`
- content source: `hybrid`
- quality flags: none
- paragraphs: `14`

Important cleaned-text observations:

- The saved HTML was good enough for the preprocessor to recover the main article body.
- The key transfer sentence survived preprocessing.
- This is not a case where extraction failure can be blamed on empty or mangled article text.

## Actual Pipeline Output

High-level result:

- relevance: `true`
- relevance score: `0.67`
- entities: `17`
- facts: `6`
- events: `0`
- relations: `0`

Facts emitted:

- `Adam Struzik` -> `PARTY_MEMBERSHIP` -> `Polskie Stronnictwo Ludowe`
- `Adam Struzik` -> `POLITICAL_OFFICE` -> `Marszałek Województwa`
- `Marcelina Zawisza` -> `POLITICAL_OFFICE` -> `Poseł` (duplicated / near-duplicated 3 times)
- false positive:
  - `PERSONAL_OR_POLITICAL_TIE`
  - `Karol Bielski` linked via a `family` relation
  - evidence sentence is the transfer sentence about a foundation founded by the director

Notable entity behavior:

- `Karol Bielski` was extracted correctly as a person.
- `Adam Struzik` was extracted correctly as a person.
- `PSL` was extracted correctly as a political party.
- `Marcelina Zawisza` was extracted, but canonicalized incorrectly as `Marcelina Zawisz`.
- `Razem` was not extracted as an entity.
- the unnamed foundation was not extracted as an organization.
- `urząd marszałkowski` was not extracted as an organization / institution.
- `Meditrans` did not survive as an entity in the final output.

## Comparison

### Correct

- Relevance is correct.
- The pipeline recovered the strongest obvious political context for `Adam Struzik -> PSL`.
- It also recovered `Adam Struzik` as holding marshal office.

### Misses

1. The core public-money fact is completely missing.
   The article explicitly restates that `100 tysięcy złotych` went from the marshal's office to the foundation founded by Karol Bielski.

2. The recipient and payer organizations are missing.
   This removes the backbone needed for either `FUNDING` or typed public-contract/public-money extraction.

3. `Karol Bielski -> PSL` is missing.
   The article states this directly.

4. `Marcelina Zawisza -> Razem` is missing.
   The article states she is an MP from Razem.

5. `Karol Bielski` public-role context is missing.
   The article states he heads the ambulance service.

### False positives / quality problems

1. The extractor hallucinated a `family` tie from the sentence saying that the foundation was founded by the director.
   This is a serious semantic error. The sentence is about organizational founding / control, not kinship.

2. `Marcelina Zawisza` was canonicalized as `Marcelina Zawisz`.

3. `POLITICAL_OFFICE -> Poseł` was emitted three times for the same person.

## Interpretation

- The main failure here is not relevance and not article fetch quality.
- The main failure is downstream extraction:
  - organization recovery for public institution / foundation mentions
  - money-flow extraction from a clear public-money transfer sentence
  - party-membership coverage for secondary subjects
  - a bad kinship trigger that fires on `fundacja założona przez ...`

## Most Important Next Checks If We Decide To Fix This

1. Trace why the NER/clustering path drops the unnamed foundation and `urząd marszałkowski` despite the cleaned text being intact.
2. Inspect whether the funding extractor currently requires stronger organization typing than this article provides.
3. Find the tie extractor rule that mapped `założona przez dyrektora ...` onto `family` with `score_reason: tie_trigger:żona`.
4. Add a regression test that forbids kinship extraction from organization-founding patterns and expects the public-money transfer sentence to yield at least payer/recipient/amount structure.
