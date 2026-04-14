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
- No `APPOINTED_TO` or `MEMBER_OF_BOARD` finding is required here unless the article itself mentions company posts.
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
  Expected relations: `MEMBER_OF_BOARD`, likely also `APPOINTED_TO`
- Piotr Szymanek -> Energa
  Expected relation/event: management appointment, vice-president role
- Karol Bielski -> PKP Telkol
  Expected relation: `MEMBER_OF_BOARD`
- Leszek Świętowski -> Zakład Mechaniczny "Siarkopol"
  Expected relation: `MEMBER_OF_BOARD`
- Leszek Zawadzki -> Pomorska Agencja Rozwoju Regionalnego
  Expected relation: `MEMBER_OF_BOARD`
- Michał Olejniczak -> Narzędziownia-Mechanik
  Expected relation: `MEMBER_OF_BOARD`
- Marek Rutka -> Zarząd Morskiego Portu Gdynia
  Expected relation: `MEMBER_OF_BOARD`
- Bartłomiej Gębala -> Nowe Centrum Administracyjne
  Expected relation: `MEMBER_OF_BOARD`
- Andrzej Pilot -> JSW Logistics
  Expected relation: `MEMBER_OF_BOARD`
- Magdalena Roguska -> Polska Wytwórnia Papierów Wartościowych
  Expected relation/event: appointment to supervisory board
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

Expected relations and events:
- Jarosław Hodura -> Grupa Hoteli WAM
  Expected: `APPOINTED_TO` or equivalent employment/position relation
- Jarosław Hodura -> Bogdan Klich
  Expected: `RELATED_TO` with acquaintance / collaborator semantics
- Marcin Dulian -> Grupa Hoteli WAM
  Expected: management-board / president role
- Marcin Dulian -> Bogdan Klich
  Expected: `RELATED_TO` with friend / former bureau chief semantics
- Krzysztof Kuczmański -> Przedsiębiorstwo Usług Hotelarskich i Turystycznych
  Expected: `APPOINTED_TO`, management / president role
- Krzysztof Kuczmański -> Bogdan Klich
  Expected: `RELATED_TO` with acquaintance / campaign helper semantics
- Bogdan Klich -> Platforma Obywatelska
  Expected: `AFFILIATED_WITH_PARTY`

Important text cues:
- "dostał się bez konkursu"
- "od grudnia jest prezesem"
- "znajomy szefa MON"
- "były szef biura europoselskiego Klicha i jego wieloletni przyjaciel"

Expected comparison standard:
- This article should definitely yield non-empty relations.
- If the system fails to emit acquaintance links and appointment relations here, extraction coverage is still too weak.

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

Expected relations and events:
- Multiple `APPOINTED_TO` findings into `Totalizator Sportowy`
- Multiple `HOLDS_POSITION_AT` or equivalent management-role findings for regional director roles
- At least one `DISMISSED_FROM` or `dismissal` event for earlier management removals
- Multiple `AFFILIATED_WITH_PARTY` findings for PO, PSL, Lewica
- Multiple typed `RELATED_TO` findings for collaborator / parliamentary-office / political-network ties
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

Expected relations and events:
- Marek Rząsowski -> `APPOINTED_TO` -> AMW Rewita
- Marek Rząsowski -> `HOLDS_POSITION_AT` -> AMW Rewita
  Expected role: `wiceprezes`
- Marek Rząsowski -> `AFFILIATED_WITH_PARTY` -> Platforma Obywatelska
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

Expected relations and events:
- Stanisław Mazur -> `APPOINTED_TO` -> WFOŚiGW w Lublinie
  Expected role: `prezes`
- Andrzej Kloc -> `APPOINTED_TO` -> WFOŚiGW w Lublinie
  Expected role: `wiceprezes`
- Agnieszka Kruk -> `DISMISSED_FROM` -> WFOŚiGW w Lublinie
- Anna Pokwapisz -> `DISMISSED_FROM` -> WFOŚiGW w Lublinie
- Stanisław Mazur -> `AFFILIATED_WITH_PARTY` -> Lewica
- Andrzej Kloc -> `AFFILIATED_WITH_PARTY` -> PSL
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

Expected relations and events:
- Łukasz Bałajewicz -> `APPOINTED_TO` or `HOLDS_POSITION_AT` -> Krajowy Zasób Nieruchomości
  Expected role: `prezes`
- Łukasz Bałajewicz -> `AFFILIATED_WITH_PARTY` -> Polska 2050
- Rafał Komarewicz -> `RELATED_TO` -> Łukasz Bałajewicz
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
- A good first-pass result here is non-empty funding relations and public-institution links, not perfect full-network reconstruction.

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

Expected relations and events:
- Jarosław Słoma -> `APPOINTED_TO` or `HOLDS_POSITION_AT` -> Przedsiębiorstwo Wodociągów i Kanalizacji w Olsztynie
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
  - at least one typed `RELATED_TO` or conflict / patronage-network signal between local party actors and city authorities

Important text cues:
- "Kolesiostwo, rozdawanie posad, brak wizji działania"
- "prezydentem miasta"
- "PO tworzy tam koalicję z lokalnym Forum Samorządowym"
- "lokalnych partyjnych baronów"
- "nagrody dla prezydentów i członków jego ekipy"

Expected comparison standard:
- This is not a board-appointment article, but it is still a valid `koryciarstwo` benchmark.
- A reasonable first-pass result is non-empty relevance plus people / party / municipal-power-network extraction, even if there is no clean `APPOINTED_TO` event.

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

Expected relations and events:
- at least one `MEMBER_OF_BOARD` or `APPOINTED_TO` fact into the supervisory board of NFOŚiGW
- at least one `AFFILIATED_WITH_PARTY` fact for Polska 2050
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

Expected relations and events:
- Jolanta Sobczyk -> `APPOINTED_TO` -> Natura Tour
  Expected role: `prezes`
- multiple `MEMBER_OF_BOARD` / board facts for people tied to PSL in Natura Tour
- multiple `AFFILIATED_WITH_PARTY` facts for PSL
- at least one typed `RELATED_TO` fact such as acquaintance / sibling / family-political tie when explicitly stated

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

Expected relations and events:
- Katarzyna Zapał -> `DISMISSED_FROM` or equivalent exit fact -> Zarząd Budynków Komunalnych
- Marcin Paradyż -> succession / `APPOINTED_TO` or role-change fact -> Zarząd Budynków Komunalnych
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

Expected relations and events:
- A. Góralczyk -> `APPOINTED_TO` -> Stadnina Koni Iwno
  Expected role: `prezes zarządu`
- Przemysław Pacia -> `DISMISSED_FROM` or equivalent exit event -> Stadnina Koni Iwno
- A. Góralczyk -> `AFFILIATED_WITH_PARTY` -> PSL
- KOWR should be recognized as the controlling public institution supervising the stadnina

Important text cues:
- "działaczka Polskiego Stronnictwa Ludowego"
- "awansowała na stanowisko prezesa zarządu"
- "spółki Skarbu Państwa"
- "odwołano poprzedniego prezesa"
- "KOWR sprawuje nadzór właścicielski nad stadniną"

Expected comparison standard:
- This article should yield one appointment, one dismissal/change fact, one party tie, and one state-ownership signal.

## Comparison Guidance

When comparing current output against this file:
- Treat WP salaries and Olsztyn utility-salary articles as relevant public-money oversight cases.
- Treat Demagog and RP as high-value positives where missing appointments, board memberships, party links, or acquaintance links indicate real extraction gaps.
- Treat the negative examples below as true negatives.
- A good next milestone is:
  - Demagog: recover several appointment / board relations
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
