# ruff: noqa: E501
import json

articles = {
    "ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm": (
        "scratch/comparison_v1_new/ai42.pl__2024__08__04__czy-wojt-ukrywa-nepotyzm.json",
        "scratch/comparison_v2_new/document-2361b44b3ad767f1.json",
    ),
    "dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715": (
        "scratch/comparison_v1_new/dziennikpolski24.pl__kontrowersje-wokol-wojta-charsznicy-tak-prace-dostala-jego-partnerka-tomasz-koscielniak-zaprzecza-zarzutom__c1p2-28656825__webarchive_20260422220715.json",
        "scratch/comparison_v2_new/document-eff4bd00b459a340.json",
    ),
    "dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383": (
        "scratch/comparison_v1_new/dziennikzachodni.pl__nepotyzm-w-bytomiu-radni-reprezentujacy-pis-zawiadomienie-cba__c1-16375383.json",
        "scratch/comparison_v2_new/document-d669ea67fa3f4baa.json",
    ),
    "radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470": (
        "scratch/comparison_v1_new/radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470.json",
        "scratch/comparison_v2_new/document-30799fdd9b13e275.json",
    ),
}

out = open("scratch/parsed.md", "w")

for name, (v1_path, v2_path) in articles.items():
    out.write(f"# Article: {name}\n")

    with open(v1_path) as f:
        v1_data = json.load(f)
    with open(v2_path) as f:
        v2_data = json.load(f)

    out.write(f"**V1 Relevance:** {v1_data.get('is_relevant', False)}\n")
    out.write(f"**V2 Relevance:** {v2_data.get('relevance', {}).get('is_relevant', False)}\n\n")

    out.write("## V1 Facts\n")
    v1_entities = {e["entity_id"]: e for e in v1_data.get("entities", [])}
    for fact in v1_data.get("facts", []):
        subj = v1_entities.get(fact.get("subject_entity_id"), {}).get(
            "canonical_name", fact.get("subject_entity_id", "")
        )
        obj = v1_entities.get(fact.get("object_entity_id"), {}).get(
            "canonical_name", fact.get("object_entity_id", "")
        )
        role = fact.get("role", "")
        val = fact.get("value_text", "")
        ev = fact.get("evidence", {}).get("text", "")[:80].replace("\n", " ")
        out.write(
            f"- `{fact.get('fact_type')}` | Subj: {subj} | Obj: {obj} | Role: {role} | Val: {val} | Ev: {ev}\n"
        )

    out.write("\n## V2 Facts (score >= 0.5)\n")
    v2_entities = {e["id"]: e for e in v2_data.get("entities", [])}
    v2_candidates = {c["id"]: c for c in v2_data.get("fact_candidates", [])}
    for assessment in v2_data.get("fact_assessments", []):
        if assessment["assessment"]["score"] >= 0.5:
            cand = v2_candidates[assessment["fact_candidate_id"]]
            args_str = []
            for arg in cand.get("arguments", []):
                role = arg.get("role")
                if "entity_id" in arg:
                    val = v2_entities.get(arg["entity_id"], {}).get(
                        "canonical_hint", arg["entity_id"]
                    )
                else:
                    val = arg.get("value", "")
                args_str.append(f"{role}: {val}")

            evidence_ids = cand.get("evidence_ids", [])
            # Try to get evidence from somewhere if it's stored.
            # In V2, sentences contain the text, but evidence_ids refer to spans maybe.
            out.write(
                f"- `{cand.get('kind')}` (score: {assessment['assessment']['score']:.2f}) | {', '.join(args_str)} | Ev_ids: {evidence_ids}\n"
            )
    out.write("\n---\n")

out.close()
