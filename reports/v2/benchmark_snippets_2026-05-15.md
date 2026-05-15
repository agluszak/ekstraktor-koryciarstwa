# V2 snippet benchmark snapshot — 2026-05-15

## Scope

Small deterministic V2 benchmark snapshot after adding:

- `PUBLIC_EMPLOYMENT`
- `PERSONAL_OR_POLITICAL_TIE`
- anti-corruption referral

This is a snippet-level smoke report, not a full-article benchmark. The scenarios were run with static entity/coreference inputs so the snapshot reflects current **candidate behavior, scores, and signals** rather than spaCy recall variance.

These scenarios are now also covered by fixture-backed tests in:

- `tests_v2/test_benchmark_snippets.py`

## Method

- Sentence segmentation + Morfeusz morphology were run normally.
- Entities/coreference were injected deterministically for each snippet.
- Relevant candidate stages and `FactScoringStage` were run.
- The report records the current fact candidates, arguments, scores, and main signals.

## Scenario 1 — split-sentence governance appointment

**Text**

`Jan Kowalski jest prezesem spółki Wodkan. Został powołany bez konkursu.`

**Expected**

- Emit `GOVERNANCE_APPOINTMENT`.
- Recover person, organization, and role from the adjacent-sentence discourse window.
- Do not downgrade this into public employment.

**Current**

- `governance_appointment`
  - arguments: `person=entity-0`, `organization=entity-1`, `role=entity-2`
  - score: `0.82`
  - signals: `appointment_lemma`, `discourse_window_person`, `discourse_window_organization`, `discourse_window_role`

**Status**: OK

## Scenario 2 — public-employment consultancy hire

**Text**

`Urząd miasta zatrudnił Marka Nowaka jako doradcę burmistrza.`

**Expected**

- Emit `PUBLIC_EMPLOYMENT`.
- Keep this out of governance because the role is advisory/non-board.
- Attach person, organization, and role.

**Current**

- `public_employment`
  - arguments: `person=entity-1`, `organization=entity-0`, `role=entity-2`
  - score: `0.90`
  - signals: `public_employment_lemma`, `sentence_local_person`, `sentence_local_organization`, `sentence_local_role`

**Status**: OK

## Scenario 3 — procurement stays public contract

**Text**

`Urząd podpisał umowę z firmą Alfa za 49 tys. zł.`

**Expected**

- Emit `PUBLIC_CONTRACT`.
- Do not emit `PUBLIC_EMPLOYMENT` because there is no staffing/person target.

**Current**

- `public_contract`
  - arguments: `counterparty=entity-0`, `contractor=entity-1`, `amount=49 tys. zł`
  - score: `0.85`
  - signals: `money_amount`, `public_contract_lemma`, `sentence_local_contract_counterparty`, `sentence_local_contractor`

**Status**: OK

## Scenario 4 — anti-corruption referral without forced governance/public-money fact

**Text**

`Radni PiS zapowiedzieli zawiadomienie do CBA w sprawie zatrudnienia Jana Nowaka.`

**Expected**

- Emit `ANTI_CORRUPTION_REFERRAL`.
- Preserve institution, target, and party-linked actor context.
- Do not force this into governance/public-money just because `zatrudnienia` appears in the context string.

**Current**

- `anti_corruption_referral`
  - arguments: `complainant=entity-2`, `target=entity-1`, `institution=entity-0`, `context=w sprawie zatrudnienia Jana Nowaka`
  - score: `1.00`
  - signals: `anti_corruption_referral_lemma`, `oversight_institution`, `sentence_local_actor`, `sentence_local_target`, `sentence_local_institution`
- also emitted:
  - `political_support`
    - arguments: `subject=entity-2`
    - score: `0.60`
    - signals: `party_alias_match`, `collective_party_context`

**Status**: OK after boundary fix

**Note**

- The referral behavior still looks right.
- The mixed `Radni PiS ... Jana Nowaka` phrasing now keeps weaker party context without falsely turning `Jan Nowak` into a party member.

## Scenario 5 — proxy family tie

**Text**

`Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie.`

**Expected**

- Materialize a proxy family person from the reference.
- Emit `PERSONAL_OR_POLITICAL_TIE` from the proxy person to the anchored person.
- Preserve the relationship detail.

**Current**

- `personal_or_political_tie`
  - arguments: `subject=proxy-1`, `object=entity-0`, `context=spouse`
  - score: `0.75`
  - signals: `proxy_family_entity`, `relationship_detail`

**Status**: OK

## Scenario 6 — party mention true negative

**Text**

`Radni PiS skrytykowali projekt budżetu miasta.`

**Expected**

- Keep the party alias entity if detected.
- Emit **no party relation candidate** because there is no directly attached named person and no stronger relation context.

**Current**

- no relation candidates emitted

**Status**: OK

## Scenario 7 — oversight investigation without referral phrasing

**Text**

`Prokuratura wszczęła śledztwo w sprawie Jana Nowaka.`

**Expected**

- Emit `ANTI_CORRUPTION_INVESTIGATION`.
- Preserve the oversight institution even without a named institution entity.
- Attach the sentence-local target and the `w sprawie ...` context.
- Do not force this into referral semantics just because it is anti-corruption oversight language.

**Current**

- `anti_corruption_investigation`
  - arguments: `target=entity-0`, `institution=Prokuratura`, `context=w sprawie Jana Nowaka`
  - score: `0.70`
  - signals: `anti_corruption_investigation_lemma`, `oversight_institution`, `sentence_local_target`

**Status**: OK

## Scenario 8 — same-name party contrast stays uncertain

**Text**

`Jan Kowalski z PO, nie mylić z Janem Kowalskim z PiS.`

**Expected**

- Keep both party-affiliation hypotheses representable.
- Treat the contrast phrase as uncertainty, not silent identity collapse.
- Score both affiliations below a strong-confidence threshold.

**Current**

- `party_affiliation`
  - arguments: `subject=person-po`, `object=party-po`
  - score: `0.65`
  - negative signals: `same_name_contrast_context`
- `party_affiliation`
  - arguments: `subject=person-pis`, `object=party-pis`
  - score: `0.65`
  - negative signals: `same_name_contrast_context`

**Status**: OK

## Scenario 9 — family-name overlap still yields an explicit tie

**Text**

`Marek Kowalski, syn Jana Kowalskiego, pracuje w urzędzie.`

**Expected**

- Emit `PERSONAL_OR_POLITICAL_TIE`.
- Keep two distinct people despite the shared surname.
- Preserve the kinship direction as `child`.

**Current**

- `personal_or_political_tie`
  - arguments: `subject=entity-0`, `object=entity-1`, `context=child`
  - score: `0.75`
  - signals: `named_kinship_lemma`, `sentence_local_subject`, `sentence_local_object`

**Status**: OK

## Scenario 10 — oversight plus party mention can remain fully negative

**Text**

`NIK opublikowała raport o kontroli urzędu. PiS skrytykował jego wnioski.`

**Expected**

- Emit no anti-corruption fact because this is publication/reporting language, not referral or investigation initiation.
- Emit no party relation fact because there is no directly attached person or stronger support context.

**Current**

- no fact candidates emitted

**Status**: OK

## Scenario 11 — article-style funding plus party context excerpt

**Text**

Critical paragraphs derived from the TVN24 article about public money for the foundation linked to the Warsaw ambulance-service director:

- `... fundacja założona przez ... Karola Bielskiego otrzymała 100 tysięcy złotych z urzędu marszałkowskiego ...`
- `Marszałkiem województwa ... jest Adam Struzik z Polskiego Stronnictwa Ludowego.`
- `Marcelina Zawisza, posłanka partii Razem, zapowiedziała kontrolę ...`

**Expected**

- Recover a `FUNDING` fact with more than the amount alone.
- Materialize source and recipient as explicit candidates even when NER misses those organization phrases.
- Recover article-style party context for the direct inflected party name and the reverse profile/apposition pattern.

**Current**

- `funding`
  - arguments: `funder=urzędu marszałkowskiego`, `recipient=fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola Bielskiego`, `amount=100 tysięcy złotych`
  - signals: `money_amount`, `funding_lemma`, `local_phrase_funder`, `local_phrase_recipient`
- `party_affiliation`
  - arguments: `subject=Adam Struzik`, `object=Polskie Stronnictwo Ludowe`
- `party_affiliation`
  - arguments: `subject=Marcelina Zawisza`, `object=Razem`

**Status**: OK

## Summary

Current V2 looks good on the tested smoke scenarios:

- governance discourse-window recovery is working,
- public employment is separated from governance/procurement,
- anti-corruption referral is stable,
- anti-corruption investigation/control now has its own fact family,
- same-name contrast can stay uncertain instead of collapsing into one identity,
- family-name overlap can still produce an explicit tie without identity merge,
- article-style funding recovery can now infer local organization candidates when NER misses them,
- article-style party context now covers inflected full party names and reverse profile/apposition,
- proxy-family ties now produce explicit tie facts,
- plain collective party mentions can stay truly negative,
- mixed oversight/reporting plus party mentions can stay fully negative.

## Immediate follow-ups

1. Expand the snippet benchmark from deterministic snippets toward fuller article-style fixtures.
2. Add fuller article-style ambiguity checks, especially surname-only references and multi-paragraph same-name contrasts.
