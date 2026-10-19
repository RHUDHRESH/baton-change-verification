"""Real disposable execution artifacts and adversarial mutations; no network."""
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from server import release_contract as C
from server import release_verifier as V
from scripts import release_gate_worker as W

FIXTURE = Path(__file__).with_name("fixtures") / "release_verifier"


@pytest.fixture
def evidence():
    plan = json.loads((FIXTURE / "plan.json").read_bytes())
    artifact = FIXTURE / "artifact"
    files = {path.relative_to(artifact).as_posix(): path.read_bytes() for path in artifact.rglob("*") if path.is_file()}
    run = {"id": "run-local-smoke", "plan_id": plan["id"], "plan_hash": plan["plan_hash"],
           "source_commit": C.SOURCE_COMMIT, "runner": {"workflow_sha": "a" * 40}}
    return plan, run, files


def mutate_report(files, change):
    report = json.loads(files["release-report.json"])
    change(report)
    files["release-report.json"] = C.encode(report).encode()


def replace_raw(files, path, raw, hash_field):
    files[path] = raw
    def change(report):
        row = next(row for row in report["environments"] if path.startswith(row["id"] + "/"))
        (row["checks"][0] if hash_field in {"log_sha256", "junit_sha256"} else row)[hash_field] = C.sha(raw)
    mutate_report(files, change)


def test_actual_two_environment_run_is_verified_failure_not_infrastructure_error(evidence):
    plan, run, files = evidence
    result = V.verify_artifact(plan, run, files)
    assert result["verified"] is True
    assert result["evidence_verified"] is True
    assert result["status"] == "blocked"
    assert (result["total"], result["passed"], result["failed"], result["errors"], result["skipped"]) == (8, 6, 2, 0, 0)
    assert result["source_unchanged"] is True
    assert [(row["id"], row["passed"], row["failed"]) for row in result["environments"]] == [
        ("redis-8.0.0", 4, 0), ("redis-8.1.0", 2, 2)]
    assert len(result["results"]) == 8
    failures = [row for row in result["results"] if row["status"] == "failed"]
    assert all("himport_registry" in row["failure_excerpt"] and "async" in row["check_id"] for row in failures)


@pytest.mark.parametrize("path", ["release-report.json", "source.zip", "redis-8.0.0/junit.xml", "redis-8.1.0/pytest.log",
                                 "redis-8.0.0/requirements.lock", "redis-8.1.0/setup.log"])
def test_missing_required_evidence_is_rejected(evidence, path):
    plan, run, files = evidence
    del files[path]
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


@pytest.mark.parametrize("field,value", [("run_id", "different"), ("plan_id", "different"), ("plan_hash", "b" * 64),
                                         ("workflow_sha", "b" * 40), ("source_commit", "b" * 40),
                                         ("source_unchanged", False), ("source_unchanged", 1), ("schema_version", True)])
def test_forged_report_binding_is_rejected(evidence, field, value):
    plan, run, files = evidence
    mutate_report(files, lambda report: report.update({field: value}))
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


@pytest.mark.parametrize("field,value", [("redis_version", "7.1.0"), ("python_version", "3.14.0"),
                                         ("python_image", "python:latest"), ("falkordb_image", "falkordb/falkordb:latest"),
                                         ("dependencies", {}), ("source_hashes_after", {})])
def test_environment_substitution_is_rejected(evidence, field, value):
    plan, run, files = evidence
    mutate_report(files, lambda report: report["environments"][1].update({field: value}))
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


def test_source_blob_and_dependency_lock_substitution_are_rejected(evidence):
    plan, run, files = evidence
    for path in ("source.zip", "redis-8.0.0/requirements.lock"):
        changed = dict(files)
        changed[path] += b"\n"
        with pytest.raises(ValueError):
            V.verify_artifact(plan, run, changed)


def test_omitting_or_duplicating_a_required_environment_is_rejected(evidence):
    plan, run, files = evidence
    for environments in ([], [json.loads(files["release-report.json"])["environments"][0]] * 2):
        changed = dict(files)
        mutate_report(changed, lambda report: report.update(environments=environments))
        with pytest.raises(ValueError):
            V.verify_artifact(plan, run, changed)


@pytest.mark.parametrize("kind", ["skip", "different-test", "duplicate-test", "zero-tests", "contradictory-counts"])
def test_junit_tampering_is_rejected_even_with_recomputed_hash(evidence, kind):
    plan, run, files = evidence
    path = "redis-8.0.0/junit.xml"
    root = ET.fromstring(files[path])
    suite = root[0]
    if kind == "skip":
        ET.SubElement(suite[0], "skipped")
        suite.set("skipped", "1")
    elif kind == "different-test":
        suite[0].set("name", "test_unapproved")
    elif kind == "duplicate-test":
        suite[1].set("name", suite[0].get("name"))
    elif kind == "zero-tests":
        for case in list(suite):
            suite.remove(case)
        suite.set("tests", "0")
    else:
        suite.set("failures", "1")
    replace_raw(files, path, ET.tostring(root), "junit_sha256")
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


def test_cannot_turn_actual_async_failures_into_a_passing_claim(evidence):
    plan, run, files = evidence
    def forge(report):
        check = report["environments"][1]["checks"][0]
        check.update(exit_code=0, passed=4, failed=0, errors=0)
    mutate_report(files, forge)
    with pytest.raises(ValueError, match="contradict"):
        V.verify_artifact(plan, run, files)


@pytest.mark.parametrize("old,new", [(b"collected 4 items", b"collected 0 items"),
                                   (b"PASSED", b"FAILED"), (b"BATON_EXIT_CODE 0", b"BATON_EXIT_CODE 1")])
def test_forged_raw_log_rejected_after_rehash(evidence, old, new):
    plan, run, files = evidence
    path = "redis-8.0.0/pytest.log"
    replace_raw(files, path, files[path].replace(old, new, 1), "log_sha256")
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


def test_command_injection_and_forged_setup_measurement_are_rejected(evidence):
    plan, run, files = evidence
    changed = dict(files)
    mutate_report(changed, lambda report: report["environments"][0]["checks"][0]["argv"].append("--collect-only"))
    with pytest.raises(ValueError, match="command"):
        V.verify_artifact(plan, run, changed)
    path = "redis-8.0.0/setup.log"
    replace_raw(files, path, files[path].replace(b'"redis":"8.0.0"', b'"redis":"8.1.0"'), "setup_log_sha256")
    with pytest.raises(ValueError, match="measurements"):
        V.verify_artifact(plan, run, files)


def test_modified_or_arbitrary_plan_cannot_execute(evidence):
    plan, run, files = evidence
    changed = copy.deepcopy(plan)
    changed["required_checks"][0]["id"] = "tests/test_graph.py::test_unapproved"
    changed["plan_hash"] = C.plan_hash(changed)
    with pytest.raises(ValueError, match="registry"):
        V.verify_artifact(changed, run, files)
    changed = copy.deepcopy(plan)
    changed["plan_hash"] = "b" * 64
    with pytest.raises(ValueError, match="hash"):
        V.verify_artifact(changed, run, files)


@pytest.mark.parametrize("payload", [b"{}", b"[]", b"{", b'{"schema_version":1,"schema_version":1}',
                                     b'{"schema_version":1,"environments":[null]}'])
def test_malformed_reports_have_stable_rejection(evidence, payload):
    plan, run, files = evidence
    files["release-report.json"] = payload
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


def test_unexpected_artifact_file_is_rejected(evidence):
    plan, run, files = evidence
    files["credentials.txt"] = b"unapproved"
    with pytest.raises(ValueError):
        V.verify_artifact(plan, run, files)


@pytest.mark.parametrize("mutation", [lambda info: info.update(Mounts=[{"Source": "/var/run/docker.sock"}]),
                                     lambda info: info["HostConfig"].update(Privileged=True),
                                     lambda info: info["HostConfig"].update(PortBindings={"6379/tcp": [{"HostPort": "6379"}]}),
                                     lambda info: info["Config"].update(Env=["BATON_CALLBACK_TOKEN=capability"])])
def test_host_mount_exposure_or_container_credential_blocks_execution(monkeypatch, mutation):
    info = {"Mounts": [], "HostConfig": {"Privileged": False, "PortBindings": {}, "NetworkMode": "bridge"},
            "Config": {"Env": ["PATH=/usr/bin"], "Image": C.PYTHON_IMAGE}}
    mutation(info)
    monkeypatch.setattr(W, "docker", lambda *args: SimpleNamespace(stdout=json.dumps([info]).encode()))
    with pytest.raises(ValueError):
        W.inspect_isolation("disposable")


def test_finalizer_publishes_only_after_independent_evidence_and_graph_certificate(monkeypatch):
    calls = []
    monkeypatch.setenv("BATON_CALLBACK_TOKEN", "scoped-capability")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    def callback(run_id, token, suffix, payload):
        calls.append((run_id, token, suffix, payload))
        return {"evidence_status": "verified", "graph_receipt": {"verified": True}, "status": "publishing"}
    monkeypatch.setattr(W, "callback", callback)
    assert W.main(["--run-id", "run-local-smoke", "--finalize"]) == 0
    assert [call[2] for call in calls] == ["complete", "publish"]
    assert calls[0][3] == {"github_run_id": "123", "artifact_name": "baton-verify-run-local-smoke"}
    assert calls[1][3] == {"github_run_id": "123"}


@pytest.mark.parametrize("response", [{}, {"evidence_status": "verified"},
    {"evidence_status": "unconfirmed", "graph_receipt": {"verified": True}, "status": "publishing"},
    {"evidence_status": "verified", "graph_receipt": {"verified": False}, "status": "publishing"},
    {"evidence_status": "verified", "graph_receipt": {"verified": True}, "status": "error"}])
def test_finalizer_cannot_publish_unconfirmed_completion(monkeypatch, response):
    calls = []
    def callback(run_id, token, suffix, payload):
        calls.append(suffix)
        return response
    monkeypatch.setattr(W, "callback", callback)
    with pytest.raises(ValueError, match="publication blocked"):
        W.main(["--run-id", "run-local-smoke", "--finalize"])
    assert calls == ["complete"]


def test_worker_still_runs_second_required_environment_after_first_infrastructure_failure(monkeypatch, tmp_path, evidence):
    plan, run, files = evidence
    called, events = [], []
    report = json.loads(files["release-report.json"])
    monkeypatch.setattr(W.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(files["source.zip"]))
    monkeypatch.setattr(W, "docker", lambda *args, **kwargs: None)
    def environment(run_id, approved, *args):
        called.append(approved["id"])
        if len(called) == 1:
            raise RuntimeError("disposable setup timed out")
        return report["environments"][1]
    monkeypatch.setattr(W, "execute_environment", environment)
    with pytest.raises(RuntimeError, match="complete evidence"):
        W.run_plan(plan, run["id"], "a" * 40, tmp_path / "artifact", lambda *args: events.append(args))
    assert called == [row["id"] for row in C.ENVIRONMENTS]
    partial = json.loads((tmp_path / "artifact" / "release-report.json").read_bytes())
    assert partial["source_unchanged"] is False
    assert partial["infrastructure_errors"] == [{"environment_id": "redis-8.0.0", "error": "RuntimeError"}]
    assert partial["environments"][0]["checks"][0]["failed"] == 2
    assert [event[0] for event in events] == ["environment-started", "failed", "environment-started", "environment-completed"]


def test_advisory_callback_outage_does_not_turn_observed_failures_into_an_execution_error(monkeypatch, capsys, evidence):
    plan, run, files = evidence
    monkeypatch.setenv("BATON_CALLBACK_TOKEN", "scoped-capability")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(W, "public_get", lambda path: plan)
    calls = []
    def unavailable(*args):
        calls.append(args[2])
        raise RuntimeError("callback unavailable")
    monkeypatch.setattr(W, "callback", unavailable)
    def execute(plan, run_id, sha, out, emit):
        emit("environment-started", "Executing approved checks", "redis-8.0.0", "running")
        emit("environment-completed", "Evidence captured", "redis-8.1.0", "blocked")
        return json.loads(files["release-report.json"])
    monkeypatch.setattr(W, "run_plan", execute)
    assert W.main(["--run-id", run["id"], "--plan-id", plan["id"], "--plan-hash", plan["plan_hash"]]) == 0
    assert calls == ["events"] * 3
    assert "scoped-capability" not in capsys.readouterr().out
