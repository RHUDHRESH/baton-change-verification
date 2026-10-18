#!/usr/bin/env python3
"""Approve and lock a feature's checks. Run ONLY after the human has approved the plain-language list.

  lock_checks.py <feature> --approved-by "Joyal: 'looks right, go' (2026-10-09)"
  lock_checks.py <feature> --approved-by "..." --amend            # add new checks to an already-locked feature (ratchet)
  lock_checks.py <feature> --approved-by "..." --amend --replace  # replace existing checks (check dispute resolved by a human)
  lock_checks.py --refresh-tools --approved-by "..."              # re-bless loop/bin after a human-approved tool change

What it does:
  1. moves checks/pending/<feature>/ into checks/locked/<feature>/
  2. records a sha256 for every locked file in checks/locked/MANIFEST.json (plus the audit trail)
  3. makes the files read-only and commits them (the commit is a second, independent anchor)

PROVISIONAL locks (optimization mode only): when the human asked for an unattended run but never saw the scorer, pass
  --approved-by "PROVISIONAL (no human review): <why>". Refused unless config.json has opt_command (a single-number optimization
  job on an isolated branch); build/frontier checks always need a human. The report must lead with the provisional lock.

The --approved-by text is stored in the manifest history. It is a speed bump and an audit trail:
the agent has to write down whose approval it is relying on.
"""
import argparse
import os
import shutil
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    find_root, load_config, load_manifest, locked_dir, manifest_path, sha256_file, is_ignored,
    tool_hashes, fixed_hash, git, in_git_repo, write_json,
)


def make_readonly(path):
    os.chmod(path, os.stat(path).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def make_writable(path):
    os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feature", nargs="?")
    ap.add_argument("--approved-by", required=True)
    ap.add_argument("--amend", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--refresh-tools", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    a = ap.parse_args()

    root = find_root()
    cfg = load_config(root)
    if a.approved_by.strip().upper().startswith("PROVISIONAL") and not cfg.get("opt_command"):
        sys.exit("refusing a PROVISIONAL lock: only optimization mode (config opt_command) may lock without a human. "
                 "For build/frontier checks stop at the approval gate and leave the plain-language list.")
    ldir = locked_dir(root, cfg)
    pdir = root / cfg.get("pending_dir", "checks/pending")
    mp = manifest_path(root, cfg)
    man = load_manifest(root, cfg) or {"version": 0, "files": {}, "tools": {}, "history": []}

    if mp.exists():
        make_writable(mp)

    if a.refresh_tools:
        man["tools"] = tool_hashes(root)
        action, moved = "refresh-tools", []
        feature = "-"
    else:
        if not a.feature:
            sys.exit("feature name required")
        feature = a.feature
        src = pdir / feature
        if not src.is_dir() or not any(src.rglob("*")):
            sys.exit("nothing to lock: %s is missing or empty" % src)
        dst = ldir / feature
        if dst.exists() and not a.amend:
            sys.exit("%s is already locked. Use --amend to add checks (or --amend --replace to replace)." % dst)
        moved = []
        for f in sorted(src.rglob("*")):
            if f.is_dir() or is_ignored(f):
                continue
            rel = f.relative_to(src)
            target = dst / rel
            relkey = str(Path(feature) / rel)
            if target.exists():
                if not a.replace:
                    sys.exit("refusing to overwrite locked file %s (use --replace, human-approved only)" % relkey)
                make_writable(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            make_readonly(target)
            man["files"][relkey] = sha256_file(target)
            moved.append(relkey)
        shutil.rmtree(src)
        action = "amend-replace" if (a.amend and a.replace) else ("amend" if a.amend else "lock")
        if not man.get("tools"):
            man["tools"] = tool_hashes(root)
        if man.get("program_fixed_sha256") is None:
            man["program_fixed_sha256"] = fixed_hash(root)

    man["version"] = int(man.get("version", 0)) + 1
    man.setdefault("history", []).append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "feature": feature,
        "approved_by": a.approved_by, "files": moved, "manifest_version": man["version"],
    })
    write_json(mp, man)
    make_readonly(mp)

    committed = ""
    if not a.no_commit and in_git_repo(root):
        rel_locked = cfg.get("locked_dir", "checks/locked")
        git(root, "add", "-A", "--", rel_locked, "loop/bin", "loop/config.json")
        r = git(root, "commit", "-m",
                "loop: %s checks for %s (manifest v%d) - approved by: %s" % (action, feature, man["version"], a.approved_by[:120]))
        if r and r.returncode == 0:
            h = git(root, "rev-parse", "--short", "HEAD")
            committed = h.stdout.strip() if h else ""
        elif r:
            sys.stderr.write("git commit failed (is anything staged / is git configured?): %s\n" % (r.stderr or r.stdout))
    print("%s ok: %d file(s), manifest v%d%s" % (action, len(moved), man["version"],
          (", committed " + committed) if committed else " (not committed)"))
    if action in ("lock", "amend") and feature != "-":
        print("next: run run_checks.py then `decide.py --feature %s --init` to record the baseline" % feature)


if __name__ == "__main__":
    main()
