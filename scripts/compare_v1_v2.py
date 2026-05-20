"""
compare_v1_v2.py  –  side-by-side comparison of V1 and V2 extraction outputs.

Usage:
    uv run python scripts/compare_v1_v2.py \
        --v1-dir scratch/comparison_v1_improved \
        --v2-dir scratch/comparison_v2_improved \
        --article-names olsztyn_wodkan onet_wfosigw_lublin zona-posla-pis \
                        rp_tk_negative onet_totalizator niezalezna_polski2050_synekury \
        --report-out reports/v2/comparison_2026-05-20.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _v1_facts(data: dict) -> list[dict]:
    return data.get("facts", [])


def _v2_facts(data: dict, threshold: float = 0.5) -> list[dict]:
    assessments = {
        a["fact_candidate_id"]: a["assessment"]
        for a in data.get("fact_assessments", [])
    }
    entity_map = {e["id"]: e for e in data.get("entities", [])}

    out = []
    for f in data.get("fact_candidates", []):
        fid = f["id"]
        score = assessments.get(fid, {}).get("score", 0.0)
        if score < threshold:
            continue
        args: dict[str, str] = {}
        for arg in f.get("arguments", []):
            role = arg["role"]
            val = arg.get("value") or arg.get("entity_id", "")
            if val in entity_map:
                val = entity_map[val].get("canonical_hint", val)
            args[role] = val
        out.append({"kind": f["kind"], "score": score, **args})
    return out


def _resolve_v2_file(v2_dir: Path, article_name: str) -> Path | None:
    # V2 names by document_id; find by scanning the dir
    for p in sorted(v2_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        src = data.get("source_url") or data.get("title") or ""
        # Try to match by article name fragment
        if article_name.replace("_", "-") in (data.get("title") or "").replace(" ", "-").lower():
            return p
    # Fallback: return first file (for single-article runs)
    files = sorted(v2_dir.glob("*.json"))
    return files[0] if files else None


def _find_v1_file(v1_dir: Path, article_name: str) -> Path | None:
    candidates = sorted(v1_dir.glob(f"{article_name}*.json"))
    if candidates:
        return candidates[0]
    # look for any json that mentions the article name
    for p in sorted(v1_dir.glob("*.json")):
        if article_name.replace("_", "-") in p.stem.replace("_", "-"):
            return p
    return None


def _trunc(s: str, n: int = 80) -> str:
    s = s.replace("\n", " ")
    return s[:n] + "…" if len(s) > n else s


# ---------------------------------------------------------------------------
# report generation
# ---------------------------------------------------------------------------

def compare_article(
    article_name: str,
    v1_dir: Path,
    v2_dir: Path,
    threshold: float = 0.5,
) -> str:
    lines: list[str] = [f"## `{article_name}`\n"]

    # --- V1 ---
    v1_path = _find_v1_file(v1_dir, article_name)
    if v1_path is None:
        lines.append("**V1**: output not found.\n")
        v1_data: dict = {}
    else:
        v1_data = json.loads(v1_path.read_text(encoding="utf-8"))

    v1_relevant = v1_data.get("is_relevant", "?")
    entities_v1 = {e["entity_id"]: e for e in v1_data.get("entities", [])}
    v1_facts = _v1_facts(v1_data)

    # --- V2 ---
    # V2 batch outputs one file per article; find by scanning all files
    v2_path = None
    all_v2 = sorted(v2_dir.glob("*.json"))
    
    # Map article name to a v2 file by matching source_url or title
    for p in all_v2:
        d = json.loads(p.read_text(encoding="utf-8"))
        
        # Try matching by source_url from V1
        v1_url = v1_data.get("source_url")
        v2_url = d.get("source_url")
        if v1_url and v2_url and v1_url == v2_url:
            v2_path = p
            v2_data = d
            break
            
        title = (d.get("title") or "").casefold()
        if any(part in title for part in article_name.replace("_", " ").split()):
            v2_path = p
            v2_data = d
            break
    else:
        if all_v2:
            lines.append("**V2**: output could not be matched to this article.\n")
            v2_data = {}
        else:
            v2_data = {}

    v2_relevant = (v2_data.get("relevance") or {}).get("is_relevant", "?")
    v2_facts = _v2_facts(v2_data, threshold)

    # --- Relevance ---
    lines.append(f"**Relevance**: V1={v1_relevant} | V2={v2_relevant}\n")

    # --- V1 facts table ---
    if v1_facts:
        lines.append("### V1 facts\n")
        lines.append("| kind | subject | object | role | evidence |\n")
        lines.append("|------|---------|--------|------|----------|\n")
        for f in v1_facts:
            kind = f.get("fact_type", "")
            subj = entities_v1.get(f.get("subject_entity_id", ""), {}).get("canonical_name", f.get("subject_entity_id", ""))
            obj = entities_v1.get(f.get("object_entity_id", ""), {}).get("canonical_name", f.get("object_entity_id", ""))
            role = f.get("role") or ""
            ev = _trunc((f.get("evidence") or {}).get("text", ""))
            lines.append(f"| {kind} | {subj} | {obj} | {role} | {ev} |\n")
    else:
        if v1_relevant:
            lines.append("**V1**: relevant but no facts extracted.\n")
        else:
            lines.append("**V1**: irrelevant — no facts expected.\n")

    # --- V2 facts table ---
    if v2_facts:
        lines.append("### V2 facts (score ≥ 0.5)\n")
        lines.append("| kind | score | person | org | amount | other |\n")
        lines.append("|------|-------|--------|-----|--------|-------|\n")
        for f in v2_facts:
            kind = f.get("kind", "")
            score = f.get("score", 0.0)
            person = f.get("person", "")
            org = f.get("organization", "")
            amount = f.get("amount", "")
            other = " | ".join(
                f"{k}={_trunc(v, 30)}"
                for k, v in f.items()
                if k not in {"kind", "score", "person", "organization", "amount"}
            )
            lines.append(f"| {kind} | {score:.2f} | {_trunc(person, 30)} | {_trunc(org, 30)} | {amount} | {other} |\n")
    else:
        if v2_relevant:
            lines.append("**V2**: relevant but no facts scored ≥ 0.5.\n")
        elif v2_relevant is False:
            lines.append("**V2**: irrelevant — no facts expected.\n")
        else:
            lines.append("**V2**: output not found or empty.\n")

    # --- Gap analysis ---
    lines.append("### Gap analysis\n")
    v1_kinds = {f.get("fact_type", "") for f in v1_facts}
    v2_kinds = {f.get("kind", "") for f in v2_facts}
    missing = v1_kinds - v2_kinds
    extra = v2_kinds - v1_kinds
    if missing:
        lines.append(f"- ⚠️  **V2 missing** fact kinds present in V1: `{'`, `'.join(sorted(missing))}`\n")
    if extra:
        lines.append(f"- ℹ️  **V2 emits** fact kinds not in V1: `{'`, `'.join(sorted(extra))}`\n")
    if not missing and not extra and (v1_facts or v2_facts):
        lines.append("- ✅ Same fact kinds in both pipelines.\n")
    if not v1_facts and not v2_facts:
        lines.append("- Both pipelines produced no facts (expected for negative/irrelevant articles).\n")

    lines.append("\n")
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-dir", type=Path, required=True)
    parser.add_argument("--v2-dir", type=Path, required=True)
    parser.add_argument("--article-names", nargs="+", required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    sections = ["# V1 vs V2 Pipeline Comparison\n\n"]
    for name in args.article_names:
        sections.append(compare_article(name, args.v1_dir, args.v2_dir, args.threshold))

    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text("".join(sections), encoding="utf-8")
    print(f"Report written to {args.report_out}")


if __name__ == "__main__":
    main()
