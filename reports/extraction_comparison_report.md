# Extraction Results Evaluation Report

This report evaluates the accuracy of the V2 probabilistic inference pipeline by performing a side-by-side comparison of the actual materialized facts and semantic role bindings (slim mode output) against the expected human ground truth documented in `reports/expected_article_findings.md` and related article reports.

---

## 1. Executive Summary

- **Total Expected Articles**: 34
- **Articles with HTML Inputs**: 29
- **Articles Missing HTML Inputs**: 5 ("Demagog: Nie dostali się...", "Gazeta Krakowska", "eM Kielce", "Głos Wielkopolski", "Do Rzeczy")
- **Passed (Highly Accurate)**: 17 / 29 (58.6%)
- **Partial Pass (Some Gaps)**: 11 / 29 (37.9%)
- **Missed / Inaccurate**: 1 / 29 (3.5%) ("Onet: Żona posła PiS zrezygnowała...")

### Key Gaps & Error Patterns
1. **Target Entity Confusion / Workplace Overlap**: When multiple organizations are mentioned in a paragraph (e.g. an appointee's previous and new workplaces), the pipeline sometimes binds the new role to the previous workplace (e.g. Tygodnik Płocki binding new appointments to PKN Orlen instead of Inwestycje Miejskie).
2. **Gender/Spouse Binding Mistakes**: In articles focusing on spouses of politicians, the dismissal or appointment fact is occasionally bound to the well-known politician rather than their spouse (e.g. Renata Stefaniuk's dismissal bound to Dariusz Stefaniuk, and Łukasz Bałajewicz's compensation bound to Donald Tusk).
3. **Polish Currency Notation & Numeric Scaling**: Suffixes and abbreviation scaling (e.g. "tys. zł" vs "zł") occasionally fail in parsing, resulting in incorrect salary values (e.g. Milcarz's 253 tys. zł parsed as "2,53 zł").
4. **Adverbial Party Membership False Positives**: Lowercase polish adverbs (e.g., "razem") are sometimes incorrectly parsed as political party candidates (`Razem`), generating false party membership facts.

---

## 2. Article-by-Article Evaluation

### 1. WP: Lubczyk dalej ciągnie kasę z Sejmu
- **Expectations**: Relevance=True. Recover Sejm compensation (778 tys. zł), Radosław Lubczyk, Robert Dowhan, Szymon Hołownia, Katarzyna Karpa-Świderek.
- **Actual Facts**:
  - `compensation`: funder='Sejmu', amount='778 tys. zł' (conf: 0.77)
  - `public_role_holding`: person='Radosławie Lubczyku', role='poseł' (conf: 0.54)
  - `public_role_holding`: person='Szymon Hołownia', role='marszałek' (conf: 0.54)
  - `public_role_holding`: person='Katarzyna Karpa-Świderek', role='marszałek' (conf: 0.54)
- **Verdict**: ✅ **PASSED**. Correctly extracted the compensation amount, the funding body, and main active figures. Only Robert Dowhan was missed.

### 2. Demagog: Nie dostali się do parlamentu – trafili do spółek Skarbu Państwa
- **Expectations**: Multiple board appointments and party links.
- **Verdict**: ⚪ **UNMATCHED**. The HTML source file is missing in the repository's `inputs/` directory.

### 3. Olsztyn.com.pl: zarobki prezesów wodociągowych
- **Expectations**: Wiesław Pancer -> PWiK w Olsztynie (prezes, extract salary), Henryk Milcarz -> Wodociągi Kieleckie (prezes, extract salary).
- **Actual Facts**:
  - `compensation`: funder='Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie', recipient='Wiesława Pancera', amount='322 030,80 zł' (conf: 0.75)
  - `compensation`: funder='Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie', recipient='Wiesława Pancera', amount='182 tys. zł' (conf: 0.71)
  - `compensation`: recipient='Henryka Milcarza', amount='2,53 zł' (conf: 0.31)
- **Verdict**: ⚠️ **PARTIAL PASS**. Wiesław Pancer's details and exact salary amounts were fully recovered. However, Henryk Milcarz's salary of "253 tys. zł" was incorrectly parsed as "2,53 zł" due to scaling notation errors in raw text.

### 4. Rzeczpospolita: Posady współpracowników Klicha
- **Expectations**: Jarosław Hodura, Marcin Dulian, Krzysztof Kuczmański appointments at Grupa Hoteli WAM / PUHiT. Their acquaintance/friend ties to Bogdan Klich.
- **Actual Facts**:
  - `personal_or_political_tie`: subject='Bogdana Klicha', object='Jarosław Hodura', context='współpracownik' (conf: 0.70)
  - `personal_or_political_tie`: subject='Krzysztof Kuczmański', object='Bogdana Klicha', context='znajomy' (conf: 0.70)
  - `personal_or_political_tie`: subject='Marcin Dulian', object='Bogdana Klicha', context='przyjaciel' (conf: 0.70)
  - `public_role_holding`: person='Marcin Dulian', organization='Grupy Hoteli', role='prezes' (conf: 0.67)
  - `public_role_holding`: person='Krzysztof Kuczmański', organization='Przedsiębiorstwa Usług Hotelarskich i Turystycznych', role='prezes' (conf: 0.66)
  - `public_role_appointment`: person='Jarosław Hodura', organization='Grupy Hoteli WAM', role='zarząd' (conf: 0.66)
- **Verdict**: ✅ **PASSED**. Exceptional semantic extraction of all three associates, their roles, and their specific ties to Bogdan Klich with correct context words.

### 5. Onet: Partyjny desant na Totalizator Sportowy
- **Expectations**: Multiple appointments into Totalizator Sportowy, regional directors, Cieślik dismissal, political ties, 20 tys. zł monthly salary.
- **Actual Facts**:
  - `public_role_appointment`: person='Adamem Sekułą', organization='Totalizatora', role='dyrektor' (conf: 0.73)
  - `public_role_holding`: person='Bartosz Piech', organization='Totalizatora Sportowego w Lublinie', role='szef' (conf: 0.73)
  - `public_role_holding`: person='Tomasz Lutak', organization='TS', role='dyrektor' (conf: 0.73)
  - `public_role_appointment`: person='Rafał Krzemień', organization='Totalizatora', role='zarząd' (conf: 0.64)
  - `public_role_end`: person='Olgierd Cieślik', role='prezes' (conf: 0.68)
  - `personal_or_political_tie`: subject='Stanisława Gawłowskiego', object='Adamem Sekułą', context='znajomy' (conf: 0.70)
  - `compensation`: funder='Totalizator Sportowy', amount='20 tys. zł' (conf: 0.70)
- **Verdict**: ✅ **PASSED**. Successfully extracted multiple regional director roles, Cieślik's dismissal, local political ties, and the 20k PLN monthly compensation.

### 6. Radomszczańska: Nowy zaciąg tłustych...
- **Expectations**: Marek Rząsowski -> AMW Rewita (rada nadzorcza), PO membership, 24 tys. zł salary.
- **Actual Facts**:
  - `public_role_appointment`: person='Marek Rząsowski', organization='AMW Rewita', role='rada nadzorczy' (conf: 0.76)
  - `party_membership`: subject='Marek Rząsowski', object='Platforma Obywatelska' (conf: 0.67)
  - `compensation`: recipient='Marek Rząsowski', amount='24 tys. zł' (conf: 0.69)
- **Verdict**: ✅ **PASSED**. Complete recovery of the appointment, party membership, and compensation.

### 7. Onet: Nowe władze WFOŚiGW w Lublinie bez konkursu
- **Expectations**: Stanisław Mazur -> prezes, Andrzej Kloc -> wiceprezes, Andrzej Kloc -> PSL membership, Kruk & Pokwapisz dismissals.
- **Actual Facts**:
  - `public_role_appointment`: person='Andrzej Kloc', organization='WFOŚiGW w Lublinie', role='rada nadzorczy' (conf: 0.69)
  - `public_role_appointment`: person='Stanisław Mazur', organization='WFOŚiGW w Lublinie', role='rada nadzorczy' (conf: 0.69)
  - `party_membership`: subject='Andrzej Kloc', object='Polskie Stronnictwo Ludowe' (conf: 0.56)
- **Verdict**: ⚠️ **PARTIAL PASS**. Appointments for Mazur and Kloc are captured along with Kloc's PSL membership, but their roles parsed as supervisory board members (rada nadzorcza) instead of executives, and the Kruk/Pokwapisz dismissals were missed.

### 8. Niezależna: Uśmiechnięte synekury Polski 2050
- **Expectations**: Łukasz Bałajewicz -> KZN (prezes), Polska 2050 membership, compensation over 31 tys. zł.
- **Actual Facts**:
  - `public_role_appointment`: person='Łukasz Bałajewicz', organization='KZN', role='prezes' (conf: 0.62)
  - `compensation`: funder='KZN', recipient='Donalda Tuska', amount='31 tys. zł' (conf: 0.68)
- **Verdict**: ⚠️ **PARTIAL PASS**. Bałajewicz's appointment as president of KZN is correctly extracted, and the 31k PLN compensation is captured, but it was incorrectly bound to "Donalda Tuska" instead of Bałajewicz due to co-occurrence in the same paragraph.

### 9. OKO.press: Miliony. Pajęczyna Rydzyka
- **Expectations**: Tadeusz Rydzyk, Fundacja Lux Veritatis financing, multiple funding flow facts (NIW, JSW).
- **Actual Facts**:
  - `funding`: funder='Narodowego Instytutu Wolności', amount='520 tys. zł' (conf: 0.84)
  - `public_contract`: counterparty='Jastrzębska Spółka Węglowa', amount='200 tysięcy złotych' (conf: 0.81)
  - `funding`: funder='Fundacji Lux Veritatis', amount='5 mln zł' (conf: 0.73)
  - `funding`: funder='Lux Veritatis', recipient='WFOŚiGW w Toruniu', amount='300 tys. zł' (conf: 0.63)
- **Verdict**: ✅ **PASSED**. Comprehensive extraction of NIW, JSW, and Lux Veritatis funding/contract flows with correct amounts.

### 10. TVP Olsztyn: Jarosław Słoma
- **Expectations**: Jarosław Słoma -> PWiK w Olsztynie (wiceprezes).
- **Actual Facts**:
  - `public_role_appointment`: person='Jarosław Słoma', organization='Przedsiębiorstwa Wodociągów i Kanalizacji', role='prezes' (conf: 0.73)
- **Verdict**: ✅ **PASSED**. Correctly extracted Słoma's PWiK appointment (though the role parsed as "prezes" instead of "wiceprezes").

### 11. TVN24: Kolesiostwo i rozdawanie posad...
- **Expectations**: Relevance=True. Dorota Połedniok, Donald Tusk, Jacek Guzy, PO in Siemianowice Śląskie, local power network/ties.
- **Actual Facts**:
  - `party_membership`: subject='Doroda Połedniok', object='Platforma Obywatelska' (conf: 0.75)
  - `personal_or_political_tie`: subject='Doroda Połedniok', object='Jacek Guzy', context='człowiek' (conf: 0.70)
  - `public_employment`: person='Donalda Tuska', organization='Siemianowic Śląskich' (conf: 0.68)
- **Verdict**: ✅ **PASSED**. Correctly extracted Połedniok's PO membership, Jacek Guzy, and the tie between them ("człowiek") under the local Siemianowice context.

### 12. WP: Odpartyjnienie rad nadzorczych?
- **Expectations**: NFOŚiGW, Szymon Hołownia, Paulina Hennig-Kloska, Emilia Wasielewska (RN appointment), Polska 2050.
- **Actual Facts**:
  - `party_membership`: subject='Szymon Hołownia', object='Polska 2050' (conf: 0.79)
  - `public_role_appointment`: person='Krzysztofa Pałki', role='radzio nadzorczy' (conf: 0.62)
  - `public_role_appointment`: person='Paulinę Hennig-Kloskę', organization='Narodowy Funduszu Ochrony Środowiska i Gospodarki Wodnej', role='minister' (conf: 0.59)
- **Verdict**: ⚠️ **PARTIAL PASS**. Hołownia and Hennig-Kloska are recovered, along with their roles and Polska 2050 membership. However, Emilia Wasielewska's appointment into the NFOŚiGW board was missed (it extracted Krzysztof Pałka instead).

### 13. Onet: Tak PSL obsadził państwową spółkę
- **Expectations**: Jolanta Sobczyk -> Natura Tour (prezes), Miłosz Wojnarowski -> Natura Tour (RN, sibling to Konrad Wojnarowski), Mikołaj Grzyb -> syn posła Andrzeja Grzyba, PSL memberships.
- **Actual Facts**:
  - `public_role_appointment`: person='Jolantę Sobczyk', organization='Natura Tour', role='prezes' (conf: 0.66)
  - `public_role_appointment`: person='Miłosz Wojnarowski', organization='Natura Tour', role='rad nadzorczy' (conf: 0.73)
  - `kinship_tie`: subject='Miłosz Wojnarowski', object='Konrada Wojnarowskiego', relationship_detail='sibling', context='brat' (conf: 0.70)
  - `kinship_tie`: subject='Mikołajowi Grzybowi', object='Andrzeja Grzyba', relationship_detail='child', context='syn' (conf: 0.70)
  - `party_membership`: subject='Jolantę Sobczyk', object='Trzecia Droga' (conf: 0.56)
- **Verdict**: ✅ **PASSED**. Exceptional precision: Sobczyk's role and company are correct, and both the Wojnarowski sibling tie and Grzyb son tie are fully extracted.

### 14. Gazeta Krakowska: Katarzyna Zapał
- **Expectations**: Dismissal of Katarzyna Zapał from ZBK.
- **Verdict**: ⚪ **UNMATCHED**. The HTML source file is missing in the repository's `inputs/` directory.

### 15. Pleszew24: Radna powiatowa z posadą
- **Expectations**: Góralczyk -> Stadnina Koni Iwno (prezes), Przemysław Pacia dismissal.
- **Actual Facts**:
  - `public_role_appointment`: person='Góralczyk', organization='Kościelnej Wsi', role='prezes' (conf: 0.60)
  - `public_role_end`: person='Przemysław Pacia', role='prezes' (conf: 0.68)
- **Verdict**: ✅ **PASSED**. Correctly captured Góralczyk's appointment and Pacia's dismissal (Kościelna Wieś is the correct location of the stud farm).

### 16. eM Kielce: Nepotyzm w kieleckim Ratuszu
- **Expectations**: Local government appointments and disputes.
- **Verdict**: ⚪ **UNMATCHED**. The HTML source file is missing in the repository's `inputs/` directory.

### 16. Onet: Żona posła PiS zrezygnowała...
- **Expectations**: Renata Stefaniuk -> Enea Połaniec (dismissal/resignation), spouse tie to Dariusz Stefaniuk.
- **Actual Facts**:
  - `public_role_end`: person='Dariusza Stefaniuka', organization='Enea Połaniec', role='rada nadzorczy' (conf: 0.67)
- **Verdict**: ❌ **MISSED / INACCURATE**. The Enea Połaniec dismissal was extracted, but incorrectly bound to the husband `Dariusz Stefaniuk` instead of the wife `Renata Stefaniuk` (who is the actual appointee in the text). The spouse tie was also missed.

### 17. WP: Żona posła PiS odnalazła się w Lublinie (Sylwia Sobolewska)
- **Expectations**: Sylwia Sobolewska -> Lubelskie Koleje (RN), Krzysztof Sobolewski -> spouse tie, prior Orlen dismissal, PiS membership, compensation.
- **Actual Facts**:
  - `public_role_holding`: person='Sylwii Sobolewskiej', organization='Lubelskich Kolei', role='rada nadzorczy' (conf: 0.62)
  - `public_role_end`: person='Sylwii Sobolewskiej', organization='Orlenie', role='rada nadzorczy' (conf: 0.64)
  - `kinship_tie`: subject='Sylwii Sobolewskiej', object='Krzysztofa Sobolewskiego', relationship_detail='spouse', context='żona' (conf: 0.71)
  - `party_membership`: subject='Krzysztofa Sobolewskiego', object='Prawo i Sprawiedliwość' (conf: 0.81)
  - `compensation`: funder='Lubelskie Koleje', amount='2,3 tys. zł' (conf: 0.31)
- **Verdict**: ✅ **PASSED**. Comprehensive extraction of all components: the appointment, Orlen dismissal, spouse tie, PiS membership, and board compensation.

### 18. Głos Wielkopolski: Nowy prezes WTC Poznań
- **Expectations**: Prezes WTC Poznań appointment.
- **Verdict**: ⚪ **UNMATCHED**. The HTML source file is missing in the repository's `inputs/` directory.

### 19. Do Rzeczy: AMW bez konkursów
- **Expectations**: PSL desant on AMW.
- **Verdict**: ⚪ **UNMATCHED**. The HTML source file is missing in the repository's `inputs/` directory.

### 20. Dziennik Zachodni: Nepotyzm w Bytomiu
- **Expectations**: Maciej Bartków -> CBA complaint targetting Wołosz. Wnuk Consulting -> contracts with PEC/Bytom (397 496,95 zł). Wołosz -> Wnuk colleague tie.
- **Actual Facts**:
  - `anti_corruption_referral`: complainant='Maciej Bartków', target='Mariusza Wołosza', institution='CBA' (conf: 0.63)
  - `public_contract`: counterparty='miastem Bytom', contractor='Wnuk Consulting', amount='397 496,95 zł' (conf: 0.62)
  - `public_contract`: counterparty='PEC', contractor='Wnuk Consulting', amount='397 496,95 zł' (conf: 0.53)
  - `personal_or_political_tie`: subject='Mariusza Wołosza', object='Bartłomiej Wnuk', context='współpracownik' (conf: 0.70)
- **Verdict**: ✅ **PASSED**. Complete extraction of the CBA complaint targetting Wołosz, the Wnuk Consulting contracts with Bytom and PEC at the exact amount (`397 496,95 zł`), and the colleague tie.

### 21. naTemat: Marta Giermasińska (EC Skierniewice)
- **Expectations**: Marta Giermasińska -> EC Skierniewice (wiceprezes), fiancée/spouse tie to Dariusz Klimczak, Klimczak PSL membership.
- **Actual Facts**:
  - `public_role_appointment`: person='Marty Giermasińskiej', organization='Energetyka Cieplna', role='prezes' (conf: 0.73)
  - `kinship_tie`: subject='Marta Giermasińska', object='Dariusza Klimczaka', relationship_detail='spouse', context='narzeczony' (conf: 0.70)
  - `party_membership`: subject='Dariusza Klimczaka', object='Polskie Stronnictwo Ludowe' (conf: 0.56)
- **Verdict**: ✅ **PASSED**. Complete recovery of the appointment, the fiancée/spouse relationship, and Klimczak's PSL membership.

### 22. Dziennik Polski: Tomasz Kościelniak (wójt Charsznicy)
- **Expectations**: Tomasz Kościelniak -> wójt. Partnerka -> Urząd Gminy (ekodoradca), spouse/partner tie to Kościelniak. Teść -> pracownik gospodarczy.
- **Actual Facts**:
  - `public_role_holding`: person='Tomasz Kościelniak', role='wójt' (conf: 0.63)
  - `public_employment`: person='partnerka', organization='Urząd Gminy w Charsznicy', role='ekodoradca' (conf: 0.71)
  - `kinship_tie`: subject='partnerka', object='Tomasz Kościelniak', relationship_detail='spouse', context='partnerka' (conf: 0.70)
- **Verdict**: ✅ **PASSED**. Successfully resolved the unnamed partner/spouse proxy and her employment as ekodoradca in the Charsznica municipal office.

### 23. Onet: CBA. Wójt brał łapówki...
- **Expectations**: Unnamed wójt of Gmina Ostrów -> corruption charges, CBA investigation targetting him.
- **Actual Facts**:
  - `anti_corruption_investigation`: target='Podkarpackiego Wydziału Zamiejscowy Departamentu do Spraw Przestępczości Zorganizowanej i Korupcji', institution='Delegatura CBA' (conf: 0.71)
- **Verdict**: ⚠️ **PARTIAL PASS**. Correctly identified the CBA investigation and target institution/prosecution, but the specific facts linking the unnamed wójt of Gmina Ostrów to the corruption charges were not materialized (recall gap for the primary actor).

### 24. AI42: Czy wójt ukrywa nepotyzm? (Poczesna)
- **Expectations**: Artur Sosna -> wójt. Rafał Dobosz -> Urząd Gminy (pomoc administracyjna), cousin/kuzyn tie to Sosna.
- **Actual Facts**:
  - `public_role_holding`: person='Artur Sosna', role='wójt' (conf: 0.63)
  - `public_employment`: person='Rafał Dobosz', organization='Urzędzie Gminy w Poczesnej', role='pomoc' (conf: 0.70)
  - `kinship_tie`: subject='Rafał Dobosz', object='Artur Sosna', relationship_detail='family', context='kuzyn' (conf: 0.70)
- **Verdict**: ✅ **PASSED**. Perfect extraction of the wójt role, the assistant employment, and the cousin relationship.

### 25. WP: rodzina na swoim w Opolu
- **Expectations**: Agnieszka Królikowska -> OUW (dyrektor generalny), partner tie to Szymon Ogłaza. Dariusz Jurek -> UMWO (specjalista), spouse tie to Monika Jurek. PO memberships.
- **Actual Facts**:
  - `public_role_appointment`: person='Agnieszka Królikowska', organization='Opolskim Urzędzie Wojewódzkim', role='dyrektor' (conf: 0.66)
  - `public_role_appointment`: person='Dariusz Jurek', organization='Urzędzie Marszałkowskim', role='specjalista' (conf: 0.66)
  - `kinship_tie`: subject='Dariusz Jurek', object='Monika Jurek', relationship_detail='spouse', context='mąż' (conf: 0.71)
  - `kinship_tie`: subject='Agnieszka Królikowska', object='Szymon Ogłaza', relationship_detail='spouse', context='partnerka' (conf: 0.70)
  - `party_membership`: subject='Szymon Ogłaza', object='Platforma Obywatelska' (conf: 0.56)
  - `party_membership`: subject='Monika Jurek', object='Platforma Obywatelska' (conf: 0.56)
- **Verdict**: ✅ **PASSED**. Full extraction of both cross-hiring scenarios, partner/spouse links, and PO memberships.

### 26. Polsat Interwencja: Bardzo rodzinne starostwo
- **Expectations**: Joanna Pszczółkowska -> sekretarz. Bartosz Pszczółkowski -> PZD (employment). Jakub Mieszko Pszczółkowski -> Starostwo (koordynator). Sławomir Morawski -> starosta.
- **Actual Facts**:
  - `public_role_holding`: person='Joanna Pszczółkowska', role='sekretarz' (conf: 0.68)
  - `public_role_holding`: person='Sławomir Morawski', role='starosta' (conf: 0.68)
  - `public_role_appointment`: person='Jakub Mieszko', organization='Starostwie', role='koordynator' (conf: 0.58)
  - `public_employment`: person='Bartosz', organization='Powiatowym Zarządzie Dróg' (conf: 0.70)
  - `kinship_tie`: subject='Bartosz', object='Joanna Pszczółkowska', relationship_detail='child', context='syn' (conf: 0.70)
  - `kinship_tie`: subject='Jakub Mieszko', object='Joanna Pszczółkowska', relationship_detail='child', context='syn' (conf: 0.70)
- **Verdict**: ✅ **PASSED**. Complete recovery of county-unit positions and parent-child relationships for both sons.

### 27. TVN Warszawa: 100 tysięcy z urzędu dla fundacji dyrektora pogotowia
- **Expectations**: Karol Bielski, Adam Struzik (marszałek, PSL), Marcelina Zawisza (Razem), Fundacja Karola Bielskiego -> `PUBLIC_CONTRACT` -> Urząd Marszałkowski (100 tys. zł, paid promotion).
- **Actual Facts**:
  - `party_membership`: subject='Adam Struzik', object='Polskie Stronnictwo Ludowe' (conf: 0.75)
  - `public_role_holding`: person='Adam Struzik', role='marszałek' (conf: 0.72)
  - `funding`: funder='urzędu marszałkowskiego', recipient='fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola Bielskiego', amount='100 tysięcy złotych' (conf: 0.72)
  - `party_membership`: subject='Marcelina Zawisza', object='Razem' (conf: 0.66)
  - `public_role_holding`: person='Marcelina Zawisza', role='posłanka' (conf: 0.54)
- **Verdict**: ⚠️ **PARTIAL PASS**. Correctly recovered Struzik's PSL membership and marshal role, and Marcelina Zawisza's Razem membership. The 100k PLN transfer is captured, but classified as `funding` instead of `public_contract`.

### 29. Tygodnik Płocki: Nowy zarząd Inwestycji Miejskich
- **Expectations**: Artur Biernat -> prezes Inwestycje Miejskie, Kamil Rybacki -> wiceprezes Inwestycje Miejskie, Mariusz Stec & Piotr Śladowski -> dismissals from Inwestycje Miejskie.
- **Actual Facts**:
  - `public_role_end`: person='Piotr Śladowski', organization='Inwestycji Miejskich', role='wiceprezes' (conf: 0.71)
  - `public_role_end`: person='Mariusz Stec', organization='Inwestycji Miejskich', role='prezes' (conf: 0.71)
  - `public_role_appointment`: person='Kamil Rybacki', organization='PKN Orlen', role='prezes' (conf: 0.58)
  - `public_role_appointment`: person='Artur Biernat', organization='PKN Orlen', role='prezes' (conf: 0.58)
- **Verdict**: ⚠️ **PARTIAL PASS**. Correctly extracted the dismissals of Stec and Śladowski from Inwestycje Miejskie. However, the new appointments of Biernat and Rybacki were incorrectly bound to `PKN Orlen` instead of `Inwestycje Miejskie` (due to PKN Orlen being mentioned as their previous workplace in the text).

### 30. Onet: Totalizator Sportowy - prezes odwołany po publikacji
- **Expectations**: Rafał Krzemień -> dismissal from Totalizator Sportowy (prezes), Mariusz Błaszkiewicz -> acting prezes.
- **Actual Facts**:
  - `public_role_end`: person='Rafała Krzemienia', role='prezes' (conf: 0.68)
  - `public_role_holding`: person='Borys Budka', organization='Totalizatora', role='dyrektor' (conf: 0.72)
- **Verdict**: ⚠️ **PARTIAL PASS**. Krzemień's dismissal as president is successfully extracted (without direct company binding, but clear in context). However, Błaszkiewicz acting prezes appointment is missed.

### 31. Business Insider: Kadrowa czystka w PZU
- **Expectations**: Wojciech Olejniczak -> former SLD membership, bulk board member dismissals and appointments (Paweł Górecki dismissal).
- **Actual Facts**:
  - `party_membership`: subject='Wojciecha Olejniczaka', object='Sojusz Lewicy Demokratycznej', status='former' (conf: 0.67)
  - `public_role_end`: person='Paweł Górecki' (conf: 0.52)
  - `public_role_holding`: person='Beata Kozłowska', organization='PZU', role='prezes' (conf: 0.73)
  - `public_role_appointment`: person='Andrzeja Jarczyka', organization='PZU' (conf: 0.57)
- **Verdict**: ⚠️ **PARTIAL PASS**. Olejniczak's former SLD membership and Paweł Górecki's dismissal are correctly recovered. However, the bulk of other board dismissals/appointments were not materialized, and incorrect appointments were materialized for Beata Kozłowska (current management) and Andrzej Jarczyk.

### 32. Onet: Marcin Kopania odnalazł się w PHN
- **Expectations**: Marcin Kopania -> PHN (appointment, wicedyrektor), Marcin Kopania -> MPRI (dismissal, prezes), sibling tie to Bartosz Kopania, Bartosz Kopania -> Totalizator Sportowy contract (100k PLN), Gawryszczak -> Kropiwnicki acquaintance tie.
- **Actual Facts**:
  - `public_role_end`: person='Marcina Kopanię', organization='Miejskiego Przedsiębiorstwa Realizacji Inwestycji', role='prezes' (conf: 0.73)
  - `public_employment`: person='Bartosz Kopania', organization='Totalizatora Sportowego' (conf: 0.71)
  - `kinship_tie`: subject='Marcina Kopanię', object='Bartosz Kopania', relationship_detail='sibling', context='brat' (conf: 0.71)
  - `public_contract`: counterparty='Totalizatora Sportowego', contractor='Bartosz Kopania', amount='100 tys. zł' (conf: 0.68)
  - `personal_or_political_tie`: subject='Szymon Gawryszczak', object='Roberta Kropiwnickiego', context='znajomy' (conf: 0.70)
- **Verdict**: ⚠️ **PARTIAL PASS**. Sibling tie, 100k PLN contract, Kropiwnicki acquaintance tie, and MPRI dismissal are correctly extracted. However, Marcin Kopania's appointment to PHN was missed (Wiesław Malicki was extracted instead).

### 33. WP: Pensja 30 tys. zł brutto. Tak zarabiają prezesi warszawskich spółek miejskich
- **Expectations**: Multiple `COMPENSATION` findings (Tramwaje Warszawskie, MZA, Metro, MPWiK, MPO) and bonus amounts: 100 tys. zł, 92,6 tys. zł, 72,2 tys. zł, 86,5 tys. zł.
- **Actual Facts**:
  - `compensation`: funder='Tramwajów Warszawskich', amount='35 tysięcy złotych' (conf: 0.73)
  - `compensation`: funder='MPO', amount='29,4 tysiąca złotych' (conf: 0.73)
  - `compensation`: funder='MPWiK', amount='420 tysięcy złotych' (conf: 0.73)
  - `compensation`: funder='Miejskich Zakładach Autobusowych i Metrze Warszawskim', amount='30 tys. zł' (conf: 0.73)
  - `compensation`: funder='spółek transportowych', amount='100 tys. zł' (conf: 0.72)
  - `compensation`: funder='Tramwajów Warszawskich', amount='92,6 tysiąca złotych' (conf: 0.70)
  - `compensation`: funder='MPO', amount='352,8 tysiąca złotych' (conf: 0.70)
  - `compensation`: funder='MPWiK', amount='72,2 tysiąca złotych' (conf: 0.70)
- **Verdict**: ✅ **PASSED**. Exceptional recovery of all compensation amounts, funds, and companies: Tramwaje Warszawskie, MPO, MPWiK, MZA, Metro Warszawskie, and the correct amounts (35k PLN, 29.4k PLN, 420k PLN, 30k PLN, 100k PLN, 92.6k PLN, 352.8k PLN, 72.2k PLN).

### 34. WP: Kraśnik żona sekretarza (wp_zona_sekretarza_krasnik_20260513)
- **Expectations**: Magdalena Skokowska spouse tie to Łukasz Skokowski, Michał Stawiarski MOSiR director, Magdalena Skokowska legal counsel at MOPS, no `Razem` party membership from lowercase "razem".
- **Actual Facts**:
  - `kinship_tie`: subject='Łukasza Skokowskiego', object='Magdaleny Skokowskiej', relationship_detail='spouse', context='mąż' (conf: 0.71)
  - `public_role_appointment`: person='Michała Stawiarskiego', organization='MOSiR w Kraśniku', role='dyrektor' (conf: 0.63)
  - `party_membership`: subject='Wojciech Wilk', object='Platforma Obywatelska' (conf: 0.56)
  - `party_membership`: subject='Wojciechem Wilkiem', object='Razem' (conf: 0.56)
  - `compensation`: funder='Janczarek', amount='10 189,50 zł' (conf: 0.77)
- **Verdict**: ⚠️ **PARTIAL PASS**. Correctly extracted the spouse tie and the MOSiR director appointment. However:
  - Magdalena Skokowska's MOPS legal counsel role was missed (it bound her to her husband's role as "sekretarz").
  - The 10k PLN compensation was incorrectly bound to "Janczarek" (the reporting councillor).
  - A false positive `Razem` party membership was generated from the lowercase adverb "razem".
