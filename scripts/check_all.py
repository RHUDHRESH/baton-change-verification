"""Run original scoring unchanged, then separately report the added checks."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    [sys.executable, "loop/bin/run_checks.py"],
    [sys.executable, "-m", "pytest", "tests/test_phase_one.py", "tests/locked/M01", "-q", "--junitxml=artifacts/foundation-tests.xml"],
    [sys.executable, "-m", "pytest", "tests/integration", "-q", "--junitxml=artifacts/transport-tests.xml"],
    [sys.executable, "-m", "pytest", "tests/redteam", "-q", "--junitxml=artifacts/redteam-tests.xml"],
]


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    statuses = []
    for command in COMMANDS:
        print("Running:", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT)
        statuses.append({"command": command[1:], "exit_code": result.returncode})
    (ROOT / "artifacts/check-run.json").write_text(json.dumps(statuses, indent=2) + "\n", encoding="utf-8")
    return int(any(status["exit_code"] for status in statuses))


if __name__ == "__main__":
    raise SystemExit(main())
