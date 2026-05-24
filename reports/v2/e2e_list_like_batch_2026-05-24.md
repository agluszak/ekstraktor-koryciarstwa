# V2 e2e list-like batch — 2026-05-24

Run command:

```bash
uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir /tmp/v2-fresh-listlike-20260524
```

Validation state before the run:

```bash
uv run ruff check pipeline_v2 tests_v2
uv run ty check
uv run pytest -c pytest-v2.ini -q
```

Result: `179 passed`.

## Batch Summary

The full local input set produced `33` JSON outputs. The negative controls
remained clean:

- `wp_meloni_negative`: relevance false, `0` facts.
- `rp_tk_negative`: relevance false, `0` facts.

The list-like / multi-person appointment articles now generally produce many
facts instead of failing silently. This is a substantial improvement over older
runs, especially for thin articles and party-patronage lists. The current
problem is no longer "zero extraction"; it is noisy binding and weak suppression
of bad role assignments.

## List-Like Articles

### Onet: Partyjny desant na Totalizator Sportowy

Output: `32` facts.

Good:

- Multiple `governance_appointment` records for director / board-role cases.
- Multiple party affiliations: PO, KO, Lewica, PiS.
- Patronage-network and patronage-allegation events are present.
- Totalizator organization context is often present.

Problems:

- Media/source organization leakage remains: `Onet` / `Onetowi` appears as a
  governance organization and patronage institution.
- Some person-role bindings are wrong or descriptor-like, e.g. `dyrektora` as a
  person.
- False kinship/proxy ties still appear, e.g. `partner of Donaldem Tuskiem`.
- Patronage events still include self-tie candidates.

### Onet: Tak PSL obsadził państwową spółkę

Output: `47` facts.

Good:

- Strong overproduction: governance appointments, party affiliations, kinship,
  patronage events, and compensation are all present.
- Key expected facts are partially present:
  - Jolanta Sobczyk -> Natura Tour / prezes.
  - Miłosz Wojnarowski -> Konrad Wojnarowski sibling.
  - Mikołaj Grzyb -> Andrzej Grzyb child.
  - Several PSL affiliations.

Problems:

- Many patronage records have only institution/context and no grounded
  complainant/target or subject/object.
- Several self-ties remain: Adam Struzik -> Adam Struzik, Jolanta Sobczyk ->
  Jolanta Sobczyk.
- `Onet` / `Onetu` / `Onetem` leaks into institution slots.
- Some governance records attach appointment/dismissal to contextual people.

### Niezależna: Uśmiechnięte synekury Polski 2050

Output: `27` facts.

Good:

- Core KZN result is present:
  - Łukasz Bałajewicz -> KZN -> prezes.
  - Compensation: KZN -> Łukasz Bałajewicz -> `31 tys. zł`.
- Several board / employment alternatives appear.
- Political-network facts are emitted.

Problems:

- Self-tie patronage records remain for Bałajewicz, Rafał Komarewicz, and
  Szymon Hołownia.
- Media/source organization `GP` leaks into patronage institution.
- Some governance appointment variants bind Łukasz Bałajewicz to the wrong
  organization context, e.g. Sejm media-office context.

### WP: Odpartyjnienie rad nadzorczych

Output: `10` facts.

Good:

- Board/governance records are present.
- Paulina Hennig-Kloska -> NFOŚiGW / supervisory-board context appears.
- Compensation and patronage framing appear.

Problems:

- Main appointee binding is still noisy: Szymon Hołownia appears as a board
  appointee in Sejm context.
- Wirtualna Polska leaks as a compensation funder.
- Expected Polska 2050 / Trzecia Droga party context is weak.

### Onet/WFOŚiGW Lublin

There are two local files for the same article. The richer output produced `21`
facts.

Good:

- Party affiliations for Andrzej Kloc / PSL are present.
- Agnieszka Kruk dismissal is present.
- WFOŚiGW organization context is present.

Problems:

- The key appointment is still wrong in the richer file: Jarosław Stawiarski is
  repeatedly bound as the new WFOŚiGW president instead of Stanisław Mazur.
- Some party affiliations are wrong: Jarosław Stawiarski -> Lewica.
- Andrzej Kloc appointment as vice-president is missing or too weak.
- Descriptor entity `prezesem` still appears as a person in one dismissal.

### Business Insider: Kadrowa czystka

Output: `2` facts.

Good:

- Both facts are governance dismissals.
- MAP appears as context rather than the main organization.

Problems:

- No replacement / appointment facts.
- Sparse extraction relative to list-style personnel-change article.

### WP Warszawa salaries

Output: `7` facts.

Good:

- Compensation extraction works well for multiple municipal-company amounts.
- Tramwaje Warszawskie, MZA / Metro Warszawskie, and MPWiK are recovered as
  funder/employer-like organizations.

Problems:

- One salary item is still classified as `funding`.
- Salary/compensation articles are reasonably covered, but they still lack
  person-role-organization linking where names are available.

### Olsztyn TVP thin appointment

Output: `1` fact.

Good:

- The previous zero-fact failure is fixed.
- Jarosław Słoma -> PWiK -> prezes role is now present.

Problem:

- Relevance score remains low (`0.45`) despite the article being clearly in
  scope. It is relevant enough in practice because extraction ran, but the
  relevance model still underestimates thin title-led appointment stories.

## Cross-Batch Failure Modes

### 1. Self-Tie Patronage Is Still Common

Across the full batch, `34` materialized facts have identical endpoints in
`subject/object` or `complainant/target`. Many are patronage events created from
list-like complaint context. Examples:

- Andrzej Kloc -> Andrzej Kloc in WFOŚiGW.
- Jolanta Sobczyk -> Jolanta Sobczyk in the PSL/Natura Tour article.
- Bałajewicz -> Bałajewicz in Niezależna.
- Iwona Koperska -> Iwona Koperska in the WP Lublin article.

The new reference-aware self-tie factor helps proxy/reference cases, but direct
same-person alternatives are still materialized for patronage events. This needs
a general distinct-role constraint for `PATRONAGE_ALLEGATION` and stronger
handling of role variables where the same entity wins both sides.

### 2. Media/Source Leakage Persists

Detected `15` materialized facts where source/media names appear in semantic
roles such as organization, institution, or funder. Examples:

- `Onet` as patronage institution or governance organization.
- `WP` as public-employment organization.
- `Wirtualna Polska` as compensation funder.
- `GP` as patronage institution.

Entity-context media tagging exists, but it does not suppress enough roles or
does not cover inflected/source forms consistently.

### 3. List Articles Need Better Row/Item Segmentation

The system now emits many plausible facts from list-like articles, but it mixes
people, roles, organizations, and contexts across adjacent list items. This is
visible in:

- WFOŚiGW: Stawiarski gets Mazur's incoming-president context.
- Totalizator: politician/source context gets mixed with director appointment
  facts.
- PSL/Natura Tour: institution-only patronage facts and contextual people are
  overproduced.

This points to a missing discourse/list-item layer: before inference, the
pipeline should expose paragraph/list-item windows or article sections as
evidence scopes, and factors should prefer bindings inside the same list item.

## Current Assessment

The system is now in the desired "overproduce with scores" regime for list-like
articles. It recovers many expected entities/facts and keeps negatives clean.

The next quality step should not be adding article-specific words. The next
step should be structural:

1. Add typed list-item / paragraph-section evidence scopes and use them in role
   binding factors.
2. Strengthen generic distinct-role constraints for all directed tie/allegation
   schemas.
3. Make media/source entity context suppression stronger and more reusable
   across governance, employment, compensation, and patronage roles.
4. Improve governance person-role binding with syntax/list-item locality so
   contextual politicians do not win incoming appointment roles.
