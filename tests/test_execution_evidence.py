"""Execution import contracts with the real reviewed manifest and mocked graph I/O."""
import copy
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from server import execution_evidence as evidence


URL = "https://github.com/RHUDHRESH/baton-graph-workspace/blob/1b76598a72bc1ac878dc46389851a995caef7379/docs/evidence/KAN-2.md"
MANIFEST = Path(__file__).resolve().parents[1] / "docs/evidence/execution.json"


@pytest.fixture
def captured(tmp_path, monkeypatch):
    # Preserve the audited CRLF bytes. Text-mode universal-newline translation
    # would create a different artifact, even if its JSON values matched.
    raw = MANIFEST.read_bytes().decode("utf-8")
    snapshot_id = "a" * 24
    task = {"id": evidence.TASK_ID, "item_id": evidence.ITEM_ID, "graph": "baton_public_falkordb_" + snapshot_id,
            "snapshot_id": snapshot_id, "status": "done", "title": "Verify grow-only restore"}
    records = {"tasks.json": [task], "snapshots/" + snapshot_id + ".json": {"id": snapshot_id, "graph": task["graph"],
        "items": [{"id": evidence.ITEM_ID, "url": evidence.SOURCE_URL, "source_ids": ["source"]}], "sources": [{"id": "source"}]}}
    monkeypatch.setattr(evidence.public, "read", lambda data, path, default=None: copy.deepcopy(records.get(path, default)))
    monkeypatch.setattr(evidence.public, "write", lambda data, path, value: records.__setitem__(path, copy.deepcopy(value)))
    graph = MagicMock()
    stored = {}
    def write(query, params):
        assert query == evidence.WRITE_QUERY
        if stored and stored["receipt"]["evidence_url"] != params["url"]:
            return SimpleNamespace(result_set=[])
        if not stored:
            stored.update(receipt=json.loads(params["receipt"]), checks=params["checks"])
        return SimpleNamespace(result_set=[[json.dumps(stored["receipt"]), 20]])
    graph.query.side_effect = write
    def read(query, params):
        nodes = []
        for row in stored.get("checks", []):
            check = json.loads(row["json"])
            nodes.append({key: check[key] for key in ("id", "name", "expectation", "exit_code", "matched_expectation", "log_sha256")})
            nodes[-1]["payload"] = row["json"]
        return SimpleNamespace(result_set=[[json.dumps(stored["receipt"]), nodes]] if stored else [])
    graph.ro_query.side_effect = read
    connection = MagicMock()
    connection.select_graph.return_value = graph
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(evidence.G, "connect", connect)
    return SimpleNamespace(path=tmp_path, raw=raw, records=records, task=task, graph=graph, stored=stored, connect=connect)


def test_import_binds_actual_audited_bytes_and_twenty_checks_to_real_task_graph(captured):
    result = evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    assert hashlib.sha256(captured.raw.encode()).hexdigest() == evidence.APPROVED_REPORT_SHA256
    assert result["status"] == "passed" and result["task_status"] == "done"
    assert result["summary"] == {"checks": 20, "graph_library": {"passed": 530, "failed": 0, "ignored": 17},
        "targeted_checks": 8, "expected_regression_failures": 4, "rdb": {"round_trips": 2, "nodes_preserved": 2, "parallel_edges_preserved": 2}}
    assert result["initial_failure"]["failed"] == 1 and result["workaround"]["path"] == evidence.PATCH_PATH
    assert result["executor"] == "Codex isolated Docker runner" and "Lambda and Groq did not execute" in result["scope"]
    assert len(result["checks"]) == 20 and {check["name"] for check in result["checks"]} == evidence.CHECK_NAMES
    assert result["public_evidence_url"].endswith("/evidence/KAN-2.md")
    assert result["manifest_url"].endswith("/evidence/execution.json")
    assert next(c for c in result["checks"] if c["name"] == "head_real_rdb_roundtrip")["log_url"].endswith("/kan2-logs/rdb_roundtrip.json")
    parameters = captured.graph.query.call_args.args[1]
    assert parameters["task"] == evidence.TASK_ID and parameters["item"] == evidence.ITEM_ID
    assert len(parameters["checks"]) == 20
    assert "HAS_EXECUTION" in evidence.WRITE_QUERY and "VALIDATES" in evidence.WRITE_QUERY and "HAS_CHECK" in evidence.WRITE_QUERY
    assert "[:TRACKS]" in evidence.READ_QUERY and "[:VALIDATES]" in evidence.READ_QUERY
    assert captured.graph.ro_query.call_count == 1
    assert captured.records[evidence.INDEX_PATH]["graph"] == captured.task["graph"]
    assert "MERGE (t:LocalTask" not in evidence.WRITE_QUERY and "MERGE (w:WorkItem" not in evidence.WRITE_QUERY


def test_import_is_idempotent_and_public_read_comes_from_graph(captured):
    first = evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    second = evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    assert first == second
    result = evidence.list_executions(captured.path, 6379)
    assert result["limit"] == 10 and len(result["executions"]) == 1
    assert result["executions"][0]["id"] == first["id"]
    assert "LIMIT 10" in evidence.READ_QUERY
    assert captured.graph.ro_query.call_args.args[1] == {"task": evidence.TASK_ID, "item": evidence.ITEM_ID}
    assert {c["name"] for c in result["executions"][0]["checks"]} == evidence.CHECK_NAMES


@pytest.mark.parametrize("mutation", ["running", "zero-tests", "wrong-argv", "audit-missing", "missing-check", "extra-secret", "normalized-newlines"])
def test_altered_or_invented_manifest_never_reaches_graph(captured, mutation):
    report = json.loads(captured.raw)
    if mutation == "running": report["status"] = "running"
    elif mutation == "zero-tests": next(c for c in report["checks"] if c["name"] == "head_graph_library")["test_summaries"][0]["passed"] = 0
    elif mutation == "wrong-argv": report["checks"][1]["command"] = ["cargo", "fmt"]
    elif mutation == "audit-missing": del report["post_run_audit"]
    elif mutation == "missing-check": report["checks"].pop()
    elif mutation == "extra-secret": report["SLACK_BOT_TOKEN"] = "test-secret-do-not-persist"
    raw = captured.raw.replace("\r\n", "\n") if mutation == "normalized-newlines" else json.dumps(report)
    with pytest.raises(evidence.ExecutionError) as error:
        evidence.import_execution(captured.path, 6379, evidence.TASK_ID, raw, URL)
    assert "test-secret" not in str(error.value)
    captured.connect.assert_not_called()


@pytest.mark.parametrize("url", [URL.replace("1b76598a72bc1ac878dc46389851a995caef7379", "main"), URL.replace("1b76598a72bc1ac878dc46389851a995caef7379", "f" * 40), URL + "?token=test-secret", URL.replace("github.com", "github.com.evil.test")])
def test_only_immutable_approved_document_urls_are_accepted(captured, url):
    with pytest.raises(evidence.ExecutionError):
        evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, url)
    captured.connect.assert_not_called()


def test_wrong_task_or_wrong_root_issue_cannot_reuse_execution(captured):
    with pytest.raises(evidence.ExecutionError):
        evidence.import_execution(captured.path, 6379, "task-other", captured.raw, URL)
    captured.records["tasks.json"][0]["item_id"] = "FalkorDB/FalkorDB#9999"
    with pytest.raises(evidence.ExecutionError):
        evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    captured.connect.assert_not_called()


def test_missing_snapshot_provenance_rejects_graph_write(captured):
    snapshot = captured.records["snapshots/" + captured.task["snapshot_id"] + ".json"]
    snapshot["items"][0]["source_ids"] = ["not-captured"]
    with pytest.raises(evidence.ExecutionError, match="provenance"):
        evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    captured.connect.assert_not_called()


def test_graph_noop_and_incomplete_readback_are_not_success(captured):
    captured.graph.query.side_effect = None
    captured.graph.query.return_value = SimpleNamespace(result_set=[])
    with pytest.raises(RuntimeError, match="not confirmed"):
        evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    receipt = evidence._receipt(json.loads(captured.raw), evidence.APPROVED_REPORT_SHA256, URL)
    captured.graph.ro_query.side_effect = None
    captured.graph.ro_query.return_value = SimpleNamespace(result_set=[[json.dumps(receipt), []]])
    with pytest.raises(RuntimeError, match="incomplete"):
        evidence.list_executions(captured.path, 6379)


def test_missing_task_returns_empty_without_success_fallback(captured):
    captured.records["tasks.json"] = []
    assert evidence.list_executions(captured.path, 6379)["executions"] == []
    captured.connect.assert_not_called()


def test_empty_logs_keep_hash_and_byte_count_without_broken_link(captured):
    result = evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    empty = [check for check in result["checks"] if check["log_bytes"] == 0]
    assert len(empty) == 5 and all(check["log_url"] is None for check in empty)
    assert all(check["log_sha256"] == hashlib.sha256(b"").hexdigest() for check in empty)
    assert all(check["log_url"] for check in result["checks"] if check["log_bytes"] > 0)


def test_saved_graph_binding_survives_new_import_pointer_and_task_graph_change(captured):
    evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    original = captured.task["graph"]
    captured.records["current.json"] = {"id": "b" * 24}
    captured.records["tasks.json"][0]["graph"] = "new_graph"
    result = evidence.list_executions(captured.path, 6379)
    assert len(result["executions"]) == 1
    assert captured.connect.return_value.select_graph.call_args.args == (original,)


def test_contradictory_check_payload_and_node_properties_fail_closed(captured):
    evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    changed = json.loads(captured.stored["checks"][0]["json"])
    changed["matched_expectation"] = False
    changed["exit_code"] = 999
    captured.stored["checks"][0]["json"] = json.dumps(changed)
    with pytest.raises(RuntimeError, match="contradicts"):
        evidence.list_executions(captured.path, 6379)


def test_independent_read_failure_does_not_create_stable_success_index(captured):
    captured.graph.ro_query.side_effect = RuntimeError("read failed")
    with pytest.raises(RuntimeError, match="read failed"):
        evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    assert evidence.INDEX_PATH not in captured.records


def test_missing_recorded_relationships_cannot_silently_hide_execution(captured):
    evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    captured.graph.ro_query.side_effect = None
    captured.graph.ro_query.return_value = SimpleNamespace(result_set=[])
    with pytest.raises(RuntimeError, match="relationships"):
        evidence.list_executions(captured.path, 6379)


def test_same_tampering_in_receipt_and_nodes_still_fails_approved_projection_digest(captured):
    evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    changed = json.loads(captured.stored["checks"][0]["json"])
    changed["command"] = ["cargo", "fmt"]
    captured.stored["checks"][0]["json"] = json.dumps(changed)
    captured.stored["receipt"]["checks"][0]["command"] = ["cargo", "fmt"]
    with pytest.raises(RuntimeError, match="contradicts"):
        evidence.list_executions(captured.path, 6379)


@pytest.mark.parametrize("field", ["summary", "initial_failure", "workaround", "audit"])
def test_displayed_metrics_and_audit_scope_cannot_diverge_from_approved_receipt(captured, field):
    evidence.import_execution(captured.path, 6379, evidence.TASK_ID, captured.raw, URL)
    captured.stored["receipt"][field]["forged"] = "unreviewed-metric"
    if field == "summary":
        captured.stored["receipt"][field]["graph_library"]["passed"] = 999
    with pytest.raises(RuntimeError, match="summary contradicts"):
        evidence.list_executions(captured.path, 6379)


def test_authenticated_route_imports_and_public_route_reads_without_secret_errors(captured, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server import app as api, security

    values = {}
    control = SimpleNamespace(get=lambda key: values.get(key), set=lambda key, value, **kwargs: values.__setitem__(key, value),
        incr=lambda key: 1, expire=lambda *args: None, lock=lambda *args, **kwargs: nullcontext())
    token = "operator-contract-" + "x" * 32
    monkeypatch.setenv("BATON_OPERATOR_TOKEN", token)
    monkeypatch.setattr(api, "auth_db", lambda: control)
    monkeypatch.setattr(api, "DATA", captured.path)
    application = FastAPI()
    paths = {"/api/auth/login", "/api/public/executions"}
    application.router.routes.extend(route for route in api.app.routes if getattr(route, "path", None) in paths)
    application.add_middleware(security.RequestGuard)
    client = TestClient(application, base_url="https://baton-workspace.vercel.app")
    payload = {"task_id": evidence.TASK_ID, "evidence_url": URL, "manifest_json": captured.raw}
    assert client.post("/api/public/executions", json=payload).status_code == 401
    assert client.post("/api/auth/login", json={"token": token}).status_code == 200
    assert client.post("/api/public/executions", json=payload).status_code == 201
    assert client.get("/api/public/executions").json()["executions"][0]["summary"]["checks"] == 20
    assert client.post("/api/public/executions", json={**payload, "token": "test-secret-extra"}).status_code == 422
    assert client.post("/api/public/executions", json={**payload, "task_id": "task-other"}).status_code == 422
    captured.graph.query.side_effect = ValueError("test-secret-provider-body")
    response = client.post("/api/public/executions", json=payload)
    assert response.status_code == 503 and "test-secret" not in response.text
    captured.graph.ro_query.side_effect = RuntimeError("test-secret-provider-body")
    response = client.get("/api/public/executions")
    assert response.status_code == 503 and "test-secret" not in response.text
