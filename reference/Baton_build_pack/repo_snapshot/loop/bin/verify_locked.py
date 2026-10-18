#!/usr/bin/env python3
"""Tamper check for the locked checks, the loop tools and program.md's FIXED rules.

Exit 0 = intact, exit 2 = something changed (details on stderr).

Why this exists: a deny rule in settings.json stops the agent's Edit/Write tools, but it
cannot stop every way a process can write a file. Hashes can. The loop only trusts a score
when this script says the judge is untouched.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    find_root, load_config, load_manifest, locked_dir, sha256_file, is_ignored,
    fixed_hash, tool_hashes, git, in_git_repo,
)


def verify(root):
    cfg = load_config(root)
    problems = []
    man = load_manifest(root, cfg)
    if man is None:
        return ["MANIFEST.json missing from %s (judge cannot be trusted)" % cfg.get("locked_dir")]

    ldir = locked_dir(root, cfg)
    listed = man.get("files", {})
    for rel, digest in listed.items():
        f = ldir / rel
        if not f.exists():
            problems.append("locked check deleted: %s" % rel)
        elif sha256_file(f) != digest:
            problems.append("locked check modified: %s" % rel)

    for f in ldir.rglob("*"):
        if f.is_dir() or f.name == "MANIFEST.json" or is_ignored(f):
            continue
        rel = str(f.relative_to(ldir))
        if rel not in listed:
            problems.append("unapproved file in locked dir: %s" % rel)

    for rel, digest in man.get("tools", {}).items():
        f = root / rel
        if not f.exists():
            problems.append("loop tool deleted: %s" % rel)
        elif sha256_file(f) != digest:
            problems.append("loop tool modified: %s" % rel)

    want = man.get("program_fixed_sha256")
    if want is not None:
        have = fixed_hash(root)
        if have != want:
            problems.append("program.md FIXED RULES changed (only a human may edit them)")

    if in_git_repo(root):
        rel_locked = cfg.get("locked_dir", "checks/locked")
        r = git(root, "status", "--porcelain", "--", rel_locked)
        if r and r.returncode == 0:
            for line in r.stdout.splitlines():
                if not is_ignored(line):
                    problems.append("uncommitted change in locked dir: %s" % line.strip())
    return problems


def main():
    root = find_root()
    problems = verify(root)
    if problems:
        sys.stderr.write("INTEGRITY FAILURE - do not trust any score until a human reviews this:\n")
        for p in problems:
            sys.stderr.write("  - %s\n" % p)
        sys.exit(2)
    print("integrity ok: locked checks, loop tools and FIXED rules match the manifest")


if __name__ == "__main__":
    main()
