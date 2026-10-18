#!/usr/bin/env python3
"""Run the locked checks and write a machine-readable score.

1. verify_locked  -> refuse to score if the judge was touched (exit 2)
2. run config.check_command (must emit JUnit XML to config.junit_path)
3. parse JUnit into passing / failing sets; write loop/last_score.json

Skipped and xfail tests count as FAILING. A check that can be skipped is a check that can
be gamed.

Exit codes: 0 all pass | 1 some fail | 2 integrity failure | 3 no results (crash) | 4 timeout
"""
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_root, load_config, write_json  # noqa: E402
from verify_locked import verify  # noqa: E402


def parse_junit(path):
    tree = ET.parse(path)
    passing, failing, skipped = [], [], []
    for tc in tree.getroot().iter("testcase"):
        cls = tc.get("classname", "") or ""
        name = (cls + "::" + (tc.get("name") or "")).strip(":")
        if tc.find("failure") is not None or tc.find("error") is not None:
            failing.append(name)
        elif tc.find("skipped") is not None:
            skipped.append(name)
            failing.append(name + " [skipped]")
        else:
            passing.append(name)
    return sorted(set(passing)), sorted(set(failing)), len(skipped)


def main():
    root = find_root()
    cfg = load_config(root)
    score_path = root / "loop" / "last_score.json"

    problems = verify(root)
    if problems:
        write_json(score_path, {"integrity": "FAILED", "problems": problems})
        sys.stderr.write("INTEGRITY FAILURE:\n" + "\n".join("  - " + p for p in problems) + "\n")
        sys.exit(2)

    junit = root / cfg.get("junit_path", "loop/junit.xml")
    if junit.exists():
        junit.unlink()  # a stale file must never be mistaken for a fresh run

    t0 = time.time()
    log = root / "loop" / "last_run.log"
    try:
        proc = subprocess.run(
            cfg["check_command"], shell=True, cwd=str(root),
            capture_output=True, text=True, timeout=cfg.get("timeout_seconds", 600),
        )
        log.write_text((proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or ""))
    except subprocess.TimeoutExpired:
        write_json(score_path, {"integrity": "ok", "crash": "timeout"})
        sys.stderr.write("check_command timed out\n")
        sys.exit(4)

    secs = round(time.time() - t0, 1)
    if not junit.exists():
        write_json(score_path, {"integrity": "ok", "crash": "no junit output", "returncode": proc.returncode})
        sys.stderr.write("no JUnit XML at %s - the check command did not run. Tail of loop/last_run.log:\n" % junit)
        tail = log.read_text().strip().splitlines()[-15:] if log.exists() else []
        sys.stderr.write("\n".join("  | " + l for l in tail) + "\n")
        sys.exit(3)

    try:
        passing, failing, nskipped = parse_junit(junit)
    except ET.ParseError as e:
        write_json(score_path, {"integrity": "ok", "crash": "bad junit: %s" % e})
        sys.exit(3)

    total = len(passing) + len(failing)
    score = {
        "integrity": "ok",
        "passed": len(passing),
        "failed": len(failing),
        "skipped_counted_as_failed": nskipped,
        "total": total,
        "passing": passing,
        "failing": failing,
        "seconds": secs,
        "returncode": proc.returncode,
    }
    write_json(score_path, score)
    print("score: %d/%d passing (%d failing) in %ss" % (len(passing), total, len(failing), secs))
    for f in failing[:15]:
        print("  FAIL", f)
    if len(failing) > 15:
        print("  ... and %d more (see loop/last_score.json)" % (len(failing) - 15))
    sys.exit(0 if not failing and total > 0 else 1)


if __name__ == "__main__":
    main()
