#!/usr/bin/env python3
"""Append one row to loop/results.tsv (the experiment log - Edison's notebook, Karpathy's results.tsv).

Every round gets a row, including reverts and crashes: a failure nobody wrote down gets repeated,
and the outer loop learns only from what is logged.

  log_round.py --feature auth --round 3 --status revert --tag wiring-gap \
      --hypothesis "store session in cookie" --predicted "test_login;test_logout" \
      --note "handler never registered" --commit abc123 --loc-delta 40

status: baseline | keep | revert | crash | blocked | audit
  audit = the post-green wiring / go-and-see audit (log what it found; tag wiring-gap etc.)
tag: short kebab-case cause. Defaults: wiring-gap regression spec-misread edge-case persistence
     shared-code-drift invariant integration perf flaky-env scope-creep check-dispute other
--predicted: ';'-separated check names you expected to flip to passing (PDCA: prediction first).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_root, load_config  # noqa: E402

COLUMNS = [
    "ts", "feature", "round", "method_v", "status", "passed", "total", "delta_passed",
    "newly_failing", "tag", "hypothesis", "predicted_hit", "note", "commit", "loc_delta",
    "failing_checks",
]
STATUSES = {"baseline", "keep", "revert", "crash", "blocked", "audit"}


def clean(s, limit=400):
    s = "" if s is None else str(s)
    return " ".join(s.replace("\t", " ").split())[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--status", required=True, choices=sorted(STATUSES))
    ap.add_argument("--tag", default="")
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--predicted", default="", help="';'-separated check names expected to flip to passing")
    ap.add_argument("--note", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--loc-delta", default="")
    a = ap.parse_args()

    root = find_root()
    cfg = load_config(root)
    results = root / "loop" / "results.tsv"

    score, dec = {}, {}
    sp, dp = root / "loop" / "last_score.json", root / "loop" / "last_decision.json"
    if sp.exists():
        score = json.loads(sp.read_text())
    if dp.exists():
        dec = json.loads(dp.read_text())

    predicted = [p.strip() for p in a.predicted.split(";") if p.strip()]
    hit = ""
    if predicted and a.status in ("keep", "revert"):
        flipped = set(dec.get("newly_passing", []))
        # match on substring so the agent can name checks loosely (test name without classname)
        n = sum(1 for p in predicted if any(p in f for f in flipped))
        hit = "%d/%d" % (n, len(predicted))

    best_before = dec.get("best_passed")
    delta = ""
    if best_before is not None and "passed" in dec:
        delta = dec["passed"] - best_before

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "feature": a.feature, "round": a.round, "method_v": cfg.get("method_version", 1),
        "status": a.status,
        "passed": score.get("passed", ""), "total": score.get("total", ""),
        "delta_passed": delta,
        "newly_failing": ";".join(dec.get("newly_failing", []))[:300],
        "tag": clean(a.tag, 40),
        "hypothesis": clean(a.hypothesis), "predicted_hit": hit,
        "note": clean(a.note), "commit": clean(a.commit, 12), "loc_delta": a.loc_delta,
        "failing_checks": ";".join(score.get("failing", []))[:300],
    }

    new = not results.exists() or results.stat().st_size == 0
    with open(results, "a") as f:
        if new:
            f.write("\t".join(COLUMNS) + "\n")
        f.write("\t".join(clean(row[c], 600) for c in COLUMNS) + "\n")
    print("logged %s#%s %s%s" % (a.feature, a.round, a.status, (" tag=" + row["tag"]) if row["tag"] else ""))


if __name__ == "__main__":
    main()
