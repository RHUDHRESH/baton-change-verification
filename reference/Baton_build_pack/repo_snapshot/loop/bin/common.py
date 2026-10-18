"""Shared helpers for the karpathy-loop scripts. Standard library only.

These files get copied into <project>/loop/bin/ by scaffold.py so a project is
self-contained and does not depend on where the skill is installed.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

FIXED_BEGIN = "<!-- FIXED:BEGIN -->"
FIXED_END = "<!-- FIXED:END -->"
METHOD_BEGIN = "<!-- METHOD:BEGIN"
METHOD_END = "<!-- METHOD:END -->"

IGNORED_PARTS = ("__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".DS_Store")
IGNORED_SUFFIXES = (".pyc", ".pyo")

TOOL_FILES = [
    "common.py",
    "verify_locked.py",
    "run_checks.py",
    "decide.py",
    "log_round.py",
    "mine_habits.py",
    "lock_checks.py",
    "guard_locked.py",
    "opt_step.py",
]


def find_root(start=None):
    """Walk upward from `start` (default cwd) to the dir that holds loop/config.json."""
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / "loop" / "config.json").exists():
            return d
    sys.exit("karpathy-loop: no loop/config.json found above %s - run scaffold.py first" % p)


def load_config(root):
    return json.loads((root / "loop" / "config.json").read_text())


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_ignored(path):
    s = str(path)
    return any(part in s for part in IGNORED_PARTS) or s.endswith(IGNORED_SUFFIXES)


def git(root, *args):
    """Run git in root. Returns CompletedProcess, or None if git is unavailable."""
    try:
        return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)
    except FileNotFoundError:
        return None


def in_git_repo(root):
    r = git(root, "rev-parse", "--is-inside-work-tree")
    return bool(r and r.returncode == 0 and r.stdout.strip() == "true")


def locked_dir(root, cfg=None):
    cfg = cfg or load_config(root)
    return root / cfg.get("locked_dir", "checks/locked")


def manifest_path(root, cfg=None):
    return locked_dir(root, cfg) / "MANIFEST.json"


def load_manifest(root, cfg=None):
    mp = manifest_path(root, cfg)
    if not mp.exists():
        return None
    return json.loads(mp.read_text())


def fixed_section(program_text):
    """Return the text between the FIXED markers (inclusive of markers), or None."""
    a = program_text.find(FIXED_BEGIN)
    b = program_text.find(FIXED_END)
    if a == -1 or b == -1 or b < a:
        return None
    return program_text[a : b + len(FIXED_END)]


def fixed_hash(root):
    p = root / "program.md"
    if not p.exists():
        p = root / "loop" / "program.md"
    if not p.exists():
        return None
    sec = fixed_section(p.read_text())
    return sha256_text(sec) if sec is not None else None


def program_path(root):
    p = root / "loop" / "program.md"
    return p if p.exists() else root / "program.md"


def tool_hashes(root):
    out = {}
    for name in TOOL_FILES:
        f = root / "loop" / "bin" / name
        if f.exists():
            out["loop/bin/" + name] = sha256_file(f)
    return out


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")
