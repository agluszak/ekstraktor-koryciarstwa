# Pipeline Extraction Summary and Comparison

Comparison of active pipeline v2 output against expectations in `reports/expected_article_findings.md`.

### Overall Statistics
- **Relevance Matches**: 31 / 34 (91.2%)

## 1. WP: Lubczyk dalej ciągnie kasę z Sejmu. Ale są lepsi od niego
**URL**: https://wiadomosci.wp.pl/lubczyk-dalej-ciagnie-kase-z-sejmu-ale-sa-lepsi-od-niego-6998874649205248a
- **Filename**: `document-957b1b416028b76f.json`
- **Title**: *Lubczyk dalej ciągnie kasę z Sejmu. Ale są lepsi od niego*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `compensation` (conf: 0.773): funder='Sejmu', amount='778 tys. zł'
  - `public_role_holding` (conf: 0.721): person='niezawodowy', role='poseł', role_domain='political_office'
  - `public_role_end` (conf: 0.664): person='Lubczyk', organization='Sejmu'
  - `party_membership` (conf: 0.563): subject='Anna-Maria Żukowska', object='Lewica', status='unknown'
  - `public_role_holding` (conf: 0.544): person='Szymon Hołownia', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Radosławie Lubczyku', role='poseł', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Katarzyna Karpa-Świderek', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Lubczyk', role='poseł', role_domain='political_office'

## 2. Demagog: Nie dostali się do parlamentu – trafili do spółek Skarbu Państwa [Lista]
**URL**: https://demagog.org.pl/analizy_i_raporty/nie-dostali-sie-do-parlamentu-trafili-do-spolek-skarbu-panstwa-lista
- **Filename**: `document-fc08c34bd3a606f4.json`
- **Title**: *Rafał Trzaskowski wyrzucił go za hejterstwo. Teraz odnalazł się w spółce Skarbu Państwa*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.95)
- **Extracted Facts**:
  - `public_role_end` (conf: 0.727): person='Marcina Kopanię', organization='Miejskiego Przedsiębiorstwa Realizacji Inwestycji', role='prezes', role_domain='public_company_management'
  - `public_employment` (conf: 0.713): person='Bartosz Kopania', organization='Totalizatora Sportowego'
  - `kinship_tie` (conf: 0.708): subject='Marcina Kopanię', object='Bartosz Kopania', relationship_detail='sibling', context='brat'
  - `public_role_appointment` (conf: 0.708): person='Wiesław Malicki', organization='PHN', role='prezes', role_domain='public_company_management'
  - `personal_or_political_tie` (conf: 0.697): subject='Szymon Gawryszczak', object='Roberta Kropiwnickiego', context='znajomy'
  - `personal_or_political_tie` (conf: 0.697): subject='Rafała Trzaskowskiego', object='Magdalenie Biejat', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Przemysław Wipler', object='Magdalenie Biejat', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Przemysław Wipler', object='Rafała Trzaskowskiego', context='człowiek'
  - `public_contract` (conf: 0.683): counterparty='Totalizatora Sportowego', contractor='Bartosz Kopania', amount='100 tys. zł'
  - `public_employment` (conf: 0.625): person='Krzysztofa Gołąba', organization='warszawskiej'
  - `public_employment` (conf: 0.609): person='Malicki', organization='Ministerstwo'
  - `public_role_appointment` (conf: 0.603): person='Krzysztofa Gołąba', organization='PHN', role='doradca', role_domain='other_public_role'
  - `public_employment` (conf: 0.579): person='Przemysław Wipler', organization='Warszawy'
  - `personal_or_political_tie` (conf: 0.579): subject='Wiesław Malicki', object='Malicki', context='współpracownik'
  - `public_employment` (conf: 0.546): person='Marcina Kopanię', organization='Skarbu Państwa'
  - `public_employment` (conf: 0.542): person='Kopani', organization='Polskiego Holdingu Nieruchomości'
  - `public_role_end` (conf: 0.541): person='Marcina Kopanię', role='prezes', role_domain='public_company_management'
  - `public_role_end` (conf: 0.541): person='Rafała Trzaskowskiego', role='prezes', role_domain='public_company_management'

## 3. Olsztyn.com.pl: zarobki prezesów przedsiębiorstw wodociągowych
**URL**: https://www.olsztyn.com.pl/artykul,sprawdzili-zarobki-prezesow-przedsiebiorstw-wodociagowych-w-najwiekszych-miastach-ile-zarabia-prezes-wodkanu,33659.html
- **Filename**: `document-b00ab57c9aa249fd.json`
- **Title**: *Sprawdzili zarobki prezesów przedsiębiorstw wodociągowych w największych miastach. Ile zarabia prezes WodKanu w Olsztynie?*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.64)
- **Extracted Facts**:
  - `compensation` (conf: 0.748): funder='Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie', recipient='Wiesława Pancera', amount='322 030,80 zł'
  - `compensation` (conf: 0.708): funder='Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie', recipient='Wiesława Pancera', amount='182 tys. zł'
  - `public_role_holding` (conf: 0.526): person='prezes', role='prezes', role_domain='public_company_management'
  - `compensation` (conf: 0.381): funder='Stowarzyszenie Przyjazne Kielce', recipient='Wiesława Pancera', amount='1,88 zł'
  - `compensation` (conf: 0.308): recipient='Henryka Milcarza', amount='2,53 zł'
  - `compensation` (conf: 0.308): recipient='prezesa', amount='3,33 zł'

## 4. Rzeczpospolita: Posady współpracowników Klicha
**URL**: https://www.rp.pl/polityka/art15805981-posady-wspolpracownikow-klicha
- **Filename**: `document-e1dbc211ada890ae.json`
- **Title**: *Posady współpracowników Klicha*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.6)
- **Extracted Facts**:
  - `personal_or_political_tie` (conf: 0.697): subject='Bogdana Klicha', object='Jarosław Hodura', context='współpracownik'
  - `personal_or_political_tie` (conf: 0.697): subject='Krzysztof Kuczmański', object='Bogdana Klicha', context='znajomy'
  - `personal_or_political_tie` (conf: 0.697): subject='Marcin Dulian', object='Bogdana Klicha', context='przyjaciel'
  - `personal_or_political_tie` (conf: 0.697): subject='Jarosław Hodura', object='Bogdana Klicha', context='współpracownik'
  - `public_role_holding` (conf: 0.67): person='Marcin Dulian', organization='Grupy Hoteli', role='prezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.66): person='Krzysztof Kuczmański', organization='Przedsiębiorstwa Usług Hotelarskich i Turystycznych', role='prezes', role_domain='public_company_management', context='MON'
  - `public_role_appointment` (conf: 0.659): person='Jarosław Hodura', organization='Grupy Hoteli WAM', role='zarząd', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.544): person='Bogdana Klicha', role='minister', role_domain='political_office'
  - `patronage_network_tie` (conf: 0.524): subject='Marcin Dulian', object='Bogdana Klicha', institution='Grupy Hoteli'
  - `public_employment` (conf: 0.425): person='Bogdana Klicha', organization='MON'

## 5. Onet: Partyjny desant na Totalizator Sportowy
**URL**: https://wiadomosci.onet.pl/kraj/partyjny-desant-na-totalizator-sportowy-oni-dostali-lukratywne-stanowiska/7nvq01b
- **Filename**: `document-a1ee394bf319a368.json`
- **Title**: *Partyjny desant na Totalizator Sportowy. Polityczni działacze dostali lukratywne stanowiska*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `party_membership` (conf: 0.755): subject='Stanisława Gawłowskiego', object='Platforma Obywatelska', status='unknown'
  - `compensation` (conf: 0.731): funder='Totalizatora Sportowego', amount='345 tys. zł'
  - `public_role_holding` (conf: 0.727): person='Szymon Osowski', organization='Sieci Obywatelskiej Watchdog Polska', role='prezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.727): person='Magdalena Sekuła', organization='Ergo Areną', role='prezes', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.727): person='Adamem Sekułą', organization='Totalizatora', role='dyrektor', role_domain='institution_management'
  - `public_role_holding` (conf: 0.727): person='Bartosz Piech', organization='Totalizatora Sportowego w Lublinie', role='szef', role_domain='institution_management'
  - `public_role_holding` (conf: 0.727): person='Tomasz Lutak', organization='TS', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.724): person='Michała Małeckiego', role='członek zarząd', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.708): person='Sławomir Czwal', organization='Suwerennej Polski', role='radny', role_domain='political_office'
  - `compensation` (conf: 0.702): funder='Totalizator Sportowy', amount='20 tys. zł'
  - `public_role_end` (conf: 0.697): person='Anny Makarewicz', organization='Onetowi', role='dyrektor', role_domain='institution_management'
  - `public_role_end` (conf: 0.697): person='Stanisława Gawłowskiego', organization='Onetowi', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.697): person='Anny Makarewicz', organization='Onetowi', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.697): person='Stanisława Gawłowskiego', organization='Onetowi', role='dyrektor', role_domain='institution_management'
  - `personal_or_political_tie` (conf: 0.697): subject='Wilczyński', object='Sebastian Nowaczkiewicz', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Magdalena Sekuła', object='Adamem Sekułą', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Stanisława Gawłowskiego', object='Adamem Sekułą', context='znajomy'
  - `public_employment` (conf: 0.677): person='Sławomir Czwal', organization='Google'
  - `public_role_appointment` (conf: 0.675): person='Paweł Siedlecki', role='szef', role_domain='institution_management'
  - `public_role_end` (conf: 0.675): person='Michała Małeckiego', role='członek zarząd', role_domain='public_company_management'
  - `public_role_end` (conf: 0.675): person='Olgierd Cieślik', role='prezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.67): person='Sebastian Nowaczkiewicz', organization='Nowin', role='wójt', role_domain='political_office'
  - `public_role_end` (conf: 0.649): person='Sławomir Czwal'
  - `compensation` (conf: 0.637): funder='Skarbu Państwa', amount='353 mln zł'
  - `public_role_appointment` (conf: 0.637): person='Rafał Krzemień', organization='Totalizatora', role='zarząd', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.63): person='Stanisława Gawłowskiego', role='senator', role_domain='political_office'
  - `public_role_holding` (conf: 0.63): person='Stanisława Gawłowskiego', role='minister', role_domain='political_office'
  - `public_role_appointment` (conf: 0.622): person='Stanisława Gawłowskiego', organization='Ministerstwo Sportu', role='dyrektor', role_domain='institution_management', context='Ministerstwo Sportu'
  - `public_role_appointment` (conf: 0.619): person='Karol Wilczyński', organization='Totalizatora Sportowego', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.618): person='Sławomir Czwal', role='dyrektor', role_domain='institution_management'
  - `public_role_holding` (conf: 0.599): person='Stanisława Gawłowskiego', organization='Totalizatorze Sportowym', role='poseł', role_domain='other_public_role'
  - `public_role_holding` (conf: 0.599): person='Anny Makarewicz', organization='Totalizatorze Sportowym', role='poseł', role_domain='other_public_role'
  - `political_support` (conf: 0.575): subject='Koalicja Obywatelska', object='Sławomir Czwal'
  - `party_membership` (conf: 0.563): subject='Sławomir Rybicki', object='Platforma Obywatelska', status='unknown'
  - `party_membership` (conf: 0.563): subject='Sławomir Czwal', object='Koalicja Obywatelska', status='unknown'
  - `party_membership` (conf: 0.563): subject='Marcin Posadzy', object='Prawo i Sprawiedliwość', status='unknown'
  - `party_membership` (conf: 0.563): subject='Remigiuszowi Zagórskiemu', object='Lewica', status='unknown'
  - `party_membership` (conf: 0.563): subject='Tomasz Lutak', object='Prawo i Sprawiedliwość', status='former'
  - `party_membership` (conf: 0.563): subject='Karol Wilczyński', object='Koalicja Obywatelska', status='unknown'
  - `personal_or_political_tie` (conf: 0.562): subject='Karol Wilczyński', object='Wilczyński', context='związany'
  - `public_role_holding` (conf: 0.544): person='Stanisława Gawłowskiego', role='poseł', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Jacek Karnowski', role='poseł', role_domain='political_office'
  - `public_employment` (conf: 0.542): person='szefami', organization='Lublinie', role='szef'
  - `public_employment` (conf: 0.536): person='Michała Małeckiego', organization='Agencji Restrukturyzacji i Modernizacji Rolnictwa'
  - `public_role_holding` (conf: 0.532): person='Sławomir Czwal', role='prezes', role_domain='political_office'
  - `public_employment` (conf: 0.506): person='Piotr Kaciunka', organization='Katowicach'
  - `election_candidacy` (conf: 0.48): person='Tomasz Lutak'
  - `public_role_appointment` (conf: 0.464): person='dyrektora', role='dyrektor', role_domain='institution_management'
  - `kinship_tie` (conf: 0.268): subject='partner of Donaldem Tuskiem', object='Stanisława Gawłowskiego'

## 6. Radomszczańska: Nowy zaciąg tłustych...
**URL**: https://radomszczanska.pl/artykul/nowy-zaciag-tlustych-n1256470
- **Filename**: `document-52274d3cd5381f2c.json`
- **Title**: *Hotelarz Rząsowski: Robota w spółce podległej MON dla radnego powiatowego. Nowy zaciąg tłustych kotów?*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_role_appointment` (conf: 0.755): person='Marek Rząsowski', organization='AMW Rewita', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_employment` (conf: 0.716): person='Marku', organization='starostwu', role='sekretarz'
  - `public_employment` (conf: 0.71): person='Marku', organization='starostwu'
  - `kinship_tie` (conf: 0.708): subject='Mirella Zugaj', object='Radka Zugaja', relationship_detail='spouse', context='żona'
  - `personal_or_political_tie` (conf: 0.697): subject='Marek Rząsowski', object='Jacka Łęskiego', context='związany'
  - `compensation` (conf: 0.687): recipient='Marek Rząsowski', amount='24 tys. zł'
  - `party_membership` (conf: 0.666): subject='Marek Rząsowski', object='Platforma Obywatelska', status='unknown'
  - `public_role_holding` (conf: 0.544): person='Marek Rząsowski', role='radny', role_domain='political_office'
  - `election_candidacy` (conf: 0.48): person='Jacka Łęskiego'

## 7. Onet: Nowe władze WFOŚiGW w Lublinie bez konkursu
**URL**: https://wiadomosci.onet.pl/lublin/nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow/cpw9ltt
- **Filename**: `document-23b7a85f053e9abe.json`
- **Title**: *Bez konkursu i bez wysłuchania kandydatów. Tak nowa władza wprowadza swoich ludzi do ważnej instytucji*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.97)
- **Extracted Facts**:
  - `personal_or_political_tie` (conf: 0.697): subject='Stanisław Mazur', object='Andrzej Kloc', context='człowiek'
  - `public_role_appointment` (conf: 0.691): person='Andrzej Kloc', organization='Wojewódzkim Funduszem Ochrony Środowiska i Gospodarki Wodnej w Lublinie', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.691): person='Stanisław Mazur', organization='Wojewódzkim Funduszem Ochrony Środowiska i Gospodarki Wodnej w Lublinie', role='rada nadzorczy', role_domain='supervisory_board'
  - `party_membership` (conf: 0.563): subject='Andrzej Kloc', object='Polskie Stronnictwo Ludowe', status='unknown'

## 8. Niezależna: Uśmiechnięte synekury Polski 2050
**URL**: https://niezalezna.pl/polityka/usmiechniete-synekury-polski-2050-31-tys-zl-dla-prezesa-kzn-i-etaty-dla-dzialaczy/533532
- **Filename**: `document-4f6b7548a2d87cf8.json`
- **Title**: *Uśmiechnięte synekury Polski 2050. 31 tys. zł dla prezesa KZN i etaty dla działaczy | Niezalezna.pl*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `compensation` (conf: 0.731): funder='KZN', amount='11 tys. zł'
  - `compensation` (conf: 0.702): funder='KZN', amount='10 tys. zł'
  - `personal_or_political_tie` (conf: 0.697): subject='Waldemar Buda', object='Gabriela Sowa', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Bałajewicza', object='Rafała Kukli', context='znajomy'
  - `personal_or_political_tie` (conf: 0.697): subject='Michał Szymczyk', object='Bałajewicza', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Emil Rojek', object='Szymona Hołowni', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Łukasz Bałajewicz', object='Szymona Hołowni', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Łukasz Bałajewicz', object='Emil Rojek', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Szymona Hołowni', object='Emil Rojek', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Szymona Hołowni', object='Łukasz Bałajewicz', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Bartosz Wilk', object='Szymona Hołowni', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Bartosz Wilk', object='Emil Rojek', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Bartosz Wilk', object='Łukasz Bałajewicz', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Rafał Komarewicz', object='Szymona Hołowni', context='baron'
  - `compensation` (conf: 0.68): funder='KZN', recipient='Donalda Tuska', amount='31 tys. zł'
  - `kinship_tie` (conf: 0.647): subject='Pawła Śliza', object='Filip Curyło', relationship_detail='spouse'
  - `public_role_holding` (conf: 0.631): person='Katarzyna Pełczyńska-Nałęcz', organization='KZN', role='rado', role_domain='other_public_role', context='Ministerstwo Funduszy i Polityki Regionalnej'
  - `public_role_appointment` (conf: 0.619): person='Łukasz Bałajewicz', organization='KZN', role='prezes', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.619): person='Filip Curyło', role='radzio nadzorczy', role_domain='supervisory_board'
  - `public_role_holding` (conf: 0.618): person='Filip Curyło', role='rado', role_domain='other_public_role'
  - `public_role_holding` (conf: 0.616): person='Szymona Hołowni', organization='Skarbu Państwa', role='zarząd', role_domain='public_company_management', context='Skarbu Państwa'
  - `public_role_holding` (conf: 0.616): person='Rafał Komarewicz', organization='Skarbu Państwa', role='zarząd', role_domain='public_company_management', context='Skarbu Państwa'
  - `public_role_holding` (conf: 0.587): person='Katarzyna Pełczyńska-Nałęcz', organization='KZN', role='prezes', role_domain='public_company_management', context='Ministerstwo Funduszy i Polityki Regionalnej'
  - `public_role_appointment` (conf: 0.582): person='Szymona Hołowni', organization='Sejmu', role='przewodniczący', role_domain='other_public_role'
  - `public_role_appointment` (conf: 0.582): person='Bartosz Wilk', organization='Sejmu', role='przewodniczący', role_domain='other_public_role'
  - `political_support` (conf: 0.575): subject='Polska 2050', object='Michał Szymczyk'
  - `public_role_appointment` (conf: 0.57): person='Prezes', organization='KZN', role='prezes', role_domain='public_company_management', context='Skarbu Państwa'
  - `public_role_holding` (conf: 0.555): person='Sebastian Puchajda', organization='SIM', role='doradca', role_domain='other_public_role'
  - `public_role_appointment` (conf: 0.555): person='Szymona Hołowni', organization='Sejmu', role='radzio nadzorczy', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.555): person='Emil Rojek', organization='Sejmu', role='radzio nadzorczy', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.555): person='Łukasz Bałajewicz', organization='Sejmu', role='radzio nadzorczy', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.554): person='Emil Rojek', organization='RN KZN', role='minister', role_domain='other_public_role'
  - `public_role_holding` (conf: 0.544): person='Rafała Kukli', role='burmistrz', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Szymona Hołowni', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Rafał Komarewicz', role='poseł', role_domain='political_office'
  - `public_role_appointment` (conf: 0.532): person='Pawła Śliza', role='radzio nadzorczy', role_domain='political_office'
  - `public_role_appointment` (conf: 0.532): person='Filip Curyło', role='radzio nadzorczy', role_domain='political_office'
  - `patronage_network_tie` (conf: 0.524): subject='Szymona Hołowni', object='Rafał Komarewicz', institution='„GP”'
  - `public_role_appointment` (conf: 0.513): person='Szymona Hołowni', role='radzio nadzorczy', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.513): person='Emil Rojek', role='radzio nadzorczy', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.513): person='Łukasz Bałajewicz', role='radzio nadzorczy', role_domain='public_company_management'
  - `election_candidacy` (conf: 0.48): person='Rafała Kukli'
  - `election_candidacy` (conf: 0.48): person='Michał Szymczyk'
  - `public_employment` (conf: 0.443): person='Waldemar Buda', organization='KZN'
  - `public_employment` (conf: 0.346): person='Rafała Kukli', organization='KZN'

## 9. OKO.press: Miliony. Pajęczyna Rydzyka
**URL**: https://oko.press/miliony-pajeczyna-rydzyka
- **Filename**: `document-173edfb3cc5e3032.json`
- **Title**: *Miliony złotych od państwa na „pajęczynę” o. Rydzyka. Liczymy pieniądze, pokazujemy zdjęcia z drona*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `funding` (conf: 0.841): funder='Narodowego Instytutu Wolności', amount='520 tys. zł'
  - `public_contract` (conf: 0.805): counterparty='Jastrzębska Spółka Węglowa', amount='200 tysięcy złotych'
  - `funding` (conf: 0.739): amount='520 tys. zł'
  - `funding` (conf: 0.731): funder='Fundacji Lux Veritatis', amount='5 mln zł'
  - `kinship_tie` (conf: 0.697): subject='córka of Zbigniewa Ziobro', object='Zbigniewa Ziobro', relationship_detail='child', context='córka'
  - `funding` (conf: 0.626): funder='Lux Veritatis', recipient='Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu', amount='300 tys. zł'
  - `public_contract` (conf: 0.62): counterparty='Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu', contractor='Lux Veritatis', amount='300 tys. zł'
  - `funding` (conf: 0.557): funder='Fundacji Lux Veritatis', recipient='Jastrzębskie Zakłady Remontowe', amount='100 tys. zł'
  - `public_role_holding` (conf: 0.526): person='Zbigniewa Ziobro', organization='WFOŚiGW w Toruniu', role='prezes', role_domain='other_public_role'
  - `public_role_holding` (conf: 0.526): person='Ireneusz Stachowiak', organization='WFOŚiGW w Toruniu', role='prezes', role_domain='other_public_role'

## 10. TVP Olsztyn: Jarosław Słoma w zarządzie olsztyńskich wodociągów
**URL**: https://olsztyn.tvp.pl/41863255/z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow
- **Filename**: `document-f5e2dbc98f974e2a.json`
- **Title**: *Z wiceprezydenta na wiceprezesa. Jarosław Słoma w zarządzie olsztyńskich wodociągów*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.45)
- **Extracted Facts**:
  - `public_role_appointment` (conf: 0.727): person='Jarosław Słoma', organization='Przedsiębiorstwa Wodociągów i Kanalizacji', role='prezes', role_domain='public_company_management'

## 11. TVN24: Kolesiostwo i rozdawanie posad...
**URL**: https://tvn24.pl/polska/kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831v
- **Filename**: `document-7f4fd3f91fc24873.json`
- **Title**: *"Kolesiostwo i rozdawanie posad. Miasto umiera". Radna PO ze Śląska pisze do premiera*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `party_membership` (conf: 0.754): subject='Doroda Połedniok', object='Platforma Obywatelska', status='unknown'
  - `public_role_holding` (conf: 0.726): person='Bolesław Piecha', organization='Senatu', role='senator', role_domain='political_office'
  - `personal_or_political_tie` (conf: 0.697): subject='Doroda Połedniok', object='Jacek Guzy', context='człowiek'
  - `public_employment` (conf: 0.678): person='Donalda Tuska', organization='Siemianowic Śląskich'
  - `party_membership` (conf: 0.563): subject='Bolesław Piecha', object='Prawo i Sprawiedliwość', status='unknown'
  - `election_candidacy` (conf: 0.48): person='Jacek Guzy'

## 12. WP: Odpartyjnienie rad nadzorczych? "Nie tak miało być, wygląda to bardzo źle"
**URL**: https://wiadomosci.wp.pl/odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle-6996280410176160a
- **Filename**: `document-fbcdc570dcaf8c7c.json`
- **Title**: *Odpartyjnienie rad nadzorczych? "Nie tak miało być, wygląda to bardzo źle"*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `party_membership` (conf: 0.788): subject='Szymon Hołownia', object='Polska 2050', status='unknown'
  - `personal_or_political_tie` (conf: 0.697): subject='Paweł Marciniak', object='Szymon Hołownia', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Szymon Hołownia', object='Paweł Marciniak', context='człowiek'
  - `compensation` (conf: 0.691): funder='Wirtualnej Polski', recipient='Krzysztof Izdebski', amount='8 tys. zł'
  - `public_role_holding` (conf: 0.678): person='Paweł Marciniak', organization='Sejmu', role='marszałek', role_domain='political_office', context='Ministerstwo Klimatu i Środowiska'
  - `public_role_holding` (conf: 0.678): person='Szymon Hołownia', organization='Sejmu', role='marszałek', role_domain='political_office', context='Ministerstwo Klimatu i Środowiska'
  - `public_role_holding` (conf: 0.658): person='Paweł Pudłowski', organization='Wirtualnej Polski', role='przewodniczący', role_domain='other_public_role'
  - `public_role_holding` (conf: 0.632): person='Szymon Hołownia', role='marszałek', role_domain='political_office'
  - `public_role_end` (conf: 0.619): person='Szymon Hołownia', role='radzio nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.619): person='Szymon Hołownia', role='radzio nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.618): person='Krzysztofa Pałki', role='radzio nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.606): person='Szymon Hołownia', organization='Sejmie', role='marszałek', role_domain='political_office', context='Skarbu Państwa'
  - `public_role_appointment` (conf: 0.588): person='Mariola Rzepka', organization='Narodowy Funduszu Ochrony Środowiska i Gospodarki Wodnej', role='minister', role_domain='political_office', context='Skarbu Państwa'
  - `public_role_appointment` (conf: 0.588): person='Paulinę Hennig-Kloskę', organization='Narodowy Funduszu Ochrony Środowiska i Gospodarki Wodnej', role='minister', role_domain='political_office', context='Skarbu Państwa'
  - `public_role_end` (conf: 0.57): person='Szymon Hołownia', organization='Sejmie', role_domain='political_office', context='Skarbu Państwa'
  - `party_membership` (conf: 0.563): subject='Ewy Patalas', object='Polska 2050', status='unknown'
  - `party_membership` (conf: 0.563): subject='Marek Papuga', object='Sojusz Lewicy Demokratycznej', status='unknown'
  - `public_role_holding` (conf: 0.544): person='Olgierd Geblewicz', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Emilii Wasielewskiej', role='radna', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Paulinę Hennig-Kloskę', role='minister', role_domain='political_office'

## 13. Onet: Tak PSL obsadził państwową spółkę. Pracę dostał m.in. 29-letni brat wiceministra
**URL**: https://wiadomosci.onet.pl/kraj/tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra/ezt8y9t
- **Filename**: `document-f0783c96c2832eb7.json`
- **Title**: *Znajoma ministra, brat wiceministra. Tak PSL obsadził państwową spółkę*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `compensation` (conf: 0.731): funder='PKP', amount='53 mln zł'
  - `public_role_appointment` (conf: 0.727): person='Miłosz Wojnarowski', organization='Natura Tour', role='rad nadzorczy', role_domain='supervisory_board'
  - `public_role_holding` (conf: 0.727): person='Dariusza Klimczaka', organization='PKP', role='minister', role_domain='political_office'
  - `public_role_holding` (conf: 0.722): person='Piotra Smogorzewskiego', organization='Natura Tour', role='członek zarząd', role_domain='public_company_management'
  - `kinship_tie` (conf: 0.721): subject='narzeczony of Dariusza Klimczaka', object='Dariusza Klimczaka', relationship_detail='spouse', context='narzeczony'
  - `public_role_holding` (conf: 0.708): person='Wojnarowskich', organization='Natura Tour', role='członek zarząd', role_domain='public_company_management'
  - `kinship_tie` (conf: 0.697): subject='Marta Giermasińska', object='Dariusza Klimczaka', relationship_detail='spouse', context='narzeczony'
  - `kinship_tie` (conf: 0.697): subject='Miłosz Wojnarowski', object='Konrada Wojnarowskiego', relationship_detail='sibling', context='brat'
  - `kinship_tie` (conf: 0.697): subject='Mikołajowi Grzybowi', object='Andrzeja Grzyba', relationship_detail='child', context='syn'
  - `kinship_tie` (conf: 0.697): subject='Piotra Smogorzewskiego', object='Romana Smogorzewskiego', relationship_detail='sibling', context='brat'
  - `personal_or_political_tie` (conf: 0.697): subject='Jażdżyku', object='Marta Giermasińska', context='powiązać'
  - `personal_or_political_tie` (conf: 0.697): subject='Andrzej Melon', object='Krzysztof Jażdżyk', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Jolantę Sobczyk', object='Dariusza Klimczaka', context='znajomy'
  - `public_role_holding` (conf: 0.675): person='Dariusza Klimczaka', role='wiceprezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.675): person='Krzysztof Jażdżyk', role='prezydent', role_domain='political_office'
  - `public_role_holding` (conf: 0.675): person='Piotra Smogorzewskiego', role='prezydent', role_domain='political_office'
  - `public_role_appointment` (conf: 0.675): person='Piotra Smogorzewskiego', role='członek zarząd', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.675): person='Jolantę Sobczyk', role='prezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.669): person='Dariusza Klimczaka', organization='OSP Czerniewice', role='wiceszef', role_domain='institution_management'
  - `public_role_holding` (conf: 0.659): person='Jolantę Sobczyk', organization='Gminnego Centrum Kultury, Rekreacji i', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.656): person='Piotra Smogorzewskiego', organization='Natura Tour', role='prezes', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.656): person='Jolantę Sobczyk', organization='Natura Tour', role='prezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.651): person='Andrzej Melon', role='rad', role_domain='other_public_role'
  - `public_role_holding` (conf: 0.651): person='Piotra Smogorzewskiego', role='członek zarząd', role_domain='public_company_management'
  - `public_role_end` (conf: 0.651): person='Piotra Smogorzewskiego', role='członek zarząd', role_domain='public_company_management'
  - `kinship_tie` (conf: 0.647): subject='Jażdżyku', object='Dariusza Klimczaka', relationship_detail='spouse'
  - `public_role_appointment` (conf: 0.619): person='Dariusza Klimczaka', organization='PKP', role='prezes', role_domain='political_office'
  - `public_role_appointment` (conf: 0.619): person='Jolantę Sobczyk', organization='PKP', role='prezes', role_domain='political_office'
  - `public_role_appointment` (conf: 0.618): person='Dariusza Klimczaka', role='wiceszef', role_domain='institution_management'
  - `personal_or_political_tie` (conf: 0.579): subject='Wojnarowskich', object='Wojnarowskim', context='związany'
  - `political_support` (conf: 0.575): subject='Polskie Stronnictwo Ludowe', object='Jolantę Sobczyk'
  - `party_membership` (conf: 0.563): subject='Andrzeja Grzyba', object='Polskie Stronnictwo Ludowe', status='unknown'
  - `party_membership` (conf: 0.563): subject='Jolantę Sobczyk', object='Trzecia Droga', status='unknown'
  - `party_membership` (conf: 0.563): subject='Jan Grabiec', object='Platforma Obywatelska', status='unknown'
  - `public_role_end` (conf: 0.544): person='Dariusza Klimczaka'
  - `public_role_end` (conf: 0.544): person='Jażdżyku'
  - `public_role_appointment` (conf: 0.544): person='Wojciechem Brzeskim'
  - `public_role_holding` (conf: 0.544): person='Dariusza Klimczaka', role='minister', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Jolantę Sobczyk', role='minister', role_domain='political_office'
  - `patronage_network_tie` (conf: 0.524): subject='Jolantę Sobczyk', object='Dariusza Klimczaka', institution='PKP'
  - `election_candidacy` (conf: 0.48): person='Wojciechem Brzeskim'
  - `election_candidacy` (conf: 0.48): person='Piotra Smogorzewskiego'
  - `public_role_holding` (conf: 0.474): person='Wojciechem Brzeskim', role='radny', role_domain='administrative_office'
  - `public_role_end` (conf: 0.455): person='Jan Grabiec', role_domain='political_office'
  - `compensation` (conf: 0.277): funder='PKP', amount='3,7 tys. zł'

## 14. Gazeta Krakowska: To koniec rządów Katarzyny Zapał w Zarządzie Budynków Komunalnych
**URL**: https://gazetakrakowska.pl/za-jej-czasow-wybuchla-w-krakowie-wielka-afera-to-koniec-rzadow-katarzyny-zapal-w-zarzadzie-budynkow-komunalnych/ar/c1p2-27523231
⚠️ **Status**: No matching pipeline output document found.

## 15. Pleszew24: Radna powiatowa z posadą. Zmiana prezesa słynnej państwowej stadniny koni
**URL**: https://pleszew24.info/pl/12_biznes/16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni.html
- **Filename**: `document-bca39f694cdf57f5.json`
- **Title**: *Radna powiatowa z posadą prezesa państwowej spółki. A. Góralczyk odpowiadać będzie za stadninę koni pełnej krwi angielskiej*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `personal_or_political_tie` (conf: 0.697): subject='A.', object='Góralczyk', context='związany'
  - `public_role_holding` (conf: 0.675): person='Przemysław Pacia', role='prezes', role_domain='public_company_management'
  - `public_role_end` (conf: 0.675): person='Przemysław Pacia', role='prezes', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.597): person='Góralczyk', organization='Kościelnej Wsi', role='prezes', role_domain='public_company_management', context='Skarbu Państwa'
  - `public_role_appointment` (conf: 0.597): person='A.', organization='Kościelnej Wsi', role='prezes', role_domain='public_company_management', context='Skarbu Państwa'
  - `patronage_allegation` (conf: 0.382): complainant='Góralczyk', target='A.', context='Radna'

## 16. eM Kielce: Zarzuty o nepotyzm i ostre personalne spory w kieleckim Ratuszu
**URL**: https://emkielce.pl/miasto-4/zarzuty-o-nepotyzm-i-ostre-personalne-spory-w-kieleckim-ratuszu-80925
⚠️ **Status**: No matching pipeline output document found.

## 16. Onet: Żona posła PiS zrezygnowała z zasiadania w radach nadzorczych państwowych spółek
**URL**: https://wiadomosci.onet.pl/lublin/zona-posla-pis-zrezygnowala-z-zasiadania-w-radach-nadzorczych-panstwowych-spolek/hhpswdf
- **Filename**: `document-21eb69e6db17272b.json`
- **Title**: *Żona posła PiS zrezygnowała z zasiadania w radach nadzorczych państwowych spółek*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_role_end` (conf: 0.727): person='Jacka Sasina', organization='Portu Lotniczego Lublin', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_holding` (conf: 0.727): person='Jacka Sasina', organization='Portu Lotniczego Lublin', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_holding` (conf: 0.68): person='Angelika Konaszczuk', organization='Portu Lotniczego w Lublinie', role='prezes', role_domain='public_company_management'
  - `public_role_holding` (conf: 0.675): person='Dariusza Stefaniuka', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_holding` (conf: 0.666): person='Dariusza Stefaniuka', organization='Enea Połaniec', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_end` (conf: 0.666): person='Dariusza Stefaniuka', organization='Enea Połaniec', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.658): person='Dariusza Stefaniuka', organization='MBA', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_holding` (conf: 0.544): person='Dariusza Stefaniuka', role='poseł', role_domain='political_office'
  - `public_role_holding` (conf: 0.503): person='Angelika Konaszczuk', role='poseł', role_domain='political_office'
  - `public_role_end` (conf: 0.503): person='Angelika Konaszczuk', role='poseł', role_domain='political_office'

## 17. WP: Żona posła PiS odnalazła się w Lublinie. Była "ofiarą" uchwały o nepotyzmie
**URL**: https://wiadomosci.wp.pl/zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie-7273798906222848a
- **Filename**: `document-52df1436a9a8d7c0.json`
- **Title**: *Żona posła PiS odnalazła się w Lublinie. Była "ofiarą" uchwały o nepotyzmie*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `party_membership` (conf: 0.807): subject='Krzysztofa Sobolewskiego', object='Prawo i Sprawiedliwość', status='former'
  - `party_membership` (conf: 0.796): subject='Jarosława Kaczyńskiego', object='Prawo i Sprawiedliwość', status='unknown'
  - `kinship_tie` (conf: 0.708): subject='Sylwii Sobolewskiej', object='Krzysztofa Sobolewskiego', relationship_detail='spouse', context='żona'
  - `kinship_tie` (conf: 0.697): subject='Przemysław Czarnek', object='Krzysztofa Sobolewskiego', relationship_detail='spouse', context='żona'
  - `personal_or_political_tie` (conf: 0.697): subject='Stawiarski', object='Morawieckiego', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Mateuszem Morawieckim', object='Stawiarski', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Krzysztofa Sobolewskiego', object='Morawieckiego', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Krzysztofa Sobolewskiego', object='Stawiarski', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Krzysztofa Sobolewskiego', object='Mateuszem Morawieckim', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Krzysztofa Sobolewskiego', object='Jarosława Kaczyńskiego', context='współpracownik'
  - `public_role_holding` (conf: 0.675): person='Krzysztofa Sobolewskiego', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_end` (conf: 0.675): person='Krzysztofa Sobolewskiego', role='sekretarz', role_domain='administrative_office'
  - `compensation` (conf: 0.657): funder='Przedsiębiorstwie Gospodarki Komunalnej w Kamieniu Pomorskim', recipient='Sylwii Sobolewskiej', amount='niemal pół miliona złotych'
  - `public_role_holding` (conf: 0.651): person='Jarosława Kaczyńskiego', role='marszałek', role_domain='political_office'
  - `public_role_end` (conf: 0.638): person='Sylwii Sobolewskiej', organization='Orlenie', role='rada nadzorczy', role_domain='supervisory_board', context='Skarbu Państwa'
  - `public_role_holding` (conf: 0.619): person='Sylwii Sobolewskiej', organization='Lubelskich Kolei', role='rada nadzorczy', role_domain='other_public_role'
  - `public_role_appointment` (conf: 0.608): person='Paweł Majewski', organization='Lotosu', role='prezes', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.607): person='Sylwii Sobolewskiej', organization='Przedsiębiorstwie Gospodarki Komunalnej w Kamieniu Pomorskim', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.601): person='Krzysztofa Sobolewskiego', organization='Spółka Lubelskie', role='poseł', role_domain='political_office'
  - `public_role_appointment` (conf: 0.601): person='Sylwii Sobolewskiej', organization='Spółka Lubelskie', role='poseł', role_domain='political_office'
  - `public_role_holding` (conf: 0.59): person='Jarosława Kaczyńskiego', organization='Skarbu Państwa', role='poseł', role_domain='political_office', context='Skarbu Państwa'
  - `public_role_holding` (conf: 0.59): person='Krzysztofa Sobolewskiego', organization='Skarbu Państwa', role='poseł', role_domain='political_office', context='Skarbu Państwa'
  - `public_role_appointment` (conf: 0.571): person='Łukasz Jakubowski', organization='PKP CARGO', role='członek zarząd', role_domain='other_public_role'
  - `asset_declaration` (conf: 0.57): person='Sylwii Sobolewskiej', amount='niemal pół miliona złotych'
  - `party_membership` (conf: 0.563): subject='Grzegorz Schreiber', object='Prawo i Sprawiedliwość', status='former'
  - `personal_or_political_tie` (conf: 0.562): subject='Mateuszem Morawieckim', object='Morawieckiego', context='człowiek'
  - `public_role_appointment` (conf: 0.549): person='Sylwii Sobolewskiej', organization='Lubelskie Koleje', role='marszałek', role_domain='administrative_office'
  - `public_role_appointment` (conf: 0.549): person='Krzysztofa Sobolewskiego', organization='Lubelskie Koleje', role='marszałek', role_domain='administrative_office'
  - `public_role_appointment` (conf: 0.548): person='Krzysztofa Sobolewskiego', role='poseł', role_domain='political_office'
  - `public_role_appointment` (conf: 0.548): person='Sylwii Sobolewskiej', role='poseł', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Łukasza Smółki', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Krzysztofa Sobolewskiego', role='poseł', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Stawiarski', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Sylwii Sobolewskiej', role='poseł', role_domain='political_office'
  - `patronage_network_tie` (conf: 0.534): subject='Paweł Majewski', object='Iwonie Koperskiej', institution='PiS'
  - `patronage_allegation` (conf: 0.525): complainant='Paweł Majewski', target='Iwonie Koperskiej', institution='PiS'
  - `public_role_holding` (conf: 0.499): person='Łukasza Smółki', organization='Lubelskich Kolei', role='rad nadzorczy', role_domain='institution_management'
  - `public_role_holding` (conf: 0.499): person='Mariolę Duraj-Majdę', organization='Lubelskich Kolei', role='rad nadzorczy', role_domain='institution_management'
  - `public_role_holding` (conf: 0.499): person='Sylwii Sobolewskiej', organization='Lubelskich Kolei', role='rad nadzorczy', role_domain='institution_management'
  - `election_candidacy` (conf: 0.48): person='Przemysław Czarnek'
  - `compensation` (conf: 0.308): funder='Lubelskie Koleje', amount='2,3 tys. zł'

## 18. Głos Wielkopolski: Nowy prezes WTC Poznań, spółki podległej MTP, wybrany bez konkursu
**URL**: https://gloswielkopolski.pl/nowy-prezes-wtc-poznan-spolki-podleglej-mtp-wybrany-bez-konkursu-ma-dyplom-collegium-humanum/ar/c1p2-27186205
- **Filename**: `document-52274d3cd5381f2c.json`
- **Title**: *Hotelarz Rząsowski: Robota w spółce podległej MON dla radnego powiatowego. Nowy zaciąg tłustych kotów?*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_role_appointment` (conf: 0.755): person='Marek Rząsowski', organization='AMW Rewita', role='rada nadzorczy', role_domain='supervisory_board'
  - `public_employment` (conf: 0.716): person='Marku', organization='starostwu', role='sekretarz'
  - `public_employment` (conf: 0.71): person='Marku', organization='starostwu'
  - `kinship_tie` (conf: 0.708): subject='Mirella Zugaj', object='Radka Zugaja', relationship_detail='spouse', context='żona'
  - `personal_or_political_tie` (conf: 0.697): subject='Marek Rząsowski', object='Jacka Łęskiego', context='związany'
  - `compensation` (conf: 0.687): recipient='Marek Rząsowski', amount='24 tys. zł'
  - `party_membership` (conf: 0.666): subject='Marek Rząsowski', object='Platforma Obywatelska', status='unknown'
  - `public_role_holding` (conf: 0.544): person='Marek Rząsowski', role='radny', role_domain='political_office'
  - `election_candidacy` (conf: 0.48): person='Jacka Łęskiego'

## 19. Do Rzeczy: PSL rozdał posady swoim w Agencji Mienia Wojskowego. Bez konkursów
**URL**: https://dorzeczy.pl/kraj/658447/bez-konkursow-desant-psl-na-agencje-mienia-wojskowego.html
⚠️ **Status**: No matching pipeline output document found.

## 20. Dziennik Zachodni: Nepotyzm w Bytomiu? Radni PiS zapowiadają zawiadomienie do CBA
**URL**: https://dziennikzachodni.pl/nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zapowiedzieli-ze-zloza-zawiadomienie-do-cba-o-mozliwosci-popelnienia-przestepstwa/ar/c1-16375383
- **Filename**: `document-99789fa1120e40cd.json`
- **Title**: *Nepotyzm w Bytomiu? Radni reprezentujący PIS zapowiedzieli, że złożą zawiadomienie do CBA o możliwości popełnienia przestępstwa*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `anti_corruption_referral` (conf: 0.786): institution='CBA'
  - `public_role_appointment` (conf: 0.741): person='Mirosław Luks', organization='Urzędu Miejskiego w Bytomiu', role='sekretarz', role_domain='administrative_office'
  - `personal_or_political_tie` (conf: 0.701): subject='Bytomski', object='Bytomski', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Macieja Bartkowa', object='Mariuszem Wołoszem', context='związany'
  - `kinship_tie` (conf: 0.647): subject='Mariuszem Wołoszem', object='Macieja Bartkowa', relationship_detail='spouse'
  - `public_role_holding` (conf: 0.618): person='Bartłomieja Wnuka', role='radny', role_domain='political_office'
  - `public_role_holding` (conf: 0.618): person='Wnuk Consulting', role='radny', role_domain='political_office'
  - `public_role_holding` (conf: 0.588): person='Macieja Bartkowa', role='radny', role_domain='political_office'
  - `public_role_end` (conf: 0.545): person='Mariuszem Wołoszem'
  - `public_role_end` (conf: 0.545): person='Waldemar Gawron'
  - `public_role_holding` (conf: 0.544): person='Robert Rabus', role='radny', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Mariusz Janas', role='radny', role_domain='political_office'
  - `public_contract` (conf: 0.477): counterparty='PEC', contractor='Wnuk Consulting', amount='397 496,95 zł'

## 21. naTemat: 24 lata i już została wiceprezeską elektrociepłowni w Skierniewicach
**URL**: https://natemat.pl/141731,24-lata-i-juz-zostala-wiceprezeska-elektrocieplowni-skierniewice-takie-kariery-tylko-z-psl
- **Filename**: `document-dbc20646922c1243.json`
- **Title**: *24 LATA I JUŻ ZOSTAŁA WICEPREZESKĄ ELEKTROCIEPŁOWNI W SKIERNIEWICACH. TAKIE KARIERY TYLKO Z PSL?*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `personal_or_political_tie` (conf: 0.743): subject='Lucjan Ograsiński', object='Mariusz Suchecki', context='związany'
  - `kinship_tie` (conf: 0.708): subject='Urszula Bury', object='Jana Burego', relationship_detail='spouse', context='żona'
  - `public_employment` (conf: 0.702): person='Jana Burego', organization='Agencji Rynku Rolnego', role='sekretarz'
  - `kinship_tie` (conf: 0.697): subject='Eugeniusza Kłopotka', object='Stanisława Żelichowskiego', relationship_detail='child', context='syn'
  - `kinship_tie` (conf: 0.697): subject='Stanisława Żelichowskiego', object='Eugeniusza Kłopotka', relationship_detail='sibling', context='brat'
  - `kinship_tie` (conf: 0.697): subject='brat of Jarosława Kalinowskiego', object='Jarosława Kalinowskiego', relationship_detail='sibling', context='brat'
  - `personal_or_political_tie` (conf: 0.697): subject='Urszula Bury', object='Jana Burego', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Mariusz Suchecki', object='Jana Burego', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Mariusz Suchecki', object='Urszula Bury', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Lucjan Ograsiński', object='Jana Burego', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Lucjan Ograsiński', object='Urszula Bury', context='związany'
  - `party_membership` (conf: 0.67): subject='Lucjan Ograsiński', object='Polskie Stronnictwo Ludowe', status='unknown'
  - `public_role_appointment` (conf: 0.618): person='Mariusz Suchecki', role='rad nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.618): person='Lucjan Ograsiński', role='rad nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.561): person='Jacek Śmietanko', organization='Elewarru', role='minister', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.551): person='Adam Kalinowski', organization='Zamojskich Zakładach Zbożowych', role_domain='institution_management'
  - `public_employment` (conf: 0.506): person='Adam Kalinowski', organization='Elewarr'
  - `public_role_holding` (conf: 0.484): person='Paweł Bejda', role='rada nadzorczy', role_domain='other_public_role'

## 21. naTemat: 24 lata i już została wiceprezeską elektrociepłowni w Skierniewicach (Baseline Run Review)
- **Filename**: `document-dbc20646922c1243.json`
- **Title**: *24 LATA I JUŻ ZOSTAŁA WICEPREZESKĄ ELEKTROCIEPŁOWNI W SKIERNIEWICACH. TAKIE KARIERY TYLKO Z PSL?*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `personal_or_political_tie` (conf: 0.743): subject='Lucjan Ograsiński', object='Mariusz Suchecki', context='związany'
  - `kinship_tie` (conf: 0.708): subject='Urszula Bury', object='Jana Burego', relationship_detail='spouse', context='żona'
  - `public_employment` (conf: 0.702): person='Jana Burego', organization='Agencji Rynku Rolnego', role='sekretarz'
  - `kinship_tie` (conf: 0.697): subject='Eugeniusza Kłopotka', object='Stanisława Żelichowskiego', relationship_detail='child', context='syn'
  - `kinship_tie` (conf: 0.697): subject='Stanisława Żelichowskiego', object='Eugeniusza Kłopotka', relationship_detail='sibling', context='brat'
  - `kinship_tie` (conf: 0.697): subject='brat of Jarosława Kalinowskiego', object='Jarosława Kalinowskiego', relationship_detail='sibling', context='brat'
  - `personal_or_political_tie` (conf: 0.697): subject='Urszula Bury', object='Jana Burego', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Mariusz Suchecki', object='Jana Burego', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Mariusz Suchecki', object='Urszula Bury', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Lucjan Ograsiński', object='Jana Burego', context='związany'
  - `personal_or_political_tie` (conf: 0.697): subject='Lucjan Ograsiński', object='Urszula Bury', context='związany'
  - `party_membership` (conf: 0.67): subject='Lucjan Ograsiński', object='Polskie Stronnictwo Ludowe', status='unknown'
  - `public_role_appointment` (conf: 0.618): person='Mariusz Suchecki', role='rad nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.618): person='Lucjan Ograsiński', role='rad nadzorczy', role_domain='supervisory_board'
  - `public_role_appointment` (conf: 0.561): person='Jacek Śmietanko', organization='Elewarru', role='minister', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.551): person='Adam Kalinowski', organization='Zamojskich Zakładach Zbożowych', role_domain='institution_management'
  - `public_employment` (conf: 0.506): person='Adam Kalinowski', organization='Elewarr'
  - `public_role_holding` (conf: 0.484): person='Paweł Bejda', role='rada nadzorczy', role_domain='other_public_role'

## 22. Dziennik Polski: Kontrowersje wokół wójta Charsznicy. Tak pracę dostała jego partnerka
**URL**: https://dziennikpolski24.pl/kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom/ar/c1p2-28656825
- **Filename**: `document-1a83884e3d8716dd.json`
- **Title**: *Kontrowersje wokół wójta Charsznicy. Tak pracę dostała jego partnerka. Tomasz Kościelniak zaprzecza zarzutom*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_employment` (conf: 0.808): person='dziewczyna of Tomasz Kościelniak', organization='urzędzie', role='ekodoradca'
  - `public_employment` (conf: 0.743): person='teść of Tomasz Kościelniak', organization='Urzędzie Stanu Cywilnego', role='pracownik gospodarczy'
  - `public_role_holding` (conf: 0.737): person='Jan Kowalski', organization='Urzędzie Stanu Cywilnego', role='wójt', role_domain='political_office'
  - `public_role_holding` (conf: 0.737): person='dziewczyna of Tomasz Kościelniak', organization='Urzędzie Stanu Cywilnego', role='wójt', role_domain='political_office'
  - `public_role_holding` (conf: 0.737): person='Tomasza Kościelniaka', organization='Urzędzie Stanu Cywilnego', role='wójt', role_domain='political_office'
  - `public_role_holding` (conf: 0.721): person='Tomasza Kościelniaka', role='wójt', role_domain='political_office'
  - `kinship_tie` (conf: 0.708): subject='dziewczyna of Tomasz Kościelniak', object='Tomasza Kościelniaka', relationship_detail='spouse', context='dziewczyna'
  - `kinship_tie` (conf: 0.697): subject='teść of Tomasz Kościelniak', object='Tomasza Kościelniaka', relationship_detail='family', context='teść'
  - `public_role_holding` (conf: 0.619): person='Paweł Janicki', organization='Gminnego Ośrodka Kultury', role='dyrektor', role_domain='institution_management'
  - `public_role_holding` (conf: 0.619): person='Szymon Kubit', organization='Gminnego Ośrodka Kultury', role='dyrektor', role_domain='institution_management'
  - `party_membership` (conf: 0.563): subject='Paweł Janicki', object='Prawo i Sprawiedliwość', status='unknown'
  - `public_role_holding` (conf: 0.544): person='teść of Tomasz Kościelniak', role='wójt', role_domain='political_office'
  - `election_candidacy` (conf: 0.48): person='Tomasza Kościelniaka'
  - `election_candidacy` (conf: 0.48): person='Szymon Kubit'
  - `election_candidacy` (conf: 0.48): person='Jan Żebrak'
  - `public_role_appointment` (conf: 0.454): person='Tomasza Kościelniaka', role_domain='institution_management'

## 23. Onet: CBA. Wójt brał łapówki za zlecanie remontów i zatrudnianie pracowników
**URL**: https://wiadomosci.onet.pl/krakow/cba-wojt-bral-lapowki-za-zlecanie-remontow-i-zatrudnianie-pracownikow/vdc04xe
- **Filename**: `document-95a5a4f966179347.json`
- **Title**: *CBA: wójt brał łapówki za zlecanie remontów i zatrudnianie pracowników*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `anti_corruption_investigation` (conf: 0.711): target='Podkarpackiego Wydziału Zamiejscowy Departamentu do Spraw Przestępczości Zorganizowanej i Korupcji', institution='Delegatura CBA'

## 24. AI42: Czy wójt ukrywa nepotyzm?
**URL**: https://ai42.pl/2024/08/04/czy-wojt-ukrywa-nepotyzm
- **Filename**: `document-8e140526bcbbf0b3.json`
- **Title**: *Czy wójt ukrywa nepotyzm?*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.95)
- **Extracted Facts**:
  - `public_role_holding` (conf: 0.739): person='Arturem Sosną', role='wójt', role_domain='political_office'
  - `public_employment` (conf: 0.715): person='Rafała Dobosza', organization='samorządzie', role='pomoc administracyjny'
  - `kinship_tie` (conf: 0.708): subject='Rafała Dobosza', object='Arturem Sosną', relationship_detail='family', context='kuzyn'
  - `kinship_tie` (conf: 0.697): subject='kuzyn of Sosna', object='Arturem Sosną', relationship_detail='family', context='kuzyn'
  - `personal_or_political_tie` (conf: 0.697): subject='Rafała Dobosza', object='Arturem Sosną', context='współpracownik'
  - `public_employment` (conf: 0.528): person='Rafała Dobosza', organization='urzędzie'

## 25. WP: Wiedza, doświadczenie i kompetencje, czyli rodzina na swoim w Opolu
**URL**: https://wiadomosci.wp.pl/wiedza-doswiadczenie-i-kompetencje-czyli-rodzina-na-swoim-w-opolu-7147022691576352a
- **Filename**: `document-af2bb982c6f4ea8d.json`
- **Title**: *Wiedza, doświadczenie i kompetencje, czyli rodzina na swoim w Opolu*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_employment` (conf: 0.756): person='Agnieszki Królikowskiej', organization='Generalnego Opolskiego Urzędu Wojewódzkiego', role='dyrektor'
  - `public_role_appointment` (conf: 0.751): person='Jarosław Draguć', organization='Urzędu Wojewódzkiego', role='marszałek', role_domain='political_office'
  - `public_role_appointment` (conf: 0.751): person='Andrzej Buła', organization='Urzędu Wojewódzkiego', role='marszałek', role_domain='political_office'
  - `public_role_appointment` (conf: 0.742): person='Agnieszki Królikowskiej', organization='Urzędu Wojewódzkiego', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.742): person='Agnieszki Królikowskiej', organization='Generalnego Opolskiego Urzędu Wojewódzkiego', role='dyrektor', role_domain='institution_management'
  - `kinship_tie` (conf: 0.721): subject='Dariusz Jurek', object='Monika Jurek', relationship_detail='spouse', context='mąż'
  - `kinship_tie` (conf: 0.697): subject='Agnieszki Królikowskiej', object='Szymona Ogłazy', relationship_detail='spouse', context='partnerka'
  - `public_role_holding` (conf: 0.671): person='Agnieszki Królikowskiej', organization='OUW', role='dyrektor', role_domain='institution_management'
  - `public_employment` (conf: 0.645): person='Agnieszki Królikowskiej', organization='urzędu'
  - `public_employment` (conf: 0.64): person='Agnieszki Królikowskiej', organization='Urząd', role='marszałek'
  - `public_role_holding` (conf: 0.618): person='Agnieszki Królikowskiej', role='wojewoda', role_domain='political_office'
  - `public_role_end` (conf: 0.589): person='Monika Jurek', role='wojewoda', role_domain='institution_management'
  - `public_role_holding` (conf: 0.581): person='Szymona Ogłazy', role='marszałek', role_domain='political_office'
  - `public_role_holding` (conf: 0.568): person='Monika Jurek', role='wojewoda', role_domain='political_office'
  - `public_role_holding` (conf: 0.568): person='Jurek', role='wojewoda', role_domain='political_office'
  - `public_role_appointment` (conf: 0.547): person='Monika Jurek', role='wojewoda', role_domain='institution_management'

## 26. Polsat Interwencja: Bardzo rodzinne starostwo
**URL**: https://interwencja.polsatnews.pl/reportaz/2013-11-29/bardzo-rodzinne-starostwo_1329791
- **Filename**: `document-7e1ccff9c2940169.json`
- **Title**: *Bardzo rodzinne starostwo… - Interwencja*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_employment` (conf: 0.764): person='syn of Jakub Mieszko', organization='unijnego'
  - `public_employment` (conf: 0.754): person='mąż of Joanna Pszczółkowska', organization='starostwu'
  - `public_role_holding` (conf: 0.727): person='Anna Karaś', organization='Powiatowego Centrum Pomocy Rodzinie w Ciechanowie', role='sekretarz', role_domain='administrative_office'
  - `public_role_appointment` (conf: 0.727): person='Joanna Pszczółkowska', organization='Powiatowym Centrum Pomocy Rodzinie', role='sekretarz', role_domain='administrative_office'
  - `public_role_appointment` (conf: 0.727): person='mąż of Joanna Pszczółkowska', organization='Powiatowym Centrum Pomocy Rodzinie', role='sekretarz', role_domain='administrative_office'
  - `public_role_holding` (conf: 0.721): person='Ciechanowski', role='starosta', role_domain='political_office'
  - `public_employment` (conf: 0.709): person='Joanna Pszczółkowska', organization='unijnego', role='sekretarz'
  - `kinship_tie` (conf: 0.697): subject='mąż of Joanna Pszczółkowska', object='Joanna Pszczółkowska', relationship_detail='spouse', context='mąż'
  - `kinship_tie` (conf: 0.697): subject='syn of Roman', object='Roman', relationship_detail='child', context='syn'
  - `personal_or_political_tie` (conf: 0.697): subject='mąż of Joanna Pszczółkowska', object='Joanna Pszczółkowska', context='posada'
  - `public_role_appointment` (conf: 0.675): person='Jakub Mieszko', role='sekretarz', role_domain='administrative_office'
  - `public_role_appointment` (conf: 0.675): person='syn of Jakub Mieszko', role='sekretarz', role_domain='administrative_office'
  - `public_role_holding` (conf: 0.675): person='Sławomir Morawski', role='starosta', role_domain='political_office'
  - `public_role_appointment` (conf: 0.675): person='Joanna Pszczółkowska', role='sekretarz', role_domain='administrative_office'
  - `public_employment` (conf: 0.629): person='syn of Roman', organization='starostwo'
  - `kinship_tie` (conf: 0.623): subject='Bartosz', object='Joanna Pszczółkowska', relationship_detail='child', context='syn'
  - `public_role_appointment` (conf: 0.561): person='Józef Borkowski', role='zarząd', role_domain='public_company_management'

## 27. TVN Warszawa: 100 tysięcy z urzędu dla fundacji dyrektora pogotowia
**URL**: https://tvn24.pl/tvnwarszawa/srodmiescie/warszawa-100-tysiecy-z-urzedu-dla-fundacji-dyrektora-pogotowia-razem-chce-kontroli-st8987644
- **Filename**: `document-8785682e9842a554.json`
- **Title**: *"Adam Struzik chroni swoich". Chcą kontroli umów w urzędzie*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `party_membership` (conf: 0.748): subject='Adam Struzik', object='Polskie Stronnictwo Ludowe', status='unknown'
  - `public_role_holding` (conf: 0.721): person='Adam Struzik', role='marszałek', role_domain='political_office'
  - `funding` (conf: 0.715): funder='urzędu marszałkowskiego', recipient='fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola Bielskiego', amount='100 tysięcy złotych'
  - `party_membership` (conf: 0.659): subject='Marcelina Zawisza', object='Razem', status='unknown'
  - `public_role_holding` (conf: 0.544): person='Marcelina Zawisza', role='posłanka', role_domain='political_office'

## 29. Tygodnik Płocki: Nowy zarząd Inwestycji Miejskich
**URL**: https://tp.com.pl/artykul/nowy-zarzad-inwestycji-miejskich-n684452
- **Filename**: `document-6322bbb016b3f603.json`
- **Title**: *Nowy zarząd Inwestycji Miejskich*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.7)
- **Extracted Facts**:
  - `public_role_holding` (conf: 0.727): person='Artur Biernat', organization='PKN Orlen', role='dyrektor', role_domain='institution_management'
  - `public_role_end` (conf: 0.707): person='Piotr Śladowski', organization='Inwestycji Miejskich', role='wiceprezes', role_domain='public_company_management'
  - `public_role_end` (conf: 0.707): person='Mariusz Stec', organization='Inwestycji Miejskich', role='prezes', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.701): person='Mirosław Milewski', organization='Inwestycje Miejskie'
  - `public_role_appointment` (conf: 0.582): person='Kamil Rybacki', organization='PKN Orlen', role='prezes', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.582): person='Artur Biernat', organization='PKN Orlen', role='prezes', role_domain='institution_management'
  - `public_role_end` (conf: 0.526): person='prezesa', organization='Urzędu Miasta', role='rada nadzorczy', role_domain='public_company_management'
  - `public_employment` (conf: 0.418): person='Artur Biernat', organization='Płocku', role='dyrektor'

## 30. Onet: Totalizator Sportowy - prezes odwołany po publikacji
**URL**: https://wiadomosci.onet.pl/kraj/sa-skutki-afery-ujawnionej-przez-onet-leca-glowy-na-szczytach-totalizatora/v1x1k0e
- **Filename**: `document-8bad6dd3c40384ea.json`
- **Title**: *Trzęsienie ziemi w Totalizatorze Sportowym. Prezes odwołany ze stanowiska po publikacji Onetu*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_role_holding` (conf: 0.718): person='Borys Budka', organization='Totalizatora', role='dyrektor', role_domain='institution_management'
  - `personal_or_political_tie` (conf: 0.697): subject='Stanisława Gawłowskiego', object='Donaldem Tuskiem', context='współpracownik'
  - `personal_or_political_tie` (conf: 0.697): subject='Sławomira Nitrasa', object='Donaldem Tuskiem', context='współpracownik'
  - `personal_or_political_tie` (conf: 0.697): subject='Sławomira Nitrasa', object='Stanisława Gawłowskiego', context='współpracownik'
  - `public_role_end` (conf: 0.675): person='Rafała Krzemienia', role='prezes', role_domain='public_company_management'
  - `public_role_end` (conf: 0.649): person='Krzemienia'
  - `public_role_holding` (conf: 0.61): person='Jakub Jaworowski', organization='Skarbu Państwa', role='minister', role_domain='political_office', context='Skarbu Państwa'
  - `public_role_end` (conf: 0.571): person='Jakub Jaworowski', role='prezes', role_domain='political_office'
  - `public_role_appointment` (conf: 0.549): person='Jaworowski', organization='Totalizatora', role='rad nadzorczy', role_domain='institution_management'
  - `public_role_holding` (conf: 0.544): person='Stanisława Gawłowskiego', role='senator', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Sławomira Nitrasa', role='minister', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Jakub Jaworowski', role='minister', role_domain='political_office'
  - `public_role_holding` (conf: 0.544): person='Borys Budka', role='minister', role_domain='political_office'
  - `public_role_end` (conf: 0.505): person='Prezes', role='prezes', role_domain='public_company_management'
  - `public_role_appointment` (conf: 0.49): person='Donaldem Tuskiem', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.49): person='Stanisława Gawłowskiego', role='dyrektor', role_domain='institution_management'
  - `public_role_appointment` (conf: 0.49): person='Sławomira Nitrasa', role='dyrektor', role_domain='institution_management'

## 31. Business Insider: Kadrowa czystka w PZU
**URL**: https://businessinsider.com.pl/biznes/kadrowa-czystka-objela-kolejna-panstwowa-spolke-nastepne-zmiany-niebawem/v75q3s4
- **Filename**: `document-4982ef87c5db770d.json`
- **Title**: *Kadrowa czystka objęła kolejną państwową spółkę. Następne zmiany niebawem*
- **Relevance**: Expected=True | Actual=True ✅ (score: 1.0)
- **Extracted Facts**:
  - `public_role_holding` (conf: 0.727): person='Beata Kozłowska', organization='PZU', role='prezes', role_domain='public_company_management'
  - `party_membership` (conf: 0.666): subject='Wojciecha Olejniczaka', object='Sojusz Lewicy Demokratycznej', status='former'
  - `public_role_appointment` (conf: 0.61): person='Wojciecha Olejniczaka', organization='Skarbu Państwa', role='szef', role_domain='institution_management', context='Skarbu Państwa'
  - `public_role_appointment` (conf: 0.569): person='Andrzeja Jarczyka', organization='PZU'
  - `public_role_end` (conf: 0.523): person='Paweł Górecki', role_domain='administrative_office', context='MAP'
  - `election_candidacy` (conf: 0.48): person='Wojciecha Olejniczaka'

## 32. Onet: Marcin Kopania odnalazł się w PHN
**URL**: https://wiadomosci.onet.pl/tylko-w-onecie/rafal-trzaskowski-wyrzucil-go-za-hejterstwo-marcin-kopania-odnalazl-sie-w-phn/3zp8m3y
- **Filename**: `document-fc08c34bd3a606f4.json`
- **Title**: *Rafał Trzaskowski wyrzucił go za hejterstwo. Teraz odnalazł się w spółce Skarbu Państwa*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.95)
- **Extracted Facts**:
  - `public_role_end` (conf: 0.727): person='Marcina Kopanię', organization='Miejskiego Przedsiębiorstwa Realizacji Inwestycji', role='prezes', role_domain='public_company_management'
  - `public_employment` (conf: 0.713): person='Bartosz Kopania', organization='Totalizatora Sportowego'
  - `kinship_tie` (conf: 0.708): subject='Marcina Kopanię', object='Bartosz Kopania', relationship_detail='sibling', context='brat'
  - `public_role_appointment` (conf: 0.708): person='Wiesław Malicki', organization='PHN', role='prezes', role_domain='public_company_management'
  - `personal_or_political_tie` (conf: 0.697): subject='Szymon Gawryszczak', object='Roberta Kropiwnickiego', context='znajomy'
  - `personal_or_political_tie` (conf: 0.697): subject='Rafała Trzaskowskiego', object='Magdalenie Biejat', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Przemysław Wipler', object='Magdalenie Biejat', context='człowiek'
  - `personal_or_political_tie` (conf: 0.697): subject='Przemysław Wipler', object='Rafała Trzaskowskiego', context='człowiek'
  - `public_contract` (conf: 0.683): counterparty='Totalizatora Sportowego', contractor='Bartosz Kopania', amount='100 tys. zł'
  - `public_employment` (conf: 0.625): person='Krzysztofa Gołąba', organization='warszawskiej'
  - `public_employment` (conf: 0.609): person='Malicki', organization='Ministerstwo'
  - `public_role_appointment` (conf: 0.603): person='Krzysztofa Gołąba', organization='PHN', role='doradca', role_domain='other_public_role'
  - `public_employment` (conf: 0.579): person='Przemysław Wipler', organization='Warszawy'
  - `personal_or_political_tie` (conf: 0.579): subject='Wiesław Malicki', object='Malicki', context='współpracownik'
  - `public_employment` (conf: 0.546): person='Marcina Kopanię', organization='Skarbu Państwa'
  - `public_employment` (conf: 0.542): person='Kopani', organization='Polskiego Holdingu Nieruchomości'
  - `public_role_end` (conf: 0.541): person='Marcina Kopanię', role='prezes', role_domain='public_company_management'
  - `public_role_end` (conf: 0.541): person='Rafała Trzaskowskiego', role='prezes', role_domain='public_company_management'

## 33. WP: Pensja 30 tys. zł brutto. Tak zarabiają prezesi warszawskich spółek miejskich
**URL**: https://wiadomosci.wp.pl/warszawa/pensja-30-tys-zl-brutto-tak-zarabiaja-prezesi-warszawskich-spolek-miejskich-7283597240129600a
- **Filename**: `document-39dbbdfaf68399bb.json`
- **Title**: *Pensja 30 tys. zł brutto. Tak zarabiają prezesi warszawskich spółek miejskich*
- **Relevance**: Expected=True | Actual=True ✅ (score: 0.84)
- **Extracted Facts**:
  - `funding` (conf: 0.739): amount='86,5 tysiąca złotych'
  - `funding` (conf: 0.739): amount='72,2 tysiąca złotych'
  - `compensation` (conf: 0.731): funder='Tramwajów Warszawskich', amount='35 tysięcy złotych'
  - `compensation` (conf: 0.731): funder='MPO', amount='29,4 tysiąca złotych'
  - `compensation` (conf: 0.731): funder='MPWiK', amount='420 tysięcy złotych'
  - `compensation` (conf: 0.731): funder='Miejskich Zakładach Autobusowych i Metrze Warszawskim', amount='30 tys. zł'
  - `compensation` (conf: 0.72): funder='spółek transportowych', amount='100 tys. zł'
  - `compensation` (conf: 0.702): funder='Tramwajów Warszawskich', amount='92,6 tysiąca złotych'
  - `compensation` (conf: 0.702): funder='Miejskich Zakładach Autobusowych i Metrze Warszawskim', amount='100 tys. zł'
  - `compensation` (conf: 0.702): funder='MPO', amount='352,8 tysiąca złotych'
  - `compensation` (conf: 0.702): funder='MPWiK', amount='72,2 tysiąca złotych'
  - `funding` (conf: 0.696): recipient='spółek transportowych', amount='100 tys. zł'
