"""Provider lifecycle tests for app-owned autonomous workflow finalization."""
import copy
from contextlib import nullcontext
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
from unittest.mock import MagicMock

import pytest

from server import autonomous_publication as publication
REAL_BINDING = publication._binding


@pytest.fixture
def setup(monkeypatch, tmp_path):
    identity = "a" * 32
    run = {"id": identity, "task_id": publication.TASK, "status": "succeeded",
        "runner": {"provider": "GitHub Actions", "run_id": 123456, "run_url": "https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/123456",
            "verified": True, "conclusion": "success", "source_commit": "b" * 40, "image_digest": "sha256:" + "c" * 64},
        "evidence": {"url": "https://baton-workspace.vercel.app/api/public/workflows/" + identity + "/evidence", "sha256": "d" * 64},
        "checks": [{"name": "grow_only_debug", "status": "passed", "exit_code": 0, "test_count": 1},
                   {"name": "graph_library", "status": "passed", "exit_code": 0, "test_count": 530}],
        "verification": {"read_back_verified": True}}
    records = {"autonomous:run:" + identity: json.dumps(run)}
    def store(key, value, **kwargs):
        records[key] = value
        return True
    control = SimpleNamespace(get=lambda key: records.get(key), set=MagicMock(side_effect=store), lock=MagicMock(return_value=nullcontext()))
    configs = {"jira": {"site": publication.SITE, "project": "KAN", "email": "operator@example.test", "token": "private-jira-token", "cloud_id": ""},
        "slack": {"channel": publication.CHANNEL, "token": "private-slack-token"}}
    monkeypatch.setattr(publication, "control_connect", lambda port: control)
    monkeypatch.setattr(publication, "_binding", lambda data: copy.deepcopy(configs))
    monkeypatch.setattr(publication.connections, "_config", lambda target: copy.deepcopy(configs[target]))
    remote = {"comments": [], "done": False, "slack": "Original task " + publication.TASK + "\nPublic evidence: " + publication.SOURCE}
    calls = []
    failures = {}
    def provider(target, method, path, config, payload=None):
        calls.append((target, method, path, payload))
        if (target, method, path) in failures:
            action = failures[(target, method, path)]
            if callable(action): return action(payload)
            raise action
        if target == "slack":
            if method == "GET":
                return {"ok": True, "messages": [{"ts": publication.TS, "bot_id": "B12345", "text": remote["slack"]}]}
            remote["slack"] = payload["text"]
            return {"ok": True, "channel": publication.CHANNEL, "ts": publication.TS}
        if "?fields=" in path:
            return {"key": "KAN-2", "fields": {"project": {"key": "KAN"}, "description": publication.connections._adf(publication.TASK + " " + publication.SOURCE),
                "status": {"statusCategory": {"key": "done" if remote["done"] else "new"}}}}
        if "/comment?" in path:
            return {"comments": remote["comments"], "total": len(remote["comments"])}
        if path.endswith("/comment"):
            comment = {"id": str(10000 + len(remote["comments"])), "body": payload["body"]}
            remote["comments"].append(comment)
            return comment
        if "/comment/" in path:
            return next(comment for comment in remote["comments"] if comment["id"] == path.rsplit("/", 1)[1])
        if method == "GET":
            return {"transitions": [{"id": "31", "to": {"statusCategory": {"key": "done"}}}]}
        remote["done"] = True
        return {}
    monkeypatch.setattr(publication, "_call", provider)
    def save_run(): records["autonomous:run:" + identity] = json.dumps(run)
    return SimpleNamespace(id=identity, run=run, records=records, control=control, configs=configs, remote=remote, calls=calls,
        failures=failures, save_run=save_run, data=tmp_path, provider=provider)


def finalize(setup):
    return publication.finalize_run(setup.data, 6379, setup.id)


def writes(setup, target=None):
    return [call for call in setup.calls if call[1] == "POST" and (target is None or call[0] == target)]


def test_success_is_application_owned_exact_artifact_updates_with_independent_readback(setup):
    original = setup.remote["slack"]
    result = finalize(setup)
    assert result["status"] == "verified" and result["outcome"] == "succeeded"
    assert setup.remote["done"] is True and len(setup.remote["comments"]) == 1
    assert setup.remote["slack"].startswith(original + "\n\n")
    assert "Executor: GitHub Actions" in setup.remote["slack"] and "No upstream fix or merge" in setup.remote["slack"]
    assert len(writes(setup)) == 3
    assert any(call[1] == "GET" and "/comment/10000" in call[2] for call in setup.calls)
    assert len([call for call in setup.calls if call[0] == "slack" and call[1] == "GET"]) == 2
    assert "private-jira-token" not in json.dumps(result) and "private-slack-token" not in json.dumps(setup.records)


def test_replay_verifies_without_repeating_any_mutation(setup):
    first = finalize(setup)
    count = len(writes(setup))
    second = finalize(setup)
    assert first["status"] == second["status"] == "verified"
    assert len(writes(setup)) == count and len(setup.remote["comments"]) == 1


def test_failed_actual_run_comments_and_updates_slack_without_done_transition(setup):
    setup.run["status"] = "failed"
    setup.run["runner"]["conclusion"] = "failure"
    setup.run["checks"][0].update(status="failed", exit_code=101)
    setup.save_run()
    result = finalize(setup)
    assert result["status"] == "verified" and result["outcome"] == "failed"
    assert setup.remote["done"] is False
    assert not any(call[1] == "POST" and call[2].endswith("transitions") for call in setup.calls)
    assert "failed; review the evidence" in setup.remote["slack"]


def test_verified_job_failure_after_passing_checks_is_reported_without_done(setup):
    setup.run["status"] = "failed"
    setup.run["runner"]["conclusion"] = "failure"
    setup.save_run()
    result = finalize(setup)
    assert result["status"] == "verified" and result["outcome"] == "failed" and setup.remote["done"] is False
    text = publication._flatten(setup.remote["comments"][0]["body"])
    assert "verified runner conclusion: failure" in text and "grow_only_debug: passed" in text


@pytest.mark.parametrize("mutation", ["not-verified", "zero-tests", "mixed-failure", "wrong-task", "foreign-url", "bad-source", "bad-image", "artifact-unverified"])
def test_unverified_or_inconsistent_success_never_reaches_providers(setup, mutation):
    if mutation == "not-verified": setup.run["runner"]["verified"] = False
    elif mutation == "zero-tests":
        for check in setup.run["checks"]: check["test_count"] = 0
    elif mutation == "mixed-failure": setup.run["checks"][0].update(status="failed", exit_code=101)
    elif mutation == "wrong-task": setup.run["task_id"] = "another-task"
    elif mutation == "foreign-url": setup.run["evidence"]["url"] = "https://evil.test/report"
    elif mutation == "bad-source": setup.run["runner"]["source_commit"] = "main"
    elif mutation == "bad-image": setup.run["runner"]["image_digest"] = "latest"
    else: setup.run["verification"]["read_back_verified"] = False
    setup.save_run()
    with pytest.raises(publication.PublicationError): finalize(setup)
    assert setup.calls == []


def test_ambiguous_comment_that_was_created_reconciles_without_duplicate(setup):
    path = ("jira", "POST", "/rest/api/3/issue/KAN-2/comment")
    def ambiguous(payload):
        setup.remote["comments"].append({"id": "10000", "body": payload["body"]})
        raise TimeoutError("private-provider-body")
    setup.failures[path] = ambiguous
    assert finalize(setup)["status"] == "pending"
    del setup.failures[path]
    assert finalize(setup)["status"] == "verified"
    assert len([call for call in writes(setup) if call[2].endswith("/comment")]) == 1


def test_ambiguous_comment_not_observed_is_never_resent(setup):
    setup.failures[("jira", "POST", "/rest/api/3/issue/KAN-2/comment")] = TimeoutError("private-provider-body")
    assert finalize(setup)["status"] == "pending"
    assert finalize(setup)["status"] == "pending"
    assert len([call for call in writes(setup) if call[2].endswith("/comment")]) == 1
    assert "private-provider-body" not in json.dumps(finalize(setup))


def test_ambiguous_slack_update_is_reconciled_by_exact_readback(setup):
    def ambiguous(payload):
        setup.remote["slack"] = payload["text"]
        raise TimeoutError("uncertain")
    setup.failures[("slack", "POST", "chat.update")] = ambiguous
    assert finalize(setup)["status"] == "pending"
    del setup.failures[("slack", "POST", "chat.update")]
    assert finalize(setup)["status"] == "verified"
    assert len(writes(setup, "slack")) == 1


def test_done_transition_uncertainty_cannot_trigger_second_transition(setup):
    setup.failures[("jira", "POST", "/rest/api/3/issue/KAN-2/transitions")] = TimeoutError("uncertain")
    assert finalize(setup)["status"] == "pending"
    assert finalize(setup)["status"] == "pending"
    assert len([call for call in writes(setup) if call[2].endswith("transitions")]) == 1


def test_persistence_failure_stops_before_any_external_write(setup):
    setup.control.set.side_effect = RuntimeError("state unavailable")
    with pytest.raises(RuntimeError): finalize(setup)
    assert writes(setup) == []


def test_changed_evidence_after_intent_cannot_change_existing_publication(setup):
    assert finalize(setup)["status"] == "verified"
    count = len(writes(setup))
    setup.run["evidence"]["sha256"] = "e" * 64
    setup.save_run()
    with pytest.raises(publication.PublicationError, match="changed"): finalize(setup)
    assert len(writes(setup)) == count


def test_later_run_replaces_owned_summary_without_overwriting_original_context(setup):
    original = setup.remote["slack"]
    assert finalize(setup)["status"] == "verified"
    previous = setup.id
    setup.id = "f" * 32
    setup.run["id"] = setup.id
    setup.run["evidence"]["url"] = setup.run["evidence"]["url"].replace(previous, setup.id)
    setup.records["autonomous:run:" + setup.id] = json.dumps(setup.run)
    assert finalize(setup)["status"] == "verified"
    assert setup.remote["slack"].startswith(original + "\n\n")
    assert setup.remote["slack"].count("[Baton autonomous run ") == 1 and previous not in setup.remote["slack"]


def test_external_slack_change_is_not_overwritten(setup):
    assert finalize(setup)["status"] == "verified"
    setup.remote["slack"] += "\nSomeone changed this message"
    count = len(writes(setup, "slack"))
    assert finalize(setup)["status"] == "pending"
    assert len(writes(setup, "slack")) == count


def test_fixed_transport_rejects_arbitrary_urls_before_network(monkeypatch):
    opener = MagicMock()
    monkeypatch.setattr(publication.urllib.request, "build_opener", opener)
    for path in ("https://evil.test", "/rest/api/3/issue/KAN-3/comment", "/rest/api/3/issue/KAN-2/comment?redirect=evil"):
        with pytest.raises(publication.PublicationError): publication._call("jira", "POST", path, {})
    opener.assert_not_called()


def test_transport_errors_are_sanitized_and_never_retry(monkeypatch):
    opener = MagicMock()
    opener.open.side_effect = urllib.error.HTTPError("https://private-url", 403, "private-body", {}, io.BytesIO(b"private-body"))
    monkeypatch.setattr(publication.urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(publication.connections.ProviderFailure) as error:
        publication._call("slack", "POST", "chat.update", {"token": "private-token"}, {"channel": publication.CHANNEL, "ts": publication.TS})
    assert error.value.rejected is True and "private" not in str(error.value)
    opener.open.assert_called_once()


def test_known_write_refusal_keeps_actionable_diagnostic_across_replays(setup):
    setup.failures[("jira", "POST", "/rest/api/3/issue/KAN-2/comment")] = publication.connections.ProviderFailure(
        "jira_http_403", "Provider denied access. Check token scopes.", rejected=True, http_status=403)
    first = finalize(setup)
    assert first["providers"]["jira"]["status"] == "rejected"
    second = finalize(setup)
    assert second["providers"]["jira"]["diagnostic"] == first["providers"]["jira"]["diagnostic"]
    assert second["providers"]["jira"]["status"] == "rejected"
    assert len([call for call in writes(setup) if call[2].endswith("comment")]) == 1


def test_mismatched_comment_readback_never_marks_done(setup):
    setup.failures[("jira", "GET", "/rest/api/3/issue/KAN-2/comment/10000")] = lambda payload: {
        "id": "10000", "body": publication.connections._adf("different evidence")}
    result = finalize(setup)
    assert result["providers"]["jira"]["status"] == "pending" and setup.remote["done"] is False


@pytest.mark.parametrize("mutation", [None, "jira-id", "slack-id", "unverified", "missing", "source", "config"])
def test_real_binding_requires_exact_previously_verified_connected_artifacts(setup, monkeypatch, mutation):
    task, item = {"item_id": publication.ITEM}, {"url": publication.SOURCE}
    records = {}
    for target, remote in (("jira", publication.ISSUE), ("slack", publication.TS)):
        key = "connections/" + publication.hashlib.sha256((publication.TASK + ":" + target).encode()).hexdigest() + ".json"
        records[key] = {"target": target, "task_id": publication.TASK, "status": "verified", "remote_id": remote}
        if mutation == target + "-id": records[key]["remote_id"] = "other-artifact"
        if mutation == "unverified": records[key]["status"] = "pending"
    if mutation == "missing": records.clear()
    elif mutation == "source": item["url"] = "https://github.com/FalkorDB/FalkorDB/issues/9999"
    elif mutation == "config": setup.configs["slack"]["channel"] = "C1111111111"
    monkeypatch.setattr(publication.connections, "_load_task", lambda *args: (task, item))
    monkeypatch.setattr(publication.workspace, "read", lambda data, path: records.get(path))
    if mutation:
        with pytest.raises(publication.PublicationError): REAL_BINDING(setup.data)
    else:
        assert REAL_BINDING(setup.data) == setup.configs
