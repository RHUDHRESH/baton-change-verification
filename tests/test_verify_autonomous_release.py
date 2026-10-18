"""Read-only release proof rejects divergence between app, runner and raw bytes."""
import base64
import copy
import difflib
import io
import json
from types import SimpleNamespace
import zipfile
from unittest.mock import MagicMock

import pytest

from scripts import verify_autonomous_release as proof
from scripts import autonomous_worker as worker


@pytest.fixture
def fixture():
    identity, run_id, head = "a" * 32, "123", "b" * 40
    source = "fn cap() { 42 }\n#[cfg(test)]\nmod tests {}\n"
    region = proof.sha(source[source.index("#[cfg(test)]"):])
    report = {"execution_id": identity, "executor": "GitHub Actions isolated Docker runner", "status": "passed_no_fix",
        "github": {"run_id": run_id, "workflow_sha": head}, "source": {"commit": proof.SOURCE_COMMIT, "image": proof.IMAGE,
            "tracked_blobs": 957, "test_region_sha256": region, "final_test_region_sha256": region, "final_changed_paths": [],
            "initial_blob_hashes_sha256": "c" * 64, "final_blob_hashes_sha256": "c" * 64, "final_source_sha256": proof.sha(source)},
        "checks": [], "repairs": []}
    files = {}
    for name, argv in [("graph_library_initial", worker.LIBRARY_ARGV)] + [(name, worker.target_argv(name)) for name in worker.TESTS] + [("format", ["cargo", "fmt", "--all", "--check"])]:
        count, ignored = (530, 17) if name.startswith("graph_library") else (1, 0)
        raw = f"running {count + ignored} tests\ntest result: ok. {count} passed; 0 failed; {ignored} ignored\n".encode() if name != "format" else b""
        path = "checks/" + name + ".log"
        files[path] = raw
        report["checks"].append({"name": name, "argv": argv, "exit_code": 0, "passed": True, "log_path": path,
            "log_sha256": proof.sha(raw), "log_bytes": len(raw), "test_summaries": worker.summaries(raw)})
    def archive():
        files["report.json"] = json.dumps(report, indent=2).replace("\n", "\r\n").encode()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as package:
            for path, raw in files.items(): package.writestr(path, raw)
        return stream.getvalue()
    package = archive()
    record = {"id": identity, "task_id": proof.TASK, "status": "completed", "graph_verified": True,
        "runner": {"provider": "GitHub Actions", "run_id": run_id, "verified": True, "artifact_sha256": proof.sha(package)},
        "checks": {"verified": True, "passed": 534, "failed": 0, "ignored": 17}, "repairs": [],
        "evidence": [{"url": proof.ORIGIN + "/api/public/workflows/" + identity + "/evidence", "sha256": proof.sha(files["report.json"])}],
        "investigation_task_id": "task-investigation", "publication": {
            "jira": {"status": "verified", "read_back_verified": True, "url": "https://rhudhresh3697.atlassian.net/browse/KAN-2"},
            "slack": {"status": "verified", "read_back_verified": True, "url": "https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199"}}}
    metadata = {"status": "completed", "conclusion": "success", "run_attempt": 1, "event": "workflow_dispatch", "display_title": "Baton execution " + identity,
        "path": ".github/workflows/baton-execute.yml", "repository": {"full_name": proof.REPO}, "head_sha": head}
    base = "/repos/" + proof.REPO + "/actions/runs/" + run_id
    public_overrides = {}
    class Reader:
        def json(self, path, github=False):
            if path == "/api/public/workflows/" + identity: return copy.deepcopy(record)
            if path == base: return metadata
            if path.endswith("/jobs?per_page=30"): return {"jobs": [{"name": name, "status": "completed", "conclusion": "success"} for name in ("execute", "finalization")]}
            if path.endswith("/artifacts?per_page=30"): return {"artifacts": [{"id": 789, "name": "baton-run-" + identity,
                "expired": False, "workflow_run": {"id": run_id}, "digest": "sha256:" + proof.sha(package)}]}
            if "/contents/" in path: return {"content": base64.b64encode(source.encode()).decode()}
            if path == "/api/public/workspace": return {"tasks": [{"id": task, "status": "done"} for task in (proof.TASK, "task-investigation")]}
            raise AssertionError("unexpected read path")
        def raw(self, path, github=False, archive=False):
            if archive: return package
            if path in public_overrides: return public_overrides[path]
            if path.endswith("/evidence"): return files["report.json"]
            return files[path.rsplit("/", 1)[1].replace("checks_", "checks/", 1)]
    return SimpleNamespace(id=identity, source=source, report=report, files=files, record=record, metadata=metadata, reader=Reader(), overrides=public_overrides)


def test_completed_release_proof_rehashes_raw_artifact_and_public_bytes(fixture):
    result = proof.verify(fixture.id, fixture.reader)
    assert result["status"] == "verified" and result["passed"] == 534 and result["raw_public_logs_verified"] == 6
    assert result["tracked_blobs"] == 957 and result["repairs"] == []
    assert any("did not query Jira or Slack directly" in limit for limit in result["limits"])
    assert "fn cap" not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["not-complete", "fake-provider-readback", "wrong-provider-url", "wrong-evidence-bytes", "wrong-log-bytes", "zero-tests", "wrong-job"])
def test_independent_release_rejects_divergence(fixture, mutation):
    if mutation == "not-complete": fixture.record["status"] = "running"
    elif mutation == "fake-provider-readback": fixture.record["publication"]["slack"]["read_back_verified"] = False
    elif mutation == "wrong-provider-url": fixture.record["publication"]["jira"]["url"] += "?fake"
    elif mutation == "zero-tests": fixture.record["checks"]["passed"] = 0
    elif mutation == "wrong-job": fixture.metadata["conclusion"] = "failure"
    elif mutation == "wrong-evidence-bytes": fixture.overrides["/api/public/workflows/" + fixture.id + "/evidence"] = b"{}"
    else: fixture.overrides["/api/public/workflows/" + fixture.id + "/logs/checks_debug_resize.log"] = b"invented"
    with pytest.raises(proof.ProofError): proof.verify(fixture.id, fixture.reader)


def test_claimed_name_with_wrong_actual_command_is_rejected(fixture):
    fixture.report["checks"][1]["argv"] = ["cargo", "fmt"]
    with pytest.raises(proof.ProofError, match="command"):
        proof.check_logs(fixture.report["checks"], fixture.files, fixture.id, fixture.reader)


def test_model_edit_is_reconstructed_from_actual_raw_output_and_source(fixture):
    prefix, marker, tests = fixture.source.partition("#[cfg(test)]")
    old, new = "42", "43"
    updated = prefix.replace(old, new, 1)
    patch = "diff --git a/" + proof.EDITABLE + " b/" + proof.EDITABLE + "\n" + "".join(difflib.unified_diff(
        prefix.splitlines(keepends=True), updated.splitlines(keepends=True), fromfile="a/" + proof.EDITABLE, tofile="b/" + proof.EDITABLE))
    receipt = {"cached": False, "id": "chatcmpl-real", "model": "openai/gpt-oss-20b", "usage": {"prompt_tokens": 100, "completion_tokens": 30},
        "input_sha256": "d" * 64, "response_sha256": "e" * 64}
    entry = {"attempt": 1, "applied": True, "tests_unchanged": True, "patch_path": "patches/repair-1.patch", "patch_sha256": proof.sha(patch),
        "provider_receipt": receipt, "post_apply_source": {"tracked_blobs": 957, "tests_unchanged": True, "changed_paths": [proof.EDITABLE],
            "test_region_sha256": proof.sha(marker + tests), "production_before_sha256": proof.sha(prefix), "production_after_sha256": proof.sha(updated)}}
    fixture.files[entry["patch_path"]] = patch.encode()
    fixture.report["repairs"] = [entry]
    fixture.report["status"] = "passed"
    fixture.report["source"]["final_source_sha256"] = proof.sha(updated + marker + tests)
    fixture.report["checks"].insert(1, {"name": "graph_library_repair_1"})
    model = {"attempt": 1, "raw_model_output": json.dumps({"old": old, "new": new}), "model_edit": {"old": old, "new": new},
        "diff": patch, "provider_receipt": receipt, "provider_response_id": receipt["id"]}
    fixture.record["repairs"] = [model]
    assert proof.check_repairs(fixture.record, fixture.report, fixture.files, fixture.source)[0]["applied"] is True
    model["raw_model_output"] = json.dumps({"old": old, "new": "999"})
    with pytest.raises(proof.ProofError, match="Raw model edit"):
        proof.check_repairs(fixture.record, fixture.report, fixture.files, fixture.source)


def test_existing_gcm_credential_uses_explicit_helper_and_username_without_config_changes(monkeypatch):
    command = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="username=RHUDHRESH\npassword=private-test-token\n"))
    monkeypatch.setattr(proof.subprocess, "run", command)
    assert proof.credential() == "private-test-token"
    assert command.call_args.args[0] == ["git", "-c", "credential.helper=", "-c", "credential.helper=manager", "credential", "fill"]
    assert command.call_args.kwargs["input"] == "protocol=https\nhost=github.com\nusername=RHUDHRESH\n\n"
    assert command.call_args.kwargs["capture_output"] is True


def test_actual_failure_proof_is_distinct_from_success_and_rejects_done_transition(fixture):
    check = fixture.report["checks"][0]
    raw = b"running 547 tests\ntest result: FAILED. 529 passed; 1 failed; 17 ignored\n"
    fixture.files[check["log_path"]] = raw
    check.update(exit_code=101, passed=False, log_bytes=len(raw), log_sha256=proof.sha(raw), test_summaries=worker.summaries(raw))
    fixture.report.update(status="failed", error="App callback failed; inspect this run's saved artifact", checks=[check])
    fixture.files["report.json"] = json.dumps(fixture.report).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("report.json", fixture.files["report.json"])
        archive.writestr(check["log_path"], raw)
    package = stream.getvalue()
    fixture.record.update(status="failed", checks={"passed": 529, "failed": 1, "ignored": 17})
    fixture.record["runner"].update(conclusion="failure", artifact_sha256=proof.sha(package))
    fixture.record["evidence"][0]["sha256"] = proof.sha(fixture.files["report.json"])
    fixture.record["publication"]["jira"]["comment"] = {"status": "verified", "id": "10001"}
    fixture.metadata["conclusion"] = "failure"
    original = fixture.reader
    class FailureReader:
        def json(self, path, github=False):
            if "/jobs?" in path:
                return {"jobs": [{"name": "execute", "status": "completed", "conclusion": "failure"},
                    {"name": "finalization", "status": "completed", "conclusion": "success"}]}
            if "/artifacts?" in path:
                value = copy.deepcopy(original.json(path, github))
                value["artifacts"][0]["digest"] = "sha256:" + proof.sha(package)
                return value
            return original.json(path, github)
        def raw(self, path, github=False, archive=False):
            return package if archive else original.raw(path, github)
    reader = FailureReader()
    result = proof.verify_failure(fixture.id, reader)
    assert result["status"] == "verified_failure" and result["outcome"] == "failed" and result["passed"] == 529
    assert result["applied_repairs"] == 0 and result["new_task_completion"] is False
    fixture.record["publication"]["jira"]["transition"] = {"status": "verified"}
    with pytest.raises(proof.ProofError, match="Done transition"):
        proof.verify_failure(fixture.id, reader)
