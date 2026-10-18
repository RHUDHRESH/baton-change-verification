#!/usr/bin/env python3
"""Mine loop/results.tsv for the outer loop (auto-loop). Prints a markdown report; --json for machines.

This script does the counting. YOU do the judgement: decide which recurring patterns are real
habits worth a rule, phrase the rule, and check it against the evidence rows.

Reports:
  1. Recurring failure tags with evidence ids (feature#round)  -> candidate habits
       STRONG   : >=2 rounds across >=2 features
       MODERATE : >=3 rounds inside one feature
       weak     : anything else - do NOT codify (one incident is an anecdote)
  2. Regression-prone checks (newly failing >=2 times)
  3. Performance by method version (rounds-to-green, reverts, audit gaps, prediction accuracy)
  4. Habit effectiveness: for each habit in program.md written as
       - H3 (tag: wiring-gap, since v2, evidence: auth#2,auth#3): <rule text>
     did its tag stop recurring after adoption? Flags ineffective and retire-candidate habits.
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_root, load_config, program_path  # noqa: E402

HABIT_RE = re.compile(r"^\s*-\s*(H\d+)\s*\(tag:\s*([\w\-]+),\s*since\s*v(\d+)(?:,\s*evidence:\s*([^)]*))?\)\s*:?\s*(.*)$")


def load_rows(root):
    p = root / "loop" / "results.tsv"
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def as_int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def parse_habits(root):
    p = program_path(root)
    habits = []
    if p.exists():
        for line in p.read_text().splitlines():
            m = HABIT_RE.match(line)
            if m:
                habits.append({"id": m.group(1), "tag": m.group(2), "since": int(m.group(3)),
                               "evidence": (m.group(4) or "").strip(), "text": m.group(5).strip()})
    return habits


def analyse(rows, habits, min_features_for_retire=2):
    by_feature = defaultdict(list)
    for r in rows:
        by_feature[r["feature"]].append(r)

    # 1. tags
    tag_rows = defaultdict(list)
    for r in rows:
        if r["status"] in ("revert", "crash", "audit", "blocked") and r["tag"]:
            tag_rows[r["tag"]].append(r)
    tags = []
    for tag, rs in tag_rows.items():
        feats = sorted({r["feature"] for r in rs})
        ev = ["%s#%s" % (r["feature"], r["round"]) for r in rs]
        if len(rs) >= 2 and len(feats) >= 2:
            strength = "STRONG"
        elif len(rs) >= 3:
            strength = "MODERATE"
        else:
            strength = "weak"
        tags.append({"tag": tag, "rounds": len(rs), "features": feats, "evidence": ev, "strength": strength,
                     "examples": [r["note"] for r in rs if r["note"]][:3]})
    tags.sort(key=lambda t: ({"STRONG": 0, "MODERATE": 1, "weak": 2}[t["strength"]], -t["rounds"]))

    # 2. regression-prone checks
    reg = defaultdict(list)
    for r in rows:
        for c in filter(None, r.get("newly_failing", "").split(";")):
            reg[c].append("%s#%s" % (r["feature"], r["round"]))
    regress = [{"check": c, "times": len(v), "evidence": v} for c, v in reg.items() if len(v) >= 2]

    # 3. by method version
    perf = defaultdict(lambda: {"features": 0, "green": 0, "rounds_to_green": [], "reverts": 0, "audit_gaps": 0,
                                "pred_hits": 0, "pred_total": 0})
    for feat, rs in by_feature.items():
        rs = sorted(rs, key=lambda r: (as_int(r["round"]), r["ts"]))
        mv = as_int(rs[0]["method_v"], 1)
        p = perf[mv]
        p["features"] += 1
        n = 0
        green = False
        for r in rs:
            if r["status"] in ("keep", "revert", "crash"):
                n += 1
            if r["status"] == "keep" and as_int(r["passed"], -1) == as_int(r["total"], -2) and r["total"]:
                green = True
                break
        for r in rs:
            if r["status"] in ("revert", "crash"):
                p["reverts"] += 1
            if r["status"] == "audit":
                p["audit_gaps"] += 1
            m = re.match(r"(\d+)/(\d+)", r.get("predicted_hit", "") or "")
            if m:
                p["pred_hits"] += int(m.group(1))
                p["pred_total"] += int(m.group(2))
        if green:
            p["green"] += 1
            p["rounds_to_green"].append(n)

    # 4. habit effectiveness
    eff = []
    for h in habits:
        after = [r for r in rows if r["tag"] == h["tag"] and as_int(r["method_v"], 1) >= h["since"]
                 and r["status"] in ("revert", "crash", "audit")]
        feats_after = {r["feature"] for r in rows if as_int(r["method_v"], 1) >= h["since"]}
        if after:
            verdict = "INEFFECTIVE?" if len(after) >= 2 else "watch"
        elif len(feats_after) >= min_features_for_retire:
            verdict = "holding (0 recurrences over %d features) - keep; retire only if it costs more than it saves" % len(feats_after)
        else:
            verdict = "too early (%d feature(s) since adoption)" % len(feats_after)
        eff.append({"habit": h["id"], "tag": h["tag"], "since": h["since"], "recurrences_since": len(after),
                    "evidence_since": ["%s#%s" % (r["feature"], r["round"]) for r in after], "verdict": verdict})
    return {"tags": tags, "regression_prone": regress, "perf": perf, "habit_effectiveness": eff}


def render(res, n_rows):
    out = ["# Habit-mining report (%d logged rounds)\n" % n_rows]
    out.append("## Candidate habits by failure tag\n")
    if not res["tags"]:
        out.append("_No tagged reverts/audit gaps yet. Nothing to codify._\n")
    for t in res["tags"]:
        out.append("- **%s** [%s] - %d round(s) in %d feature(s): %s" % (
            t["tag"], t["strength"], t["rounds"], len(t["features"]), ", ".join(t["evidence"])))
        for ex in t["examples"]:
            out.append("    - e.g. %s" % ex)
    out.append("\n_Only STRONG/MODERATE patterns may become habits. A single incident is an anecdote, not a pattern._\n")
    out.append("## Regression-prone checks\n")
    out += ["- `%s` regressed %d times: %s" % (r["check"], r["times"], ", ".join(r["evidence"])) for r in res["regression_prone"]] or ["_none_"]
    out.append("\n## Performance by method version\n")
    out.append("| method | features | reached green | mean rounds-to-green | reverts | audit gaps | prediction hit-rate |")
    out.append("|---|---|---|---|---|---|---|")
    for mv in sorted(res["perf"]):
        p = res["perf"][mv]
        mean = ("%.1f" % (sum(p["rounds_to_green"]) / len(p["rounds_to_green"]))) if p["rounds_to_green"] else "-"
        hr = ("%d%%" % round(100 * p["pred_hits"] / p["pred_total"])) if p["pred_total"] else "-"
        out.append("| v%d | %d | %d | %s | %d | %d | %s |" % (mv, p["features"], p["green"], mean, p["reverts"], p["audit_gaps"], hr))
    out.append("\n_Features differ in difficulty and n is tiny: treat differences as weak evidence. Revert a method change only on a clear, repeated degradation or when a habit's tag keeps recurring._\n")
    out.append("## Habit effectiveness\n")
    out += ["- %s (tag %s, since v%d): %d recurrence(s) since adoption%s -> %s" % (
        e["habit"], e["tag"], e["since"], e["recurrences_since"],
        (" [" + ", ".join(e["evidence_since"]) + "]") if e["evidence_since"] else "", e["verdict"])
        for e in res["habit_effectiveness"]] or ["_no habits recorded in program.md yet_"]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = find_root()
    load_config(root)
    rows = load_rows(root)
    res = analyse(rows, parse_habits(root))
    if a.json:
        print(json.dumps(res, indent=2, default=dict))
    else:
        print(render(res, len(rows)))


if __name__ == "__main__":
    main()
