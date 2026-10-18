#!/usr/bin/env python3
"""Keep-or-revert verdict for one round, from loop/last_score.json.

Usage:
  decide.py --feature F --init              # record the baseline (after locking checks)
  decide.py --feature F [--loc-delta N]     # judge the latest round

Rules (Karpathy's keep/discard, hardened for software):
  crash                          -> revert
  any previously-passing check now failing -> revert   (regressions are never traded for progress)
  more checks passing            -> keep
  same passing set               -> keep only if the change made the code simpler (loc-delta < 0)
  otherwise                      -> revert

Exit: 0 keep | 1 revert | 3 crash. Writes loop/last_decision.json for log_round.py.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_root, write_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", required=True)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--loc-delta", type=int, default=None, help="net lines added(+)/removed(-) by the round")
    a = ap.parse_args()

    root = find_root()
    score_p = root / "loop" / "last_score.json"
    best_p = root / "loop" / "state" / ("%s.best.json" % a.feature)
    dec_p = root / "loop" / "last_decision.json"

    score = json.loads(score_p.read_text()) if score_p.exists() else {}
    if score.get("integrity") == "FAILED":
        sys.exit("integrity failure - no verdict possible; a human must review")

    if a.init:
        if "passing" not in score:
            sys.exit("no valid score to initialise from; run run_checks.py first")
        write_json(best_p, {"passed": score["passed"], "total": score["total"], "passing": score["passing"]})
        print("baseline recorded: %d/%d passing" % (score["passed"], score["total"]))
        return

    if "passing" not in score:
        out = {"verdict": "crash", "reason": score.get("crash", "no score"), "newly_passing": [], "newly_failing": []}
        write_json(dec_p, out)
        print("verdict: revert (crash: %s)" % out["reason"])
        sys.exit(3)

    if not best_p.exists():
        sys.exit("no baseline for feature %s - run decide.py --init after locking checks" % a.feature)
    best = json.loads(best_p.read_text())
    best_set, now_set = set(best["passing"]), set(score["passing"])
    newly_passing = sorted(now_set - best_set)
    newly_failing = sorted(best_set - now_set)

    if newly_failing:
        verdict, reason = "revert", "regression: %d previously-passing check(s) now fail" % len(newly_failing)
    elif len(now_set) > len(best_set):
        verdict, reason = "keep", "+%d check(s) passing" % (len(now_set) - len(best_set))
    elif now_set == best_set and a.loc_delta is not None and a.loc_delta < 0:
        verdict, reason = "keep", "same score, %d fewer lines (simplification)" % -a.loc_delta
    else:
        verdict, reason = "revert", "no improvement"

    all_green = verdict == "keep" and score["failed"] == 0 and score["total"] > 0
    out = {
        "verdict": verdict, "reason": reason, "all_green": all_green,
        "passed": score["passed"], "total": score["total"],
        "best_passed": best["passed"],
        "newly_passing": newly_passing, "newly_failing": newly_failing,
    }
    write_json(dec_p, out)
    if verdict == "keep":
        write_json(best_p, {"passed": score["passed"], "total": score["total"], "passing": score["passing"]})
    print("verdict: %s (%s)%s" % (verdict, reason, "  ** ALL GREEN **" if all_green else ""))
    sys.exit(0 if verdict == "keep" else 1)


if __name__ == "__main__":
    main()
