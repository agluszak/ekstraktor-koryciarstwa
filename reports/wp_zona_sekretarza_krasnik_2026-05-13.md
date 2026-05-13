# WP: dwa dni i trzy umowy dla zony sekretarza UM Krasnik

Source: <https://wiadomosci.wp.pl/dwa-dni-i-trzy-umowy-dla-zony-sekretarza-urzedu-miasta-7138977147599616a>

Checked on: 2026-05-13

## Commands

```bash
curl -L -A 'Mozilla/5.0' -s 'https://wiadomosci.wp.pl/dwa-dni-i-trzy-umowy-dla-zony-sekretarza-urzedu-miasta-7138977147599616a' -o tmp/article_checks/wp_zona_sekretarza_krasnik_20260513.html
uv run python scripts/setup_models.py
uv run python main.py --html-path tmp/article_checks/wp_zona_sekretarza_krasnik_20260513.html --document-id wp_zona_sekretarza_krasnik_20260513 --source-url 'https://wiadomosci.wp.pl/dwa-dni-i-trzy-umowy-dla-zony-sekretarza-urzedu-miasta-7138977147599616a' --output-dir output/wp_zona_sekretarza_krasnik_20260513
```

Result JSON:

```text
output/wp_zona_sekretarza_krasnik_20260513/wp_zona_sekretarza_krasnik_20260513.json
```

## Expected Findings

This is a strong positive article. It describes a concrete public-employment/nepotism sequence in Kraśnik, not just generic commentary.

Expected core entities:

- Agnieszka Bebel: radca prawny, former MOPS employee, former supervisory-board member at the municipal company, former MOSiR legal-service contractor.
- Magdalena Skokowska: radca prawny, wife of Łukasz Skokowski, later appointed/employed on the MOPS legal-counsel position.
- Łukasz Skokowski: secretary of Urząd Miasta Kraśnik, husband of Magdalena Skokowska.
- Krzysztof Staruch: mayor of Kraśnik, officially supported by PiS in the election context.
- Wojciech Wilk: former mayor / PO election opponent.
- Michał Stawiarski: new MOSiR director.
- Jarosław Stawiarski: PiS politician/marshal, father of Michał Stawiarski.
- Piotr Janczarek: PSL councillor and source of the interpellation.
- Ewa Nowak: MOPS manager, confirms re-creation of the position.
- Organizations: Urząd Miasta Kraśnik, MOPS w Kraśniku, MOSiR w Kraśniku, Kraśnickie Przedsiębiorstwo Mieszkaniowe, Wody Polskie.

Expected facts:

- `DISMISSAL`: Agnieszka Bebel removed from the supervisory board of a municipal company by the new mayor.
- `DISMISSAL` or public-employment termination: Agnieszka Bebel's MOPS employment ended after the legal-counsel position was allegedly liquidated.
- `APPOINTMENT` or public-employment fact: Magdalena Skokowska employed as legal counsel / radca prawny at MOPS after the position was re-created.
- `APPOINTMENT`: Michał Stawiarski became director of MOSiR in Kraśnik.
- `PERSONAL_OR_POLITICAL_TIE`: Magdalena Skokowska is the spouse of Łukasz Skokowski.
- `PERSONAL_OR_POLITICAL_TIE`: Michał Stawiarski is the son of Jarosław Stawiarski.
- `PUBLIC_CONTRACT` and/or `COMPENSATION`: Magdalena Skokowska receives 10 189,50 zł brutto from three contracts/sources in city-subordinate units.
- `PARTY_MEMBERSHIP` / political affiliation: Jarosław Stawiarski -> PiS, Piotr Janczarek -> PSL, Wojciech Wilk -> PO.
- Political support context: Krzysztof Staruch was formally backed by PiS but described as non-party, so this should not become a hard `PARTY_MEMBERSHIP` unless the schema has a weaker support/candidacy fact.

Expected non-facts:

- The word `razem` in "razem z Wojciechem Wilkiem rozdawała..." must not create a `PARTY_MEMBERSHIP` fact for Razem.
- The section heading "Radny odkrywa..." must not make Agnieszka Bebel a councillor.
- Piotr Janczarek is the councillor who obtained the documents; he is not the beneficiary of the 10 189,50 zł.
- MOPS and MOSiR should remain separate organizations.
- Surname-only `Stawiarskiego` should not become a separate parent entity when the article already contains Jarosław Stawiarski.

## Actual Output

The article was marked relevant:

```json
{
  "is_relevant": true,
  "score": 1.0,
  "reasons": [
    "keyword hits: stanowisko, zarząd, posady",
    "public-fund context: instytucja",
    "structural co-occurrence hits: 4",
    "contains person-like full name",
    "contains public institution or board marker",
    "contains board or management marker",
    "contains appointment or dismissal language"
  ]
}
```

Fact counts:

```text
PERSONAL_OR_POLITICAL_TIE: 5
PARTY_MEMBERSHIP: 5
APPOINTMENT: 4
ELECTION_CANDIDACY: 4
POLITICAL_OFFICE: 2
DISMISSAL: 1
COMPENSATION: 1
```

Good or partly-good output:

- `DISMISSAL`: Agnieszka Bebel removed from a supervisory board was extracted, though the object is polluted by the MOPS/MOSiR merge.
- `APPOINTMENT`: Michał Stawiarski as MOSiR director was extracted, again with the target polluted by MOPS/MOSiR merging.
- `APPOINTMENT`: Magdalena Skokowska was extracted as occupying/employed on the recreated MOPS position.
- `PERSONAL_OR_POLITICAL_TIE`: Michał Stawiarski -> Stawiarski as `child_son` was extracted, but the parent should resolve to Jarosław Stawiarski.
- `PARTY_MEMBERSHIP`: Jarosław Stawiarski -> PiS and Piotr Janczarek -> PSL were extracted.

Main mismatches:

- The 10 189,50 zł `COMPENSATION` fact is attached to Piotr Janczarek, because the sentence starts with "Z dokumentów, które dostał z urzędu radny Janczarek wynika...". The semantic beneficiary is "kobieta", i.e. Magdalena Skokowska.
- The three city-unit contracts are not represented as `PUBLIC_CONTRACT`; the output only has a weak/incorrect `COMPENSATION`.
- Magdalena Skokowska and Łukasz Skokowski are not connected by a clean direct spouse fact. The output creates proxy-person facts and identity hypotheses, which preserve uncertainty but do not produce the desired final relationship.
- `MOPS`, `Miejski Ośrodek Pomocy Społecznej`, `MOSiR`, and `MOSiR w Kraśniku` are merged into one organization cluster. This contaminates appointment/dismissal targets.
- Krzysztof Staruch receives a false `PARTY_MEMBERSHIP` to PO from the sentence "Wojciech Wilk z PO oraz Krzysztof Staruch, bezpartyjny, ale oficjalnie popierany przez PiS".
- Wojciech Wilk receives a false `PARTY_MEMBERSHIP` to Razem from the ordinary adverb "razem".
- Agnieszka Bebel and a "Pani Agnieszka" proxy receive false `POLITICAL_OFFICE` facts with value `Radny`, apparently from the nearby heading "Radny odkrywa trzy umowy...".
- Jarosław Stawiarski receives a false `ELECTION_CANDIDACY` fact from the phrase "jego kandydaturę wspierał...", where "jego" refers to Staruch, not Stawiarski.

## Implementation Target

If this article is promoted into the integration benchmark, the test should encode behavior, not exact fact IDs:

- relevance is true;
- Magdalena Skokowska has an appointment/public-employment fact at MOPS;
- Magdalena Skokowska has a public-money fact for `10 189,50 zł brutto` or a `PUBLIC_CONTRACT` fact tied to city-subordinate units;
- Magdalena Skokowska and Łukasz Skokowski are connected as spouses, directly or via a resolved probable identity;
- Michał Stawiarski has an appointment as MOSiR director and a son/family tie to Jarosław Stawiarski;
- MOPS and MOSiR are not the same canonical entity;
- no `Razem` party fact is emitted from lower-case `razem`;
- no `POLITICAL_OFFICE`/`Radny` fact is emitted for Agnieszka Bebel;
- no hard PO membership is emitted for Krzysztof Staruch.

The main fix area is not relevance. It is entity clustering plus beneficiary resolution across appositive/reporting clauses, with a smaller political-profile precision issue around party abbreviations and section-heading leakage.
