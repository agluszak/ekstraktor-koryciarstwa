import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest import Subtests


@pytest.fixture(scope="session")
def benchmark_results(
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
) -> dict[str, Any]:
    """
    Runs the pipeline in batch mode over all inputs and returns the parsed JSON results.
    """
    output_dir = tmp_path_factory.mktemp("benchmark_output")
    inputs_dir = Path("inputs")

    if not inputs_dir.exists():
        pytest.skip("No inputs directory found")

    # Run the batch pipeline
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "main.py",
            "--input-dir",
            str(inputs_dir),
            "--glob",
            "*.html",
            "--output-dir",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
    )

    results: dict[str, Any] = {}
    for json_file in output_dir.glob("*.json"):
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
            results[json_file.stem] = data

    # Store results in config for the terminal summary hook
    setattr(request.config, "_benchmark_results", results)

    return results


def get_entity_name(doc: dict[str, Any], entity_id: str | None) -> str:
    """Helper to resolve entity ID to name."""
    if not entity_id:
        return ""
    for e in doc.get("entities", []):
        if e["entity_id"] == entity_id:
            return str(e["canonical_name"])
    return entity_id or ""


def get_facts_by_type(doc: dict[str, Any], fact_type: str) -> list[dict[str, Any]]:
    return [f for f in doc.get("facts", []) if f["fact_type"] == fact_type]


def target_assert(subtests: Subtests, condition: bool, message: str) -> None:
    """
    Assertion that we want to pass in the future, but currently might fail.
    Uses subtests to avoid stopping the test and mark the specific check as XFAIL.
    """
    with subtests.test(msg=f"TARGET: {message}"):
        if not condition:
            pytest.xfail(f"TARGET_FAIL: {message}")


# --- Benchmarks ---


def test_wp_lubczyk(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Lubczyk dalej ciągnie kasę z Sejmu. Ale są lepsi od niego
    URL: https://wiadomosci.wp.pl/lubczyk-dalej-ciagnie-kase-z-sejmu-ale-sa-lepsi-od-niego-6998874649205248a
    Expectation:
    - Relevant public-money oversight.
    - Recover Radosław Lubczyk, Sejm / Kancelaria Sejmu.
    - No APPOINTMENT required, but generic public-money signal useful.
    """
    key = "wp_lubczyk"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]

    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Lubczyk" in e for e in entities)
    assert any("Radosław" in e for e in entities)

    # Target: recover the institution and other people
    target_assert(
        subtests,
        any("Sejm" in e or "Kancelaria Sejmu" in e for e in entities),
        "Should recover Sejm/Kancelaria Sejmu",
    )
    target_assert(
        subtests,
        any("Hołownia" in e for e in entities),
        "Should recover Szymon Hołownia",
    )


def test_onet_totalizator(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Partyjny desant na Totalizator Sportowy
    URL: https://wiadomosci.onet.pl/kraj/partyjny-desant-na-totalizator-sportowy-oni-dostali-lukratywne-stanowiska/7nvq01b
    Expectation:
    - Strongly in scope.
    - Multiple APPOINTMENT findings into Totalizator Sportowy.
    - Regional director roles (HOLDS_POSITION_AT).
    - PARTY_MEMBERSHIP for PO, PSL, Lewica.
    - Compensation: over 20 tys. zł miesięcznie.
    """
    key = "onet_totalizator"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Totalizator" in e for e in entities)

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    assert any(
        "Adam Sekuła" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments
    )

    # Target assertions
    target_assert(
        subtests,
        len(appointments) >= 3,
        f"Expected many appointments in Totalizator article, found {len(appointments)}",
    )
    target_assert(
        subtests,
        any("Nitras" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments),
        "Should find Sławomir Nitras",
    )

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    target_assert(
        subtests,
        any("PO" in p or "Platforma" in p or "Koalicja Obywatelska" in p for p in parties),
        "Should recover PO membership",
    )
    target_assert(subtests, any("PSL" in p for p in parties), "Should recover PSL membership")

    compensation = get_facts_by_type(doc, "COMPENSATION")
    target_assert(
        subtests, len(compensation) > 0, "Should extract compensation metadata (20 tys. zł)"
    )


def test_pleszew24_stadnina(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Radna powiatowa z posadą. Zmiana prezesa słynnej państwowej stadniny koni
    URL: https://pleszew24.info/pl/12_biznes/16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni.html
    Expectation:
    - Strongly in scope.
    - A. Góralczyk -> APPOINTMENT -> Stadnina Koni Iwno.
    - Przemysław Pacia -> DISMISSAL -> Stadnina Koni Iwno.
    - A. Góralczyk -> PARTY_MEMBERSHIP -> PSL.
    """
    key = "pleszew24.info__pl__12_biznes__16076_radna-powiatowa-z-posada-zmiana-prezesa-slynnej-panstwowej-stadniny-koni"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    assert any(
        "Góralczyk" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments
    )

    assert any("Iwno" in get_entity_name(doc, f.get("object_entity_id")) for f in appointments), (
        "Object should be Stadnina Koni Iwno"
    )

    dismissals = get_facts_by_type(doc, "DISMISSAL")
    assert any(
        "Pacia" in get_entity_name(doc, f.get("subject_entity_id"))
        or "Pacie" in get_entity_name(doc, f.get("subject_entity_id"))
        for f in dismissals
    )

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    target_assert(
        subtests,
        any("PSL" in p or "Polskie Stronnictwo Ludowe" in p for p in parties),
        "Should recover PSL membership for Góralczyk",
    )


def test_oko_rydzyk_funding(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Miliony. Pajęczyna Rydzyka
    URL: https://oko.press/miliony-pajeczyna-rydzyka
    Expectation:
    - In scope, structurally harder.
    - Flows of public money into projects associated with Tadeusz Rydzyk / Fundacja Lux Veritatis.
    - Public institutions providing money (e.g., WFOŚiGW).
    """
    key = "oko_miliony_pajeczyna_rydzyka"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Lux Veritatis" in e for e in entities)
    assert any("Rydzyk" in e for e in entities)

    funding_facts = get_facts_by_type(doc, "FUNDING")
    target_assert(subtests, len(funding_facts) > 0, "Expected FUNDING facts in OKO Rydzyk article")
    target_assert(
        subtests,
        any(
            "Wojewódzki Fundusz Ochrony Środowiska"
            in get_entity_name(doc, f.get("subject_entity_id"))
            for f in funding_facts
        ),
        "Should find WFOŚiGW as funder",
    )


def test_rp_klich(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Posady współpracowników Klicha
    URL: https://www.rp.pl/polityka/art15805981-posady-wspolpracownikow-klicha
    Expectation:
    - Strongly in scope, patronage network.
    - Hodura, Dulian, Kuczmański obtaining positions.
    - Acquaintance / collaborator links to Bogdan Klich.
    """
    key = "rp_klich"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    subjects = [get_entity_name(doc, f.get("subject_entity_id")) for f in appointments]

    target_assert(
        subtests, any("Hodura" in s for s in subjects), "Should find Jarosław Hodura appointment"
    )
    target_assert(
        subtests, any("Dulian" in s for s in subjects), "Should find Marcin Dulian appointment"
    )

    ties = get_facts_by_type(doc, "PERSONAL_OR_POLITICAL_TIE")
    assert any("Klich" in get_entity_name(doc, t.get("object_entity_id")) for t in ties)
    target_assert(
        subtests,
        any(
            "friend" in str(t.get("value_normalized"))
            or "acquaintance" in str(t.get("value_normalized"))
            for t in ties
        ),
        "Should extract tie semantics",
    )


def test_niezalezna_synekury(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Uśmiechnięte synekury Polski 2050
    URL: https://niezalezna.pl/polityka/usmiechniete-synekury-polski-2050-31-tys-zl-dla-prezesa-kzn-i-etaty-dla-dzialaczy/533532
    Expectation:
    - Strongly in scope.
    - Łukasz Bałajewicz -> APPOINTMENT -> Krajowy Zasób Nieruchomości.
    - Łukasz Bałajewicz -> PARTY_MEMBERSHIP -> Polska 2050.
    - Compensation: ponad 31 tys. zł brutto miesięcznie.
    """
    key = "niezalezna_polski2050_synekury"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    assert any(
        "Bałajewicz" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments
    )

    target_assert(
        subtests,
        any(
            "Krajowy Zasób Nieruchomości" in get_entity_name(doc, f.get("object_entity_id"))
            for f in appointments
        ),
        "KZN should be the object",
    )

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    target_assert(
        subtests, any("Polska 2050" in p for p in parties), "Should recover Polska 2050 membership"
    )

    compensation = get_facts_by_type(doc, "COMPENSATION")
    target_assert(subtests, len(compensation) > 0, "Should extract compensation (31 tys. zł)")


def test_radomszczanska_rzasowski(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Nowy zaciąg tłustych...
    URL: https://radomszczanska.pl/artykul/nowy-zaciag-tlustych-n1256470
    Expectation:
    - Marek Rząsowski -> APPOINTMENT -> AMW Rewita (wiceprezes).
    - Marek Rząsowski -> PARTY_MEMBERSHIP -> Platforma Obywatelska.
    - AMW Rewita recognized as state-controlled.
    - Compensation: 24 tys. zł brutto.
    """
    key = "radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    assert any(
        "Rząsowski" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments
    )

    target_assert(
        subtests,
        any("Rewita" in get_entity_name(doc, f.get("object_entity_id")) for f in appointments),
        "AMW Rewita should be the object",
    )

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    target_assert(
        subtests,
        any("Platforma Obywatelska" in p or "PO" in p for p in parties),
        "Should recover PO membership",
    )


def test_natura_tour(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Tak PSL obsadził państwową spółkę
    URL: https://wiadomosci.onet.pl/kraj/tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra/ezt8y9t
    Expectation:
    - Jolanta Sobczyk -> APPOINTMENT -> Natura Tour (prezes).
    - Multiple board facts for PSL-tied people.
    - PSL / Trzecia Droga context.
    """
    key = "wiadomosci.onet.pl__kraj__tak-psl-obsadzil-panstwowa-spolke-prace-dostal-min-29-letni-brat-wiceministra__ezt8y9t"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    assert any("Sobczyk" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments)

    target_assert(
        subtests,
        any("Natura Tour" in get_entity_name(doc, f.get("object_entity_id")) for f in appointments),
        "Natura Tour should be the object",
    )

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    target_assert(
        subtests,
        any("PSL" in p or "Polskie Stronnictwo Ludowe" in p for p in parties),
        "Should recover PSL context",
    )


def test_nfosigw_odpartyjnienie(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Odpartyjnienie rad nadzorczych?
    URL: https://wiadomosci.wp.pl/odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle-6996280410176160a
    Expectation:
    - Emilia Wasielewska -> MEMBER_OF_BOARD / APPOINTMENT -> NFOŚiGW.
    - Polska 2050 membership.
    """
    key = "wiadomosci.wp.pl__odpartyjnienie-rad-nadzorczych-nie-tak-mialo-byc-wyglada-to-bardzo-zle__6996280410176160a"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    board_members = get_facts_by_type(doc, "MEMBER_OF_BOARD")
    target_assert(
        subtests,
        any(
            "Wasielewska" in get_entity_name(doc, f.get("subject_entity_id"))
            for f in appointments + board_members
        ),
        "Emilia Wasielewska should be found as board member or appointment",
    )

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    target_assert(
        subtests, any("Polska 2050" in p for p in parties), "Should recover Polska 2050 membership"
    )


def test_sloma_olsztyn(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Jarosław Słoma w zarządzie olsztyńskich wodociągów
    URL: https://olsztyn.tvp.pl/41863255/z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow
    Expectation:
    - Jarosław Słoma -> APPOINTMENT -> PWiK Olsztyn (wiceprezes).
    - Event date: 25 lutego.
    """
    key = "olsztyn.tvp.pl__41863255__z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    assert any("Słoma" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments)

    target_assert(
        subtests,
        any("Wodociąg" in get_entity_name(doc, f.get("object_entity_id")) for f in appointments),
        "Object should be PWiK Olsztyn",
    )


def test_zona_posla_pis(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Żona posła PiS zrezygnowała...
    URL: https://wiadomosci.onet.pl/lublin/zona-posla-pis-zrezygnowala-z-zasiadania-w-radach-nadzorczych-panstwowych-spolek/hhpswdf
    Expectation:
    - Renata Stefaniuk -> DISMISSAL -> Enea Połaniec, Jelcz.
    - Renata Stefaniuk -> PERSONAL_OR_POLITICAL_TIE -> Dariusz Stefaniuk (wife).
    - Dariusz Stefaniuk -> PARTY_MEMBERSHIP -> PiS.
    """
    key = "zona-posla-pis"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    dismissals = get_facts_by_type(doc, "DISMISSAL")
    assert any("Stefaniuk" in get_entity_name(doc, f.get("subject_entity_id")) for f in dismissals)

    target_assert(subtests, len(dismissals) >= 2, "Should find multiple dismissals (Enea, Jelcz)")

    ties = get_facts_by_type(doc, "PERSONAL_OR_POLITICAL_TIE")
    assert any(t.get("kinship_detail") == "spouse" for t in ties), (
        "Should identify spouse relationship"
    )

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Dariusz Stefaniuk" in e for e in entities)


def test_wp_zona_posla_pis_lubelskie_koleje(
    benchmark_results: dict[str, Any],
    subtests: Subtests,
) -> None:
    """
    Article: Żona posła PiS odnalazła się w Lublinie...
    URL: https://wiadomosci.wp.pl/zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-uchwaly-o-nepotyzmie-7273798906222848a
    Expectation:
    - Sylwia Sobolewska -> APPOINTMENT / MEMBER_OF_BOARD -> Lubelskie Koleje.
    - Sylwia Sobolewska -> PERSONAL_OR_POLITICAL_TIE -> Krzysztof Sobolewski (wife).
    - Krzysztof Sobolewski -> PARTY_MEMBERSHIP -> PiS.
    - TODO: prior Orlen / Port Lotniczy exits and board remuneration are important supporting
      findings, but need better historical-event and compensation-target handling before hard asserts.
    """
    key = (
        "wiadomosci.wp.pl__zona-posla-pis-odnalazla-sie-w-lublinie-byla-ofiara-"
        "uchwaly-o-nepotyzmie__7273798906222848a"
    )
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Sobolewska" in e for e in entities)
    assert any("Sylwia Sobolewska" in e for e in entities), (
        "Should recover normalized Sylwia Sobolewska"
    )
    assert any("Krzysztof Sobolewski" in e for e in entities), "Should recover Krzysztof Sobolewski"
    assert any("Lubelskie Koleje" in e for e in entities), "Should recover Lubelskie Koleje"

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    board_memberships = get_facts_by_type(doc, "MEMBER_OF_BOARD")
    governance_facts = appointments + board_memberships
    assert any(
        "Sobolewska" in get_entity_name(doc, f.get("subject_entity_id")) for f in governance_facts
    ), "Should create a governance fact for Sylwia Sobolewska"
    assert any(
        "Lubelskie Koleje" in get_entity_name(doc, f.get("object_entity_id"))
        for f in governance_facts
    ), "Governance target should be Lubelskie Koleje"

    ties = get_facts_by_type(doc, "PERSONAL_OR_POLITICAL_TIE")
    assert any(
        "Sobolewska" in get_entity_name(doc, t.get("subject_entity_id"))
        and "Sobolewski" in get_entity_name(doc, t.get("object_entity_id"))
        and t.get("kinship_detail") == "spouse"
        for t in ties
    ), "Should identify Sobolewska/Sobolewski spouse relationship"

    parties = [
        get_entity_name(doc, f.get("object_entity_id"))
        for f in get_facts_by_type(doc, "PARTY_MEMBERSHIP")
    ]
    assert any("PiS" in p or "Prawo i Sprawiedliwość" in p for p in parties), (
        "Should recover PiS affiliation"
    )


def test_olsztyn_wodkan(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: zarobki prezesów przedsiębiorstw wodociągowych
    URL: https://www.olsztyn.com.pl/artykul,sprawdzili-zarobki-prezesow-przedsiebiorstw-wodociagowych-w-najwiekszych-miastach-ile-zarabia-prezes-wodkanu,33659.html
    Expectation:
    - Relevant public-money oversight.
    - Wiesław Pancer -> PWiK Olsztyn (prezes).
    - Henryk Milcarz -> Wodociągi Kieleckie (prezes).
    - Salary figures captured.
    """
    key = "olsztyn_wodkan"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Pancer" in e for e in entities)

    target_assert(subtests, any("Milcarz" in e for e in entities), "Should recover Henryk Milcarz")

    compensation = get_facts_by_type(doc, "COMPENSATION")
    target_assert(subtests, len(compensation) >= 2, "Should extract multiple compensation facts")


def test_tvn24_siemianowice(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Kolesiostwo i rozdawanie posad...
    URL: https://tvn24.pl/polska/kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831v
    Expectation:
    - Relevant municipal patronage complaint.
    - Dorota Połedniok, Jacek Guzy.
    - Patronage / kolesiostwo language.
    """
    key = "tvn24.pl__polska__kolesiostwo-i-rozdawanie-posad-miasto-umiera-radna-po-ze-slaska-pisze-do-premiera-ra323735-ls3431831__webarchive_20250427191848"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Połedniok" in e for e in entities)

    ties = get_facts_by_type(doc, "PERSONAL_OR_POLITICAL_TIE")
    target_assert(subtests, len(ties) > 0, "Should extract political ties / patronage signal")


def test_dziennik_zachodni_bytom(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Nepotyzm w Bytomiu?
    URL: https://dziennikzachodni.pl/nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zapowiedzieli-ze-zloza-zawiadomienie-do-cba-o-mozliwosci-popelnienia-przestepstwa/ar/c1-16375383
    Expectation:
    - Strongly in scope.
    - CBA complaint context.
    - Wnuk Consulting contracts with city/PEC/BPK.
    - Mariusz Wołosz -> colleague link -> Bartłomiej Wnuk.
    - Contract amounts: 397k, 241k.
    """
    key = "dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    entities = [e["canonical_name"] for e in doc.get("entities", [])]
    assert any("Bartków" in e for e in entities)
    assert any("Wnuk" in e for e in entities)

    target_assert(
        subtests,
        any("CBA" in e or "Centralne Biuro" in e for e in entities),
        "Should recover CBA institution",
    )

    funding = get_facts_by_type(doc, "FUNDING")
    target_assert(
        subtests, len(funding) > 0, "Should extract contract/funding facts (Wnuk Consulting)"
    )

    ties = get_facts_by_type(doc, "PERSONAL_OR_POLITICAL_TIE")
    target_assert(
        subtests,
        any("Wołosz" in get_entity_name(doc, t.get("subject_entity_id")) for t in ties),
        "Should find Wołosz-Wnuk link",
    )


@pytest.mark.xfail(reason="Known relevance failure documented in AGENTS.md")
def test_wfosigw_lublin_xfail(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Nowe władze WFOŚiGW in Lublinie bez konkursu
    URL: https://wiadomosci.onet.pl/lublin/nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow/cpw9ltt
    Expectation:
    - Strongly in scope.
    - Stanisław Mazur -> APPOINTMENT -> WFOŚiGW Lublin (prezes).
    - Andrzej Kloc -> APPOINTMENT -> WFOŚiGW Lublin (wiceprezes).
    - Agnieszka Kruk, Anna Pokwapisz -> DISMISSAL.
    - Party ties (Lewica, PSL).
    """
    key = "wiadomosci.onet.pl__lublin__nowe-wladze-wfosigw-w-lublinie-bez-konkursu-i-bez-wysluchania-kandydatow__cpw9ltt"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is True

    appointments = get_facts_by_type(doc, "APPOINTMENT")
    target_assert(
        subtests,
        any("Mazur" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments),
        "Should find Mazur appointment",
    )
    target_assert(
        subtests,
        any("Kloc" in get_entity_name(doc, f.get("subject_entity_id")) for f in appointments),
        "Should find Kloc appointment",
    )


def test_wp_meloni_negative(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: Giorgia Meloni krytykuje Trumpa.
    URL: https://wiadomosci.wp.pl/giorgia-meloni-krytykuje-trumpa-w-tle-komentarze-o-papiezu-7274914684700960a
    Expectation: True negative (international news).
    """
    key = "wp_meloni_negative"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is False
    assert len(doc.get("facts", [])) == 0


def test_olsztyn_roosevelta_negative(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: historia Placu Roosevelta
    URL: https://www.olsztyn.com.pl/artykul,od-targu-konskiego-do-miejskiego-wezla-niezwykla-historia-placu-roosevelta-poczatkiem-wyjatkowej-serii,46601.html
    Expectation: True negative (local history).
    """
    key = "olsztyn_roosevelta_negative"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    assert doc["relevance"]["is_relevant"] is False
    assert len(doc.get("facts", [])) == 0


def test_rp_tk_negative(benchmark_results: dict[str, Any], subtests: Subtests) -> None:
    """
    Article: status sędziego TK
    URL: https://www.rp.pl/sady-i-trybunaly/art44134041-czy-status-sedziego-tk-moze-rozstrzygnac-sad-pracy-a-moze-cywilny-analiza
    Expectation: True negative (legal analysis).
    """
    key = "rp_tk_negative"
    if key not in benchmark_results:
        pytest.skip(f"{key} not found")

    doc = benchmark_results[key]
    # Known relevance false positive in current version
    target_assert(
        subtests, doc["relevance"]["is_relevant"] is False, "Should be irrelevant (legal analysis)"
    )
    assert len(doc.get("facts", [])) == 0
