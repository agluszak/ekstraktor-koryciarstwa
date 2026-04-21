# Expected Findings For Comparison

This file is a manual target for evaluating extraction quality on specific Polish articles.
It is intentionally high-signal rather than exhaustive. The goal is to compare the
pipeline output against what a human reader would reasonably expect the v1 system to recover.

## 1. WP: Lubczyk dalej ciągnie kasę z Sejmu. Ale są lepsi od niego

Source:
- https://wiadomosci.wp.pl/lubczyk-dalej-ciagnie-kase-z-sejmu-ale-sa-lepsi-od-niego-6998874649205248a

Expectation:
- This article is **relevant public-money oversight**, but not a classic appointment article.
- It is about parliamentary salaries paid from public funds and should be treated as part of the broader
  "koryciarstwo / public money extraction" monitoring surface.

Likely relevant entities:
- Radosław Lubczyk
- Robert Dowhan
- Szymon Hołownia
- Katarzyna Karpa-Świderek
- Koalicja Obywatelska
- Sejm / Kancelaria Sejmu

Expected extraction outcome:
- Relevance should likely be `true`.
- The pipeline should at least recover people and the public institution paying the money.
- No `APPOINTMENT` or `MEMBER_OF_BOARD` finding is required here unless the article itself mentions company posts.
- A generic public-money / remuneration signal would be useful in future versions.

Useful comparison note:
- If the pipeline treats all salary-in-public-office articles as irrelevant, that is too narrow for the project.

## 2. Demagog: Nie dostali się do parlamentu – trafili do spółek Skarbu Państwa [Lista]

Source:
- https://demagog.org.pl/analizy_i_raporty/nie-dostali-sie-do-parlamentu-trafili-do-spolek-skarbu-panstwa-lista/

Expectation:
- This article is **strongly in scope**.
- It is a list-style article about unsuccessful parliamentary candidates who later obtained positions in companies with Treasury ownership.

Expected high-level findings:
- Many `Person` entities.
- Many `Organization` entities for state-owned or Treasury-controlled companies.
- Many `PoliticalParty` entities: Koalicja Obywatelska, Lewica / Nowa Lewica, Trzecia Droga, PSL.
- Many appointment events, mostly into supervisory boards and sometimes management boards.

Expected person -> organization findings explicitly visible in the article:
- Piotr Szymanek -> Energa Elektrownie Ostrołęka
  Expected facts: `MEMBER_OF_BOARD`, likely also `APPOINTMENT`
- Piotr Szymanek -> Energa
  Expected fact: management appointment, vice-president role
- Karol Bielski -> PKP Telkol
  Expected fact: `MEMBER_OF_BOARD`
- Leszek Świętowski -> Zakład Mechaniczny "Siarkopol"
  Expected fact: `MEMBER_OF_BOARD`
- Leszek Zawadzki -> Pomorska Agencja Rozwoju Regionalnego
  Expected fact: `MEMBER_OF_BOARD`
- Michał Olejniczak -> Narzędziownia-Mechanik
  Expected fact: `MEMBER_OF_BOARD`
- Marek Rutka -> Zarząd Morskiego Portu Gdynia
  Expected fact: `MEMBER_OF_BOARD`
- Bartłomiej Gębala -> Nowe Centrum Administracyjne
  Expected fact: `MEMBER_OF_BOARD`
- Andrzej Pilot -> JSW Logistics
  Expected fact: `MEMBER_OF_BOARD`
- Magdalena Roguska -> Polska Wytwórnia Papierów Wartościowych
  Expected fact: appointment to supervisory board
- Magdalena Roguska -> resignation / board exit
  Expected event: dismissal/resignation style governance event if the system handles it

Expected party links:
- Piotr Szymanek -> Trzecia Droga
- Karol Bielski -> PSL / Trzecia Droga
- Leszek Świętowski -> PSL / Trzecia Droga
- Leszek Zawadzki -> PSL / Trzecia Droga
- Michał Olejniczak -> Nowa Lewica
- Marek Rutka -> Nowa Lewica
- Bartłomiej Gębala -> Platforma Obywatelska / Koalicja Obywatelska
- Andrzej Pilot -> Koalicja Obywatelska
- Magdalena Roguska -> Platforma Obywatelska / Koalicja Obywatelska

Expected comparison standard:
- The pipeline should recover multiple appointments from this article.
- If it only extracts entities without board/appointment links, that is underperformance.

## 3. Olsztyn.com.pl: zarobki prezesów przedsiębiorstw wodociągowych

Source:
- https://www.olsztyn.com.pl/artykul,sprawdzili-zarobki-prezesow-przedsiebiorstw-wodociagowych-w-najwiekszych-miastach-ile-zarabia-prezes-wodkanu,33659.html

Expectation:
- This article is **relevant** because it tracks high salaries paid by public or municipal utility companies.
- It is not a classic network-nepotism article, but it is still part of the broader "koryto / public money" scope.

Likely relevant entities:
- Wiesław Pancer
- Henryk Milcarz
- Przedsiębiorstwo Wodociągów i Kanalizacji w Olsztynie
- Wodociągi Kieleckie
- Stowarzyszenie Przyjazne Kielce

Expected extraction outcome:
- Relevance should likely be `true`.
- The system should recover person-role-organization facts where possible.
- Expected examples:
  - Wiesław Pancer -> Przedsiębiorstwo Wodociągów i Kanalizacji w Olsztynie
    Expected role: president / prezes
  - Henryk Milcarz -> Wodociągi Kieleckie
    Expected role: president / prezes
- Salary figures are important metadata for this project even if no family/friend link is stated.

Useful comparison note:
- This should not be discarded as irrelevant just because it lacks explicit party/family ties.

## 4. Rzeczpospolita: Posady współpracowników Klicha

Source:
- https://www.rp.pl/polityka/art15805981-posady-wspolpracownikow-klicha

Expectation:
- This article is **strongly in scope**.
- It is a classic patronage/nepotism-style article about associates of a politician obtaining positions in state-involved companies.

Expected core entities:
- Bogdan Klich
- Jarosław Hodura
- Marcin Dulian
- Krzysztof Kuczmański
- Grupa Hoteli WAM
- Przedsiębiorstwo Usług Hotelarskich i Turystycznych
- MON
- Platforma Obywatelska

Expected facts:
- Jarosław Hodura -> Grupa Hoteli WAM
  Expected: `APPOINTMENT` or equivalent employment/position relation
- Jarosław Hodura -> Bogdan Klich
  Expected: `PERSONAL_OR_POLITICAL_TIE` with acquaintance / collaborator semantics
- Marcin Dulian -> Grupa Hoteli WAM
  Expected: management-board / president role
- Marcin Dulian -> Bogdan Klich
  Expected: `PERSONAL_OR_POLITICAL_TIE` with friend / former bureau chief semantics
- Krzysztof Kuczmański -> Przedsiębiorstwo Usług Hotelarskich i Turystycznych
  Expected: `APPOINTMENT`, management / president role
- Krzysztof Kuczmański -> Bogdan Klich
  Expected: `PERSONAL_OR_POLITICAL_TIE` with acquaintance / campaign helper semantics
- Bogdan Klich -> Platforma Obywatelska
  Expected: `PARTY_MEMBERSHIP`

Important text cues:
- "dostał się bez konkursu"
- "od grudnia jest prezesem"
- "znajomy szefa MON"
- "były szef biura europoselskiego Klicha i jego wieloletni przyjaciel"

Expected comparison standard:
- This article should definitely yield non-empty facts.
- If the system fails to emit acquaintance links and appointment facts here, extraction coverage is still too weak.

## 5. Onet: Partyjny desant na Totalizator Sportowy

Source:
- https://wiadomosci.onet.pl/kraj/partyjny-desant-na-totalizator-sportowy-oni-dostali-lukratywne-stanowiska/7nvq01b

Expectation:
- This article is **strongly in scope**.
- It is a classic patronage article about politically connected people receiving regional director roles in a state-owned company.

Expected core entities:
- Totalizator Sportowy
- Donald Tusk
- Sławomir Nitras
- Stanisław Gawłowski
- Rafał Krzemień
- Olgierd Cieślik
- local PO / PSL / Lewica appointees named in the body

Expected facts:
- Multiple `APPOINTMENT` findings into `Totalizator Sportowy`
- Multiple `HOLDS_POSITION_AT` or equivalent management-role findings for regional director roles
- At least one `DISMISSAL` or `dismissal` event for earlier management removals
- Multiple `PARTY_MEMBERSHIP` findings for PO, PSL, Lewica
- Multiple typed `PERSONAL_OR_POLITICAL_TIE` findings for collaborator / parliamentary-office / political-network ties
- Compensation metadata should appear where the article states that directors can earn over `20 tys. zł miesięcznie`

Important text cues:
- "powołując osoby z jasnymi politycznymi powiązaniami"
- "Partyjni działacze dostali kierownicze stanowiska"
- "na dyrektorskie fotele"
- "byli kierownicy biur parlamentarnych"
- "mogą zarobić nawet ponad 20 tys. zł miesięcznie"

Expected comparison standard:
- If the system only emits `Totalizator Sportowy` plus a few names, it is underperforming.
- This article should yield multiple appointments, multiple party ties, and at least one compensation signal.

## 6. Radomszczańska: Nowy zaciąg tłustych...

Source:
- https://radomszczanska.pl/artykul/nowy-zaciag-tlustych-n1256470

Expectation:
- This article is **in scope**.
- It is a direct appointment / party-network article about a local PO politician moving into a state-linked company role.

Expected core entities:
- Marek Rząsowski
- AMW Rewita
- Platforma Obywatelska
- Cezary Tomczyk
- Ministerstwo Obrony Narodowej

Expected facts:
- Marek Rząsowski -> `APPOINTMENT` -> AMW Rewita
- Marek Rząsowski -> `HOLDS_POSITION_AT` -> AMW Rewita
  Expected role: `wiceprezes`
- Marek Rząsowski -> `PARTY_MEMBERSHIP` -> Platforma Obywatelska
- AMW Rewita should be recognized as a state-controlled / MON-linked organization
- Compensation metadata should be captured from the line about the predecessor earning `24 tys. zł brutto`

Important text cues:
- "radny powiatowy PO"
- "został wiceprezesem spółki AMW Rewita"
- "nominowany przez radę nadzorczą"
- "spółka podległa Ministerstwu Obrony Narodowej"

Expected comparison standard:
- At minimum, this article should yield one appointment, one party tie, one role, and one state-company signal.

## 7. Onet: Nowe władze WFOŚiGW w Lublinie bez konkursu

Source:
- https://wiadomosci.onet.pl/lublin/nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow/cpw9ltt

Expectation:
- This article is **strongly in scope**.
- It is a governance-nepotism story combining party affiliation, no-competition appointment, board changes, and high compensation.

Expected core entities:
- Stanisław Mazur
- Andrzej Kloc
- Agnieszka Kruk
- Anna Pokwapisz
- Paulina Hennig-Kloska
- WFOŚiGW w Lublinie
- NFOŚiGW
- Lewica
- PSL
- Polska 2050
- Platforma Obywatelska
- PiS

Expected facts:
- Stanisław Mazur -> `APPOINTMENT` -> WFOŚiGW w Lublinie
  Expected role: `prezes`
- Andrzej Kloc -> `APPOINTMENT` -> WFOŚiGW w Lublinie
  Expected role: `wiceprezes`
- Agnieszka Kruk -> `DISMISSAL` -> WFOŚiGW w Lublinie
- Anna Pokwapisz -> `DISMISSAL` -> WFOŚiGW w Lublinie
- Stanisław Mazur -> `PARTY_MEMBERSHIP` -> Lewica
- Andrzej Kloc -> `PARTY_MEMBERSHIP` -> PSL
- board-member party links should also be recoverable where possible
- Compensation metadata should be captured from the line about `kilkadziesiąt tysięcy złotych miesięcznie`

Important text cues:
- "bez konkursu"
- "odebrał dziś nominację"
- "rada nadzorcza odwołała"
- "nowym prezesem... ma zostać"
- "wiceprezesem... Andrzej Kloc z PSL"

Expected comparison standard:
- This article should produce both appointments and dismissals.
- If the system misses the Kruk / Pokwapisz removals or the Mazur / Kloc appointments, the dismissal-and-appointment layer is still too weak.

## 8. Niezależna: Uśmiechnięte synekury Polski 2050

Source:
- https://niezalezna.pl/polityka/usmiechniete-synekury-polski-2050-31-tys-zl-dla-prezesa-kzn-i-etaty-dla-dzialaczy/533532

Expectation:
- This article is **strongly in scope**.
- It is a party-patronage / public-money article focused on appointments and employment ties around `Polska 2050` and `Krajowy Zasób Nieruchomości`.

Expected core entities:
- Łukasz Bałajewicz
- Rafał Komarewicz
- Szymon Hołownia
- Katarzyna Pełczyńska-Nałęcz
- Krajowy Zasób Nieruchomości
- Polska 2050
- PSL
- Koalicja Obywatelska
- Lewica

Expected facts:
- Łukasz Bałajewicz -> `APPOINTMENT` or `HOLDS_POSITION_AT` -> Krajowy Zasób Nieruchomości
  Expected role: `prezes`
- Łukasz Bałajewicz -> `PARTY_MEMBERSHIP` -> Polska 2050
- Rafał Komarewicz -> `PERSONAL_OR_POLITICAL_TIE` -> Łukasz Bałajewicz
  Expected relationship type: `recommender`, `party_patron`, or similar
- other KZN staff / board figures linked to `Polska 2050` should be extracted where the article names them
- Compensation metadata should capture `ponad 31 tys. zł brutto miesięcznie`

Important text cues:
- "obsadzają swoimi ludźmi"
- "pełniącym obowiązki prezesa KZN został"
- "działacz Polski 2050"
- "zarabia miesięcznie ponad 31 tys. zł brutto"
- "miał go rekomendować Rafał Komarewicz"

Expected comparison standard:
- This article should yield at least one appointment, one party affiliation, one typed political tie, and one compensation fact.

## 9. OKO.press: Miliony. Pajęczyna Rydzyka

Source:
- https://oko.press/miliony-pajeczyna-rydzyka

Expectation:
- This article is **in scope**, but it is structurally harder than the appointment pieces.
- It is about flows of public money from state institutions and companies into projects associated with `Tadeusz Rydzyk` and `Fundacja Lux Veritatis`, not a simple one-person-one-board-seat pattern.

Expected core entities:
- Tadeusz Rydzyk
- Fundacja Lux Veritatis
- Park Pamięci Narodowej
- Ministerstwo Kultury
- Narodowy Instytut Wolności
- state institutions and state-owned companies financing the project

Expected extraction outcome:
- Relevance should be `true`.
- The system should recover at least:
  - Tadeusz Rydzyk
  - Fundacja Lux Veritatis
  - one or more public institutions / state-owned entities providing money
  - one or more compensation / funding facts tied to the project
- This article is a good test for broadening the project beyond narrow board-only extraction.

Important text cues:
- "pieniądze wyłożyły w znacznej części państwowe instytucje i spółki"
- "realizacja Parku pochłonęła co najmniej 17,7 mln zł"
- "dotacje"
- "dofinansowania"

Expected comparison standard:
- Partial coverage is acceptable in the near term.
- A good first-pass result here is non-empty funding facts and public-institution links, not perfect full-network reconstruction.

## 10. TVP Olsztyn: Jarosław Słoma w zarządzie olsztyńskich wodociągów

Source:
- https://olsztyn.tvp.pl/41863255/z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow

Expectation:
- This article is **in scope**.
- It is a direct appointment story concerning a former local politician moving into a senior role in a municipal utility.

Expected core entities:
- Jarosław Słoma
- Przedsiębiorstwo Wodociągów i Kanalizacji w Olsztynie
- WodKan

Expected facts:
- Jarosław Słoma -> `APPOINTMENT` or `HOLDS_POSITION_AT` -> Przedsiębiorstwo Wodociągów i Kanalizacji w Olsztynie
  Expected role: `wiceprezes` / `zastępca prezesa`
- Event date should preferably capture `25 lutego` if the parser can normalize it from context
- The article should be treated as a municipal-company governance case

Important text cues:
- "z wiceprezydenta na wiceprezesa"
- "od 25 lutego zajął nową funkcję"
- "Przedsiębiorstwo Wodociągów i Kanalizacji"

Expected comparison standard:
- Even if the article body is thin, the title and metadata alone should be enough to recover a strong appointment signal.

## 11. TVN24: Kolesiostwo i rozdawanie posad...

Source:
- https://tvn24.pl/polska/kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831v

Expectation:
- This article is **in scope** as a local patronage / public-appointments complaint article.
- The exact live URL was not directly retrievable, but the article is available from the Wayback snapshot:
  `https://web.archive.org/web/20250427191848/https://tvn24.pl/polska/kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831`

Expected core entities:
- Dorota Połedniok
- Donald Tusk
- Jacek Guzy
- Jacek Matusewicz
- local Platforma Obywatelska structures in Siemianowice Śląskie
- Forum Samorządowe
- Siemianowice Śląskie
- Szpital Miejski

Expected extraction outcome:
- Relevance should likely be `true`.
- The system should recover:
  - strong patronage / `kolesiostwo` language
  - PO / local-coalition context
  - public-position / local-power-network framing
  - at least one typed `PERSONAL_OR_POLITICAL_TIE` or conflict / patronage-network signal between local party actors and city authorities

Important text cues:
- "Kolesiostwo, rozdawanie posad, brak wizji działania"
- "prezydentem miasta"
- "PO tworzy tam koalicję z lokalnym Forum Samorządowym"
- "lokalnych partyjnych baronów"
- "nagrody dla prezydentów i członków jego ekipy"

Expected comparison standard:
- This is not a board-appointment article, but it is still a valid `koryciarstwo` benchmark.
- A reasonable first-pass result is non-empty relevance plus people / party / municipal-power-network extraction, even if there is no clean `APPOINTMENT` event.

## 12. WP: Odpartyjnienie rad nadzorczych? "Nie tak miało być, wygląda to bardzo źle"

Source:
- https://wiadomosci.wp.pl/odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle-6996280410176160a

Saved input:
- [wiadomosci.wp.pl__odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle__6996280410176160a.html](</D:/extractor/inputs/wiadomosci.wp.pl__odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle__6996280410176160a.html>)

Expectation:
- This article is **strongly in scope**.
- It is a governance / board-appointments article about political nominations to the supervisory board of a major public institution despite public promises of depoliticization.

Expected core entities:
- Narodowy Fundusz Ochrony Środowiska i Gospodarki Wodnej
- Szymon Hołownia
- Paulina Hennig-Kloska
- Emilia Wasielewska
- Polska 2050
- Trzecia Droga

Expected facts:
- at least one `MEMBER_OF_BOARD` or `APPOINTMENT` fact into the supervisory board of NFOŚiGW
- at least one `PARTY_MEMBERSHIP` fact for Polska 2050
- at least one governance / nomination fact tied to Paulina Hennig-Kloska or the ministry context

Important text cues:
- "obsadzeniu Rady Nadzorczej"
- "politykami Polski 2050"
- "odpolitycznieniu rad"
- "wiceprzewodniczącą rady została Emilia Wasielewska"
- "startowała w wyborach parlamentarnych z list Trzeciej Drogi"

Expected comparison standard:
- This should not degrade into generic party co-occurrence.
- The main expected outcome is a clean board/governance fact attached to a public institution, plus party context for the appointees.

## 13. Onet: Tak PSL obsadził państwową spółkę. Pracę dostał m.in. 29-letni brat wiceministra

Source:
- https://wiadomosci.onet.pl/kraj/tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra/ezt8y9t

Saved input:
- [wiadomosci.onet.pl__kraj__tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra__ezt8y9t.html](</D:/extractor/inputs/wiadomosci.onet.pl__kraj__tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra__ezt8y9t.html>)

Expectation:
- This article is **strongly in scope**.
- It is a classic state-company patronage article about PSL-linked appointments into a PKP subsidiary without open competition.

Expected core entities:
- Natura Tour
- PKP
- Dariusz Klimczak
- Konrad Wojnarowski
- Andrzej Grzyb
- Adam Struzik
- Jolanta Sobczyk
- Polskie Stronnictwo Ludowe
- Trzecia Droga

Expected facts:
- Jolanta Sobczyk -> `APPOINTMENT` -> Natura Tour
  Expected role: `prezes`
- multiple `MEMBER_OF_BOARD` / board facts for people tied to PSL in Natura Tour
- multiple `PARTY_MEMBERSHIP` facts for PSL
- at least one typed `PERSONAL_OR_POLITICAL_TIE` fact such as acquaintance / sibling / family-political tie when explicitly stated

Important text cues:
- "żadnych konkursów do zarządu i rady nadzorczej nie było"
- "najważniejsze stanowiska w spółce objęli ludzie bezpośrednio związani z Polskim Stronnictwem Ludowym"
- "związana z Trzecią Drogą Jolanta Sobczyk"
- "prywatnie znajoma nadzorującego PKP ministra Dariusza Klimczaka"
- "29-letni brat wiceministra"

Expected comparison standard:
- This article should yield multiple non-empty governance facts.
- If the pipeline only extracts people and `PSL`, it is underperforming.

## 14. Gazeta Krakowska: To koniec rządów Katarzyny Zapał w Zarządzie Budynków Komunalnych

Source:
- https://gazetakrakowska.pl/za-jej-czasow-wybuchla-w-krakowie-wielka-afera-to-koniec-rzadow-katarzyny-zapal-w-zarzadzie-budynkow-komunalnych/ar/c1p2-27523231

Fetch note:
- direct live HTML fetch is currently blocked by a Cloudflare challenge in this repo environment
- expectation below is based on the available crawled article snapshot

Expectation:
- This article is **in scope** as a municipal-governance / dismissal article.
- It is not a narrow board-nepotism case, but it clearly belongs to the broader public-institution corruption / patronage monitoring set.

Expected core entities:
- Katarzyna Zapał
- Zarząd Budynków Komunalnych w Krakowie
- Bogusław Kośmider
- Krakowski Holding Komunalny
- Marcin Paradyż
- Jacek Majchrowski
- Aleksander Miszalski

Expected facts:
- Katarzyna Zapał -> `DISMISSAL` or equivalent exit fact -> Zarząd Budynków Komunalnych
- Marcin Paradyż -> succession / `APPOINTMENT` or role-change fact -> Zarząd Budynków Komunalnych
- Bogusław Kośmider -> Krakowski Holding Komunalny
  Expected role: `prezes`
- optional public-corruption / municipal-afera context should raise relevance even if kinship/party ties are absent

Important text cues:
- "odchodzi Katarzyna Zapał"
- "następcą Zapał ma zostać Marcin Paradyż"
- "prezes zarządu Krakowskiego Holdingu Komunalnego"
- "największa miejska afera korupcyjna"

Expected comparison standard:
- This should at minimum produce a governance exit/change event.
- If the pipeline misses the dismissal/change entirely, municipal-governance coverage is still too weak.

## 15. Pleszew24: Radna powiatowa z posadą. Zmiana prezesa słynnej państwowej stadniny koni

Source:
- https://pleszew24.info/pl/12_biznes/16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni.html

Saved input:
- [pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni.html](</D:/extractor/inputs/pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni.html>)

Expectation:
- This article is **strongly in scope**.
- It is a state-company appointment article with explicit party context and a management change.

Expected core entities:
- A. Góralczyk
- Stadnina Koni Iwno
- Przemysław Pacia
- Krajowy Ośrodek Wsparcia Rolnictwa
- Wojewódzki Ośrodek Doradztwa Rolniczego
- Polskie Stronnictwo Ludowe

Expected facts:
- A. Góralczyk -> `APPOINTMENT` -> Stadnina Koni Iwno
  Expected role: `prezes zarządu`
- Przemysław Pacia -> `DISMISSAL` or equivalent exit event -> Stadnina Koni Iwno
- A. Góralczyk -> `PARTY_MEMBERSHIP` -> PSL
- KOWR should be recognized as the controlling public institution supervising the stadnina

Important text cues:
- "działaczka Polskiego Stronnictwa Ludowego"
- "awansowała na stanowisko prezesa zarządu"
- "spółki Skarbu Państwa"
- "odwołano poprzedniego prezesa"
- "KOWR sprawuje nadzór właścicielski nad stadniną"

Expected comparison standard:
- This article should yield one appointment, one dismissal/change fact, one party tie, and one state-ownership signal.

## 16. eM Kielce: Zarzuty o nepotyzm i ostre personalne spory w kieleckim Ratuszu

Source:
- https://emkielce.pl/miasto-4/zarzuty-o-nepotyzm-i-ostre-personalne-spory-w-kieleckim-ratuszu-80925

Expectation:
- This article is **in scope**, but most relevant claims appear as quoted political allegations and
  rebuttals during a city council dispute.
- Extraction should preserve caution: the article reports allegations of nepotism and employment of
  politically/family-connected people, not confirmed wrongdoing.
- Focus benchmark interpretation on the section beginning with "Żona Karola Wilczyńskiego".

Expected core entities:
- Karol Wilczyński
- wife / partner of Karol Wilczyński
- Maciej Jakubczyk
- Agata Wojda
- Koalicja Obywatelska
- Miejski Urząd Pracy
- Kielecki Park Technologiczny
- Radio Kielce / public-linked company connected with Radio Kielce

Expected facts:
- Wife/partner of Karol Wilczyński -> `PERSONAL_OR_POLITICAL_TIE` -> Karol Wilczyński
  Expected relation: spouse/partner/family tie.
- Wife/partner of Karol Wilczyński -> employment / `APPOINTMENT`-style fact -> public-linked unit
  connected with Radio Kielce or Kielecki Park Technologiczny.
  This should be marked as weak/allegation or quoted context if the output model supports it.
- Sister of Karol Wilczyński -> `PERSONAL_OR_POLITICAL_TIE` -> Karol Wilczyński
  Expected relation: sibling/family tie.
- Sister of Karol Wilczyński -> `APPOINTMENT` or role fact -> Miejski Urząd Pracy
  Expected role: dyrektor / pełniąca obowiązki dyrektora.
- Karol Wilczyński -> `PARTY_MEMBERSHIP` or political affiliation -> Koalicja Obywatelska.

Important text cues:
- "Żona Karola Wilczyńskiego była zatrudniona..."
- "Moja partnerka jest zatrudniona od 10 lat w jednostce publicznej w Kieleckim Parku Technologicznym"
- "Siostra pana przewodniczącego została dyrektorem Miejskiego Urzędu Pracy"
- "radny Karol Wilczyński z Koalicji Obywatelskiej"

Expected comparison standard:
- This article should not be treated as a clean direct appointment article only.
- A useful extraction should recover the family-tie structure and the employment/role targets while
  retaining quoted/allegation context where possible.
- The spouse/partner mention should not be merged into Karol Wilczyński as the same person.
- Generic council-session conflict, culture-of-debate, and procedural dispute content should not
  produce unrelated appointment facts.

## Comparison Guidance

When comparing current output against this file:
- Treat WP salaries and Olsztyn utility-salary articles as relevant public-money oversight cases.
- Treat Demagog and RP as high-value positives where missing appointments, board memberships, party links, or acquaintance links indicate real extraction gaps.
- Treat the negative examples below as true negatives.
- A good next milestone is:
  - Demagog: recover several appointment / board facts
  - RP: recover at least the Hodura and Kuczmański appointment-and-acquaintance structure
  - Olsztyn salary article: recover at least person-role-organization-salary facts

## Negative Examples

### A. Olsztyn.com.pl: historia Placu Roosevelta

Source:
- https://www.olsztyn.com.pl/artykul,od-targu-konskiego-do-miejskiego-wezla-niezwykla-historia-placu-roosevelta-poczatkiem-wyjatkowej-serii,46601.html

Expectation:
- This is a **true negative**.
- It is a local-history article about Plac Roosevelta in Olsztyn, historical naming, urban space, and transport history.

Expected extraction outcome:
- Relevance should be `false`.
- No appointment, board, party-affiliation, remuneration, or related-person findings should be emitted.

### B. Demagog: W niedzielę wybory na Węgrzech. Uwaga na dezinformację

Source:
- https://demagog.org.pl/na-biezaco/w-niedziele-wybory-na-wegrzech-uwaga-na-dezinformacje/

Expectation:
- This is a **true negative**.
- It is an election/dezinformation alert about Hungary, Viktor Orbán, Fidesz, and TISZA.

Expected extraction outcome:
- Relevance should be `false`.
- No nepotism / public-company appointment findings should be emitted.

### C. WP: Giorgia Meloni krytykuje Trumpa. W tle komentarze o papieżu

Source:
- https://wiadomosci.wp.pl/giorgia-meloni-krytykuje-trumpa-w-tle-komentarze-o-papiezu-7274914684700960a

Expectation:
- This is a **true negative**.
- It is international political news about Giorgia Meloni, Donald Trump, and Pope Leo XIV.

Expected extraction outcome:
- Relevance should be `false`.
- No board, salary, public-company, or koryciarstwo-related findings should be emitted.

### D. Rzeczpospolita: status sędziego TK

Source:
- https://www.rp.pl/sady-i-trybunaly/art44134041-czy-status-sedziego-tk-moze-rozstrzygnac-sad-pracy-a-moze-cywilny-analiza

Expectation:
- This is a **true negative**.
- It is a legal analysis of the status of judges of the Constitutional Tribunal and possible court paths.

Expected extraction outcome:
- Relevance should be `false`.
- No company appointment, salary-in-public-company, board membership, or acquaintance-network findings should be emitted.

## 16. Onet: Żona posła PiS zrezygnowała z zasiadania w radach nadzorczych państwowych spółek

Source:
- https://wiadomosci.onet.pl/lublin/zona-posla-pis-zrezygnowala-z-zasiadania-w-radach-nadzorczych-panstwowych-spolek/hhpswdf

Expectation:
- This article is **strongly in scope**.
- It is about a dismissal/resignation of a politician's family member from state-owned company boards due to party resolutions against nepotism.

Expected core entities:
- Renata Stefaniuk
- Dariusz Stefaniuk
- Enea Połaniec
- Jelcz
- PiS / Prawo i Sprawiedliwość

Expected facts:
- Renata Stefaniuk -> `DISMISSAL` (or resignation) -> Enea Połaniec
- Renata Stefaniuk -> `DISMISSAL` (or resignation) -> Jelcz
- Renata Stefaniuk -> `PERSONAL_OR_POLITICAL_TIE` -> Dariusz Stefaniuk
  Expected relationship type: `wife / spouse`
- Dariusz Stefaniuk -> `PARTY_MEMBERSHIP` -> PiS

Important text cues:
- "Renata Stefaniuk nie zasiada już w radach nadzorczych"
- "Złożyła rezygnację"
- "Żona posła PiS"
- "Dariusz Stefaniuk"

Expected comparison standard:
- This should yield at least one or two board exit facts (dismissal/resignation), a kinship fact (wife/spouse), and a party affiliation.

## 17. Głos Wielkopolski: Nowy prezes WTC Poznań, spółki podległej MTP, wybrany bez konkursu

Source:
- https://gloswielkopolski.pl/nowy-prezes-wtc-poznan-spolki-podleglej-mtp-wybrany-bez-konkursu-ma-dyplom-collegium-humanum/ar/c1p2-27186205

Archived source:
- https://web.archive.org/web/20250120123235/https://gloswielkopolski.pl/nowy-prezes-wtc-poznan-spolki-podleglej-mtp-wybrany-bez-konkursu-ma-dyplom-collegium-humanum/ar/c1p2-27186205

Fetch note:
- use the archived source above as the canonical benchmark reference for this case
- the live page is currently paid-access / anti-bot protected in this repo environment

Expectation:
- This article is **strongly in scope**.
- It is a municipal / city-linked patronage article about the appointment of a new president of `WTC Poznań`, a company subordinate to `Międzynarodowe Targi Poznańskie`, without an open competition process.
- It is also a qualification-risk article because of the `Collegium Humanum` cue in the title.

Expected core entities:
- Jarosław Nowak
- WTC Poznań
- World Trade Center Poznań
- Międzynarodowe Targi Poznańskie
- MTP
- Jacek Jaśkowiak
- Platforma Obywatelska / PO
- Lena Bretes-Dorożała

Expected facts:
- Jarosław Nowak -> `APPOINTMENT` -> WTC Poznań
  Expected role: `prezes`
- Jarosław Nowak -> `HOLDS_POSITION_AT` -> WTC Poznań
  Expected role: `prezes`
- WTC Poznań should be recognized as a company subordinate to / controlled by `Międzynarodowe Targi Poznańskie`
- Jarosław Nowak -> `PARTY_MEMBERSHIP` -> Platforma Obywatelska
  or equivalent PO affiliation
- optional:
  - Lena Bretes-Dorożała -> `DISMISSAL` / `LEFT_POSITION` -> WTC Poznań
    the archived article states that she was unexpectedly removed in December 2024
  - a qualification-risk or red-flag signal tied to `Collegium Humanum`

Important text cues:
- "wybrany bez konkursu"
- "spółki podległej MTP"
- "nowy prezes WTC Poznań"
- "lider ... PO"
- "dyplom Collegium Humanum"
- "wśród członków jego partii"
- "osoby z dyplomami tej uczelni nie będą miały otwartej drogi do miejskich spółek"

Expected comparison standard:
- This should not degrade into generic city-politics output.
- At minimum, the pipeline should recover:
  - one appointment fact
  - one role fact
  - one PO affiliation
  - one company / parent-organization context linking WTC Poznań to MTP
- A useful future extension would be a qualification-risk or red-flag signal for `Collegium Humanum`, but that is not required for baseline extraction.

## 18. Do Rzeczy: PSL rozdał posady swoim w Agencji Mienia Wojskowego. Bez konkursów

Source:
- https://dorzeczy.pl/kraj/658447/bez-konkursow-desant-psl-na-agencje-mienia-wojskowego.html

Expectation:
- This article is **strongly in scope**.
- It is a state-institution patronage article about PSL-linked appointments into `Agencja Mienia Wojskowego` and its regional branches without open competition.
- It is a good benchmark for central-government / agency governance capture rather than only company-board extraction.

Expected core entities:
- Marcin Horyń
- Władysław Kosiniak-Kamysz
- Agencja Mienia Wojskowego
- AMW
- Fundacja Rozwoju
- Donald Tusk
- PSL / Polskie Stronnictwo Ludowe
- MON / Ministerstwo Obrony Narodowej

Expected facts:
- Marcin Horyń -> `APPOINTMENT` -> Agencja Mienia Wojskowego
  Expected role: `dyrektor`
- Marcin Horyń -> `PARTY_MEMBERSHIP` -> PSL
  or at minimum a strong political tie to Władysław Kosiniak-Kamysz
- Marcin Horyń -> `PERSONAL_OR_POLITICAL_TIE` -> Władysław Kosiniak-Kamysz
  Expected relationship type: trusted aide / cabinet chief / close political associate
- Donald Tusk -> appointment context for Marcin Horyń
  This may appear as an event participant or institutional appointing context rather than a stable relation
- Fundacja Rozwoju -> previous employment / role context for Marcin Horyń
- AMW regional director structure should be recognized as a broader patronage signal:
  - article says 8 of 10 regional directors are linked to PSL
  - even if the system cannot recover all names, it should detect the large-scale appointment pattern

Important text cues:
- "Bez konkursów"
- "powołuje go na stanowisko dyrektora Agencji Mienia Wojskowego"
- "jeden z zaufanych ludzi prezesa PSL"
- "szef gabinetu politycznego"
- "desant ludzi z PSL"
- "na 10 dyrektorów oddziałów regionalnych AMW, aż ośmiu jest związanych z ludowcami"

Expected comparison standard:
- This should yield at least:
  - one appointment fact for `Marcin Horyń`
  - one role fact for `dyrektor AMW`
  - one PSL affiliation or trusted-associate link
  - one clear public-institution target (`Agencja Mienia Wojskowego`)
- If the pipeline only extracts `PSL`, `Kosiniak-Kamysz`, and `AMW` as loose entities, it is underperforming.
