#!/usr/bin/env python3
"""Optimization mode (Karpathy's original autoresearch loop): judge ONE experiment against a scalar score.

The scorer is a read-only program (lock it with lock_checks.py as feature 'scorer' so it is hash-protected) that
prints a line like `score: 0.9731`. The agent changes the ONE mutable file, commits, then runs:

  python3 loop/bin/opt_step.py --description "wider MLP, GELU" [--loc-delta N]

It: verifies the judge is intact -> runs config.opt_command (time-boxed) -> parses the score -> compares to the best so
far (config.opt_direction = min|max, config.opt_epsilon) -> prints KEEP or REVERT -> appends loop/opt_results.tsv.
The agent then does the git part: on REVERT `git reset --hard HEAD~1` (and clean new files in the mutable path).

  --init     record the baseline (run on the UNMODIFIED code first)

Exit: 0 keep | 1 revert | 3 crash/timeout | 2 integrity failure.
Karpathy's simplicity criterion is built in: an equal score with less code (loc-delta < 0) is a KEEP.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_root, load_config, write_json  # noqa: E402
from verify_locked import verify  # noqa: E402

COLUMNS = ["ts", "round", "status", "score", "best_before", "loc_delta", "seconds", "description"]


def clean(s):
    return " ".join(str(s).replace("\t", " ").split())[:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--description", default="")
    ap.add_argument("--loc-delta", type=int, default=None)
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args()

    root = find_root()
    cfg = load_config(root)
    cmd = cfg.get("opt_command")
    if not cmd:
        sys.exit("config.opt_command missing (e.g. 'python3 checks/locked/scorer/score.py'); see references/optimization-mode.md")
    direction = cfg.get("opt_direction", "max")
    eps = float(cfg.get("opt_epsilon", 0.0))
    rx = re.compile(cfg.get("opt_score_regex", r"^score:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"), re.M)

    problems = verify(root)
    if problems:
        sys.stderr.write("INTEGRITY FAILURE:\n" + "\n".join("  - " + p for p in problems) + "\n")
        sys.exit(2)

    state = root / "loop" / "state" / "opt.best.json"
    results = root / "loop" / "opt_results.tsv"
    best = json.loads(state.read_text())["score"] if state.exists() else None
    rnd = (sum(1 for _ in open(results)) - 1) if results.exists() else 0

    t0 = time.time()
    status, score, note = "crash", None, ""
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True,
                           timeout=cfg.get("opt_timeout_seconds", 600))
        (root / "loop" / "last_run.log").write_text((p.stdout or "") + "\n--- stderr ---\n" + (p.stderr or ""))
        m = rx.search(p.stdout or "")
        if m:
            score = float(m.group(1))
        else:
            note = "no score line; tail: " + " | ".join((p.stderr or p.stdout or "").strip().splitlines()[-3:])
    except subprocess.TimeoutExpired:
        note = "timeout (treated as failure)"
    secs = round(time.time() - t0, 1)

    if score is not None:
        if a.init or best is None:
            status = "baseline"
        else:
            better = (score < best - eps) if direction == "min" else (score > best + eps)
            same = abs(score - best) <= eps
            if better:
                status = "keep"
            elif same and a.loc_delta is not None and a.loc_delta < 0:
                status, note = "keep", "same score, simpler code"
            else:
                status = "revert"
        if status in ("baseline", "keep"):
            write_json(state, {"score": score, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})

    new = not results.exists()
    with open(results, "a") as f:
        if new:
            f.write("\t".join(COLUMNS) + "\n")
        f.write("\t".join(clean(x) for x in [
            time.strftime("%Y-%m-%dT%H:%M:%S"), rnd, status, "" if score is None else score,
            "" if best is None else best, "" if a.loc_delta is None else a.loc_delta, secs,
            (a.description + (" | " + note if note else "")),
        ]) + "\n")

    shown = "n/a" if score is None else score
    print("%s: score=%s best_before=%s (%s is better)%s" % (status.upper(), shown, best, direction, (" - " + note) if note else ""))
    sys.exit({"keep": 0, "baseline": 0, "revert": 1}.get(status, 3))


if __name__ == "__main__":
    main()
