"""Live verifier gates with the approved artifact and no network calls."""
import copy
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock
import urllib.error

import pytest

from server import execution_evidence as evidence


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_execution", ROOT / "deploy/verify_execution.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


@pytest.fixture
def proof(monkeypatch):
    report = ROOT / "docs/evidence/execution.json"
    receipt = evidence._receipt(json.loads(report.read_bytes()), evidence.APPROVED_REPORT_SHA256, evidence.APPROVED_EVIDENCE_URL)
    receipt["task_status"] = "done"
    receipt["checks"].sort(key=lambda check: check["name"])
    nodes = [{"data": {"id": receipt["id"], "kind": "ExecutionReceipt", "properties": {
        "report_sha256": verify.DIGEST, "task_id": verify.TASK, "item_id": verify.ITEM, "status": "passed"}}}]
    nodes += [{"data": {"id": check["id"], "kind": "ExecutionCheck", "properties": check}} for check in receipt["checks"]]
    edge = lambda kind, source, target: {"data": {"kind": kind, "source": source, "target": target}}
    edges = [edge("HAS_EXECUTION", verify.TASK, verify.RECEIPT), edge("VALIDATES", verify.RECEIPT, verify.ITEM),
             edge("TRACKS", verify.TASK, verify.ITEM)]
    edges += [edge("HAS_CHECK", verify.RECEIPT, check["id"]) for check in receipt["checks"]]
    graph = {"graph": "baton_public_test", "nodes": nodes, "edges": edges, "tasks": [{"id": verify.TASK, "status": "done"}]}
    token = MagicMock(return_value="mock-private-operator")
    monkeypatch.setattr(verify, "operator_token", token)
    client = MagicMock()
    client.request.side_effect = [{"authenticated": True}, copy.deepcopy(receipt), copy.deepcopy(receipt),
        {"executions": [copy.deepcopy(receipt)]}, graph]
    return report, receipt, graph, client, token


def test_two_imports_independent_public_receipt_and_live_graph_inventory(proof):
    report, receipt, graph, client, token = proof
    result = verify.verify(report, client)
    assert result["status"] == "verified" and result["execution_checks"] == 20
    assert result["source_graph"] == graph["graph"] and result["idempotent_import"] is True
    assert client.request.call_count == 5
    sent = client.request.call_args_list[1].args[1]
    assert sent["manifest_json"].encode() == report.read_bytes()
    assert "mock-private-operator" not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["missing-check", "duplicate-link", "wrong-target", "task-todo", "corrupt-outcome"])
def test_independent_graph_failures_cannot_report_verified(proof, mutation):
    _, receipt, graph, _, _ = proof
    if mutation == "missing-check": graph["nodes"].pop()
    elif mutation == "duplicate-link": graph["edges"].append(copy.deepcopy(graph["edges"][-1]))
    elif mutation == "wrong-target": graph["edges"][1]["data"]["target"] = "wrong-root"
    elif mutation == "task-todo": graph["tasks"][0]["status"] = "todo"
    elif mutation == "corrupt-outcome": graph["nodes"][1]["data"]["properties"]["exit_code"] = 999
    with pytest.raises(verify.VerificationError):
        verify.verify_workspace(graph, {check["id"] for check in receipt["checks"]})


def test_unapproved_report_stops_before_private_configuration_read(proof, tmp_path):
    _, _, _, client, token = proof
    path = tmp_path / "report.json"
    path.write_text('{"status":"passed"}')
    with pytest.raises(verify.VerificationError, match="approved"):
        verify.verify(path, client)
    token.assert_not_called()
    client.request.assert_not_called()


def test_failed_login_stops_before_import(proof):
    report, _, _, client, _ = proof
    client.request.side_effect = [{"authenticated": False}]
    with pytest.raises(verify.VerificationError, match="login"):
        verify.verify(report, client)
    assert client.request.call_count == 1


def test_provider_error_body_and_redirect_never_escape():
    client = verify.Workspace()
    client.opener = MagicMock()
    client.opener.open.side_effect = urllib.error.HTTPError(verify.ORIGIN, 500, "private-token", {}, io.BytesIO(b"private-token"))
    with pytest.raises(verify.VerificationError) as error:
        client.request("/api/public/executions")
    assert "private-token" not in str(error.value)
    with pytest.raises(verify.VerificationError, match="redirect"):
        verify.NoRedirect().redirect_request(None, None, 302, "secret", {}, "https://evil.test")
