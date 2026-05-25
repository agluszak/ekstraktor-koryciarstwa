# Batch Findings — 2026-05-25

Full e2e run across all 34 inputs after the event-frame / political-office / candidacy commit.
Compared against `reports/expected_article_findings.md`.

## Run summary

- 34 inputs → 33 outputs (1 silently skipped — probable malformed HTML)
- 2 correctly non-relevant: TK legal analysis, Meloni/Trump article
- 31 relevant

---

## Per-article assessment

### 1. Lubczyk / parliamentary salaries (WP)

**Expected:** Relevant, compensation, public institution paying salary.

**Actual:** True (1.00), 9 facts — 1 compensation, 1 party_affiliation (Piotr Zgorzelski/PSL), 1
governance_dismissal, 6 political_office (all 0.48).

**Status: PASS.** Compensation present, relevant. The six political_office facts at 0.48 are low-confidence
boilerplate from the new frame extraction and do not hurt, but add no signal.

---

### 2. Olsztyn salary article (wodociągowe)

**Expected:** Relevant, compensation, person-role-organization facts (Pancer → PWiK Olsztyn).

**Actual:** True (0.64), 5 facts — all compensation, no subject/org binding.

**Status: PARTIAL.** Compensation facts present. Entity binding (person → org) is missing.
No named presidents attached to their organizations in slim output.

---

### 3. Posady współpracowników Klicha (RP)

**Expected:** Employment/appointment for Hodura, Dulian, Kuczmański; PO party affiliation;
personal ties to Klich.

**Actual:** True (0.60), 8 facts — 1 public_employment, 1 governance_appointment, 1
patronage_network_tie (Bogdan Klich), 3 patronage_allegation, 1 political_office, 1 patronage_allegation.

**Status: UNDERPERFORMING.** Klich patronage_network_tie is there but the three key person-to-person
acquaintance ties (Hodura, Dulian, Kuczmański → Klich) are missing. No PO party affiliation. No named
person appears in the appointment or employment facts. Low relevance score (0.60) suggests the relevance
model is also uncertain.

---

### 4. Partyjny desant na Totalizator Sportowy (Onet, full article)

**Expected:** Multiple appointments, party ties (PO/PSL/Lewica), dismissals, compensation.

**Actual:** True (1.00), 30 facts — 9 governance_appointment, 4 governance_dismissal, 5 party_affiliation
(Posadzy/PiS, Gawłowski/PO×2, Zagórski/Lewica, Czwal/KO), 1 personal_tie (partner of Donald Tusk →
Gawłowski), 2 extended_kinship, 2 patronage_allegation, 5 political_office, 1 election_candidacy.

**Status: PASS.** Strong. Party ties correctly bound. Multiple appointments and dismissals. Kinship
includes "żona of Magdalena Sekuła → Magdalena Sekuła" (self-referential — see issue #3 below).
The "partner of Donald Tusk → Gawłowski" is a legitimate finding from the article text.

---

### 5. Radomszczańska: Nowy zaciąg tłustych

**Expected:** APPOINTMENT (Rząsowski → AMW Rewita), party (PO), compensation.

**Actual:** True (1.00), 6 facts — 1 governance_appointment (0.74), 1 party_affiliation
(Marek Rząsowski/PO ✓), 1 extended_kinship (Mirella Zugaj → Radka Zugaja), 1 compensation,
1 election_candidacy, 1 political_office.

**Status: PASS.** Party tie and appointment present. Compensation present.
Organization binding (AMW Rewita) not visible in slim output.

---

### 6. Onet: WFOŚiGW w Lublinie (short article — 5 facts)

**Expected:** 2 appointments (Mazur/prezes, Kloc/wiceprezes), 2 dismissals (Kruk, Pokwapisz),
party ties (Mazur/Lewica, Kloc/PSL).

**Actual:** True (0.97), 5 facts — 2 party_affiliation (Kloc/PSL ✓, Mazur/Lewica ✓), 1
governance_appointment, 1 patronage_network_tie (Kloc→Mazur), 1 patronage_allegation.

**Status: PARTIAL.** Party ties correct. Only 1 appointment, 0 dismissals. The Kruk and Pokwapisz
dismissals are missing.

*Note: there are two WFOŚiGW articles in the inputs — this is the shorter one. The longer version
(24 facts) recovers 5 appointments and 3 dismissals with richer party context.*

---

### 7. Niezależna: Uśmiechnięte synekury Polski 2050

**Expected:** APPOINTMENT (Bałajewicz → KZN), party (Polska 2050), personal tie
(Komarewicz → Bałajewicz), compensation.

**Actual:** True (1.00), 28 facts — 3 compensation, 7 governance_appointment, 2 public_employment,
2 extended_kinship (Paweł Śliz ↔ Filip Curyło, duplicated), personal_tie (Waldemar Buda → Gabriela Sowa,
Rafał Komarewicz → Szymon Hołowni ✓), political_support (Polska 2050 → Michał Szymczyk ✓),
patronage_network_tie (Łukasz Bałajewicz ✓).

**Status: PASS.** Multiple appointments, compensation, political support fact, patronage tie
for Bałajewicz. The Curyło/Śliz kinship is duplicated (both directions materialized separately).

---

### 8. OKO.press: Pajęczyna Rydzyka

**Expected:** FUNDING facts, Fundacja Lux Veritatis, public-institution money flows.

**Actual:** True (1.00), 8 facts — 4 funding, 2 public_contract, 1 funding(0.55), 1 extended_kinship
(córka of Rydzyka → Rydzyka 0.51).

**Status: PASS.** Funding and public_contract facts present. The kinship "córka of Rydzyka →
Rydzyka" is self-referential (see issue #3 below). No false family tie from "fundacja założona przez".

---

### 9. TVP Olsztyn: Słoma w zarządzie wodociągów

**Expected:** APPOINTMENT (Słoma → PWiK Olsztyn), wiceprezes role.

**Actual:** True (0.45), 1 fact — governance_appointment (0.69, no entity binding shown).

**Status: MINIMAL.** Appointment is there. Relevance score of 0.45 is too low for a clear
governance story — suggests the body text is thin and only the title drives the result.
No entity binding in slim output.

---

### 10. TVN24 Wayback: Kolesiostwo i rozdawanie posad (Śląsk)

**Expected:** Relevant, party ties, patronage network, personal ties between local actors.

**Actual:** True (0.90), 8 facts — party_affiliation (Bolesław Piecha/PO ✓, **Bolesław Piecha/PiS ←
FALSE POSITIVE**, Doroda Połedniok/PO ✓), 2 patronage_network_tie (Donald Tusk, Bolesław Piecha),
2 patronage_allegation, 1 election_candidacy.

**Status: PARTIAL.** Connects Piecha to both PO and PiS. The dual-party assignment is a false positive
— the article likely mentions PiS in a negative comparison context and the party producer is picking
it up. Donald Tusk as a patronage_network_tie subject with empty object is noise.

---

### 11. TVN Warszawa: Bielski fundacja (100 tys. PLN)

**Expected:** PUBLIC_CONTRACT (fundacja → Urząd Marszałkowski, 100k), party ties
(Struzik/PSL, Zawisza/Razem, Bielski/PSL), NOT a family tie from "fundacja założona przez".

**Actual:** True (1.00), 5 facts — party_affiliation (Zawisza/Razem ✓, Struzik/PSL ✓), funding
(0.70 ← wrong kind), 2 political_office.

**Status: PARTIAL.** Party ties correct. Money fact is FUNDING not PUBLIC_CONTRACT (Bug E from prior
report — paid promotional service misclassified). No family tie from "fundacja założona przez" (good).
Missing: Bielski/PSL party affiliation.

---

### 12. WP: Odpartyjnienie rad nadzorczych

**Expected:** APPOINTMENT to NFOŚiGW supervisory board, party (Polska 2050),
Hennig-Kloska governance context.

**Actual:** True (1.00), 17 facts — 1 party_affiliation (Olgierd Geblewicz/PO ← unexpected),
4 governance_appointment, 2 governance_dismissal, 1 compensation, 9 political_office.

**Status: PARTIAL.** Appointments and dismissals present. But no Polska 2050 party affiliation
(the primary party in the article). The Geblewicz/PO tie is likely from a quoted comparison paragraph.
No Hennig-Kloska link.

---

### 13. Onet: Tak PSL obsadził Natura Tour

**Expected:** APPOINTMENT (Sobczyk → prezes), party ties (PSL), personal tie
(Sobczyk → Klimczak), kinship (Wojnarowski brat wiceministra).

**Actual:** True (1.00), 36 facts — 4 party_affiliation (Jażdżyk/PSL ✓, Grzyb/PSL ✓,
Brzeski/PSL ✓, Smogorzewski/PO ✓), 7 governance_appointment, 3 governance_dismissal,
2 personal_tie (Andrzej Melon → Jażdżyk, Jolanta Sobczyk → Dariusz Klimczak ✓),
3 extended_kinship (Miłosz → Konrad Wojnarowski ✓, Mikołaj Grzyb → Andrzej Grzyb ✓,
brat of Smogorzewski ✓), 9 political_office, 1 election_candidacy, 1 compensation.

**Status: PASS.** Strong. Jolanta Sobczyk → Klimczak personal tie ✓, sibling kinship for
Wojnarowski ✓, all PSL ties ✓.

---

### 14. Pleszew24: Radna powiatowa / Stadnina Koni Iwno

**Expected:** APPOINTMENT (Góralczyk → Stadnina Koni Iwno), DISMISSAL, party (PSL).

**Actual:** True (1.00), 4 facts — 1 governance_dismissal, 1 governance_appointment,
1 patronage_network_tie (subject="A." ← abbreviated), 1 patronage_allegation.

**Status: PARTIAL.** Appointment and dismissal present. PSL party affiliation **missing**.
The patronage_network_tie subject is "A." — the initial-only name is not resolved to Góralczyk.

---

### 15. Onet: Żona posła PiS zrezygnowała z rad nadzorczych

**Expected:** DISMISSAL x2 (Enea Połaniec, Jelcz), kinship (żona/Stefaniuk), party (PiS).

**Actual:** True (1.00), 7 facts — 2 governance_dismissal ✓, extended_kinship
(żona of Dariusz Stefaniuk → Dariusza Stefaniuka ✓), 1 governance_appointment ← suspicious,
2 political_office, 1 patronage_allegation.

**Status: PARTIAL.** Dismissals and kinship present. PiS party affiliation **missing**.
The governance_appointment is suspicious — Renata Stefaniuk resigned, she was not appointed.
Possible Bug G (odwołać się → dismissal+appointment co-production).

---

### 16. WP: Żona posła PiS odnalazła się w Lublinie

**Expected:** APPOINTMENT (Sobolewska → Lubelskie Koleje), kinship (żona/Sobolewski), party (PiS).

**Actual:** True (1.00), 25 facts — 1 party_affiliation (Krzysztofa Sobolewskiego/PiS ✓),
3 extended_kinship (Sylwii Sobolewskiej → Krzysztofa Sobolewskiego ✓ — 3 duplicates), 2
governance_dismissal, 6 governance_appointment, 1 personal_tie (Sobolewski → Kaczyński),
6 political_office, 1 patronage_allegation.

**Status: PASS.** Party tie ✓, kinship ✓ (duplicated 3×). Appointment present.
Kinship duplication suggests the same sentence or near-identical coreference pattern triggers
multiple materialized kinship facts.

---

### 17. Bytom: Nepotyzm / CBA

**Expected:** CBA complaint, contracts (Wnuk Consulting), Wołosz-Wnuk colleague tie,
family tie to city spokesperson.

**Actual:** True (1.00), 20 facts — 4 anti_corruption_referral ✓, 1 patronage_network_tie
("Bytomski" 0.82 ← descriptor not person), 1 patronage_allegation, 1 extended_kinship
(Mariuszem Wołoszem → Macieja Bartkowa 0.65 ← **FALSE POSITIVE**), 1 personal_tie
(Macieja Bartkowa → Mariuszem Wołoszem ✓), 11 political_office, 1 public_contract.

**Status: PASS with a false positive.** CBA referrals ✓, personal tie (Bartków → Wołosz) is
correct. The extended_kinship (Wołosz → Bartków) is wrong — they are political adversaries, not
relatives. The "Bytomski" patronage_network_tie subject is a demonym adjective, not a person.

---

### 18. naTemat: 24-latka wiceprezeską elektrociepłowni (Giermasińska)

**Expected:** APPOINTMENT (Giermasińska → Energetyka Cieplna), personal_tie
(fiancée/narzeczona → Klimczak), party (PSL/Klimczak).

**Actual:** True (1.00), 12 facts — 2 extended_kinship (Urszula Bury → Jana Burego, Kłopotek →
Żelichowski), 1 public_employment, 2 governance_appointment, 1 personal_tie (Ograsiński → Suchecki),
1 patronage_network_tie, 1 patronage_allegation, 2 extended_kinship (Kalinowski brat, Żelichowski/Kłopotek),
1 political_office.

**Status: FAILING.** Marta Giermasińska does not appear in any fact. No appointment for the main
subject. No fiancée tie (narzeczona) to Klimczak. The extracted facts are from the historical context
section of the article (Kłopotek, Kalinowski, Żelichowski). This was already failing on 2026-05-06 and
remains unresolved.

**Root cause candidate:** The main subject name "Marta Giermasińska" is being poorly lemmatized
(noted as "Marta Giermasińk" in the May baseline). If NER misses or incorrectly resolves the name, the
appointment binding fails. The "narzeczona" kinship signal likely needs to be added to the proxy/kinship
producer.

---

### 19. Charsznica: Partnerka wójta

**Expected:** public_employment (partnerka → urząd), kinship (teść, szwagierka, etc.),
POLITICAL_OFFICE (Kościelniak → wójt), no Jan Kowalski ghost entity.

**Actual:** True (1.00), 14 facts — 2 public_employment (no binding), extended_kinship
(**Jan Kowalski** → Tomasza Kościelniaka ← Bug F ghost), 2 patronage_network_tie,
2 patronage_allegation, extended_kinship (teść of Kościelniak → Kościelniak ✓),
3 election_candidacy, 3 political_office.

**Status: PARTIAL.** Public employment present (binding still missing). Teść kinship ✓.
Jan Kowalski ghost entity (Bug F) still present. Self-tie is gone (Bug A fixed). Election candidacy
and political_office facts are new from this commit but have no entity binding at 0.48 confidence.

---

### 20. Onet: CBA wójt brał łapówki (Ostrów)

**Expected:** anti_corruption_investigation, public-function proxy for wójt, contract amounts.

**Actual:** True (1.00), 1 fact — anti_corruption_investigation (0.71).

**Status: MINIMAL.** Anti-corruption fact correct. But no amount context, no wójt proxy entity,
no gmina contract facts. Very thin extraction for a detailed article.

---

### 21. AI42: Czy wójt ukrywa nepotyzm (Poczesna)

**Expected:** POLITICAL_OFFICE (Sosna → wójt), public_employment (Dobosz → urząd), kinship
(Dobosz → Sosna, kuzyn).

**Actual:** True (0.95), 9 facts — 2 public_employment, extended_kinship (Rafała Dobosza →
Arturem Sosną ✓ 0.70), 5 political_office, extended_kinship (kuzyn of Sosna → Arturem Sosną 0.51
← self-referential).

**Status: PASS.** Employment and kinship recovered. The "kuzyn of Sosna → Arturem Sosną" is
self-referential (the descriptor-proxy IS Dobosz, but it appears to refer back to Sosna). See issue #3.

---

### 22. WP: Opole — Wiedza, doświadczenie i kompetencje

**Expected:** APPOINTMENT (Królikowska → OUW), APPOINTMENT (Dariusz Jurek → UMWO),
kinship (Ogłaza-Królikowska partner, Dariusz-Monika Jurek spouses).

**Actual:** True (1.00), 25 facts — 2 governance_appointment (0.71×2 ✓), extended_kinship
(Ogłaza → Królikowska ✓ and Królikowska → Ogłaza ✓ — both directions), 1 governance_dismissal,
2 governance_appointment, 1 public_employment, personal_tie (Moniki Jurek → Jarosław Draguć ←
unexpected), 2 patronage_network_tie, 3 patronage_allegation, 2 extended_kinship (Dariusz Jurek →
Monika Jurek ✓×2 — duplicated), 7 political_office.

**Status: PASS.** Both kinship pairs recovered. Key appointments present.
The Monika Jurek → Jarosław Draguć personal tie is unexpected — possibly noise from a
quoted context. Duplicate kinship facts (both directions, twice each) suggest deduplication gap.

The governance_dismissal — could be Bug G regression (Monika Jurek dismissal from "odwołała się").
Needs debug run to confirm.

---

### 23. Polsat Interwencja: Bardzo rodzinne starostwo

**Expected:** POLITICAL_OFFICE (Pszczółkowska → sekretarz, Morawski → starosta), employment
for family members, kinship ties (mąż, synowie, synowa).

**Actual:** True (1.00), 19 facts — 1 public_employment, 7 political_office (0.48–0.61),
1 patronage_network_tie, 2 patronage_allegation, 4 extended_kinship (Pszczółkowska → Bartosz ✓,
syn of Jakub Mieszko → Jakub Mieszko ← self-referential, syn of Roman → Roman ← self-referential,
mąż of Pszczółkowska → Pszczółkowska ← self-referential), 1 personal_tie
(mąż of Pszczółkowska → Pszczółkowska ✓ direction correct but odd), 1 patronage_network_tie
(Pszczółkowska → mąż of Pszczółkowska 0.40 ← reversed).

**Status: PARTIAL.** Political offices partially recovered. Pszczółkowska → Bartosz kinship ✓.
Self-referential kinship for Jakub Mieszko, Roman, and "mąż" is issue #3. The employment facts
for Bartosz (PZD), Jakub Mieszko (coordinator), and daughter-in-law (PUP) are not bound to specific
organizations.

---

### 24. WP: Opole — Dwa dni i trzy umowy dla żony sekretarza

**Expected:** Compensation, employment, governance facts for Skokowski/Bebel/Wilk.

**Actual:** True (1.00), 28 facts — 1 patronage_network_tie (Agnieszka Bebel ✓), 1 party_affiliation
(Wojciech Wilk/PO ✓), 2 extended_kinship (Łukasz Skokowski ↔ Magdalena Skokowska ✓), 1 patronage_allegation,
1 public_employment, 1 governance_dismissal, 1 compensation, 3 governance_appointment, 3 governance_dismissal,
personal_tie (Krzysztof Staruch → Agnieszka Bebel ✓), 1 political_support (PiS → Staruch ✓),
8 political_office, 1 election_candidacy, 2 patronage_allegation.

**Status: PASS.** Good coverage — key facts present.

---

### 25. WP: Odpartyjnienie — Totalizator leca głowy

**Expected:** DISMISSAL (Krzemień/prezes), APPOINTMENT (Błaszkiewicz/acting), political context.

**Actual:** True (1.00), 15 facts — 5 governance_dismissal, 2 governance_appointment, personal_tie
(Sławomira Nitrasa → Stanisława Gawłowskiego ✓), 2 patronage_network_tie, 2 patronage_allegation, 3 political_office.

**Status: PASS.** Dismissals and appointments present. Political tie Nitras-Gawłowski ✓.

---

### 26. Business Insider: Kadrowa czystka PZU

**Expected:** DISMISSAL (entire board except Kubicza), 8 APPOINTMENTS, FORMER_PARTY (Olejniczak/SLD).

**Actual:** True (1.00), 5 facts — 1 governance_dismissal, 2 election_candidacy, 2 political_office.

**Status: FAILING.** Only 1 dismissal, 0 appointments. Bug D (list appointments) and Bug C
(z wyjątkiem) remain unfixed. The 8 new board members (Olejniczak et al.) are not extracted.
FORMER_PARTY_MEMBERSHIP for Olejniczak/SLD is missing despite that fact kind being implemented in
this commit.

---

### 27. Onet: Marcin Kopania w PHN

**Expected:** APPOINTMENT (Kopania → PHN), DISMISSAL (Kopania → MPRI), kinship (brat/Bartosz),
PUBLIC_CONTRACT (Bartosz → Totalizator), personal tie (Gawryszczak → Kropiwnicki).

**Actual:** True (0.95), 16 facts — 1 party_affiliation (Kopania/PO ✓), 1 extended_kinship
(Kopania → Bartosz ✓ 0.70), 2 public_employment, 1 governance_dismissal ✓, 1 governance_appointment ✓,
1 public_contract (Bartosz → Totalizator ✓), personal_tie (Gawryszczak → Kropiwnicki ✓,
Przemysław Wipler → Rafał Trzaskowski — context noise?), 1 patronage_network_tie (Wiesław Malicki ✓).

**Status: PASS.** All key facts present.

---

### 28. WP: Pensja 30 tys. zł — Prezesi spółek miejskich

**Expected:** Multiple COMPENSATION facts for Warsaw transport/utility companies, not FUNDING.

**Actual:** True (0.84), 7 facts — 6 compensation ✓, 1 funding ← wrong kind.

**Status: MOSTLY PASS.** 6 compensation facts. One funding fact is likely a false positive from
an ambiguous phrase. Entity binding not visible in slim but amounts are present.

---

### 29. Inwestycje Miejskie (tp.com.pl)

**Expected:** 2 APPOINTMENTS (Biernat/prezes, Rybacki/wiceprezes), 2 DISMISSALS (Stec, Śladowski).

**Actual:** True (0.70), 4 facts — 2 governance_appointment, 2 governance_dismissal.

**Status: PASS.** All 4 expected events present. Low relevance score (0.70) but correct.

---

### 30. Roosevelt history (olsztyn.com.pl)

**Expected:** False — true negative, local history article.

**Actual:** True (0.45), 0 facts.

**Status: PARTIAL FAIL.** Relevance threshold is borderline (0.45). Correct that no facts are
emitted. But the article is incorrectly scored as relevant rather than filtered at 0.20 like
the true negatives (TK, Meloni). If a downstream consumer filters on relevance=true, this will
be included. Consider whether 0.45 should cross the relevance boundary.

---

### 31. Niezależna (WP): Żona posła PiS zrezygnowała z Lublina (second Lublin article)

**Status: PASS** — see article #16 above. Same article, covered there.

---

## Cross-cutting issues

### Issue 1 — Missing party affiliations in several clear cases (medium priority)

The following expected party ties are absent:
- Pleszew24: Góralczyk/PSL (the article says "działaczka PSL" explicitly)
- Żona posła PiS zrezygnowała: Dariusz Stefaniuk/PiS
- Odpartyjnienie rad nadzorczych: Polska 2050 affiliation for appointees
- TVN Warszawa (Bielski): Karol Bielski/PSL

The party producer is not capturing affiliations when the link is indirect (e.g., "działaczka PSL",
party mentioned as organizational context) or when the person is described by role rather than named
inline with the party.

### Issue 2 — Self-referential / reversed kinship facts (medium priority)

Multiple articles produce kinship facts where:
- subject is a descriptor-proxy ("syn of X", "mąż of Y") and object is the same named person X or Y
- the relationship loops back to the anchor person instead of to the relative

Examples:
- "syn of Jakub Mieszko → Jakub Mieszko" (starostwo article)
- "córka of Rydzyka → Rydzyka" (Rydzyk article)
- "kuzyn of Sosna → Arturem Sosną" (Ai42 article)

The materialized form should be: subject=the-unnamed-relative, object=the-named-anchor.
When the proxy descriptor IS the subject, the object should be the named anchor, not itself.

### Issue 3 — Dual party membership false positive (low priority)

Bolesław Piecha is assigned both PO and PiS in the TVN24 Śląsk article. The party producer is
picking up party names that appear in negative/comparative context ("nie jak w PiS", "radna PO
pisze do premiera"). The producer needs better scope limiting for quoted-comparison contexts.

### Issue 4 — naTemat Giermasińska: persistent main-subject miss (high priority)

Marta Giermasińska has been the primary subject of the benchmark since 2026-04-22 and her
appointment still does not materialize. The NER lemmatization artifact ("Giermasińk") may cause
the candidate to be suppressed or mismatched. The "narzeczona" (fiancée) kinship signal also
needs to be added as a recognized proxy relation type.

### Issue 5 — Funding vs PUBLIC_CONTRACT for paid services (low priority)

TVN Warszawa Bielski article: 100k promotional payment from Urząd Marszałkowski to Bielski's
foundation is labeled FUNDING instead of PUBLIC_CONTRACT. This is Bug E from the prior report;
the paid-service trigger lemmas (reklama, promocja, obsługa) should route to PUBLIC_CONTRACT.

### Issue 6 — PZU list appointments still not extracted (high priority)

The 8 new board members appointed to PZU (Olejniczak et al.) produce zero appointment facts.
Bug D (list appointments) from the prior report is unresolved. This is the hardest recall gap in
the batch: a governance article with 8 explicitly named appointments yields nothing.
Bug C (z wyjątkiem Kubicza exception clause) is also unresolved.

### Issue 7 — FORMER_PARTY_MEMBERSHIP not firing (medium priority)

PZU article mentions Wojciech Olejniczak as "były szef SLD". The FORMER_PARTY_MEMBERSHIP fact kind
was implemented in this commit but is not appearing in the batch output. Either the trigger lemmas
("były", "dawny", "poprzedni" before party mention) are not matched, or the evidence is too thin
to materialize at the default threshold.

### Issue 8 — Political_office / election_candidacy facts have no entity binding (medium priority)

Many articles produce 3–9 political_office or election_candidacy facts all at exactly 0.48 confidence
with empty subject names. These facts carry no useful signal in the slim output: they confirm the
presence of political-role language in the article but don't tell the consumer who holds the office.
Either:
- raise the materialization threshold so only facts with a resolved subject appear, or
- ensure the frame-based political_office extraction binds a person before materializing.

### Issue 9 — Kinship deduplication gap (low priority)

Several articles produce the same kinship fact 2–3 times (both directions, or from multiple sentences):
- Sobolewska → Sobolewski appears 3 times in the Lublin article
- Ogłaza ↔ Królikowska appears in both directions in the Opole article
- Curyło ↔ Śliz appears in both directions in the synekury article

Materialization should deduplicate by (subject_entity, relation_type, object_entity) before emitting.

### Issue 10 — Bug G (odwołać się reflexive) may still be active (medium priority)

The Żona posła PiS zrezygnowała article produces a governance_appointment alongside dismissals,
which matches the Bug G pattern (reflexive "odwołała się" producing a spurious dismissal or the
dismissal triggering an appointment). A debug run on this article would confirm.

---

## Previously resolved (confirmed fixed in this run)

| Bug | Description | Status |
|-----|-------------|--------|
| Bug A | Self-tie (entity→entity in tie facts) | **FIXED** — no self-ties observed |
| Issue 3 (batch-2026-05-24) | Dismissal+appointment tight cluster guard | **FIXED** for the main case |

---

## Prioritized fix order

1. **Bug D — List appointments in PZU** — single highest-recall gap; 8 named
   appointments produce nothing.
2. **Giermasińska miss** — NER lemma issue + missing "narzeczona" kinship signal.
3. **Issue 1 — Missing party ties** — indirect/role-described affiliation not captured.
4. **Issue 8 — Political_office without entity binding** — noise in slim output.
5. **Bug G regression check** — debug Żona posła PiS zrezygnowała to confirm.
6. **Issue 2 — Self-referential kinship** — proxy descriptor looping to anchor.
7. **FORMER_PARTY_MEMBERSHIP not firing** — trigger lemma or threshold issue.
8. **Bug C — z wyjątkiem exception clause** — Kubicza spurious dismissal.
9. **Issue 9 — Kinship deduplication** — cosmetic but clutters slim output.
10. **Bug E — FUNDING vs PUBLIC_CONTRACT** — Bielski foundation case.

---

## What was checked

- Full V2 test suite: 209 tests, all pass.
- ruff check + ty check: clean.
- 33 article e2e runs (full batch).
- All outputs compared against `reports/expected_article_findings.md`.
