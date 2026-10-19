"""Orchestration boundaries: provider/graph I/O are mocked, never live proof."""
from contextlib import nullcontext
import copy
import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import zipfile

import pytest

from server import release_contract as C, release_gate as gate, release_publication as publication

PLAN_ID, RUN_ID, HEAD = "a" * 32, "b" * 32, "c" * 40


class Store:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **_):
        self.values[key] = value
        return True

    def incr(self, key):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = str(value)
        return value

    def expire(self, *_):
        return True

    def lock(self, *_, **__):
        return nullcontext()


def plan():
    value = {"id": PLAN_ID, "plan_status": "ready", "change_id": C.CHANGE_ID, "title": "Real reviewed change",
             "source_commit": C.SOURCE_COMMIT, "graph": "test_release_graph", "latest_run_id": None,
             "required_checks": [C.CHECKS[key] for key in C.CHECK_IDS], "environments": list(C.ENVIRONMENTS),
             "investigation": {"status": "succeeded"}}
    value["plan_hash"] = C.plan_hash(value)
    return value


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    from server import release_graph
    store = Store()
    monkeypatch.setattr(gate, "connect", lambda _: store)
    monkeypatch.setattr(publication, "connect", lambda _: store)
    current = MagicMock(return_value=True)
    monkeypatch.setattr(release_graph, "revalidate", current)
    graph = MagicMock(return_value={"verified": True})
    monkeypatch.setattr(release_graph, "record_result", graph)
    certificate = MagicMock(side_effect=lambda data, port, plan, run: copy.deepcopy(run["graph_receipt"]))
    monkeypatch.setattr(release_graph, "verify_result", certificate, raising=False)
    p = plan()
    gate._save(0, "plan", p)
    calls = []

    def github(path, method="GET", payload=None, binary=False):
        calls.append((path, method, payload))
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": HEAD}}
        if path.endswith("/dispatches"):
            return {}
        raise AssertionError("Unexpected GitHub operation")

    monkeypatch.setattr(gate, "github", github)
    return SimpleNamespace(store=store, p=p, data=tmp_path, calls=calls, current=current, graph=graph, certificate=certificate)


def test_replayed_start_dispatches_once_and_returns_no_capability(boundary):
    first = gate.execute(boundary.data, 0, PLAN_ID, boundary.p["plan_hash"], ["jira", "slack"])
    second = gate.execute(boundary.data, 0, PLAN_ID, boundary.p["plan_hash"], ["jira", "slack"])
    assert first["id"] == second["id"]
    assert len([call for call in boundary.calls if call[1] == "POST"]) == 1
    serialized = C.encode(second)
    assert "callback_token" not in serialized and "expected_workflow_sha" not in serialized


@pytest.mark.parametrize("targets", [["jira", "jira"], ["jira"], ["jira", "email"], []])
def test_only_approved_destinations_can_reach_dispatch(boundary, targets):
    with pytest.raises(ValueError):
        gate.execute(boundary.data, 0, PLAN_ID, boundary.p["plan_hash"], targets)
    assert not boundary.calls


def test_changed_hash_and_stale_graph_cannot_dispatch(boundary):
    with pytest.raises(ValueError):
        gate.execute(boundary.data, 0, PLAN_ID, "f" * 64, ["jira", "slack"])
    boundary.current.side_effect = ValueError("Relevant graph changed")
    with pytest.raises(ValueError):
        gate.execute(boundary.data, 0, PLAN_ID, boundary.p["plan_hash"], ["jira", "slack"])
    assert not boundary.calls


def test_callback_capability_is_scoped_to_the_run(boundary):
    boundary.store.set("release:callback:" + RUN_ID, C.sha("one-run-capability"))
    gate.authenticate(0, RUN_ID, "Bearer one-run-capability")
    with pytest.raises(ValueError):
        gate.authenticate(0, "d" * 32, "Bearer one-run-capability")
    with pytest.raises(ValueError):
        gate.authenticate(0, RUN_ID, "Bearer wrong")


def test_artifact_paths_and_duplicates_are_rejected():
    for name in ("../outside", "/absolute", "evil\\file"):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("release-report.json", "{}")
            member = zipfile.ZipInfo(name)
            # Windows normalizes backslashes in ZipInfo.__init__; retain the
            # malicious archive spelling to exercise the server boundary.
            member.filename = name
            archive.writestr(member, "x")
        with pytest.raises(ValueError):
            gate._files(stream.getvalue())


def verified_run(p):
    return {"id": RUN_ID, "plan_id": PLAN_ID, "plan_hash": p["plan_hash"], "source_commit": C.SOURCE_COMMIT,
            "status": "verifying", "evidence_status": "verified", "verification_status": "failed", "decision": "blocked",
            "runner": {"run_id": "123", "run_url": "https://github.com/example/actions/runs/123", "verified": True},
            "graph_receipt": {"verified": True}, "evidence": {"url": gate.ORIGIN + "/api/public/release-runs/" + RUN_ID + "/evidence", "sha256": "e" * 64},
            "environments": [{"id": "redis-8.1.0", "redis_version": "8.1.0", "passed": 2, "failed": 2, "errors": 0,
                              "skipped": 0, "checks": [{"id": C.CHECK_IDS[2], "status": "failed"}]}]}


@pytest.fixture
def publishing(boundary, monkeypatch):
    run = verified_run(boundary.p)
    gate._save(0, "run", run)
    config = {"site": "https://example.atlassian.net", "project": "KAN", "cloud_id": "", "token": "mock-token", "email": "mock@example.test"}
    slack = {"channel": "C123456", "token": "mock-slack-token"}
    monkeypatch.setattr(publication.provider, "_config", lambda target: config if target == "jira" else slack)
    request = MagicMock(side_effect=lambda target, *args: {"key": "KAN-3"} if target == "jira" else {"channel": "C123456", "ts": "1792334785.098199"})
    monkeypatch.setattr(publication.provider, "_request", request)
    readback = MagicMock(side_effect=lambda target, *args: "https://example.atlassian.net/browse/KAN-3" if target == "jira" else
                         "https://example.slack.com/archives/C123456/p1792334785098199")
    monkeypatch.setattr(publication.provider, "_verify", readback)
    monkeypatch.setattr(publication, "_link", lambda *args: True)
    return SimpleNamespace(**boundary.__dict__, run=run, request=request, readback=readback)


def test_failed_checks_publish_blocked_evidence_without_done_transition(publishing):
    receipt = publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    assert receipt["status"] == "verified" and receipt["graph_linked"] is True
    assert "Verification outcome: blocked" in receipt["evidence_text"]
    assert "not marked Done" in receipt["evidence_text"]
    assert publishing.request.call_count == 1
    assert publishing.request.call_args.args[2] == "/rest/api/3/issue"
    publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    assert publishing.request.call_count == 1


def test_uncertain_creation_is_never_posted_twice(publishing):
    publishing.request.side_effect = TimeoutError("uncertain external effect")
    first = publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    second = publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    assert first["status"] == second["status"] == "pending"
    assert publishing.request.call_count == 1
    publishing.readback.assert_not_called()


def test_known_remote_identity_retries_only_readback(publishing):
    publishing.readback.side_effect = [ValueError("read unavailable"), "https://example.atlassian.net/browse/KAN-3"]
    first = publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    second = publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    assert first["status"] == "verification_pending" and second["status"] == "verified"
    assert publishing.request.call_count == 1 and publishing.readback.call_count == 2


def test_forged_or_changed_outcome_cannot_publish(publishing):
    forged = copy.deepcopy(publishing.run)
    forged["decision"] = "passed"
    with pytest.raises(ValueError):
        publication.publish(publishing.data, 0, publishing.p, forged, "jira")
    publishing.request.assert_not_called()


def test_publication_requires_current_graph_and_independent_certificate(publishing):
    publishing.current.side_effect = ValueError("stale graph")
    with pytest.raises(ValueError):
        publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    publishing.request.assert_not_called()


@pytest.mark.parametrize("target", ["jira", "slack"])
@pytest.mark.parametrize("state", ["missing-saved-certificate", "stale-live-certificate", "different-live-certificate"])
def test_each_publication_requires_the_exact_live_execution_certificate(publishing, target, state):
    if state == "missing-saved-certificate":
        stored = gate._read(0, "run", RUN_ID)
        stored.pop("graph_receipt")
        gate._save(0, "run", stored)
    elif state == "stale-live-certificate":
        publishing.certificate.side_effect = ValueError("Current execution measurements are missing or stale")
    else:
        publishing.certificate.side_effect = lambda *args: {"verified": True, "run_id": "another-run"}
    with pytest.raises(ValueError):
        publication.publish(publishing.data, 0, publishing.p, publishing.run, target)
    publishing.request.assert_not_called()
    publishing.readback.assert_not_called()
    assert not publishing.store.get("release:publication:" + C.sha(RUN_ID + ":" + target))
    assert gate._read(0, "run", RUN_ID)["decision"] == "blocked"


@pytest.mark.parametrize("target", ["jira", "slack"])
def test_live_execution_is_rechecked_before_each_target_post_without_relabeling_failed_tests(publishing, target):
    def request(*args, **kwargs):
        publishing.certificate.assert_called_once()
        assert publishing.certificate.call_args.args[3]["decision"] == "blocked"
        return {"key": "KAN-3"} if target == "jira" else {"channel": "C123456", "ts": "1792334785.098199"}
    publishing.request.side_effect = request
    receipt = publication.publish(publishing.data, 0, publishing.p, publishing.run, target)
    assert receipt["status"] == "verified" and receipt["graph_linked"] is True
    assert "Verification outcome: blocked" in receipt["evidence_text"]
    assert "not marked Done" in receipt["evidence_text"]
    assert gate._read(0, "run", RUN_ID)["decision"] == "blocked"


def test_second_target_cannot_post_after_execution_graph_changes(publishing):
    first = publication.publish(publishing.data, 0, publishing.p, publishing.run, "jira")
    assert first["status"] == "verified"
    publishing.certificate.side_effect = ValueError("Measurement graph changed after first publication")
    with pytest.raises(ValueError):
        publication.publish(publishing.data, 0, publishing.p, publishing.run, "slack")
    assert publishing.request.call_count == 1
    assert publishing.request.call_args.args[0] == "jira"
    assert gate._read(0, "run", RUN_ID)["decision"] == "blocked"


def test_binary_evidence_roundtrips_without_loss(boundary):
    run = verified_run(boundary.p)
    gate._save(0, "run", run)
    raw = b"PK\x03\x04\xff\x00\xfe"
    import base64
    boundary.store.set("release:file:" + RUN_ID + ":source.zip", C.encode({"sha256": C.sha(raw), "encoding": "base64", "data": base64.b64encode(raw).decode()}))
    assert gate.evidence(0, RUN_ID, "source.zip") == raw


def test_failed_actual_inference_cannot_dispatch_ready_graph_plan(boundary):
    p = read = gate.read_plan(0, PLAN_ID)
    p["investigation"] = {"status": "failed", "error": "quota"}
    gate._save(0, "plan", p)
    with pytest.raises(ValueError, match="Groq investigation"):
        gate.execute(boundary.data, 0, PLAN_ID, p["plan_hash"], ["jira", "slack"])
    assert not boundary.calls


@pytest.fixture
def completed_artifact(boundary, monkeypatch):
    from pathlib import Path
    folder = Path(__file__).with_name("fixtures") / "release_verifier"
    p = json.loads((folder / "plan.json").read_bytes())
    p.update(id=PLAN_ID, investigation={"status": "succeeded"})
    p["plan_hash"] = C.plan_hash(p)
    gate._save(0, "plan", p)
    run = verified_run(p)
    run.update(status="running", evidence_status="unconfirmed", decision="unconfirmed", expected_workflow_sha=HEAD,
               publish_targets=["jira", "slack"], last_sequence=-1)
    run["runner"] = {"verified": False, "workflow_sha": HEAD}
    run.pop("graph_receipt")
    gate._save(0, "run", run)
    directory = folder / "artifact"
    files = {path.relative_to(directory).as_posix(): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    report = json.loads(files["release-report.json"])
    report.update(run_id=RUN_ID, plan_id=PLAN_ID, plan_hash=p["plan_hash"], workflow_sha=HEAD)
    files["release-report.json"] = C.encode(report).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    raw = stream.getvalue()
    rows = [{"id": 456, "name": "baton-verify-" + RUN_ID, "expired": False,
             "workflow_run": {"id": 123}, "digest": "sha256:" + C.sha(raw)}]
    def github(path, **_):
        if path.endswith("/actions/runs/123"):
            return {"event": "workflow_dispatch", "run_attempt": 1, "head_sha": HEAD,
                    "repository": {"full_name": C.RUNNER_REPOSITORY}, "display_title": "Baton verification " + RUN_ID,
                    "path": ".github/workflows/" + C.WORKFLOW, "html_url": "https://github.com/example/actions/runs/123"}
        if "/jobs?" in path:
            return {"jobs": [{"name": "execute", "status": "completed", "conclusion": "success", "id": 789}]}
        if "/artifacts?" in path:
            return {"artifacts": rows}
        if path.endswith("/artifacts/456/zip"):
            return raw
        raise AssertionError("Unexpected GitHub GET")
    monkeypatch.setattr(gate, "github", github)
    publish = MagicMock(return_value={"status": "verified", "graph_linked": True})
    monkeypatch.setattr(publication, "publish", publish)
    return SimpleNamespace(**boundary.__dict__, rows=rows, publish=publish)


def test_independent_failure_evidence_is_not_passing_and_publication_is_separate(completed_artifact):
    b = completed_artifact
    record = gate.complete(b.data, 0, RUN_ID, {"github_run_id": "123", "artifact_name": "baton-verify-" + RUN_ID})
    assert record["status"] == "publishing" and record["evidence_status"] == "verified"
    assert record["decision"] == "blocked" and record["verification_status"] == "failed"
    assert [(e["passed"], e["failed"]) for e in record["environments"]] == [(4, 0), (2, 2)]
    b.publish.assert_not_called()
    final = gate.publish_result(b.data, 0, RUN_ID, {"github_run_id": "123"})
    assert final["status"] == "completed" and final["decision"] == "blocked"
    assert b.publish.call_count == 2
    assert gate.evidence(0, RUN_ID, "source.zip").startswith(b"PK")


def test_missing_artifact_persists_unconfirmed_error(completed_artifact):
    b = completed_artifact
    b.rows.clear()
    result = gate.complete(b.data, 0, RUN_ID, {"github_run_id": "123", "artifact_name": "baton-verify-" + RUN_ID})
    assert result["status"] == "error" and result["decision"] == "unconfirmed"
    b.publish.assert_not_called()


def test_missing_graph_certificate_blocks_publication_after_valid_artifact(completed_artifact):
    b = completed_artifact
    b.graph.return_value = {"verified": False}
    result = gate.complete(b.data, 0, RUN_ID, {"github_run_id": "123", "artifact_name": "baton-verify-" + RUN_ID})
    assert result["status"] == "error" and result["decision"] == "unconfirmed"
    with pytest.raises(ValueError):
        gate.publish_result(b.data, 0, RUN_ID, {"github_run_id": "123"})
    b.publish.assert_not_called()
