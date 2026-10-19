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
    [sys.executable, "-m", "pytest", "tests/test_groq_transport.py", "tests/test_cloud_connection.py", "tests/test_lambda_control.py", "tests/test_graph_agent.py", "tests/test_company_brain.py", "tests/test_company_connections.py", "-q", "--junitxml=artifacts/cloud-contract-tests.xml"],
    [sys.executable, "-m", "pytest", "tests/test_kan2_completion.py", "tests/test_kan2_runner.py", "tests/test_execution_evidence.py", "tests/test_verify_execution.py", "tests/test_verify_live_brief.py", "-q", "--junitxml=artifacts/execution-contract-tests.xml"],
    [sys.executable, "-m", "pytest", "tests/test_autonomous_worker.py", "tests/test_autonomous_repair.py", "tests/test_autonomous_workflow.py", "tests/test_autonomous_routes.py", "tests/test_autonomous_publication.py", "tests/test_workflow_ui.py", "-q", "--junitxml=artifacts/autonomous-contract-tests.xml"],
    [sys.executable, "-m", "pytest", "tests/test_verify_autonomous_release.py", "tests/test_verify_autonomous_cloud.py", "-q", "--junitxml=artifacts/autonomous-release-contract-tests.xml"],
    [sys.executable, "-m", "pytest", "tests/test_release_graph.py", "tests/test_release_verifier.py", "tests/test_release_gate.py", "tests/test_release_routes.py", "tests/test_release_ui.py", "tests/test_verify_release_gate.py", "tests/test_verify_release_cloud.py", "tests/test_release_preflight.py", "-q", "--junitxml=artifacts/release-gate-contract-tests.xml"],
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
