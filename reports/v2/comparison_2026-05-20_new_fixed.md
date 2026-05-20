# Extraction Pipeline Comparison Report: V1 vs. V2 (New Articles Run)

**Date**: May 20, 2026  
**Run Label**: `new_fixed`  
**Configuration**: V2 Coreference Resolution skipped (disabled by config)

---

## Article 1: Czy wójt ukrywa nepotyzm? (`ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm`)

* **V1 Title**: Czy wójt ukrywa nepotyzm?
* **V2 Title**: Czy wójt ukrywa nepotyzm?
* **V2 Output File**: `document-2361b44b3ad767f1.json`

### Relevance
* **V1**: `True` (Score: 0.65)
* **V2**: `True` (Score: 0.95)

### V1 Facts Table
| kind | subject | object | role | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny | Sosna | None / cousin | kuzyn wójta Sosny |
| APPOINTMENT | Dobosz | Gminy Poczesna | None / None | Jak się okazuje, nowy pracownik jest blisko spokrewniony z wójtem Arturem Sosną... |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | Pomoc Administracyjnej / Pomoc Administracyjnej | Na początku lipca, w samorządzie zatrudniono Rafała Dobosza na stanowisko pomocy... |
| APPOINTMENT | Dobosz | Gminy Poczesna | None / None | Z relacji osób zatrudnionych w urzędzie wynika, że Dobosz szybko zaczął odgrywać... |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | None / None | Na pytania o zakres obowiązków i kryteria zatrudnienia Rafała Dobosza... |
| APPOINTMENT | Rafał Dobosz | Gminy Poczesna | None / None | „informacje dotyczące pana Rafała Dobosza nie podlegają upublicznieniu, gdyż na... |
| PERSONAL_OR_POLITICAL_TIE | Rafał Dobosz | Sosna | None / cousin | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emo... |
| PERSONAL_OR_POLITICAL_TIE | Kuzyn Wójta Sosny | Sosna | None / cousin | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emo... |

### V2 Facts Table (Score >= 0.5)
| kind | score | person | org | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| personal_or_political_tie | 0.80 | subject: Rafał Dobosz; object: Sosny | N/A | Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emocje wśród pracownikó... |

### Gap Analysis
* **What V1 has that V2 misses**: V1 successfully extracted multiple `APPOINTMENT` facts connecting Rafał Dobosz to `Gmina Poczesna` (with the role `pomoc administracyjna` / administrative assistant). V2 completely missed the public employment fact.
* **What V2 has that V1 misses**: V2 correctly grouped the different mentions and produced a single clean, high-confidence kinship tie (Score: 0.80) directly resolved to `Rafał Dobosz` and `Sosna` (wójt).
* **Root Cause for V2 Miss**: 
  In the V2 NER parsing (`spacy_label_to_ner_label`), the Polish spaCy model tags `"gminy Poczesna"` as `placeName`. V2's exact match list check `normalized in {"loc", "gpe", "location", "place"}` fails to match `"placename"`. Since location tagging is discarded, no organization or location entity candidate is created for Poczesna. Without an employing organization entity, the `PublicEmploymentCandidateStage` fails to pair the person with an employer, discarding the candidate.

### False Positive Flags
* **V2 False Positives**: None.

---

## Article 2: Kontrowersje wokół wójta Charsznicy (`dziennikpolski24.pl__kontrowersje-wokol-wojta...`)

* **V1 Title**: Kontrowersje wokół wójta Charsznicy. Tak pracę dostała jego partnerka. Tomasz Kościelniak zaprzecza zarzutom
* **V2 Title**: Kontrowersje wokół wójta Charsznicy. Tak pracę dostała jego partnerka. Tomasz Kościelniak zaprzecza zarzutom
* **V2 Output File**: `document-eff4bd00b459a340.json`

### Relevance
* **V1**: `True` (Score: 1.0)
* **V2**: `True` (Score: 1.0)

### V1 Facts Table
| kind | subject | object | role | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę | Tomasz Kościelniak | None / partner | swoją „dziewczynę |
| PERSONAL_OR_POLITICAL_TIE | Partnerka Wójta | Tomasz Kościelniak | None / partner | partnerka wójta |
| PERSONAL_OR_POLITICAL_TIE | Swojego Przyszłego Teścia | Tomasz Kościelniak | None / father_in_law | swojego przyszłego teścia |
| APPOINTMENT | Swoją „dziewczynę | Urzędu Gminy | Ekodoradcy / Ekodoradcy | Osoba, podpisana jako Jan Kowalski, zwróciła uwagę, że sprawujący funkcję wójta... |
| APPOINTMENT | Swojego Przyszłego Teścia | Urzędzie Stanu Cywilnego | Pracownika Gospodarczego / Pracownika Gospodarczego | To jednak jeszcze nie wszystko, gdyż z nadesłanej informacji wynika, że wójt zat... |
| PERSONAL_OR_POLITICAL_TIE | Swoją „dziewczynę | Tomasz Kościelniak | None / partner | Osoba, podpisana jako Jan Kowalski, zwróciła uwagę, że sprawujący funkcję wójta... |

### V2 Facts Table (Score >= 0.5)
| kind | score | person | org | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| governance_appointment | 0.87 | person: Tomasz Kościelniak | organization: Gminnego Ośrodka Kultury | role: dyrektor (Fact fact-0, Fact fact-4) / członek zarządu (Fact fact-1, Fact fact-5) | Zwycięzcą I tury głosowania został ten ostatni, ale na drugim miejscu znalazł się właśnie Tomasz Koś... / Tymczasem stało się inaczej: Tomasz Kościelniak „odrobił straty” z nawiązką i to on został wójtem. |
| public_employment | 0.78 | person: Tomasz Kościelniak | organization: Urzędzie Stanu Cywilnego | To jednak jeszcze nie wszystko, gdyż z nadesłanej informacji wynika, że wójt zatrudnił swojego przys... |

### Gap Analysis
* **What V1 has that V2 misses**: V1 successfully extracted multiple kinship ties (partner, future father-in-law) and their respective employment locations (hired as Ekodoradca in Gmina, hired as custodian/gospodarczy in USC) via its NP-based proxy entity matching.
* **What V2 has that V1 misses**: V2 did not extract any valid kinship ties or correct employment facts.
* **Root Cause for V2 Miss**: 
  V2 ran with coreference resolution disabled (`coreference_stage_v2: skipped`). Because the partner (`"dziewczyna"`, `"partnerka"`) and father-in-law (`"teść"`) are unnamed in the text, V2 did not generate entity candidates for them. Consequently, they could not be mapped to any kinship or employment relations.

### False Positive Flags
* **V2 False Positives**:
  * `public_employment` (Score: 0.78) claiming wójt **Tomasz Kościelniak** was hired in `Urzędzie Stanu Cywilnego`. In reality, the text says the wójt hired *his father-in-law* there. Due to the lack of coreference, V2 fell back to the nearest named person entity in the sentence (Kościelniak).
  * `governance_appointment` (Score: 0.87) claiming **Tomasz Kościelniak** was appointed as GOK director. In reality, the text refers to `Szymon Kubit` being the director.

---

## Article 3: Nepotyzm w Bytomiu? (`dziennikzachodni.pl__nepotyzm-w-bytomiu...`)

* **V1 Title**: Nepotyzm w Bytomiu? Radni reprezentujący PIS zapowiedzieli, że złożą zawiadomienie do CBA o możliwości popełnienia przestępstwa
* **V2 Title**: Nepotyzm w Bytomiu? Radni reprezentujący PIS zapowiedzieli, że złożą zawiadomienie do CBA o możliwości popełnienia przestępstwa
* **V2 Output File**: `document-d669ea67fa3f4baa.json`

### Relevance
* **V1**: `True` (Score: 1.0)
* **V2**: `True` (Score: 1.0)

### V1 Facts Table
| kind | subject | object | role | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| DISMISSAL | Waldemar Gawron | Wnuk Consulting | None / None | Przypomnijmy, że w bytomskiej Radzie Miasta jeszcze do niedawna funkcjonowała ni... |
| PUBLIC_CONTRACT | Urzędzie Miejskim w Bytomiu | Gminę Bytom | None / None | - Informacja dotycząca umów zawieranych przez gminę Bytom, miejskie jednostki or... |
| PUBLIC_CONTRACT | Wnuk Consulting | PEC | None / 397 496,95 zł | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC... |
| PUBLIC_CONTRACT | Wnuk Consulting | BPK | None / 397 496,95 zł | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC... |
| ANTI_CORRUPTION_REFERRAL | Prawo i Sprawiedliwość | Centralne Biuro Antykorupcyjne | None / Centralne Biuro Antykorupcyjne | Konferencja bytomskich radnych reprezentujących Prawo i Sprawiedliwość w sprawie... |
| ANTI_CORRUPTION_REFERRAL | Maciej Bartków | Centralne Biuro Antykorupcyjne | None / Centralne Biuro Antykorupcyjne | Jak podkreśla radny Maciej Bartków, zdecydował się on złożyć zawiadomienie do CB... |
| PERSONAL_OR_POLITICAL_TIE | Mariusz Wołosze | Bartkowa | None / spouse | – W naszym przekonaniu doszło do ewidentnego konfliktu interesów i swoistej form... |

### V2 Facts Table (Score >= 0.5)
| kind | score | person | org | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| public_contract | 0.85 | N/A | counterparty: Wnuk Consulting; contractor: PEC | – Łącznie firma Wnuk Consulting podpisała umowy z miastem Bytom oraz spółką PEC na kwotę 397 496,95 ... |
| anti_corruption_referral | 0.90 | N/A | complainant: Prawo i Sprawiedliwość; institution: CBA | Konferencja bytomskich radnych reprezentujących Prawo i Sprawiedliwość w sprawie złożenia zawiadomie... |
| anti_corruption_referral | 1.00 | complainant: Maciej Bartków | target: Przedsiębiorstwie Energetyki Cieplnej Sp.; institution: CBA | Jak podkreśla radny Maciej Bartków, zdecydował się on złożyć zawiadomienie do CBA, ponieważ uważa, ż... |
| anti_corruption_referral | 0.80 | N/A | institution: CBA | Zawiadomienie do CBA to nie wszystko. |
| personal_or_political_tie | 0.80 | subject: Mariusza Wołosza; object: Bartków | N/A | – W naszym przekonaniu doszło do ewidentnego konfliktu interesów i swoistej formy nepotyzmu, polegaj... |
| personal_or_political_tie | 0.75 | subject: Bartków; object: Wołosza | N/A | Radny Bartków zapowiedział, że do Państwowej Komisji Wyborczej zostaną zgłoszone problemy związane z... |
| public_employment | 0.78 | person: Bartków | organization: Facebook | Dlaczego promowaniem działalności spółek miejskich nie zajmowali się zatrudnieni w nich pracownicy? |

### Gap Analysis
* **What V1 has that V2 misses**: V1 extracted the second public contract with `BPK` (Bytomskie Przedsiębiorstwo Komunalne) in the same sentence as PEC. V2 missed the BPK contract, extracting only PEC.
* **What V2 has that V1 misses**: V2 correctly avoided V1's false positive `DISMISSAL` of Waldemar Gawron from Wnuk Consulting.
* **PKW Governance Check**: V2 successfully avoided any false positive governance facts for the phrase `"zostać zgłoszone do PKW"`. The governance candidate scorer scored these at 0.23 (well below the 0.5 threshold).

### False Positive Flags
* **V2 False Positives**:
  * `public_employment` (Score: 0.78) for **radny Bartków** at `Facebook`. This was triggered because the sentence mentions Bartków commenting on social media management ("Prowadzić konta...").
  * `personal_or_political_tie` (Score: 0.80) claiming **Mariusz Wołosz** (mayor) and **Bartków** (councillor) are **spouses**. This is a shared failure mode with V1: the genitive Polish case of the councillor's name (`"radnego Bartkowa"`) was misparsed as a female surname form, leading the pipeline to infer a spouse connection.

---

## Article 4: Hotelarz Rząsowski (`radomszczanska.pl__artykul__nowy-zaciag-tlustych...`)

* **V1 Title**: Hotelarz Rząsowski: Robota w spółce podległej MON dla radnego powiatowego. Nowy zaciąg tłustych kotów?
* **V2 Title**: Hotelarz Rząsowski: Robota w spółce podległej MON dla radnego powiatowego. Nowy zaciąg tłustych kotów?
* **V2 Output File**: `document-30799fdd9b13e275.json`

### Relevance
* **V1**: `True` (Score: 1.0)
* **V2**: `True` (Score: 1.0)

### V1 Facts Table
| kind | subject | object | role | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj | None / spouse | żona Radka Zugaja |
| APPOINTMENT | Rząsowski | AMW Rewita | Rada Nadzorcza / Rada Nadzorcza | Ta spółka podległa Ministerstwu Obrony Narodowej, gdzie wiceministrem jest Cezar... |
| COMPENSATION | Rząsowski | AMW Rewita | Rada Nadzorcza / 24 tys. zł brutto | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| APPOINTMENT | Rząsowski | Ministerstwu Obrony Narodowej | None / None | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| FORMER_PARTY_MEMBERSHIP | Marek Rząsowski | Platforma Obywatelska | None / Platforma Obywatelska | Marek Rząsowski, radny powiatowy PO, został wiceprezesem spółki AMW Rewita zarzą... |
| PERSONAL_OR_POLITICAL_TIE | Żona Radka Zugaja | Mirella Zugaj | None / spouse | Ciekawe kto jeszcze okaże się super fachowcem w spółkach Skarbu Państwa, SŁABO T... |

### V2 Facts Table (Score >= 0.5)
| kind | score | person | org | evidence excerpt |
| :--- | :--- | :--- | :--- | :--- |
| party_affiliation | 0.80 | subject: Marek Rząsowski | object: Platforma Obywatelska | Marek Rząsowski, radny powiatowy PO, został wiceprezesem spółki AMW Rewita zarządzającej byłymi wojs... |
| governance_appointment | 0.90 | person: Rząsowski | organization: AMW Rewita | role: radę nadzorczą | Rząsowski został nominowany przez radę nadzorczą na wiceprezesa AMW Rewita 28 czerwca. |
| governance_appointment | 0.82 | person: Rząsowski | organization: AMW Rewita | role: radę nadzorczą | Nie objął jeszcze stanowiska, poprosił o przesunięcie terminu rozpoczęcia pracy o miesiąc ze względu... |
| compensation | 0.93 | recipient: Rząsowskiego | funder: AMW Rewita | 24 tys. zł | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| compensation | 0.93 | recipient: Rząsowskiego | funder: Ministerstwu Obrony Narodowej | 24 tys. zł | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| compensation | 0.93 | recipient: Rząsowskiego | funder: Platformy | 24 tys. zł | Poprzednik Rząsowskiego na tym stanowisku zarabiał 24 tys. zł brutto |
| personal_or_political_tie | 0.80 | subject: Mirella Zugaj; object: Radka Zugaja | N/A | Mirella Zugaj, żona Radka Zugaja, osobistego ochroniarza Joachima Brudzińskiego...dziewucha prosta i... |

### Gap Analysis
* **What V1 has that V2 misses**: None of the major entities or ties were completely missed. V2 successfully extracted the party affiliation and governance appointments. Both V1 and V2 missed the active appointment fact for Mirella Zugaj to Rewita because her role is described nominally (`"pani wiceprezes teraz w Rewicie"`) without active appointment/employment verbs.
* **What V2 has that V1 misses**: V2 correctly extracted the actual compensation recipient and connected them to both the company (`AMW Rewita`) and the ministry (`Ministerstwu Obrony Narodowej`).
* **Funder Identification Check**: V2 successfully identified the correct public funders (`AMW Rewita` and `Ministerstwu Obrony Narodowej`). However, it also extracted `Platformy` (the political party) as a funder with a high score (`0.93`). 
* **Root Cause for Party Funder FP**:
  In `public_money.py`, the `_is_party_like_organization` check only performs a casefolded exact match check against a hardcoded list of political party names. While `"platformy obywatelskiej"` is in the list, the single word `"platformy"` is not. Unlike `governance.py`, `public_money.py` does not check for overlaps with other `POLITICAL_PARTY` entities in the extraction store. Consequently, `Platformy` escaped the party organization penalty (which successfully lowered `PO` and `PiS` scores to 0.33) and was scored at 0.93.

### False Positive Flags
* **V2 False Positives**:
  * `compensation` (Score: 0.93) claiming **Platformy** (Platforma Obywatelska) was the funder of the 24k PLN compensation.
  * `governance_appointment` role argument was resolved as `"radę nadzorczą"` (nominating body) instead of `"wiceprezes"` (the actual role).
