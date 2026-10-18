#!/usr/bin/env python3
"""Claude Code PreToolUse hook: stop tool calls that would modify the judge.

Protected: checks/locked/**, loop/bin/**, and (via hash check, not here) program.md FIXED rules.
Blocks (exit 2, message on stderr) any Edit/Write/NotebookEdit aimed at those paths, and any Bash
command that names those paths unless it is a read-only command or one of the loop's own scripts.

Honest limits: this reads the command text. A process that builds a path out of pieces can slip
past it. That is why verify_locked.py (hashes) runs before every score and why the final report
diffs the locked files against the lock commit using plain git. Layers, not a wall.
"""
import json
import re
import sys

PROTECTED = re.compile(r"(^|[/\s'\"=])(\./)?(checks/locked|loop/bin)(/|\b)")
READONLY_FIRST = {
    "cat", "ls", "head", "tail", "wc", "diff", "grep", "rg", "sha256sum", "find", "stat", "file",
    "pytest", "python", "python3", "node", "npx", "npm", "pnpm", "yarn", "cargo", "go",
}
WRITEY = re.compile(r"(>>?|\btee\b|\bsed\s+-i|\bperl\s+-i|\bchmod\b|\bchown\b|\brm\b|\bmv\b|\bcp\b|\bdd\b|"
                    r"\btruncate\b|\binstall\b|-delete\b|\bgit\s+(checkout|restore|reset|rm|mv|stash|clean|apply|am)\b)")
# lock_checks.py is allowed here because the orchestrator must run it after human approval; every use is
# recorded in MANIFEST.json history with the --approved-by text, and the final report lists those events.
OWN_SCRIPT = re.compile(r"^\s*(python3?|py)\s+(\./)?loop/bin/(run_checks|verify_locked|decide|log_round|mine_habits|lock_checks|opt_step)\.py\b")


def deny(msg):
    sys.stderr.write("BLOCKED by karpathy-loop guard: %s\n" % msg)
    sys.exit(2)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on malformed input
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if PROTECTED.search(path.replace("\\", "/")):
            deny("%s is part of the judge (locked checks / loop tools). If a check is wrong, write "
                 "loop/disputes/<check>.md and let a human decide." % path)
        return

    if tool == "Bash":
        cmd = inp.get("command", "")
        if not PROTECTED.search(cmd):
            return
        if OWN_SCRIPT.match(cmd):
            return
        first = cmd.strip().split()[0] if cmd.strip() else ""
        # `git diff/log/show/status` are read-only even though they mention the path
        if re.match(r"^\s*git\s+(diff|log|show|status|ls-files)\b", cmd) and not re.search(r">>?", cmd):
            return
        if first in READONLY_FIRST and not WRITEY.search(cmd):
            # python -c / node -e can write; only allow when they just run tests or our scripts
            if first in ("python", "python3", "node") and re.search(r"\s-(c|e)\b", cmd):
                deny("inline code that touches the judge's paths is not allowed")
            return
        deny("this command could modify the judge (checks/locked or loop/bin). Read-only commands and "
             "loop/bin scripts are allowed.")


if __name__ == "__main__":
    main()
