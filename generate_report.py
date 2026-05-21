# ruff: noqa: E501

import json

articles = [
    {
        "title": "Czy wójt ukrywa nepotyzm?",
        "filename": "ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm",
        "v1": "scratch/comparison_v1_new/ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm.json",
        "v2": "scratch/comparison_v2_new/document-2361b44b3ad767f1.json",
    },
    {
        "title": "Kontrowersje wokół wójta Charsznicy",
        "filename": "dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715",
        "v1": "scratch/comparison_v1_new/dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715.json",
        "v2": "scratch/comparison_v2_new/document-eff4bd00b459a340.json",
    },
    {
        "title": "Nepotyzm w Bytomiu - radni PiS",
        "filename": "dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383",
        "v1": "scratch/comparison_v1_new/dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383.json",
        "v2": "scratch/comparison_v2_new/document-d669ea67fa3f4baa.json",
    },
    {
        "title": "Nowy zaciąg tłustych",
        "filename": "radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470",
        "v1": "scratch/comparison_v1_new/radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470.json",
        "v2": "scratch/comparison_v2_new/document-30799fdd9b13e275.json",
    },
]

out = open("reports/v2/comparison_2026-05-20_new.md", "w")
out.write("# Pipeline Comparison Report: V1 vs V2\n\n")

for art in articles:
    with open(art["v1"]) as f:
        v1_data = json.load(f)
    with open(art["v2"]) as f:
        v2_data = json.load(f)

    out.write(f"## Article: {art['title']}\n")
    out.write(f"**Filename:** `{art['filename']}`\n\n")

    out.write(
        f"**Relevance:**\n- V1: `{v1_data.get('is_relevant', False)}`\n- V2: `{v2_data.get('relevance', {}).get('is_relevant', False)}`\n\n"
    )

    out.write("### V1 Facts Table\n")
    out.write("| Kind | Subject | Object | Role / Value | Evidence Excerpt |\n")
    out.write("|---|---|---|---|---|\n")

    v1_entities = {e["entity_id"]: e for e in v1_data.get("entities", [])}
    for fact in v1_data.get("facts", []):
        subj = v1_entities.get(fact.get("subject_entity_id"), {}).get(
            "canonical_name", fact.get("subject_entity_id", "")
        )
        obj = v1_entities.get(fact.get("object_entity_id"), {}).get(
            "canonical_name", fact.get("object_entity_id", "")
        )
        role_val = fact.get("role") or fact.get("value_text", "")
        if role_val is None:
            role_val = ""
        ev = fact.get("evidence", {}).get("text", "")[:80].replace("\n", " ")
        out.write(f"| {fact.get('fact_type')} | {subj} | {obj} | {role_val} | {ev} |\n")

    out.write("\n### V2 Facts Table (score >= 0.5)\n")
    out.write("| Kind | Score | Arguments | Evidence Excerpt |\n")
    out.write("|---|---|---|---|\n")

    v2_entities = {e["id"]: e for e in v2_data.get("entities", [])}
    v2_candidates = {c["id"]: c for c in v2_data.get("materialized_facts", [])}

    has_v2 = False
    for assessment in v2_data.get("materialized_fact_assessments", []):
        if assessment["assessment"]["score"] >= 0.5:
            has_v2 = True
            cand = v2_candidates[assessment["materialized_fact_id"]]
            args_str = []
            for arg in cand.get("arguments", []):
                role = arg.get("role")
                if "entity_id" in arg:
                    val = v2_entities.get(arg["entity_id"], {}).get(
                        "canonical_hint", arg["entity_id"]
                    )
                else:
                    val = arg.get("value", "")
                args_str.append(f"**{role}**: {val}")

            evidence_ids = cand.get("evidence_ids", [])

            # extract first few words of evidence if we can
            ev_text = str(
                evidence_ids
            )  # placeholder, since we don't load the full sentences mapping here simply

            out.write(
                f"| {cand.get('kind')} | {assessment['assessment']['score']:.2f} | {', '.join(args_str)} | {ev_text} |\n"
            )

    if not has_v2:
        out.write("| (none) | - | - | - |\n")

    out.write("\n### Gap Analysis & False Positive Flags\n")

    if "ai42" in art["filename"]:
        out.write(
            "- **What V1 has that V2 misses**: V1 extracts the appointment of Rafał Dobosz (Pomoc Administracyjna) and his kinship tie to Wójt Artur Sosna. V2 missed these entirely (no facts scored >= 0.5).\n"
        )
        out.write(
            "- **What V2 has that V1 misses**: None. V2 correctly identified relevance but produced no high-scoring facts.\n"
        )
    elif "charsznicy" in art["filename"]:
        out.write(
            "- **What V1 has that V2 misses**: V1 extracts the kinship ties ('partnerka wójta', 'przyszły teść') and their appointments to Urząd Gminy and USC. V2 missed these ties.\n"
        )
        out.write(
            "- **What V2 has that V1 misses**: V2 extracts appointments to Gminny Ośrodek Kultury.\n"
        )
        out.write(
            "- **False Positives**: V2 incorrectly resolved the appointee to 'Tomasz Kościelniak' (the Wójt) instead of the actual director (likely Szymon Kubit, who V1 identified as party member/election candidate).\n"
        )
    elif "nepotyzm-w-bytomiu" in art["filename"]:
        out.write(
            "- **What V1 has that V2 misses**: V1 captures multiple political office roles (Radny).\n"
        )
        out.write(
            "- **What V2 has that V1 misses**: V2 successfully extracts the exact contract amount (397 496,95 zł) for Wnuk Consulting & PEC. V2 also captures the CBA referral with high precision.\n"
        )
        out.write(
            "- **False Positives**: V2 extracted absurd governance appointments: Maciej Bartków to 'Facebook' and 'Państwowej Komisji Wyborczej' and 'Super'. This is because it misinterpreted actions like posting on Facebook or reporting to PKW as taking governance roles.\n"
        )
    elif "radomszczanska" in art["filename"]:
        out.write(
            "- **What V1 has that V2 misses**: V1 identifies the compensation as coming from AMW Rewita.\n"
        )
        out.write(
            "- **What V2 has that V1 misses**: V2 correctly maps the kinship tie between exactly resolved names: 'Mirella Zugaj' and 'Radka Zugaja' (spouse), whereas V1 had noisy nominals like 'Żona Radka Zugaja'. V2 also correctly extracts the party affiliation and governance appointment (Rada Nadzorcza).\n"
        )
        out.write(
            "- **False Positives**: V2 attributes the funder of the compensation to 'PO' (Platforma Obywatelska) instead of the company AMW Rewita.\n"
        )
        out.write(
            "- **Notable Improvements**: V2 successfully linked the nominal kinship ('żona') to the resolved entity 'Mirella Zugaj', proving the reference resolution stages work well here.\n"
        )

    out.write("\n---\n\n")

out.write("""## Summary of Key Findings

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
""")
out.close()
