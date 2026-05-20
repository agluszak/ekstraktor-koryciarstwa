# V1 vs V2 Pipeline Comparison

## `olsztyn_wodkan`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| COMPENSATION | Wiesława Pancera | Kanalizacji w Olsztynie | Prezes | Wiesław Pancer, prezes Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie, we… |
| COMPENSATION | Wiesława Pancera | Kanalizacji w Olsztynie | Prezes | Wiesław Pancer, prezes Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie, we… |
| COMPENSATION | Wiesława Pancera | Kanalizacji w Olsztynie | Prezes | Wiesław Pancer, prezes Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie, we… |
| COMPENSATION | Wiesława Pancera | Kanalizacji w Olsztynie | Prezes | Z kolei najmniej zarabiają prezesi spółek wodociągowych z Torunia (ponad 182 tys… |
| COMPENSATION | Wiesława Pancera | Kanalizacji w Olsztynie | Prezes | Z kolei najmniej zarabiają prezesi spółek wodociągowych z Torunia (ponad 182 tys… |
| COMPENSATION | Wiesława Pancera | Kanalizacji w Olsztynie | Prezes | Przekładając kwoty na liczbę mieszkańców pensja Wiesława Pancera kosztuje każdeg… |
| COMPENSATION | Henryk Milcarza | Wodociągów Kieleckich | Prezes | – Okazuje się, że pensja szefa kieleckich wodociągów kosztuje kielczanina i mies… |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| compensation | 0.85 |  |  | 322 030,80 zł | funder=Przedsiębiorstwa Wodociągów i … | recipient=Wiesław Pancer |
| compensation | 1.00 |  |  | 182 tys. zł | funder=Przedsiębiorstwa Wodociągów i … | recipient=Wiesław Pancer |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `COMPENSATION`
- ℹ️  **V2 emits** fact kinds not in V1: `compensation`

## `onet_wfosigw_lublin`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| APPOINTMENT | Andrzej Kloca | WFOŚiGW w Lublinie | Rada Nadzorcza | Stanisław Mazur, hotelarz-milioner z Lewicy, i działacz PSL Andrzej Kloc będą ki… |
| DISMISSAL | Agnieszka Kruk | WFOŚiGW w Lublinie | Rada Nadzorcza | Obecnie zasiadają w niej: Piotr Bogusz (przewodniczący) — zastępca dyrektora w D… |
| APPOINTMENT | Stanisław Mazura | WFOŚiGW w Lublinie | Prezes | W radzie ostał się jeszcze człowiek z poprzedniego nadania — Jerzy Szwaj (PiS), … |
| APPOINTMENT | Jerzy Szwaj | WFOŚiGW w Lublinie | wice/zastępca Przewodniczący Rady Nadzorczej | — Decyzje co do podziału stanowisko zapadały na górze między koalicjantami. Późn… |
| FUNDING | Departamencie Funduszy Europejskich Ministerstwa Klimatu | WFOŚiGW w Lublinie |  | To instytucja, która obraca milionami złotych w ramach rządowych dotacji na prog… |
| PARTY_MEMBERSHIP | Stanisław Mazura | Lewica |  | Stanisław Mazur, hotelarz-milioner z Lewicy, i działacz PSL Andrzej Kloc będą ki… |
| PARTY_MEMBERSHIP | Andrzej Kloca | Polskie Stronnictwo Ludowe |  | Stanisław Mazur, hotelarz-milioner z Lewicy, i działacz PSL Andrzej Kloc będą ki… |
| PARTY_MEMBERSHIP | Stanisław Mazura | Lewica |  | - Działacz Lewicy Stanisław Mazur odebrał dziś nominację na prezesa WFOŚiGW w Lu… |
| POLITICAL_OFFICE | Paulina Hennig-Kloska | Minister |  | Wcześniej takich wymogów nie było - przekonuje Paulina Hennig-Kloska, ministra k… |
| FORMER_PARTY_MEMBERSHIP | Michał Marciniak | Polskie Stronnictwo Ludowe |  | Obecnie zasiadają w niej: Piotr Bogusz (przewodniczący) — zastępca dyrektora w D… |
| FORMER_PARTY_MEMBERSHIP | Anna Glijer | Platforma Obywatelska |  | Obecnie zasiadają w niej: Piotr Bogusz (przewodniczący) — zastępca dyrektora w D… |
| PARTY_MEMBERSHIP | Jerzy Szwaj | Prawo i Sprawiedliwość |  | W radzie ostał się jeszcze człowiek z poprzedniego nadania — Jerzy Szwaj (PiS), … |
| PARTY_MEMBERSHIP | Stanisław Mazura | Lewica |  | Nowym prezesem WFOŚiGW w Lublinie ma zostać Stanisław Mazur z Lewicy, a wiceprez… |
| PARTY_MEMBERSHIP | Andrzej Kloca | Polskie Stronnictwo Ludowe |  | Nowym prezesem WFOŚiGW w Lublinie ma zostać Stanisław Mazur z Lewicy, a wiceprez… |
| PARTY_MEMBERSHIP | Grzegórz Czelej | Prawo i Sprawiedliwość |  | Mimo zdobycia niemal 72 tys. głosów sromotnie przegrał z Grzegorzem Czelejem z P… |
| PARTY_MEMBERSHIP | Andrzej Kloca | Polskie Stronnictwo Ludowe |  | Zastępcą prezesa będzie 39-letni Andrzej Kloc z PSL. |
| PARTY_MEMBERSHIP | Jarosław Stawiarski | Prawo i Sprawiedliwość |  | We wtorek 13 marca br. zarząd województwa lubelskiego, któremu przewodzi marszał… |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| party_affiliation | 0.80 |  |  |  | subject=Stanisław Mazur | object=Lewica |
| party_affiliation | 0.80 |  |  |  | subject=Stanisław Mazur | object=Lewica |
| party_affiliation | 0.80 |  |  |  | subject=Andrzej Kloc | object=Polskie Stronnictwo Ludowe |
| party_affiliation | 0.80 |  |  |  | subject=Grzegorzem Czelejem | object=Prawo i Sprawiedliwość |
| party_affiliation | 0.80 |  |  |  | subject=Andrzej Kloc | object=Polskie Stronnictwo Ludowe |
| governance_appointment | 0.80 | Stanisław Mazur |  |  | role=prezesa |
| governance_dismissal | 0.80 | Agnieszkę Kruk |  |  | role=rada nadzorcza |
| governance_appointment | 0.90 | Stanisław Mazur | WFOŚiGW w Lublinie |  | role=prezesem |
| governance_dismissal | 0.90 | Stanisław Mazur | WFOŚiGW |  | role=prezesem |
| governance_appointment | 0.80 | Paulinę Hennig-Kloskę | Koalicji 15 Października |  |  |
| governance_appointment | 0.80 | Jerzy Szwaj |  |  | role=rady nadzorczej |
| governance_appointment | 0.74 | Jarosław Stawiarski |  |  | role=zarząd |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `APPOINTMENT`, `DISMISSAL`, `FORMER_PARTY_MEMBERSHIP`, `FUNDING`, `PARTY_MEMBERSHIP`, `POLITICAL_OFFICE`
- ℹ️  **V2 emits** fact kinds not in V1: `governance_appointment`, `governance_dismissal`, `party_affiliation`

## `zona-posla-pis`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| PERSONAL_OR_POLITICAL_TIE | Moja Żona | Dariusz Stefaniuk |  | Moja żona |
| PERSONAL_OR_POLITICAL_TIE | Swojej Żony | Dariusz Stefaniuk |  | swojej żony |
| PERSONAL_OR_POLITICAL_TIE | Moja Żona | Stefaniuk |  | Moja żona |
| PERSONAL_OR_POLITICAL_TIE | Szwagierka Jacka Sasina | Jacek Sasina |  | szwagierka Jacka Sasina |
| DISMISSAL | Renata Stefaniuk | Enea Połaniec | Rada Nadzorcza | Jak dowiedział się Onet, Renata Stefaniuk nie zasiada już w radach nadzorczych s… |
| DISMISSAL | Moja Żona | Enea Połaniec | Rada Nadzorcza | - Zrobiła to dobrowolnie — mówi Onetowi poseł Dariusz Stefaniuk. - - Moja żona n… |
| APPOINTMENT | Stefaniuk | Portu Lotniczego w Lublinie | Rada Nadzorcza | Ukończyła studia MBA na Akademii Koźmińskiego i ma uprawnienia do zasiadania w r… |
| DISMISSAL | Szwagierka Jacka Sasina | Portu Lotniczego w Lublinie | Rada Nadzorcza | Ukończyła studia MBA na Akademii Koźmińskiego i ma uprawnienia do zasiadania w r… |
| PARTY_MEMBERSHIP | Dariusz Stefaniuk | Prawo i Sprawiedliwość |  | - Zrobiła to dobrowolnie — mówi Onetowi poseł Dariusz Stefaniuk. |
| POLITICAL_OFFICE | Dariusz Stefaniuk | Poseł |  | - Zrobiła to dobrowolnie — mówi Onetowi poseł Dariusz Stefaniuk. |
| PARTY_MEMBERSHIP | Renata Stefaniuk | Prawo i Sprawiedliwość |  | Na liście znalazła się również Renata Stefaniuk, żona posła PiS i byłego prezyde… |
| PARTY_MEMBERSHIP | Dariusz Stefaniuk | Prawo i Sprawiedliwość |  | Zrobiła to po uchwale podjętej przez kongres PiS — mówi w rozmowie z Onetem Dari… |
| POLITICAL_OFFICE | Dariusz Stefaniuk | Poseł |  | Zrobiła to po uchwale podjętej przez kongres PiS — mówi w rozmowie z Onetem Dari… |
| PERSONAL_OR_POLITICAL_TIE | Moja Żona | Dariusz Stefaniuk |  | - - Moja żona nie zasiada już w radach nadzorczych spółek Enea Połaniec i Jelcz … |
| PERSONAL_OR_POLITICAL_TIE | Renata Stefaniuk | Dariusz Stefaniuk |  | Na liście znalazła się również Renata Stefaniuk, żona posła PiS i byłego prezyde… |
| PERSONAL_OR_POLITICAL_TIE | Moja Żona | Stefaniuk |  | - Moja żona zasiadała w radach nadzorczych na kilka lat przed tym, jak objąłem m… |
| PERSONAL_OR_POLITICAL_TIE | Moja Żona | Dariusz Stefaniuk |  | - - Moja żona zasiadała w radach nadzorczych na kilka lat przed tym, jak objąłem… |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| governance_dismissal | 0.90 | Dariusz Stefaniuk | Enea Połaniec |  | role=radach nadzorczych |
| governance_appointment | 0.88 | Stefaniuk | MBA |  | role=radach nadzorczych |
| governance_dismissal | 0.90 | Jacka Sasina | Portu Lotniczego Lublin |  | role=radzie nadzorczej |
| personal_or_political_tie | 0.80 |  |  |  | subject=Renata Stefaniuk | object=Dariusza Stefaniuka | context=spouse |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `APPOINTMENT`, `DISMISSAL`, `PARTY_MEMBERSHIP`, `PERSONAL_OR_POLITICAL_TIE`, `POLITICAL_OFFICE`
- ℹ️  **V2 emits** fact kinds not in V1: `governance_appointment`, `governance_dismissal`, `personal_or_political_tie`

## `rp_tk_negative`
**Relevance**: V1=? | V2=False
**V1**: relevant but no facts extracted.
**V2**: irrelevant — no facts expected.
### Gap analysis
- Both pipelines produced no facts (expected for negative/irrelevant articles).

## `onet_totalizator`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| PERSONAL_OR_POLITICAL_TIE | Żona Magdalena Sekuła | Magdalena Sekuła |  | żona Magdalena Sekuła |
| APPOINTMENT | Olgierd Cieślik | Powiatu Piotrkowskiego | Prezes | Kadrowa miotła nowego rządu dotarła tu w lutym 2024 r. Wtedy to z funkcji odwoła… |
| APPOINTMENT | Rafał Krzemień | Powiatu Piotrkowskiego |  | Kadrowa miotła nowego rządu dotarła tu w lutym 2024 r. Na jego miejsce wkrótce t… |
| APPOINTMENT | Adam Sekuła | Totalizatora | Dyrektor | Tam dyrektorem regionalnym Totalizatora został w sierpniu Adam Sekuła. |
| APPOINTMENT | Karol Wilczyński | TS | Dyrektor | Tandem koalicji: dyrektor z KO, a jego zastępca z PSL Dyrektorem kieleckiego odd… |
| APPOINTMENT | Sławomir Czwal | Rady Miasta w Kielcach | Dyrektor | Kandydat KO usuwa ślady w sprawie nowej pracy Nowo wybranym dyrektorem w Rzeszow… |
| APPOINTMENT | Paweł SiedleckiMSWiA | Agencja Wyborcza.pl |  | Do Totalizatora na kierownicze stanowiska weszli nie tylko działacze PO i PSL. Z… |
| APPOINTMENT | Paweł SiedleckiMSWiA | TS | Dyrektor | Tuż przed transferem do Totalizatora przez kilka miesięcy był zastępcą dyrektora… |
| APPOINTMENT | Anna Makarewicz | TS | Dyrektor | Paweł SiedleckiMSWiA Była szefowa biura poselskiego ważnego polityka PO Beneficj… |
| APPOINTMENT | Rafał Tyrcz | Oddziału Wrocław | Dyrektor | Pozostali nowy dyrektorzy w TS to: Rafał Tyrcz, p.o. dyrektora Oddziału Wrocław … |
| APPOINTMENT | Daniel Szutko | Oddziału Białystok | Dyrektor | Pozostali nowy dyrektorzy w TS to: Rafał Tyrcz, p.o. dyrektora Oddziału Wrocław … |
| APPOINTMENT | Marek Wróbel | Oddziału Opole | Dyrektor | Rafał Tyrcz, p.o. dyrektora Oddziału Wrocław Daniel Szutko, dyrektor Oddziału Bi… |
| APPOINTMENT | Piotr Kaciunka | Oddziału Zielona Góra | Dyrektor | Daniel Szutko, dyrektor Oddziału Białystok Marek Wróbel, dyrektor Oddziału Opole… |
| COMPENSATION | Dyrektor | TS | Dyrektor | Osoby na tych stanowiskach mogą zarobić nawet ponad 20 tys. zł miesięcznie |
| COMPENSATION | Piotr Bresia | TS | Dyrektor | Z tego za 2023 r. dowiadujemy się, że jako dyrektor oddziału terenowego Totaliza… |
| COMPENSATION | Piotr Bresia | TS | Dyrektor | Z tego za 2023 r. dowiadujemy się, że jako dyrektor oddziału terenowego Totaliza… |
| APPOINTMENT | Rafał Krzemień | Powiatu Piotrkowskiego |  | Na jego miejsce wkrótce trafił Rafał Krzemień, doświadczony menedżer, wcześniej … |
| APPOINTMENT | Onet Piech | Ministerstwu Aktywów Państwowych |  | — Nie uważam, żebym dostał to stanowisko po linii politycznej — mówi Onetowi Pie… |
| POLITICAL_OFFICE | Sławomir Nitrasa | Minister |  | Na dyrektorskie fotele w Totalizatorze trafili byli kierownicy biur parlamentarn… |
| POLITICAL_OFFICE | Stanisław Gawłowski | Senator |  | Na dyrektorskie fotele w Totalizatorze trafili byli kierownicy biur parlamentarn… |
| PARTY_MEMBERSHIP | Donald Tuski | Platforma Obywatelska |  | A prywatnie — znajomy i piłkarski partner polityków Platformy Obywatelskiej, z p… |
| FORMER_PARTY_MEMBERSHIP | Sławomir Rybicki | Platforma Obywatelska |  | Na boisko dla jubilata wybiegli wtedy m.in. były szef kancelarii premiera Tomasz… |
| PARTY_MEMBERSHIP | Piotr Bresia | Prawo i Sprawiedliwość |  | Pewną wskazówką mogą być tutaj zarobki poprzednika Piecha na jego stanowisku, cz… |
| POLITICAL_OFFICE | Sebastian Nowaczkiewicz | Wójt |  | Jego zastępcą na nowym stanowisku jest z kolei Sebastian Nowaczkiewicz, były wój… |
| POLITICAL_OFFICE | Zbróg | Radny |  | Przypomnijmy, że Zbróg w latach 2014-2018 był radnym sejmiku wybranym właśnie z … |
| PARTY_MEMBERSHIP | Sławomir Czwal | Koalicja Obywatelska |  | Nowo wybranym dyrektorem w Rzeszowie jest kolejny działacz Koalicji Obywatelskie… |
| PARTY_MEMBERSHIP | Tomasz Lutak | Prawo i Sprawiedliwość |  | Poprzednim dyrektorem rzeszowskiego oddziału TS był Tomasz Lutak, niegdyś szef F… |
| ELECTION_CANDIDACY | Tomasz Lutak | None |  | Poprzednim dyrektorem rzeszowskiego oddziału TS był Tomasz Lutak, niegdyś szef F… |
| PARTY_MEMBERSHIP | Sławomir CzwalMateriały | Koalicja Obywatelska |  | Sławomir CzwalMateriały wyborcze KO |
| PARTY_MEMBERSHIP | Remigiusz Zagórskiemu | Lewica |  | W Bydgoszczy stanowisko dyrektora regionalnego przypadło Remigiuszowi Zagórskiem… |
| PARTY_MEMBERSHIP | Stanisław Gawłowski | Platforma Obywatelska |  | Beneficjentką zmian w Totalizatorze Sportowym została także Anna Makarewicz, wie… |
| PARTY_MEMBERSHIP | Stanisław GawłowskiMarcin | Koalicja Obywatelska |  | Senator KO Stanisław GawłowskiMarcin Obara / PAP |
| POLITICAL_OFFICE | Stanisław GawłowskiMarcin | Senator |  | Senator KO Stanisław GawłowskiMarcin Obara / PAP |
| POLITICAL_OFFICE | Nitrasa | Minister |  | Były dyrektor biura poselskiego ministra Nitrasa |
| PARTY_MEMBERSHIP | Sławomir Nitrasa | Platforma Obywatelska |  | W międzyczasie, w latach 2015-2019, był najpierw pracownikiem biurowym, a następ… |
| POLITICAL_OFFICE | Sławomir Nitrasa | Poseł |  | W międzyczasie, w latach 2015-2019, był najpierw pracownikiem biurowym, a następ… |
| PARTY_MEMBERSHIP | Marcin Posadza | Prawo i Sprawiedliwość |  | Wcześniej to stanowisko zajmował radny PiS Marcin Posadzy, który znalazł się na … |
| POLITICAL_OFFICE | Marcin Posadza | Radny |  | Wcześniej to stanowisko zajmował radny PiS Marcin Posadzy, który znalazł się na … |
| PARTY_MEMBERSHIP | Michał Małecki | Polskie Stronnictwo Ludowe |  | Michał Małecki (Polskie Stronnictwo Ludowe) |
| PARTY_MEMBERSHIP | Stanisław Gawłowski | Platforma Obywatelska |  | Stanisław Gawłowski (Platforma Obywatelska) |
| PERSONAL_OR_POLITICAL_TIE | Żona Magdalena Sekuła | Magdalena Sekuła |  | Na pytania o ewentualny konflikt interesów nie chciała odpowiadać też jego żona … |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| party_affiliation | 0.80 |  |  |  | subject=Sławomir Czwal | object=Koalicja Obywatelska |
| party_affiliation | 0.80 |  |  |  | subject=Remigiuszowi Zagórskiemu | object=Lewica |
| party_affiliation | 0.80 |  |  |  | subject=Stanisława Gawłowskiego | object=Platforma Obywatelska |
| party_affiliation | 0.80 |  |  |  | subject=Sławomira Nitrasa | object=Platforma Obywatelska |
| party_affiliation | 0.80 |  |  |  | subject=Marcin Posadzy | object=Prawo i Sprawiedliwość |
| governance_appointment | 0.80 | Olgierd Cieślik |  |  | role=prezes |
| governance_dismissal | 0.80 | Olgierd Cieślik |  |  | role=prezes |
| governance_appointment | 0.85 | Rafał Krzemień | Totalizatora |  | role=zarząd |
| governance_appointment | 0.90 | Adam Sekuła | Totalizatora |  | role=dyrektorem |
| governance_appointment | 0.82 | Małecki | Totalizatora Sportowego |  | role=dyrektora |
| governance_appointment | 0.80 | Małecki |  |  | role=zarządzie |
| governance_dismissal | 0.80 | Małecki |  |  | role=zarządzie |
| governance_appointment | 0.90 | Karol Wilczyński | Totalizatora Sportowego |  | role=Dyrektorem |
| governance_appointment | 0.79 | Zbróg |  |  | role=dyrektor |
| governance_appointment | 0.80 | Sławomir Czwal |  |  | role=dyrektorem |
| governance_appointment | 0.85 | Anna Makarewicz | Totalizatorze Sportowym |  |  |
| governance_appointment | 0.90 | Gawłowski | Onetowi |  | role=dyrektorem |
| governance_dismissal | 0.90 | Gawłowski | Onetowi |  | role=dyrektorem |
| governance_appointment | 0.80 | Sławomira Nitrasa |  |  | role=dyrektorem |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `APPOINTMENT`, `COMPENSATION`, `ELECTION_CANDIDACY`, `FORMER_PARTY_MEMBERSHIP`, `PARTY_MEMBERSHIP`, `PERSONAL_OR_POLITICAL_TIE`, `POLITICAL_OFFICE`
- ℹ️  **V2 emits** fact kinds not in V1: `governance_appointment`, `governance_dismissal`, `party_affiliation`

## `niezalezna_polski2050_synekury`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| APPOINTMENT | Łukasz Bałajewicz | Woj. | Prezes | Prezes – szef nowosądeckich struktur partii 3 stycznia 2024 roku, niespełna mies… |
| APPOINTMENT | Bartosz Wilk | Sejm |  | „Funkcją takiej konstrukcji prawnej powoływania rady w KZN jest zapewnienie nadz… |
| APPOINTMENT | Bałajewicz | Pegasusa | Rada Nadzorcza | Przewodniczącym został Bartosz Wilk, od marca br. doradca Marszałka Sejmu Szymon… |
| APPOINTMENT | Curyło | Pegasusa | Rada Nadzorcza | To wpływowy poseł Polski 2050, do niedawna członek sejmowej komisji śledczej ds.… |
| APPOINTMENT | Hołowni | Pegasusa | Rada Nadzorcza | Pegasusa (zastąpił go inny poseł Polski 2050 – Sławomir Ćwik). Curyło zaprzecza … |
| APPOINTMENT | Paweł Śliza | Pegasusa | Rada Nadzorcza | Curyło zaprzecza jednak, aby to dzięki Ślizowi trafił do Rady Nadzorczej KZN. – … |
| COMPENSATION | Łukasz Bałajewicz | Krajowy Zasób Nieruchomości | Prezes | Z informacji uzyskanej z KZN dowiedzieć się można, że zarabia miesięcznie ponad … |
| COMPENSATION | Poseł | Krajowy Zasób Nieruchomości | Poseł | Jak poinformował nas KZN, zarabia miesięcznie 11 tys. zł brutto. |
| COMPENSATION | Gabriela Sowa | Krajowy Zasób Nieruchomości |  | Najpierw jako rzecznik prasowy na pełnym etacie, a potem na 3/4 etatu z miesięcz… |
| COMPENSATION | Gabriela Sowa | Krajowy Zasób Nieruchomości |  | Z kolei w okresie wrzesień – listopad pracowała na pół etatu na stanowisku ekspe… |
| APPOINTMENT | Gabriela Sowa | Instytut Strategii |  | Waldemar Buda, europoseł PiS, wskazywał na swoim koncie na X, że w KZN zatrudnio… |
| POLITICAL_OFFICE | Rafał Komarewicz | Poseł |  | Z nieoficjalnych informacji „GP” wynika, że na szefa tej państwowej instytucji m… |
| POLITICAL_OFFICE | Emil Rojek | Wiek / Zastępca Wojewoda |  | W Radzie Nadzorczej KZN, która wybrała Bałajewicza na prezesa, zasiada też Emil … |
| POLITICAL_OFFICE | Emil Rojek | Wiek / Zastępca Wojewoda |  | W Radzie Nadzorczej KZN, która wybrała Bałajewicza na prezesa, zasiada też Emil … |
| POLITICAL_OFFICE | Sławomir Ćwik | Poseł |  | Pegasusa (zastąpił go inny poseł Polski 2050 – Sławomir Ćwik). |
| ELECTION_CANDIDACY | Michał Szymczyk | None |  | Michał Szymczyk, który był kandydatem na posła Polska 2050 z Gorlic, gdzie wiceb… |
| PARTY_MEMBERSHIP | Waldemar Buda | Prawo i Sprawiedliwość |  | Waldemar Buda, europoseł PiS, wskazywał na swoim koncie na X, że w KZN zatrudnio… |
| PERSONAL_OR_POLITICAL_TIE | Rafał Komarewicz | Szymon Hołownia |  | Z nieoficjalnych informacji „GP” wynika, że na szefa tej państwowej instytucji m… |
| PERSONAL_OR_POLITICAL_TIE | Bartosz Wilk | Szymon Hołownia |  | Przewodniczącym został Bartosz Wilk, od marca br. doradca Marszałka Sejmu Szymon… |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| political_support | 0.65 |  |  |  | subject=Polska 2050 | object=Michał Szymczyk |
| governance_appointment | 0.85 | Katarzynę Pełczyńską-Nałęcz | KZN |  | role=Prezes |
| governance_appointment | 0.90 | Donalda Tuska | KZN |  | role=prezesa |
| governance_appointment | 0.84 | Bałajewicza | KZN |  | role=prezesa |
| governance_appointment | 0.75 | Katarzyna Pełczyńska-Nałęcz |  |  | role=Rady Nadzorczej |
| governance_appointment | 0.90 | Bartosz Wilk | Sejmu |  | role=doradca |
| governance_appointment | 0.80 | Bałajewicza |  |  | role=Radzie Nadzorczej |
| governance_appointment | 0.74 | Szymona Hołowni |  |  | role=Radzie Nadzorczej |
| governance_appointment | 0.90 | Emil Rojek | RN KZN |  | role=Radzie Nadzorczej |
| governance_appointment | 0.75 | Curyło |  |  | role=Rady Nadzorczej |
| governance_appointment | 0.80 | Curyło |  |  | role=Rady Nadzorczej |
| public_employment | 0.90 | Bartosz Wilk | Sejmu |  | role=doradca |
| public_employment | 0.85 | Gabriela Sowa | KZN |  |  |
| compensation | 0.95 |  |  | 31 tys. zł | funder=KZN | recipient=Donalda Tuska |
| compensation | 0.85 |  |  | 11 tys. zł | funder=KZN |
| compensation | 1.00 |  |  | 10 tys. zł | funder=PiS | recipient=Waldemar Buda |
| personal_or_political_tie | 0.75 |  |  |  | subject=Waldemar Buda | object=Gabriela Sowa | context=związany |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `APPOINTMENT`, `COMPENSATION`, `ELECTION_CANDIDACY`, `PARTY_MEMBERSHIP`, `PERSONAL_OR_POLITICAL_TIE`, `POLITICAL_OFFICE`
- ℹ️  **V2 emits** fact kinds not in V1: `compensation`, `governance_appointment`, `personal_or_political_tie`, `political_support`, `public_employment`

## `radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj |  | żona Radka Zugaja |
| APPOINTMENT | Rząsowski | AMW Rewita | Rada Nadzorcza | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar… |
| COMPENSATION | Rząsowski | AMW Rewita | Rada Nadzorcza | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| APPOINTMENT | Rząsowski | Ministerstwu Obrony Narodowej |  | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| FORMER_PARTY_MEMBERSHIP | Marek Rząsowski | Platforma Obywatelska |  | Marek Rząsowski, radny powiatowy PO, został wiceprezesem spółki AMW Rewita zarzą… |
| POLITICAL_OFFICE | Marek Rząsowski | Radny |  | Marek Rząsowski, radny powiatowy PO, został wiceprezesem spółki AMW Rewita zarzą… |
| POLITICAL_OFFICE | Cezary Tomczyk | Wiek / Zastępca Minister |  | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar… |
| POLITICAL_OFFICE | Cezary Tomczyk | Wiek / Zastępca Minister |  | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar… |
| ELECTION_CANDIDACY | Jacek Łęski | None |  | Zaczynał w kampanii wyborczej Jacka Łęskiego, który startował na prezydenta Rado… |
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj |  | Ciekawe kto jeszcze okaże się super fachowcem w spółkach Skarbu Państwa, SŁABO T… |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| party_affiliation | 0.80 |  |  |  | subject=Marek Rząsowski | object=Platforma Obywatelska |
| governance_appointment | 0.90 | Rząsowski | AMW Rewita |  | role=radę nadzorczą |
| governance_appointment | 0.82 | Rząsowski | AMW Rewita |  | role=radę nadzorczą |
| governance_appointment | 0.79 | Marek Rząsowski |  |  | role=radę nadzorczą |
| compensation | 0.93 |  |  | 24 tys. zł | funder=PO | recipient=Rząsowskiego |
| personal_or_political_tie | 0.80 |  |  |  | subject=Mirella Zugaj | object=Radka Zugaja | context=spouse |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `APPOINTMENT`, `COMPENSATION`, `ELECTION_CANDIDACY`, `FORMER_PARTY_MEMBERSHIP`, `PERSONAL_OR_POLITICAL_TIE`, `POLITICAL_OFFICE`
- ℹ️  **V2 emits** fact kinds not in V1: `compensation`, `governance_appointment`, `party_affiliation`, `personal_or_political_tie`

## `oko_miliony_pajeczyna_rydzyka`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| FUNDING | NIW | Fundacja Lux Veritatis |  | Wprawdzie realizowała go założona przez o. |
| FUNDING | NIW | Fundacja Lux Veritatis |  | Jak ustaliliśmy, realizacja Parku pochłonęła co najmniej 17,7 mln zł. |
| FUNDING | Instytut Wolności | NIW |  | Wiemy, że ubiegała się jeszcze o trzy dotacje na Park Pamięci z ministerstwa kul… |
| FUNDING | NIW | NIW |  | Jednak ani resort kultury, ani NIW dotacji na park nie przyznały. |
| FUNDING | Muzeum Pamięć | Fundacja Lux Veritatis |  | Resort wyłoży 117,7 mln zł na budowę jego siedziby i nieznaną jeszcze dziś sumę … |
| FUNDING | Fundacja Lux Veritatis | Jastrzębskie Zakłady Remontowe |  | * Po publikacji otrzymaliśmy potwierdzenie z Fundacji Lux Veritatis, że 100 tys.… |
| PUBLIC_CONTRACT | Lux Veritatis | Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w Toruniu |  | W grudniu 2019 roku Wojewódzki Fundusz Ochrony Środowiska i Gospodarki Wodnej w … |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| funding | 0.85 |  |  | 520 tys. zł | funder=Narodowego Instytutu Wolności |
| funding | 0.85 |  |  | 5 mln zł | funder=Fundacji Lux Veritatis |
| funding | 0.85 |  |  | 300 tys. zł | funder=Wojewódzki Fundusz Ochrony Śro… | recipient=Lux Veritatis |
| public_contract | 0.85 |  |  | 300 tys. zł | counterparty=Wojewódzki Fundusz Ochrony Śro… | contractor=Lux Veritatis |
| funding | 0.85 |  |  | 200 tys. zł |  |
| public_contract | 0.85 |  |  | 200 tysięcy złotych | counterparty=Jastrzębska Spółka Węglowa |
| funding | 0.85 |  |  | 520 tys. zł |  |
| funding | 0.85 |  |  | 100 tys. zł | funder=Fundacji Lux Veritatis | recipient=Jastrzębskie Zakłady Remontowe |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `FUNDING`, `PUBLIC_CONTRACT`
- ℹ️  **V2 emits** fact kinds not in V1: `funding`, `public_contract`

## `wp_zona_sekretarza_krasnik_20260513`
**Relevance**: V1=? | V2=True
### V1 facts
| kind | subject | object | role | evidence |
|------|---------|--------|------|----------|
| PERSONAL_OR_POLITICAL_TIE | Żona Łukasza Skokowskiego | Magdalena Skokowska |  | żona Łukasza Skokowskiego |
| PERSONAL_OR_POLITICAL_TIE | Mąż Magdaleny Skokowskiej | Łukasz Skokowski |  | mąż Magdaleny Skokowskiej |
| DISMISSAL | Agnieszka Bebel | MOSiR w Kraśniku | Rada Nadzorcza | Nowy burmistrz po tygodniu urzędowania odwołał Agnieszkę Bebel z rady nadzorczej… |
| APPOINTMENT | Michał Stawiarski | MOSiR w Kraśniku | Dyrektor | Była połowa maja. W czerwcu nowym dyrektorem MOSiR w Kraśniku został Michał Staw… |
| APPOINTMENT | Magdalena Skokowska | Urzędu Miasta |  | Radny odkrywa trzy umowy żony sekretarza UM Kraśnik Pani Agnieszka podreperowała… |
| APPOINTMENT | Magdalena Skokowska | MOPS |  | W sprawie powodów zwolnienia radcy odsyła do kierowniczki MOPS. Zatem pytam kier… |
| COMPENSATION | Magdalena Skokowska | Urzędzie Miasta Kraśnik | Radny | Z dokumentów, które dostał z urzędu radny Janczarek wynika, że kobieta w sumie d… |
| APPOINTMENT | Magdalena Skokowska | Urzędu Miasta |  | Magdalena Skokowska pytania o jej zatrudnienie odbiera jako "formę nękania" jej … |
| PARTY_MEMBERSHIP | Wojciech Wilka | Platforma Obywatelska |  | W drugiej turze zmierzyli się urzędujący do tej pory Wojciech Wilk z PO oraz Krz… |
| PARTY_MEMBERSHIP | Jarosław Stawiarski | Prawo i Sprawiedliwość |  | To nie przypadek, że jego kandydaturę wspierał pochodzący z Kraśnika marszałek J… |
| ELECTION_CANDIDACY | Krzysztof Staruch | None |  | Fanpage należący do Stawiarskiego na dwa miesiące przed wyborami zmienił nazwę n… |
| POLITICAL_OFFICE | Piotr Janczarek | Radny |  | Informacja wyszła na jaw dzięki interpelacji złożonej przez opozycyjnego radnego… |
| PARTY_MEMBERSHIP | Piotr Janczarek | Polskie Stronnictwo Ludowe |  | Uważam, że to nie świadczy o dobrym funkcjonowaniu urzędu - mówi radny Piotr Jan… |
| POLITICAL_OFFICE | Piotr Janczarek | Radny |  | Uważam, że to nie świadczy o dobrym funkcjonowaniu urzędu - mówi radny Piotr Jan… |
| POLITICAL_OFFICE | Janczarek | Radny |  | Z dokumentów, które dostał z urzędu radny Janczarek wynika, że kobieta w sumie d… |
| PERSONAL_OR_POLITICAL_TIE | Michał Stawiarski | Stawiarski |  | W czerwcu nowym dyrektorem MOSiR w Kraśniku został Michał Stawiarski, syn wspomn… |
| PERSONAL_OR_POLITICAL_TIE | Żona Łukasza Skokowskiego | Magdalena Skokowska |  | Ale ostatnio złe wspomnienia wróciły, kiedy dowiedziała się, że jej miejsce na z… |
| PERSONAL_OR_POLITICAL_TIE | Mąż Magdaleny Skokowskiej | Łukasz Skokowski |  | Każde z nich to instytucja podległa Urzędowi Miasta Kraśnik, w którym sekretarze… |
### V2 facts (score ≥ 0.5)
| kind | score | person | org | amount | other |
|------|-------|--------|-----|--------|-------|
| party_affiliation | 0.80 |  |  |  | subject=Wojciech Wilk | object=Platforma Obywatelska |
| political_support | 0.65 |  |  |  | subject=Prawo i Sprawiedliwość | object=Krzysztof Staruch |
| governance_appointment | 0.85 | Agnieszka Bebel | Miejskiego Ośrodka Pomocy Społ… |  |  |
| governance_dismissal | 0.85 | Agnieszka Bebel | Miejskiego Ośrodka Pomocy Społ… |  |  |
| governance_dismissal | 0.80 | Agnieszkę Bebel |  |  | role=burmistrz |
| governance_appointment | 0.90 | Michał Stawiarski | MOSiR w Kraśniku |  | role=dyrektorem |
| governance_appointment | 0.85 | Michał Stawiarski | MOSiR |  |  |
| governance_appointment | 0.90 | Agnieszkę | MOPS |  | role=burmistrza |
| governance_dismissal | 0.79 | Agnieszka Bebel |  |  | role=burmistrza |
| governance_appointment | 0.74 | Wojciechem Wilkiem |  |  | role=burmistrza |
| governance_dismissal | 0.80 | Staruch | MOPS |  |  |
| governance_dismissal | 0.85 | Agnieszki Bebel | MOPS |  |  |
| personal_or_political_tie | 0.80 |  |  |  | subject=Michał Stawiarski | object=Stawiarskiego | context=child |
| personal_or_political_tie | 0.80 |  |  |  | subject=Magdalena Skokowska | object=Łukasza Skokowskiego | context=spouse |
| personal_or_political_tie | 0.80 |  |  |  | subject=Łukasz Skokowski | object=Magdaleny Skokowskiej | context=spouse |
### Gap analysis
- ⚠️  **V2 missing** fact kinds present in V1: `APPOINTMENT`, `COMPENSATION`, `DISMISSAL`, `ELECTION_CANDIDACY`, `PARTY_MEMBERSHIP`, `PERSONAL_OR_POLITICAL_TIE`, `POLITICAL_OFFICE`
- ℹ️  **V2 emits** fact kinds not in V1: `governance_appointment`, `governance_dismissal`, `party_affiliation`, `personal_or_political_tie`, `political_support`

