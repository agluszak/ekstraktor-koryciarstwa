# Pipeline Comparison Report: V1 vs V2

## Article: Czy wójt ukrywa nepotyzm?
**Filename:** `ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`

**Relevance:**
- V1: `False`
- V2: `True`

### V1 Facts Table
| Kind | Subject | Object | Role / Value | Evidence Excerpt |
|---|---|---|---|---|
| PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny | Sosna | cousin | kuzyn wójta Sosny |
| APPOINTMENT | Dobosz | Gminy Poczesna |  | Jak się okazuje, nowy pracownik jest blisko spokrewniony z wójtem Arturem Sosną, |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | Pomoc Administracyjnej | Na początku lipca, w samorządzie zatrudniono Rafała Dobosza na stanowisko pomocy |
| APPOINTMENT | Dobosz | Gminy Poczesna |  | Z relacji osób zatrudnionych w urzędzie wynika, że Dobosz szybko zaczął odgrywać |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna |  | Na pytania o zakres obowiązków i kryteria zatrudnienia Rafała Dobosza odpowiedzi |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna |  | „informacje dotyczące pana Rafała Dobosza nie podlegają upublicznieniu, gdyż na  |
| POLITICAL_OFFICE | Artur Sosna | Wójt | Wójt | Jak się okazuje, nowy pracownik jest blisko spokrewniony z wójtem Arturem Sosną, |
| POLITICAL_OFFICE | Sosna | Wójt | Wójt | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emo |
| POLITICAL_OFFICE | Sosna | Wójt | Wójt | Mimo rosnącej liczby pytań i wątpliwości, wójt Sosna unika udzielania wyczerpują |
| POLITICAL_OFFICE | Sosna | Wójt | Wójt | Czy wójt Sosna rzeczywiście ukrywa nepotyzm, zatrudniając swojego kuzyna na stan |
| PERSONAL_OR_POLITICAL_TIE | Rafał Dobosz | Sosna | cousin | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emo |
| PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny | Sosna | cousin | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emo |

### V2 Facts Table (score >= 0.5)
| Kind | Score | Arguments | Evidence Excerpt |
|---|---|---|---|
| (none) | - | - | - |

### Gap Analysis & False Positive Flags
- **What V1 has that V2 misses**: V1 extracts the appointment of Rafał Dobosz (Pomoc Administracyjna) and his kinship tie to Wójt Artur Sosna. V2 missed these entirely (no facts scored >= 0.5).
- **What V2 has that V1 misses**: None. V2 correctly identified relevance but produced no high-scoring facts.

---

## Article: Kontrowersje wokół wójta Charsznicy
**Filename:** `dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715`

**Relevance:**
- V1: `False`
- V2: `True`

### V1 Facts Table
| Kind | Subject | Object | Role / Value | Evidence Excerpt |
|---|---|---|---|---|
| PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę | Tomasz Kościelniak | partner | swoją „dziewczynę |
| PERSONAL_OR_POLITICAL_TIE | Partnerka Wójta | Tomasz Kościelniak | partner | partnerka wójta |
| PERSONAL_OR_POLITICAL_TIE | Swojego Przyszłego Teścia | Tomasz Kościelniak | father_in_law | swojego przyszłego teścia |
| APPOINTMENT | Swoją „dziewczynę | Urzędu Gminy | Ekodoradcy | Osoba, podpisana jako Jan Kowalski, zwróciła uwagę, że sprawujący funkcję wójta  |
| APPOINTMENT | Swojego Przyszłego Teścia | Urzędzie Stanu Cywilnego | Pracownika Gospodarczego | To jednak jeszcze nie wszystko, gdyż z nadesłanej informacji wynika, że wójt zat |
| POLITICAL_OFFICE | Kościelniak | Wójt | Wójt | Ostatnim z przedstawionych zarzutów wobec wójta Kościelniaka jest to, że pod jeg |
| PARTY_MEMBERSHIP | Szymon Kubit | Prawo i Sprawiedliwość | Prawo i Sprawiedliwość | Byli wśród nich m. in. dyrektor Gminnego Ośrodka Kultury Szymon Kubit oraz start |
| ELECTION_CANDIDACY | Szymon Kubit | None |  | Byli wśród nich m. in. dyrektor Gminnego Ośrodka Kultury Szymon Kubit oraz start |
| ELECTION_CANDIDACY | Tomasz Kościelniak | None |  | Zwycięzcą I tury głosowania został ten ostatni, ale na drugim miejscu znalazł si |
| PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę | Tomasz Kościelniak | partner | Osoba, podpisana jako Jan Kowalski, zwróciła uwagę, że sprawujący funkcję wójta  |

### V2 Facts Table (score >= 0.5)
| Kind | Score | Arguments | Evidence Excerpt |
|---|---|---|---|
| governance_appointment | 0.87 | **person**: Tomasz Kościelniak, **organization**: Gminnego Ośrodka Kultury, **role**: dyrektor | ['evidence-38'] |
| governance_appointment | 0.87 | **person**: Tomasz Kościelniak, **organization**: Gminnego Ośrodka Kultury, **role**: członek zarządu | ['evidence-38'] |
| governance_appointment | 0.87 | **person**: Tomasz Kościelniak, **organization**: Gminnego Ośrodka Kultury, **role**: dyrektor | ['evidence-39'] |
| governance_appointment | 0.87 | **person**: Tomasz Kościelniak, **organization**: Gminnego Ośrodka Kultury, **role**: członek zarządu | ['evidence-39'] |

### Gap Analysis & False Positive Flags
- **What V1 has that V2 misses**: V1 extracts the kinship ties ('partnerka wójta', 'przyszły teść') and their appointments to Urząd Gminy and USC. V2 missed these ties.
- **What V2 has that V1 misses**: V2 extracts appointments to Gminny Ośrodek Kultury.
- **False Positives**: V2 incorrectly resolved the appointee to 'Tomasz Kościelniak' (the Wójt) instead of the actual director (likely Szymon Kubit, who V1 identified as party member/election candidate).

---

## Article: Nepotyzm w Bytomiu - radni PiS
**Filename:** `dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383`

**Relevance:**
- V1: `False`
- V2: `True`

### V1 Facts Table
| Kind | Subject | Object | Role / Value | Evidence Excerpt |
|---|---|---|---|---|
| DISMISSAL | Waldemar Gawron | Wnuk Consulting |  | Przypomnijmy, że w bytomskiej Radzie Miasta jeszcze do niedawna funkcjonowała ni |
| PUBLIC_CONTRACT | Urzędzie Miejskim w Bytomiu | Gminę Bytom |  | - Informacja dotycząca umów zawieranych przez gminę Bytom, miejskie jednostki or |
| PUBLIC_CONTRACT | Wnuk Consulting | PEC | 397 496,95 zł | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC  |
| PUBLIC_CONTRACT | Wnuk Consulting | BPK | 397 496,95 zł | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC  |
| ANTI_CORRUPTION_REFERRAL | Prawo i Sprawiedliwość | Centralne Biuro Antykorupcyjne | Centralne Biuro Antykorupcyjne | Konferencja bytomskich radnych reprezentujących Prawo i Sprawiedliwość w sprawie |
| ANTI_CORRUPTION_REFERRAL | Maciej Bartków | Centralne Biuro Antykorupcyjne | Centralne Biuro Antykorupcyjne | Jak podkreśla radny Maciej Bartków, zdecydował się on złożyć zawiadomienie do CB |
| POLITICAL_OFFICE | Maciej Bartków | Radny | Radny | Prowadzić konta w mediach społecznościowych mogą osoby, które pracują np. w dzia |
| POLITICAL_OFFICE | Maciej Bartków | Radny | Radny | Jak podkreśla radny Maciej Bartków, zdecydował się on złożyć zawiadomienie do CB |
| POLITICAL_OFFICE | Bartkowa | Radny | Radny | – W naszym przekonaniu doszło do ewidentnego konfliktu interesów i swoistej form |
| POLITICAL_OFFICE | Bartkowa | Radny | Radny | – Naszym zdaniem, zadania, które były zlecane na zewnątrz, jak zakładanie i obsł |
| POLITICAL_OFFICE | Mariusz Janas | Radny | Radny | To pieniądze wyrzucone w błoto - dodał Mariusz Janas, radny, a do niedawna przew |
| POLITICAL_OFFICE | Rabus | Radny | Radny | Pan prezydent Wołosz wielokrotnie mówił o transparentności, ale jej nie ma – wsk |
| POLITICAL_OFFICE | Maciej Bartków | Radny | Radny | – To cyniczna gra polityczna radnego Macieja Bartkowa i jego stronników – staryc |
| POLITICAL_OFFICE | Bartkowa | Radny | Radny | Biorąc pod uwagę to, jak często i jak źle radny Bartków mówił o tym środowisku,  |
| POLITICAL_OFFICE | Bartkowa | Radny | Radny | Znam nie tylko prezydenta, ale i radnego Bartkowa. |
| POLITICAL_OFFICE | Bartkowa | Radny | Radny | Radny Bartków zapowiedział, że do Państwowej Komisji Wyborczej zostaną zgłoszone |
| PERSONAL_OR_POLITICAL_TIE | Mariusz Wołosze | Bartkowa | spouse | – W naszym przekonaniu doszło do ewidentnego konfliktu interesów i swoistej form |

### V2 Facts Table (score >= 0.5)
| Kind | Score | Arguments | Evidence Excerpt |
|---|---|---|---|
| governance_appointment | 0.90 | **person**: Mirosław Luks, **organization**: Urzędu Miejskiego w Bytomiu, **role**: sekretarz | ['evidence-103'] |
| governance_appointment | 0.85 | **person**: Bartków, **organization**: Facebook | ['evidence-104'] |
| governance_appointment | 0.85 | **person**: Bartków, **organization**: Państwowej Komisji Wyborczej | ['evidence-106'] |
| governance_appointment | 0.85 | **person**: Bartków, **organization**: Super | ['evidence-106'] |
| governance_appointment | 0.85 | **person**: Wołosza, **organization**: Państwowej Komisji Wyborczej | ['evidence-106'] |
| governance_appointment | 0.85 | **person**: Wołosza, **organization**: Super | ['evidence-106'] |
| public_contract | 0.85 | **counterparty**: Wnuk Consulting, **contractor**: PEC, **amount**: 397 496,95 zł | ['evidence-109'] |
| anti_corruption_referral | 0.90 | **complainant**: Prawo i Sprawiedliwość, **institution**: CBA, **context**: w sprawie złożenia zawiadomienia do CBA, choć z pewnymi perturbacjami, finalnie doszła do skutku | ['evidence-110'] |
| anti_corruption_referral | 1.00 | **complainant**: Maciej Bartków, **target**: Przedsiębiorstwie Energetyki Cieplnej Sp., **institution**: CBA | ['evidence-111'] |
| anti_corruption_referral | 0.80 | **institution**: CBA | ['evidence-112'] |
| personal_or_political_tie | 0.80 | **subject**: Mariusza Wołosza, **object**: Bartków, **context**: spouse | ['evidence-44'] |
| personal_or_political_tie | 0.75 | **subject**: Bartków, **object**: Wołosza, **context**: związany | ['evidence-82'] |

### Gap Analysis & False Positive Flags
- **What V1 has that V2 misses**: V1 captures multiple political office roles (Radny).
- **What V2 has that V1 misses**: V2 successfully extracts the exact contract amount (397 496,95 zł) for Wnuk Consulting & PEC. V2 also captures the CBA referral with high precision.
- **False Positives**: V2 extracted absurd governance appointments: Maciej Bartków to 'Facebook' and 'Państwowej Komisji Wyborczej' and 'Super'. This is because it misinterpreted actions like posting on Facebook or reporting to PKW as taking governance roles.

---

## Article: Nowy zaciąg tłustych
**Filename:** `radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470`

**Relevance:**
- V1: `False`
- V2: `True`

### V1 Facts Table
| Kind | Subject | Object | Role / Value | Evidence Excerpt |
|---|---|---|---|---|
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj | spouse | żona Radka Zugaja |
| APPOINTMENT | Rząsowski | AMW Rewita | Rada Nadzorcza | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar |
| COMPENSATION | Rząsowski | AMW Rewita | Rada Nadzorcza | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| APPOINTMENT | Rząsowski | Ministerstwu Obrony Narodowej |  | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| FORMER_PARTY_MEMBERSHIP | Marek Rząsowski | Platforma Obywatelska | Platforma Obywatelska | Marek Rząsowski, radny powiatowy PO, został wiceprezesem spółki AMW Rewita zarzą |
| POLITICAL_OFFICE | Marek Rząsowski | Radny | Radny | Marek Rząsowski, radny powiatowy PO, został wiceprezesem spółki AMW Rewita zarzą |
| POLITICAL_OFFICE | Cezary Tomczyk | Wiek / Zastępca Minister | Wiek / Zastępca Minister | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar |
| POLITICAL_OFFICE | Cezary Tomczyk | Wiek / Zastępca Minister | wice/zastępca Minister | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar |
| ELECTION_CANDIDACY | Jacek Łęski | None |  | Zaczynał w kampanii wyborczej Jacka Łęskiego, który startował na prezydenta Rado |
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj | spouse | Ciekawe kto jeszcze okaże się super fachowcem w spółkach Skarbu Państwa, SŁABO T |

### V2 Facts Table (score >= 0.5)
| Kind | Score | Arguments | Evidence Excerpt |
|---|---|---|---|
| party_affiliation | 0.80 | **subject**: Marek Rząsowski, **object**: Platforma Obywatelska | ['evidence-56'] |
| governance_appointment | 0.85 | **person**: Marek Rząsowski, **organization**: AMW Rewita | ['evidence-65'] |
| governance_appointment | 0.90 | **person**: Rząsowski, **organization**: AMW Rewita, **role**: radę nadzorczą | ['evidence-66'] |
| governance_appointment | 0.82 | **person**: Rząsowski, **organization**: AMW Rewita, **role**: radę nadzorczą | ['evidence-67'] |
| compensation | 0.93 | **funder**: PO, **recipient**: Rząsowskiego, **amount**: 24 tys. zł | ['evidence-70'] |
| personal_or_political_tie | 0.80 | **subject**: Mirella Zugaj, **object**: Radka Zugaja, **context**: spouse | ['evidence-19'] |

### Gap Analysis & False Positive Flags
- **What V1 has that V2 misses**: V1 identifies the compensation as coming from AMW Rewita.
- **What V2 has that V1 misses**: V2 correctly maps the kinship tie between exactly resolved names: 'Mirella Zugaj' and 'Radka Zugaja' (spouse), whereas V1 had noisy nominals like 'Żona Radka Zugaja'. V2 also correctly extracts the party affiliation and governance appointment (Rada Nadzorcza).
- **False Positives**: V2 attributes the funder of the compensation to 'PO' (Platforma Obywatelska) instead of the company AMW Rewita.
- **Notable Improvements**: V2 successfully linked the nominal kinship ('żona') to the resolved entity 'Mirella Zugaj', proving the reference resolution stages work well here.

---

## Summary of Key Findings

### What improved in V2 vs V1:
1. **Reference Resolution for Kinship**: V2 is capable of taking a nominal description (like "żona Radka Zugaja") and correctly resolving and linking it to the named entity "Mirella Zugaj" (seen in `radomszczanska.pl`).
2. **Amounts in Contracts/Compensation**: V2 correctly parses precise financial figures and ties them to public contract facts (e.g. 397 496,95 zł for Wnuk Consulting).
3. **Relevance Filtering**: V2 correctly flags all 4 articles as relevant, whereas V1 incorrectly flagged some as `False`.

### Major Gaps Remaining:
1. **Missed Substantive Ties**: In the `ai42.pl` and `dziennikpolski24.pl` articles, V2 completely misses the main appointments and personal ties (cousins, partners, fathers-in-law) that form the core nepotism event.
2. **Role Misattributions**: V2 sometimes confuses who appointed whom (e.g., claiming the Wójt Tomasz Kościelniak was appointed as director of GOK, rather than him being the context/appointer).

### False Positives V2 Produces:
1. **Absurd Organizations as Governance Destinations**: In `dziennikzachodni.pl`, V2 extracts appointments to "Facebook", "Super", and "Państwowej Komisji Wyborczej" because it interprets verbs of communication or reporting as governance events.
2. **Funder Misattribution**: V2 attributed compensation funding to a political party ("PO") rather than the employing organization ("AMW Rewita").
