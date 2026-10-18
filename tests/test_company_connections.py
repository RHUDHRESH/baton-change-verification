"""Real adapter contracts with mocked providers; never sends a company message."""
import copy
import base64
import json
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from server import company_connections as connections


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.delenv("BATON_CLOUD_STATE_GRAPH", raising=False)
    monkeypatch.delenv("JIRA_CLOUD_ID", raising=False)
    # This suite tests adapter state transitions on Windows too. Production
    # persistence stays untouched (Linux directory handles or cloud records).
    records = {}
    monkeypatch.setattr(connections.workspace, "read", lambda data, path, default=None: copy.deepcopy(records.get(path, default)))
    monkeypatch.setattr(connections.workspace, "write", lambda data, path, value: records.__setitem__(path, copy.deepcopy(value)))
    for name, value in {"JIRA_SITE_URL": "https://example.atlassian.net", "JIRA_EMAIL": "private@example.com",
                        "JIRA_API_TOKEN": "test-secret-jira", "JIRA_PROJECT_KEY": "WORK",
                        "SLACK_BOT_TOKEN": "test-secret-slack", "SLACK_CHANNEL_ID": "C123456789"}.items():
        monkeypatch.setenv(name, value)
    task = {"id": "task-one", "title": "Review public evidence", "snapshot_id": "snap", "graph": "public-graph", "item_id": "FalkorDB/FalkorDB#1"}
    item = {"id": task["item_id"], "url": "https://github.com/FalkorDB/FalkorDB/issues/1", "source_ids": ["source"]}
    connections.workspace.write(tmp_path, "tasks.json", [task])
    connections.workspace.write(tmp_path, "snapshots/snap.json", {"id": "snap", "graph": "public-graph", "items": [item], "sources": [{"id": "source"}]})
    control = MagicMock()
    control.lock.return_value.__enter__.return_value = None
    monkeypatch.setattr(connections, "control_connect", lambda port: control)
    graph = MagicMock()
    monkeypatch.setattr(connections, "_link_graph", graph)
    return tmp_path, task, item, control, graph


class Provider:
    def __init__(self):
        self.calls = []
        self.payload = None

    def __call__(self, target, method, path, config, payload=None):
        self.calls.append((target, method, path, payload))
        if method == "POST":
            self.payload = copy.deepcopy(payload)
            return {"key": "WORK-12"} if target == "jira" else {"channel": config["channel"], "ts": "1780000000.000123"}
        if target == "jira":
            return {"key": "WORK-12", "fields": self.payload["fields"]}
        if path.startswith("conversations.history?"):
            return {"messages": [{"ts": "1780000000.000123", "text": self.payload["text"]}]}
        return {"permalink": "https://company.slack.com/archives/C123456789/p1780000000000123"}


@pytest.mark.parametrize("target", ["jira", "slack"])
def test_publish_verifies_then_replays_without_another_provider_write(configured, monkeypatch, target):
    data, task, item, control, graph = configured
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    result = connections.publish_task(data, 6379, task["id"], target)
    assert result["status"] == "verified" and result["graph_linked"]
    assert result["source_url"] == item["url"] and result["verified_at"]
    assert result["write_retry_allowed"] is False
    assert result["readback_retry_allowed"] is True
    assert len([c for c in provider.calls if c[1] == "POST"]) == 1
    assert any(c[1] == "GET" for c in provider.calls)
    if target == "jira":
        assert result["url"] == "https://example.atlassian.net/browse/WORK-12"
        assert item["url"] in json.dumps(provider.payload)
    else:
        history = next(c[2] for c in provider.calls if c[2].startswith("conversations.history?"))
        assert "oldest=1780000000.000123" in history and "latest=1780000000.000123" in history and "limit=1" in history
        assert provider.payload["unfurl_links"] is False and provider.payload["mrkdwn"] is False
    call_count = len(provider.calls)
    assert connections.publish_task(data, 6379, task["id"], target)["id"] == result["id"]
    assert len(provider.calls) == call_count
    control.lock.assert_called_with("publish:" + result["id"].removeprefix("artifact-"), timeout=100, blocking_timeout=1)
    assert "test-secret" not in json.dumps(result)
    graph.assert_called()


def test_ambiguous_timeout_is_persisted_and_never_reposted(configured, monkeypatch):
    data, task, _, _, _ = configured
    post = MagicMock(side_effect=TimeoutError("test-secret-slack must not be echoed"))
    monkeypatch.setattr(connections, "_request", post)
    first = connections.publish_task(data, 6379, task["id"], "slack")
    second = connections.publish_task(data, 6379, task["id"], "slack")
    assert first == second and second["status"] == "pending"
    assert second["readback_retry_allowed"] is False
    assert "test-secret" not in json.dumps(second)
    assert post.call_count == 1


@pytest.mark.parametrize("target", ["jira", "slack"])
def test_wrong_readback_is_not_success_and_repeat_only_reads(configured, monkeypatch, target):
    data, task, _, _, graph = configured
    provider = Provider()
    def bad_readback(*args, **kwargs):
        result = provider(*args, **kwargs)
        if args[1] == "GET":
            if target == "jira":
                result["fields"] = {**result["fields"], "description": connections._adf("wrong task but same source URL https://github.com/FalkorDB/FalkorDB/issues/1")}
            elif args[2].startswith("conversations.history?"):
                result["messages"][0]["text"] = "different message"
        return result
    monkeypatch.setattr(connections, "_request", bad_readback)
    assert connections.publish_task(data, 6379, task["id"], target)["status"] == "verification_pending"
    monkeypatch.setattr(connections, "_request", provider)
    assert connections.publish_task(data, 6379, task["id"], target)["status"] == "verified"
    assert len([c for c in provider.calls if c[1] == "POST"]) == 1
    graph.assert_called_once()


@pytest.mark.parametrize("change", ["title", "source", "destination"])
def test_changed_material_contract_cannot_reuse_receipt_or_repost(configured, monkeypatch, change):
    data, task, _, _, _ = configured
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    connections.publish_task(data, 6379, task["id"], "slack")
    if change == "title":
        task["title"] = "Changed title"
        connections.workspace.write(data, "tasks.json", [task])
    elif change == "source":
        snapshot = connections.workspace.read(data, "snapshots/snap.json")
        snapshot["items"][0]["url"] = "https://github.com/FalkorDB/FalkorDB/issues/2"
        connections.workspace.write(data, "snapshots/snap.json", snapshot)
    else:
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C999999999")
    with pytest.raises(connections.ConnectionError, match="changed"):
        connections.publish_task(data, 6379, task["id"], "slack")
    assert len([c for c in provider.calls if c[1] == "POST"]) == 1


def test_failure_to_persist_intent_prevents_external_write(configured, monkeypatch):
    data, task, _, _, _ = configured
    provider = MagicMock()
    monkeypatch.setattr(connections, "_request", provider)
    monkeypatch.setattr(connections.workspace, "write", MagicMock(side_effect=OSError("disk unavailable")))
    with pytest.raises(OSError):
        connections.publish_task(data, 6379, task["id"], "jira")
    provider.assert_not_called()


def test_task_changed_at_commit_boundary_is_not_dispatched(configured, monkeypatch):
    data, task, item, _, _ = configured
    changed = {**task, "title": "Changed at dispatch"}
    monkeypatch.setattr(connections, "_load_task", MagicMock(side_effect=[(task, item), (task, item), (changed, item), (changed, item), (changed, item)]))
    provider = MagicMock()
    monkeypatch.setattr(connections, "_request", provider)
    result = connections.publish_task(data, 6379, task["id"], "jira")
    assert result["status"] == "error" and "no provider write" in result["message"]
    provider.assert_not_called()


def test_graph_failure_keeps_verified_receipt_and_replay_repairs_only_graph(configured, monkeypatch):
    data, task, _, _, graph = configured
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    graph.side_effect = RuntimeError("graph unavailable")
    first = connections.publish_task(data, 6379, task["id"], "jira")
    assert first["status"] == "verified" and first["graph_linked"] is False
    graph.side_effect = None
    assert connections.publish_task(data, 6379, task["id"], "jira")["graph_linked"] is True
    assert len(provider.calls) == 2


@pytest.mark.parametrize("url", ["http://example.atlassian.net", "https://example.atlassian.net.evil.test", "https://127.0.0.1",
                                "https://user:password@example.atlassian.net", "https://example.atlassian.net:443", "https://example.atlassian.net/rest"])
def test_jira_origin_is_fixed_https_cloud_host(configured, monkeypatch, url):
    monkeypatch.setenv("JIRA_SITE_URL", url)
    result = connections.status()
    assert result["jira"]["configured"] is False
    assert url not in json.dumps(result)


def test_status_is_presence_only_and_never_reveals_credentials(configured):
    result = connections.status()
    assert all(x["configured"] and not x["verified"] for x in result.values())
    assert "test-secret" not in json.dumps(result) and "private@example.com" not in json.dumps(result)


def test_http_transport_is_bounded_no_redirect_and_sanitizes_exceptions(configured, monkeypatch):
    opener = MagicMock()
    response = opener.open.return_value.__enter__.return_value
    response.read.return_value = b'{"ok": true}'
    factory = MagicMock(return_value=opener)
    monkeypatch.setattr(connections.urllib.request, "build_opener", factory)
    connections._request("slack", "POST", "chat.postMessage", connections._config("slack"), {"text": "public"})
    assert isinstance(factory.call_args.args[0], connections.NoRedirect)
    opener.open.assert_called_once()
    assert opener.open.call_args.kwargs["timeout"] == 20
    response.read.assert_called_once_with(512_001)
    request = opener.open.call_args.args[0]
    assert request.full_url == "https://slack.com/api/chat.postMessage"
    opener.open.side_effect = OSError("test-secret-slack https://secret.example")
    with pytest.raises(connections.ConnectionError) as error:
        connections._request("slack", "POST", "chat.postMessage", connections._config("slack"), {})
    assert "test-secret" not in str(error.value) and "secret.example" not in str(error.value)
    with pytest.raises(connections.ConnectionError, match="redirect refused"):
        connections.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")


@pytest.mark.parametrize("raw", [b"x" * 512_001, b"[]", b"not-json", b'{"ok": false, "error":"test-secret-slack"}'],
                         ids=["oversized", "array", "invalid-json", "provider-error"])
def test_transport_rejects_oversized_malformed_and_error_responses(configured, monkeypatch, raw):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = raw
    monkeypatch.setattr(connections.urllib.request, "build_opener", lambda *a: opener)
    with pytest.raises(connections.ConnectionError) as error:
        connections._request("slack", "POST", "chat.postMessage", connections._config("slack"), {})
    assert "test-secret" not in str(error.value)


def test_slack_title_cannot_inject_mentions(configured, monkeypatch):
    data, task, _, _, _ = configured
    task["title"] = "Review <!channel> & <@U12345678>"
    connections.workspace.write(data, "tasks.json", [task])
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    assert connections.publish_task(data, 6379, task["id"], "slack")["status"] == "verified"
    assert "<!channel>" not in provider.payload["text"] and "&lt;!channel&gt;" in provider.payload["text"]
    assert provider.payload["link_names"] is False


def test_concurrent_clicks_serialize_to_one_provider_write(configured, monkeypatch):
    data, task, _, _, _ = configured
    mutex = threading.Lock()
    class SerializedControl:
        @contextmanager
        def lock(self, *args, **kwargs):
            with mutex:
                yield
    monkeypatch.setattr(connections, "control_connect", lambda port: SerializedControl())
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: connections.publish_task(data, 6379, task["id"], "slack"), range(2)))
    assert all(r["status"] == "verified" for r in receipts)
    assert receipts[0]["id"] == receipts[1]["id"]
    assert len([c for c in provider.calls if c[1] == "POST"]) == 1


def test_unprovenanced_or_external_source_is_not_dispatched(configured, monkeypatch):
    data, task, _, _, _ = configured
    snapshot = connections.workspace.read(data, "snapshots/snap.json")
    snapshot["items"][0]["source_ids"] = ["not-captured"]
    connections.workspace.write(data, "snapshots/snap.json", snapshot)
    provider = MagicMock()
    monkeypatch.setattr(connections, "_request", provider)
    with pytest.raises(connections.ConnectionError, match="captured public"):
        connections.publish_task(data, 6379, task["id"], "jira")
    provider.assert_not_called()


@pytest.mark.parametrize("target", ["jira", "slack"])
def test_untrusted_provider_identity_is_not_persisted_or_echoed(configured, monkeypatch, target):
    data, task, _, _, _ = configured
    provider = MagicMock(return_value={"key": "test-secret-jira", "channel": "C123456789", "ts": "test-secret-slack"})
    monkeypatch.setattr(connections, "_request", provider)
    result = connections.publish_task(data, 6379, task["id"], target)
    assert result["status"] == "pending" and "remote_id" not in result
    assert "test-secret" not in json.dumps(result)
    connections.publish_task(data, 6379, task["id"], target)
    provider.assert_called_once()


def test_acknowledgement_persistence_failure_returns_original_durable_intent(configured, monkeypatch):
    data, task, _, _, _ = configured
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    persist = connections.workspace.write
    def fail_ack(data, path, value):
        if value.get("remote_id"):
            raise OSError("state temporarily unavailable")
        persist(data, path, value)
    monkeypatch.setattr(connections.workspace, "write", fail_ack)
    result = connections.publish_task(data, 6379, task["id"], "jira")
    assert result["status"] == "pending" and "remote_id" not in result
    assert connections.publish_task(data, 6379, task["id"], "jira")["status"] == "pending"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("scoped", [False, True], ids=["site-token", "scoped-token"])
def test_jira_transport_uses_fixed_scoped_gateway_or_existing_site(configured, monkeypatch, scoped):
    cloud_id = "12345678-1234-4234-8234-123456789abc"
    if scoped:
        monkeypatch.setenv("JIRA_CLOUD_ID", cloud_id)
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = b'{"key":"WORK-12"}'
    factory = MagicMock(return_value=opener)
    monkeypatch.setattr(connections.urllib.request, "build_opener", factory)
    config = connections._config("jira")
    for method, path in [("POST", "/rest/api/3/issue"), ("GET", "/rest/api/3/issue/WORK-12?fields=summary,description,project")]:
        connections._request("jira", method, path, config, {} if method == "POST" else None)
        request = opener.open.call_args.args[0]
        origin = "https://api.atlassian.com/ex/jira/" + cloud_id if scoped else "https://example.atlassian.net"
        assert request.full_url == origin + path
        basic = "Basic " + base64.b64encode(b"private@example.com:test-secret-jira").decode()
        assert request.get_header("Authorization") == basic
        assert "test-secret" not in request.full_url and "private@example.com" not in request.full_url
    assert isinstance(factory.call_args.args[0], connections.NoRedirect)
    assert connections.status()["jira"]["destination"] == "https://example.atlassian.net/projects/WORK"


@pytest.mark.parametrize("cloud_id", ["https://evil.example", "../test-secret-jira", "12345678-1234-4234-8234-123456789abc/rest/api/3/issue",
                                    "12345678-1234-4234-8234-123456789abc?url=https://evil.example", "12345678123442348234123456789abc",
                                    "12345678-1234-4234-8234-123456789ABC", " 12345678-1234-4234-8234-123456789abc"])
def test_cloud_id_rejects_noncanonical_uuid_without_echo_or_network(configured, monkeypatch, cloud_id):
    monkeypatch.setenv("JIRA_CLOUD_ID", cloud_id)
    opener = MagicMock()
    monkeypatch.setattr(connections.urllib.request, "build_opener", opener)
    result = connections.status()["jira"]
    assert result["configured"] is False and cloud_id not in json.dumps(result)
    with pytest.raises(connections.ConnectionError, match="canonical Jira Cloud UUID"):
        connections._request("jira", "POST", "/rest/api/3/issue", {
            "site": "https://example.atlassian.net", "email": "private@example.com", "token": "test-secret-jira", "cloud_id": cloud_id}, {})
    opener.assert_not_called()


def test_scoped_publish_keeps_human_site_links_and_binds_cloud_destination(configured, monkeypatch):
    data, task, _, _, _ = configured
    monkeypatch.setenv("JIRA_CLOUD_ID", "12345678-1234-4234-8234-123456789abc")
    provider = Provider()
    monkeypatch.setattr(connections, "_request", provider)
    receipt = connections.publish_task(data, 6379, task["id"], "jira")
    assert receipt["url"] == "https://example.atlassian.net/browse/WORK-12"
    assert receipt["destination"] == "https://example.atlassian.net/WORK"
    assert "test-secret" not in json.dumps(receipt)
    monkeypatch.setenv("JIRA_CLOUD_ID", "87654321-1234-4234-8234-123456789abc")
    with pytest.raises(connections.ConnectionError, match="changed"):
        connections.publish_task(data, 6379, task["id"], "jira")
    assert len([call for call in provider.calls if call[1] == "POST"]) == 1


@pytest.mark.parametrize("path", ["https://evil.example/rest/api/3/issue", "/rest/api/3/issue/../issue", "/rest/api/3/issue?redirect=https://evil.example"])
def test_scoped_gateway_cannot_expand_approved_operations(configured, monkeypatch, path):
    monkeypatch.setenv("JIRA_CLOUD_ID", "12345678-1234-4234-8234-123456789abc")
    opener = MagicMock()
    monkeypatch.setattr(connections.urllib.request, "build_opener", opener)
    with pytest.raises(connections.ConnectionError, match="Invalid Jira API operation"):
        connections._request("jira", "POST", path, connections._config("jira"), {})
    opener.assert_not_called()


@pytest.mark.parametrize("code", ["missing_scope", "not_in_channel", "channel_not_found", "invalid_auth", "token_revoked", "rate_limited"])
def test_explicit_slack_rejection_has_actionable_sanitized_receipt_and_never_reposts(configured, monkeypatch, code):
    data, task, _, _, graph = configured
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
        "ok": False, "error": code, "needed": "test-secret-slack", "response_metadata": {"messages": ["private body"]}}).encode()
    monkeypatch.setattr(connections.urllib.request, "build_opener", lambda *a: opener)
    result = connections.publish_task(data, 6379, task["id"], "slack")
    assert result["status"] == "rejected"
    assert result["diagnostic"]["code"] == "slack_" + code
    assert result["diagnostic"]["stage"] == "publish"
    assert len(result["diagnostic"]["message"]) > 35
    assert result["write_retry_allowed"] is False and result["readback_retry_allowed"] is False
    assert "test-secret" not in json.dumps(result) and "private body" not in json.dumps(result)
    assert connections.publish_task(data, 6379, task["id"], "slack") == result
    opener.open.assert_called_once()
    graph.assert_not_called()


@pytest.mark.parametrize("error", ["internal_error", "fatal_error", "request_timeout", "unknown-test-secret-slack", {"secret": "test-secret-slack"}])
def test_unknown_or_partial_slack_failure_stays_ambiguous(configured, monkeypatch, error):
    data, task, _, _, _ = configured
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({"ok": False, "error": error}).encode()
    monkeypatch.setattr(connections.urllib.request, "build_opener", lambda *a: opener)
    result = connections.publish_task(data, 6379, task["id"], "slack")
    assert result["status"] == "pending" and result["diagnostic"]["code"] == "slack_outcome_unknown"
    assert "test-secret" not in json.dumps(result)
    connections.publish_task(data, 6379, task["id"], "slack")
    opener.open.assert_called_once()


@pytest.mark.parametrize("status,rejected", [(400, True), (401, True), (403, True), (404, True), (429, True), (500, False), (503, False)])
def test_http_provider_diagnostics_exclude_body_reason_and_url(configured, monkeypatch, status, rejected):
    data, task, _, _, _ = configured
    body = MagicMock()
    error = urllib.error.HTTPError("https://private.example/test-secret-jira", status,
        "private reason test-secret-jira", {"Retry-After": "60", "Secret-Header": "test-secret-jira"}, body)
    opener = MagicMock()
    opener.open.side_effect = error
    monkeypatch.setattr(connections.urllib.request, "build_opener", lambda *a: opener)
    result = connections.publish_task(data, 6379, task["id"], "jira")
    assert result["status"] == ("rejected" if rejected else "pending")
    assert result["diagnostic"]["http_status"] == status
    assert result["diagnostic"]["code"] == "jira_http_" + str(status)
    assert result["diagnostic"].get("retry_after_seconds") == (60 if status == 429 else None)
    assert "test-secret" not in json.dumps(result) and "private.example" not in json.dumps(result)
    body.read.assert_not_called()
    connections.publish_task(data, 6379, task["id"], "jira")
    opener.open.assert_called_once()


def test_verification_permission_failure_preserves_identity_and_later_reads_only(configured, monkeypatch):
    data, task, _, _, _ = configured
    provider = Provider()
    def fail_verification(*args, **kwargs):
        if args[1] == "GET":
            raise connections._slack_failure("missing_scope")
        return provider(*args, **kwargs)
    monkeypatch.setattr(connections, "_request", fail_verification)
    first = connections.publish_task(data, 6379, task["id"], "slack")
    assert first["status"] == "verification_pending" and first["remote_id"] == "1780000000.000123"
    assert first["diagnostic"]["stage"] == "verification" and first["diagnostic"]["code"] == "slack_missing_scope"
    assert first["readback_retry_allowed"] is True and first["write_retry_allowed"] is False
    monkeypatch.setattr(connections, "_request", provider)
    second = connections.publish_task(data, 6379, task["id"], "slack")
    assert second["status"] == "verified" and "diagnostic" not in second
    assert len([c for c in provider.calls if c[1] == "POST"]) == 1


@pytest.mark.parametrize("header", ["test-secret-jira", "-1", "99999999999", "0", "http://private.example"])
def test_retry_after_diagnostic_never_echoes_arbitrary_headers(configured, header):
    error = urllib.error.HTTPError("https://private.example", 429, "private reason", {"Retry-After": header}, None)
    diagnostic = connections._http_failure("jira", error).diagnostic
    assert "retry_after_seconds" not in diagnostic
    assert header not in json.dumps(diagnostic)
