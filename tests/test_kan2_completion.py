"""One-off completion publisher tests; all provider traffic is mocked."""
import copy
from contextlib import nullcontext
import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
import urllib.error

import pytest

from deploy import complete_kan2 as publisher


URL = "https://github.com/RHUDHRESH/baton-graph-workspace/blob/" + "a" * 40 + "/docs/evidence/KAN-2.md"
SOURCE = "https://github.com/FalkorDB/FalkorDB/pull/2554"


def check_argv(name):
    prefix = ["docker", "exec", "--workdir", "/work", "baton-kan2-executor"]
    suffixes = {"debug_resize": "graph::graphblas::tensor::tests::resize_asserts_it_never_shrinks",
        "release_resize": "graph::graphblas::tensor::tests::resize_never_shrinks",
        "debug_restore": "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices",
        "release_restore": "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"}
    if any(name.endswith("_" + suffix) for suffix in suffixes):
        suffix = next(suffix for suffix in suffixes if name.endswith("_" + suffix))
        return prefix + ["cargo", "test", "--locked"] + (["--release"] if suffix.startswith("release") else []) + [
            "-p", "graph", "--lib", suffixes[suffix], "--", "--exact", "--nocapture", "--test-threads=1"]
    fixed = {"head_graph_library": ["cargo", "test", "--locked", "-p", "graph", "--lib", "--", "--test-threads=1"],
        "head_format": ["cargo", "fmt", "--all", "--check"], "head_module_build": ["cargo", "build", "--locked"],
        "baseline_apply": ["git", "apply", "/before-grow-only.patch"], "baseline_restore": ["git", "apply", "-R", "/before-grow-only.patch"],
        "cap_clamp_apply": ["git", "apply", "/cap-clamp.patch"], "cap_clamp_restore": ["git", "apply", "-R", "/cap-clamp.patch"]}
    if name in fixed:
        return prefix + fixed[name]
    directory = "/work/kan2-rdb-" + "f" * 32
    return prefix + ["redis-server", "--bind", "127.0.0.1", "--protected-mode", "yes", "--port", "6387", "--dir", directory,
        "--dbfilename", "kan2.rdb", "--appendonly", "no", "--save", "", "--loadmodule", "/work/target/debug/libfalkordb.so",
        "--enable-debug-command", "yes", "--logfile", directory + "/redis.log", "--daemonize", "yes"]


@pytest.fixture
def evidence(tmp_path):
    report = {"task": "KAN-2", "status": "passed", "executor": "Codex isolated Docker runner", "source_commit": publisher.SOURCE_COMMIT,
        "source_repository": "https://github.com/FalkorDB/FalkorDB", "image": publisher.IMAGE, "baseline_patch_sha256": "b" * 64,
        "source_verification": {"tracked_blobs": 957, "mismatches": []}, "restored_source_verification": {"tracked_blobs": 957, "mismatches": []},
        "container_patch_sha256": {"/before-grow-only.patch": "b" * 64}, "checks": []}
    for name in sorted(publisher.REQUIRED):
        baseline = name.startswith("before_grow_only_")
        summaries = [{"status": "FAILED" if baseline else "ok", "passed": 0 if baseline else 1, "failed": 1 if baseline else 0, "ignored": 0}] if name in publisher.TARGET_CHECKS else []
        if name == "head_graph_library": summaries = [{"status": "ok", "passed": 530, "failed": 0, "ignored": 17}]
        report["checks"].append({"name": name, "command": check_argv(name),
            "expectation": "regression_failure" if baseline else "success", "matched_expectation": True, "exit_code": 101 if baseline else 0,
            "log_sha256": "c" * 64, "test_summaries": summaries})
        if name == "head_real_rdb_roundtrip":
            report["checks"][-1].update(round_trips=2, nodes_preserved=2, parallel_edges_preserved=2)
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path, report


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.comments = []
        self.is_done = False
        self.text = "Baton task: fix resize\nPublic evidence: " + SOURCE + "\nWorkspace task: " + publisher.TASK_ID
        self.timeout = None
        self.bad_readback = False
        self.workspace_done = False

    def workspace_login(self):
        self.calls.append(("workspace", "POST", "/api/auth/login", {"token": "redacted-fixture"}))

    def call(self, target, method, path, payload=None):
        self.calls.append((target, method, path, copy.deepcopy(payload)))
        if target == "workspace" and method == "GET":
            return {"tasks": [{"id": publisher.TASK_ID, "status": "done" if self.workspace_done else "todo"}]}
        if target == "workspace" and method == "PATCH":
            self.workspace_done = True
            if self.timeout == "workspace":
                raise publisher.CompletionError("Workspace request outcome is unverified.")
            return {"status": "done"}
        if path == "/rest/api/3/issue/KAN-2?fields=summary,description,status,project":
            return {"key": "KAN-2", "fields": {"project": {"key": "KAN"}, "description": publisher.adf(publisher.TASK_ID + " " + SOURCE),
                "status": {"name": "Done" if self.is_done else "To Do", "statusCategory": {"key": "done" if self.is_done else "new"}}}}
        if method == "GET" and "/comment?" in path:
            return {"comments": copy.deepcopy(self.comments), "total": len(self.comments)}
        if method == "POST" and path.endswith("/comment"):
            comment = {"id": "101", "body": payload["body"]}
            if self.timeout != "comment_before":
                self.comments.append(comment)
            if self.timeout in ("comment_before", "comment_after"):
                raise publisher.CompletionError("Provider request outcome is unverified.")
            return comment
        if method == "GET" and path.endswith("/comment/101"):
            result = copy.deepcopy(self.comments[0])
            if self.bad_readback:
                result["body"] = publisher.adf("mismatched evidence")
            return result
        if method == "GET" and path.endswith("/transitions"):
            return {"transitions": [{"id": "31", "name": "Done", "to": {"statusCategory": {"key": "done"}}}]}
        if method == "POST" and path.endswith("/transitions"):
            self.is_done = True
            if self.timeout == "transition":
                raise publisher.CompletionError("Provider request outcome is unverified.")
            return {}
        if target == "slack" and method == "GET":
            return {"messages": [{"ts": publisher.MESSAGE_TS, "text": self.text, "bot_id": "B123456789"}]}
        if target == "slack" and path == "chat.update":
            self.text = payload["text"]
            if self.timeout == "slack":
                raise publisher.CompletionError("Provider request outcome is unverified.")
            return {"ok": True, "channel": publisher.CHANNEL, "ts": publisher.MESSAGE_TS}
        raise AssertionError("Unexpected mocked provider operation")


def run(evidence, provider, path=None):
    report_path, _ = evidence
    report, digest = publisher.read_report(report_path, URL)
    state = publisher.State(path or report_path.with_name("state.json"), digest, URL)
    try:
        return publisher.complete(report, digest, URL, provider, state)
    finally:
        state.close()


def writes(provider, suffix):
    return [c for c in provider.calls if c[1] == "POST" and c[2].endswith(suffix)]


def test_complete_reads_back_comment_done_and_original_slack_message(evidence):
    provider = FakeProvider()
    original = provider.text
    result = run(evidence, provider)
    assert result["status"] == "completed" and provider.is_done
    assert result["workspace_task_status"] == "done" and provider.workspace_done
    assert provider.text.startswith(original + "\n\n") and SOURCE in provider.text and publisher.TASK_ID in provider.text
    comment_text = publisher.flatten_adf(provider.comments[0]["body"])
    assert "Groq and Lambda did not execute" in comment_text
    assert "Command argv:" in comment_text and "regression_failure; exit=101; 0 passed, 1 failed" in comment_text
    assert URL in comment_text and result["report_sha256"] in comment_text
    assert len(writes(provider, "/comment")) == len(writes(provider, "/transitions")) == len(writes(provider, "chat.update")) == 1
    assert any(c[1] == "GET" and "oldest=" + publisher.MESSAGE_TS in c[2] and "limit=1" in c[2] for c in provider.calls)
    run(evidence, provider)
    assert len(writes(provider, "/comment")) == len(writes(provider, "/transitions")) == len(writes(provider, "chat.update")) == 1


@pytest.mark.parametrize("mutation", ["running", "missing-check", "zero-tests", "baseline-passed", "wrong-image", "mismatched-source", "unchecked", "duplicate"])
def test_report_gate_refuses_incomplete_or_false_execution_claims(evidence, mutation):
    path, report = evidence
    head = next(c for c in report["checks"] if c["name"] == "head_debug_resize")
    if mutation == "running": report["status"] = "running"
    elif mutation == "missing-check": report["checks"].pop()
    elif mutation == "zero-tests": head["test_summaries"][0]["passed"] = 0
    elif mutation == "baseline-passed":
        check = next(c for c in report["checks"] if c["name"].startswith("before_grow_only_"))
        check.update(exit_code=0, expectation="success")
    elif mutation == "wrong-image": report["image"] = "image:latest"
    elif mutation == "mismatched-source": report["restored_source_verification"]["mismatches"] = ["source.rs"]
    elif mutation == "unchecked": head["matched_expectation"] = False
    elif mutation == "duplicate": report["checks"].append(copy.deepcopy(head))
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(publisher.CompletionError):
        publisher.read_report(path, URL)


@pytest.mark.parametrize("url", [URL.replace("a" * 40, "main"), URL.replace("github.com", "github.com.evil.example"), URL + "?redirect=evil", "http://github.com/anything"])
def test_evidence_url_is_exact_commit_pinned_document(evidence, url):
    with pytest.raises(publisher.CompletionError):
        publisher.read_report(evidence[0], url)


def test_pending_comment_without_visible_marker_never_posts_again(evidence):
    provider = FakeProvider()
    provider.timeout = "comment_before"
    with pytest.raises(publisher.CompletionError): run(evidence, provider)
    provider.timeout = None
    with pytest.raises(publisher.CompletionError, match="No duplicate comment"):
        run(evidence, provider)
    assert len(writes(provider, "/comment")) == 1


@pytest.mark.parametrize("step", ["comment_after", "transition", "slack", "workspace"])
def test_lost_acknowledgement_recovers_by_readback_without_duplicate_write(evidence, step):
    provider = FakeProvider()
    provider.timeout = step
    with pytest.raises(publisher.CompletionError): run(evidence, provider)
    provider.timeout = None
    assert run(evidence, provider)["status"] == "completed"
    assert len(writes(provider, "/comment")) == len(writes(provider, "/transitions")) == len(writes(provider, "chat.update")) == 1


def test_comment_readback_mismatch_prevents_transition_and_slack_update(evidence):
    provider = FakeProvider()
    provider.bad_readback = True
    with pytest.raises(publisher.CompletionError, match="exact read-back"):
        run(evidence, provider)
    assert not writes(provider, "/transitions") and not writes(provider, "chat.update")


def test_wrong_original_slack_task_stops_before_any_mutation(evidence):
    provider = FakeProvider()
    provider.text = "another task " + SOURCE
    with pytest.raises(publisher.CompletionError): run(evidence, provider)
    assert not [c for c in provider.calls if c[1] == "POST"]


def test_existing_local_lock_prevents_concurrent_completion(evidence):
    report_path, _ = evidence
    report, digest = publisher.read_report(report_path, URL)
    state_path = report_path.with_name("state.json")
    state = publisher.State(state_path, digest, URL)
    try:
        with pytest.raises(publisher.CompletionError, match="locked"):
            publisher.State(state_path, digest, URL)
    finally:
        state.close()


@pytest.fixture
def transport():
    return publisher.Provider({"JIRA_SITE_URL": publisher.SITE, "JIRA_PROJECT_KEY": "KAN", "JIRA_EMAIL": "private@example.com",
        "JIRA_API_TOKEN": "test-secret-jira", "JIRA_CLOUD_ID": "12345678-1234-4234-8234-123456789abc",
        "SLACK_BOT_TOKEN": "test-secret-slack", "SLACK_CHANNEL_ID": publisher.CHANNEL, "BATON_OPERATOR_TOKEN": "test-secret-operator"})


def test_transport_rejects_other_issues_messages_and_origins(transport, monkeypatch):
    opener = MagicMock()
    monkeypatch.setattr(publisher.urllib.request, "build_opener", opener)
    for target, method, path, payload in [("jira", "POST", "/rest/api/3/issue/KAN-3/comment", {}),
        ("jira", "POST", "https://evil.example", {}), ("slack", "POST", "chat.postMessage", {}),
        ("slack", "POST", "chat.update", {"channel": publisher.CHANNEL, "ts": "another-message"})]:
        with pytest.raises(publisher.CompletionError): transport.call(target, method, path, payload)
    opener.assert_not_called()


def test_transport_uses_gateway_no_redirects_and_sanitizes_http_failure(transport, monkeypatch):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = b'{"key":"KAN-2"}'
    factory = MagicMock(return_value=opener)
    monkeypatch.setattr(publisher.urllib.request, "build_opener", factory)
    transport.call("jira", "GET", "/rest/api/3/issue/KAN-2")
    request = opener.open.call_args.args[0]
    assert request.full_url.startswith("https://api.atlassian.com/ex/jira/12345678-1234-4234-8234-123456789abc/")
    assert isinstance(factory.call_args.args[0], publisher.NoRedirect)
    assert opener.open.call_args.kwargs["timeout"] == 20
    body = MagicMock()
    opener.open.side_effect = urllib.error.HTTPError("https://private.example/test-secret-jira", 403, "test-secret-slack", {}, body)
    with pytest.raises(publisher.CompletionError) as error:
        transport.call("jira", "GET", "/rest/api/3/issue/KAN-2")
    assert "403" in str(error.value) and "test-secret" not in str(error.value) and "private.example" not in str(error.value)
    body.read.assert_not_called()


def test_workspace_completion_occurs_only_after_jira_and_slack_readbacks(evidence):
    provider = FakeProvider()
    run(evidence, provider)
    patch_index = next(i for i, c in enumerate(provider.calls) if c[0] == "workspace" and c[1] == "PATCH")
    slack_readbacks = [i for i, c in enumerate(provider.calls) if c[0] == "slack" and c[1] == "GET"]
    assert patch_index > max(slack_readbacks)
    assert provider.calls[patch_index][2:] == ("/api/public/tasks/" + publisher.TASK_ID, {"status": "done"})
    assert provider.calls[-1][:3] == ("workspace", "GET", "/api/public/workspace")


def test_workspace_transport_uses_fixed_origin_cookiejar_and_private_login(transport, monkeypatch):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = b'{"authenticated": true, "role": "operator"}'
    factory = MagicMock(return_value=opener)
    monkeypatch.setattr(publisher.urllib.request, "build_opener", factory)
    transport.workspace_login()
    request = opener.open.call_args.args[0]
    assert request.full_url == publisher.WORKSPACE + "/api/auth/login"
    assert request.get_header("Origin") == publisher.WORKSPACE
    assert json.loads(request.data) == {"token": "test-secret-operator"}
    assert "test-secret" not in request.full_url and request.get_header("Authorization") is None
    assert any(isinstance(handler, publisher.urllib.request.HTTPCookieProcessor) for handler in factory.call_args.args)
    assert any(isinstance(handler, publisher.NoRedirect) for handler in factory.call_args.args)
    transport.call("workspace", "PATCH", "/api/public/tasks/" + publisher.TASK_ID, {"status": "done"})
    assert factory.call_count == 1
    with pytest.raises(publisher.CompletionError):
        transport.call("workspace", "PATCH", "/api/public/tasks/task-other", {"status": "done"})


def test_verified_comment_disappearing_does_not_authorize_another_comment(evidence):
    provider = FakeProvider()
    run(evidence, provider)
    provider.comments.clear()
    with pytest.raises(publisher.CompletionError, match="No duplicate comment"):
        run(evidence, provider)
    assert len(writes(provider, "/comment")) == 1


def test_cli_emits_only_safe_result_metadata_and_uses_private_lambda_config(evidence, monkeypatch, capsys):
    cloud = MagicMock()
    variables = {"secret": "test-secret-do-not-print"}
    cloud.client.return_value.get_function_configuration.return_value = {"Environment": {"Variables": variables}}
    monkeypatch.setitem(sys.modules, "boto3", cloud)
    provider = FakeProvider()
    factory = MagicMock(return_value=provider)
    monkeypatch.setattr(publisher, "Provider", factory)
    assert publisher.main(["--report", str(evidence[0]), "--report-url", URL]) == 0
    cloud.client.assert_called_once_with("lambda", region_name="ap-south-1")
    cloud.client.return_value.get_function_configuration.assert_called_once_with(FunctionName="baton-workspace")
    factory.assert_called_once_with(variables)
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "completed"
    assert "test-secret" not in output and "Command argv" not in output and "Authorization" not in output


def test_cli_refuses_running_report_before_credential_access(evidence, monkeypatch, capsys):
    path, report = evidence
    report["status"] = "running"
    path.write_text(json.dumps(report), encoding="utf-8")
    cloud = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", cloud)
    assert publisher.main(["--report", str(path), "--report-url", URL]) == 1
    cloud.client.assert_not_called()
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def patched_report(evidence):
    path, report = evidence
    report["applied_patch"] = {"sha256": "d" * 64, "path": publisher.PATCH_PATH,
        "reason": "Explicit clamp avoids the observed rustc 1.99 aggregate-return failure; regression tests are unchanged"}
    report["patched_source_verification"] = {"tracked_blobs": 957, "mismatches": [publisher.PATCHED_SOURCE]}
    report["container_patch_sha256"]["/cap-clamp.patch"] = "d" * 64
    for name in ("cap_clamp_apply", "cap_clamp_restore"):
        report["checks"].append({"name": name, "command": check_argv(name), "exit_code": 0, "expectation": "success",
            "matched_expectation": True, "log_sha256": "c" * 64, "test_summaries": []})
    initial = copy.deepcopy(next(c for c in report["checks"] if c["name"] == "head_graph_library"))
    initial.update(exit_code=101, matched_expectation=False, test_summaries=[{"status": "FAILED", "passed": 529, "failed": 1, "ignored": 17}])
    report["initial_failures"] = [initial]
    final = next(c for c in report["checks"] if c["name"] == "head_graph_library")
    final["test_summaries"] = [{"status": "ok", "passed": 530, "failed": 0, "ignored": 17}]
    path.write_text(json.dumps(report), encoding="utf-8")
    return report


def test_isolated_patch_reports_initial_failure_and_measured_final_counts(evidence):
    report = patched_report(evidence)
    provider = FakeProvider()
    run(evidence, provider)
    text = publisher.flatten_adf(provider.comments[0]["body"])
    assert "529 passed, 1 failed, 17 ignored" in text
    assert "Final graph library: 530 passed, 0 failed, 17 ignored" in text
    assert "only in the isolated workspace" in text and "original unpatched" in text
    assert publisher.PATCH_PATH in text and "d" * 64 in text
    assert "initial unpatched suite failed" in provider.text or "original unpatched suite failed" in provider.text
    assert "Final graph library: 530 passed, 0 failed, 17 ignored" in provider.text
    assert "no upstream fix or merge is claimed" in provider.text


@pytest.mark.parametrize("mutation", ["wrong-path", "bad-hash", "empty-reason", "extra-source", "wrong-source", "wrong-count", "missing-history", "history-passed", "history-no-loghash", "missing-patch"])
def test_patch_provenance_fails_closed_when_incomplete_or_out_of_scope(evidence, mutation):
    report = patched_report(evidence)
    if mutation == "wrong-path": report["applied_patch"]["path"] = "another.patch"
    elif mutation == "bad-hash": report["applied_patch"]["sha256"] = "not-a-hash"
    elif mutation == "empty-reason": report["applied_patch"]["reason"] = ""
    elif mutation == "extra-source": report["patched_source_verification"]["mismatches"].append("graph/other.rs")
    elif mutation == "wrong-source": report["patched_source_verification"]["mismatches"] = ["graph/other.rs"]
    elif mutation == "wrong-count": report["patched_source_verification"]["tracked_blobs"] = 956
    elif mutation == "missing-history": del report["initial_failures"]
    elif mutation == "history-passed": report["initial_failures"][0]["exit_code"] = 0
    elif mutation == "history-no-loghash": del report["initial_failures"][0]["log_sha256"]
    elif mutation == "missing-patch": del report["applied_patch"]
    evidence[0].write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(publisher.CompletionError):
        publisher.read_report(evidence[0], URL)


def test_workspace_wire_contract_matches_real_auth_and_task_routes(transport, monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server import app as api, security, public_workspace

    token = "operator-contract-" + "x" * 32
    monkeypatch.setenv("BATON_OPERATOR_TOKEN", token)
    transport.operator_token = token
    values = {}
    control = SimpleNamespace(get=lambda key: values.get(key), set=lambda key, value, **kwargs: values.__setitem__(key, value),
        incr=lambda key: 1, expire=lambda *args: None, lock=lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(api, "auth_db", lambda: control)
    monkeypatch.setattr(api, "DATA", tmp_path)
    rows = [{"id": publisher.TASK_ID, "status": "todo"}]
    monkeypatch.setattr(public_workspace, "view", lambda data, port: {"tasks": copy.deepcopy(rows)})
    def complete_task(data, port, task_id, status):
        assert task_id == publisher.TASK_ID and status == "done"
        rows[0]["status"] = status
        return copy.deepcopy(rows[0])
    monkeypatch.setattr(public_workspace, "complete_task", complete_task)
    application = FastAPI()
    paths = {"/api/auth/login", "/api/public/tasks/{task_id}", "/api/public/workspace"}
    application.router.routes.extend(route for route in api.app.routes if getattr(route, "path", None) in paths)
    application.add_middleware(security.RequestGuard)
    client = TestClient(application, base_url=publisher.WORKSPACE)
    class AppOpener:
        def open(self, request, timeout):
            response = client.request(request.method, request.full_url, content=request.data, headers=dict(request.header_items()))
            assert response.status_code == 200
            return io.BytesIO(response.content)
    transport.workspace_opener = AppOpener()
    assert transport.workspace_login()["authenticated"] is True
    assert "baton_operator" in client.cookies
    transport.call("workspace", "PATCH", "/api/public/tasks/" + publisher.TASK_ID, {"status": "done"})
    assert transport.call("workspace", "GET", "/api/public/workspace")["tasks"] == [{"id": publisher.TASK_ID, "status": "done"}]


@pytest.mark.parametrize("mutation", [None, "wrong-check", "wrong-binary", "wrong-option"])
def test_empty_redis_save_argument_is_allowed_only_for_real_rdb_check(evidence, mutation):
    path, report = evidence
    optional = next(check for check in report["checks"] if check["name"] == "head_real_rdb_roundtrip")
    if mutation == "wrong-check": optional["name"] = "other_check"
    elif mutation == "wrong-binary": optional["command"][5] = "another-server"
    elif mutation == "wrong-option": optional["command"][optional["command"].index("--save")] = "--other-option"
    path.write_text(json.dumps(report), encoding="utf-8")
    if mutation:
        with pytest.raises(publisher.CompletionError):
            publisher.read_report(path, URL)
    else:
        validated, _ = publisher.read_report(path, URL)
        command = next(check for check in validated["checks"] if check["name"] == "head_real_rdb_roundtrip")["command"]
        assert command[command.index("--save") + 1] == ""


@pytest.mark.parametrize("mutation", ["fmt-for-test", "missing-release", "wrong-test-id", "missing-exact", "fake-suite-count",
    "missing-module", "missing-rdb", "fake-roundtrips", "fake-nodes", "fake-edges", "nonloopback", "wrong-module", "baseline-hash", "baseline-not-restored"])
def test_named_checks_are_bound_to_actual_commands_and_required_runtime_evidence(evidence, mutation):
    path, report = evidence
    target = next(check for check in report["checks"] if check["name"] == "head_release_resize")
    rdb = next(check for check in report["checks"] if check["name"] == "head_real_rdb_roundtrip")
    if mutation == "fmt-for-test": target["command"] = check_argv("head_format")
    elif mutation == "missing-release": target["command"].remove("--release")
    elif mutation == "wrong-test-id": target["command"][target["command"].index("graph::graphblas::tensor::tests::resize_never_shrinks")] = "graph::unrelated_test"
    elif mutation == "missing-exact": target["command"].remove("--exact")
    elif mutation == "fake-suite-count": next(c for c in report["checks"] if c["name"] == "head_graph_library")["test_summaries"][0]["passed"] = 1
    elif mutation == "missing-module": report["checks"] = [c for c in report["checks"] if c["name"] != "head_module_build"]
    elif mutation == "missing-rdb": report["checks"] = [c for c in report["checks"] if c["name"] != "head_real_rdb_roundtrip"]
    elif mutation == "fake-roundtrips": rdb["round_trips"] = 0
    elif mutation == "fake-nodes": rdb["nodes_preserved"] = 1
    elif mutation == "fake-edges": rdb["parallel_edges_preserved"] = "2"
    elif mutation == "nonloopback": rdb["command"][rdb["command"].index("127.0.0.1")] = "0.0.0.0"
    elif mutation == "wrong-module": rdb["command"][rdb["command"].index("/work/target/debug/libfalkordb.so")] = "/work/stale-module.so"
    elif mutation == "baseline-hash": report["container_patch_sha256"]["/before-grow-only.patch"] = "0" * 64
    elif mutation == "baseline-not-restored": next(c for c in report["checks"] if c["name"] == "baseline_restore")["command"].remove("-R")
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(publisher.CompletionError):
        publisher.read_report(path, URL)


@pytest.mark.parametrize("mutation", ["container-hash", "wrong-apply-argv", "missing-restore", "history-fmt", "history-counts"])
def test_patch_and_initial_failure_commands_are_bound_to_their_measured_artifacts(evidence, mutation):
    report = patched_report(evidence)
    if mutation == "container-hash": report["container_patch_sha256"]["/cap-clamp.patch"] = "0" * 64
    elif mutation == "wrong-apply-argv": next(c for c in report["checks"] if c["name"] == "cap_clamp_apply")["command"] = check_argv("head_format")
    elif mutation == "missing-restore": report["checks"] = [c for c in report["checks"] if c["name"] != "cap_clamp_restore"]
    elif mutation == "history-fmt": report["initial_failures"][0]["command"] = check_argv("head_format")
    elif mutation == "history-counts": report["initial_failures"][0]["test_summaries"][0]["passed"] = 530
    evidence[0].write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(publisher.CompletionError):
        publisher.read_report(evidence[0], URL)
