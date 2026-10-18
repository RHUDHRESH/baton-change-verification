"""Independent command/log validation and durable application completion gates."""
import copy
from contextlib import nullcontext
import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import zipfile

import pytest

from server import autonomous_workflow as workflow
from server import autonomous_publication as publication
from scripts import autonomous_worker as worker


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    identity, head = "a" * 32, "b" * 40
    source = "production source\n#[cfg(test)]\nmod tests {}\n"
    region = workflow.sha(source[source.index("#[cfg(test)]"):])
    record = {"id": identity, "status": "running", "task_id": workflow.TASK, "item_id": workflow.ITEM,
        "expected_workflow_sha": head, "runner": {"provider": "GitHub Actions", "run_id": "123", "verified": False,
            "run_url": "https://github.com/" + workflow.REPOSITORY + "/actions/runs/123", "source_commit": workflow.SOURCE_COMMIT,
            "image_digest": workflow.IMAGE.split("@", 1)[1]},
        "repair_responses": {}, "repairs": [], "investigation": {"id": "agent-1"}, "investigation_task_id": "task-investigation",
        "graph": "baton_test", "publish_targets": ["jira", "slack"], "checks": {"verified": False}, "evidence": [],
        "stages": [{"id": name, "status": "pending"} for name in ("investigate", "execute", "repair", "verify", "publish")]}
    report = {"schema_version": 1, "execution_id": identity, "status": "passed_no_fix",
        "executor": "GitHub Actions isolated Docker runner", "github": {"run_id": "123", "run_attempt": "1",
            "repository": workflow.REPOSITORY, "workflow_sha": head}, "source": {"repository": worker.REPOSITORY,
            "commit": workflow.SOURCE_COMMIT, "image": workflow.IMAGE, "tracked_blobs": 957,
            "test_region_sha256": region, "final_test_region_sha256": region, "final_changed_paths": [],
            "initial_blob_hashes_sha256": "1" * 64, "final_blob_hashes_sha256": "1" * 64, "final_source_sha256": "2" * 64},
        "checks": [], "repairs": []}
    files = {}
    def add(name, argv, passed, ignored=0, exit_code=0):
        raw = (f"running {passed + ignored} tests\ntest result: ok. {passed} passed; 0 failed; {ignored} ignored\n").encode() if name != "format" else b""
        path = "checks/" + name + ".log"
        files[path] = raw
        report["checks"].append({"name": name, "argv": argv, "exit_code": exit_code, "log_path": path,
            "log_sha256": workflow.sha(raw), "log_bytes": len(raw), "test_summaries": worker.summaries(raw), "passed": True})
    add("graph_library_initial", worker.LIBRARY_ARGV, 530, 17)
    for name in worker.TESTS: add(name, worker.target_argv(name), 1)
    add("format", ["cargo", "fmt", "--all", "--check"], 0)
    private = {"autonomous:run:" + identity: workflow.encode(record)}
    public = {}
    def store(key, value, **kwargs): private[key] = value; return True
    control = SimpleNamespace(get=lambda key: private.get(key), set=MagicMock(side_effect=store), lock=MagicMock(return_value=nullcontext()))
    monkeypatch.setattr(workflow, "connect", lambda port: control)
    monkeypatch.setattr(workflow.public, "write", lambda data, key, value: public.__setitem__(key, copy.deepcopy(value)))
    monkeypatch.setattr(workflow.public, "read", lambda data, key, default=None: copy.deepcopy(public.get(key, default)))
    monkeypatch.setattr(workflow, "original_source", lambda: source)
    graph = MagicMock()
    monkeypatch.setattr(workflow, "_graph_receipt", graph)
    publisher = MagicMock(return_value={"status": "verified", "providers": {
        "jira": {"status": "verified", "url": "https://rhudhresh3697.atlassian.net/browse/KAN-2", "comment": {"id": "10001", "status": "verified"}},
        "slack": {"status": "verified", "url": publication.SLACK_URL}}})
    monkeypatch.setattr(publication, "finalize_run", publisher)
    tasks = MagicMock(side_effect=lambda data, port, identity, status: {"id": identity, "status": status})
    monkeypatch.setattr(workflow.public, "complete_task", tasks)
    def archive():
        output = io.BytesIO()
        # Deliberate non-canonical whitespace/CRLF verifies exact evidence bytes.
        files["report.json"] = json.dumps(report, indent=2).replace("\n", "\r\n").encode()
        with zipfile.ZipFile(output, "w") as package:
            for path, raw in files.items(): package.writestr(path, raw)
        return output.getvalue()
    management = {"conclusion": "success"}
    def github(path, method="GET", payload=None, binary=False):
        if path.endswith("/jobs?per_page=30"):
            return {"jobs": [{"id": 456, "name": "execute", "status": "completed", "conclusion": management["conclusion"]}]}
        if path.endswith("/artifacts?per_page=30"):
            return {"artifacts": [{"id": 789, "name": "baton-run-" + identity, "expired": False,
                "workflow_run": {"id": 123}, "digest": "sha256:" + workflow.sha(archive())}]}
        if binary: return archive()
        return {"event": "workflow_dispatch", "run_attempt": 1, "head_sha": head, "repository": {"full_name": workflow.REPOSITORY},
            "display_title": "Baton execution " + identity, "path": ".github/workflows/" + workflow.WORKFLOW,
            "html_url": record["runner"]["run_url"]}
    monkeypatch.setattr(workflow, "github", github)
    return SimpleNamespace(data=tmp_path, id=identity, record=record, report=report, files=files, private=private, public=public,
        control=control, graph=graph, publisher=publisher, tasks=tasks, management=management, archive=archive,
        body={"github_run_id": "123", "artifact_name": "baton-run-" + identity})


def complete(fixture):
    return workflow.complete(fixture.data, 6379, fixture.id, fixture.body)


def test_actual_worker_profile_and_commands_validate(fixture):
    assert len(workflow.validate_report(fixture.record, fixture.report, fixture.files)) == 6
    workflow._validate_success(fixture.record, fixture.report, workflow._final_checks(fixture.report["checks"]))
    assert "checks/debug_resize.log" in workflow.artifact_files(fixture.archive())


@pytest.mark.parametrize("mutation", ["all-fmt", "missing-locked", "wrong-target", "wrong-release", "wrong-log", "forged-passed", "wrong-count", "missing-running", "extra-check", "bool-exit"])
def test_named_checks_cannot_forge_success_with_unrelated_commands_or_logs(fixture, mutation):
    check = fixture.report["checks"][1]
    if mutation == "all-fmt":
        for row in fixture.report["checks"]: row["argv"] = ["cargo", "fmt", "--all", "--check"]
    elif mutation == "missing-locked": check["argv"].remove("--locked")
    elif mutation == "wrong-target": check["argv"][6] = "unrelated::test"
    elif mutation == "wrong-release": check["argv"].insert(2, "--release")
    elif mutation == "wrong-log": check["log_path"] = "checks/format.log"
    elif mutation == "forged-passed": check["passed"] = False
    elif mutation == "bool-exit": check["exit_code"] = False
    elif mutation == "extra-check": check["name"] = "invented_check"
    else:
        raw = b"test result: ok. 0 passed; 0 failed; 0 ignored\n" if mutation == "wrong-count" else b"test result: ok. 1 passed; 0 failed; 0 ignored\n"
        fixture.files[check["log_path"]] = raw
        check.update(log_sha256=workflow.sha(raw), log_bytes=len(raw), test_summaries=worker.summaries(raw))
    with pytest.raises(workflow.WorkflowError): workflow.validate_report(fixture.record, fixture.report, fixture.files)


@pytest.mark.parametrize("mutation", ["missing-format", "missing-target", "zero-library", "modified-tests", "extra-path", "missing-source-proof"])
def test_success_requires_full_immutable_profile_and_source_scope(fixture, mutation):
    if mutation == "missing-format": fixture.report["checks"].pop()
    elif mutation == "missing-target": fixture.report["checks"].pop(1)
    elif mutation == "zero-library": fixture.report["checks"][0]["test_summaries"][0]["passed"] = 0
    elif mutation == "modified-tests": fixture.report["source"]["final_test_region_sha256"] = "e" * 64
    elif mutation == "extra-path": fixture.report["source"]["final_changed_paths"] = ["Cargo.toml"]
    else: del fixture.report["source"]["tracked_blobs"]
    with pytest.raises(workflow.WorkflowError):
        workflow._validate_success(fixture.record, fixture.report, workflow._final_checks(fixture.report["checks"]))


def test_complete_adapts_providers_shape_marks_real_tasks_done_and_preserves_evidence_bytes(fixture):
    result = complete(fixture)
    assert result["status"] == "completed" and result["checks"]["verified"] is True
    assert result["checks"]["passed"] == 534 and result["checks"]["ignored"] == 17
    assert all(result["publication"][name]["read_back_verified"] is True for name in ("jira", "slack"))
    assert {call.args[2] for call in fixture.tasks.call_args_list} == {workflow.TASK, "task-investigation"}
    assert all(call.args[3] == "done" for call in fixture.tasks.call_args_list)
    raw = workflow.evidence(fixture.data, 6379, fixture.id)
    assert raw.encode() == fixture.files["report.json"]
    assert workflow.sha(raw) == result["evidence"][0]["sha256"]
    assert "expected_workflow_sha" not in result and "repair_responses" not in result and "check_results" not in result
    assert complete(fixture)["status"] == "completed" and fixture.publisher.call_count == 1


def test_forged_report_becomes_durable_failure_without_graph_provider_or_task_mutations(fixture):
    fixture.report["checks"][0]["argv"] = ["cargo", "fmt"]
    result = complete(fixture)
    assert result["status"] == "failed" and "artifact failed" in result["error"]
    assert json.loads(fixture.private["autonomous:run:" + fixture.id])["status"] == "failed"
    fixture.graph.assert_not_called(); fixture.publisher.assert_not_called(); fixture.tasks.assert_not_called()


def test_publisher_exception_becomes_durable_sanitized_partial(fixture):
    fixture.publisher.side_effect = RuntimeError("private-token-provider-payload")
    result = complete(fixture)
    assert result["status"] == "partial"
    assert all(row["status"] == "pending" and row["read_back_verified"] is False for row in result["publication"].values())
    assert "private-token" not in json.dumps(result)
    assert json.loads(fixture.private["autonomous:run:" + fixture.id])["status"] == "partial"


def test_graph_readback_failure_prevents_provider_updates_and_done(fixture):
    fixture.graph.side_effect = RuntimeError("private-graph-error")
    result = complete(fixture)
    assert result["status"] == "partial" and result["graph_verified"] is False
    fixture.publisher.assert_not_called(); fixture.tasks.assert_not_called()
    assert "private-graph-error" not in json.dumps(result)


def test_one_provider_pending_stays_partial_with_independent_statuses(fixture):
    fixture.publisher.return_value["providers"]["slack"] = {"status": "pending"}
    result = complete(fixture)
    assert result["status"] == "partial" and result["publication"]["jira"]["read_back_verified"] is True
    assert result["publication"]["slack"]["read_back_verified"] is False


def test_task_status_failure_cannot_report_completed(fixture):
    fixture.tasks.return_value = None
    fixture.tasks.side_effect = RuntimeError("private-task-error")
    result = complete(fixture)
    assert result["status"] == "partial" and all(not row["read_back_verified"] for row in result["task_completion"].values())
    assert "private-task-error" not in json.dumps(result)


def test_exact_evidence_hash_detects_reserialization(fixture):
    complete(fixture)
    row = fixture.public["workflows/" + fixture.id + "/files/report.json.json"]
    row["text"] = json.dumps(json.loads(row["text"]))
    with pytest.raises(workflow.WorkflowError, match="bytes"):
        workflow.evidence(fixture.data, 6379, fixture.id)


def test_artifact_path_traversal_and_duplicate_files_rejected():
    for paths in (["report.json", "../escape"], ["report.json", "report.json"]):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for path in paths: archive.writestr(path, b"{}")
        with pytest.raises(workflow.WorkflowError): workflow.artifact_files(raw.getvalue())


def with_repair(fixture, applied):
    patch = "diff --git a/file b/file\n"
    receipt = {"id": "chatcmpl-repair", "model": "actual-model", "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}}
    fixture.record["repair_responses"]["1"] = {"response": {"patch": patch, "patch_sha256": workflow.sha(patch), "provider_receipt": receipt}}
    fixture.files["patches/repair-1.patch"] = patch.encode()
    proof = {"tracked_blobs": 957, "changed_paths": [], "test_region_sha256": fixture.report["source"]["test_region_sha256"], "tests_unchanged": True}
    fixture.report["repairs"] = [{"attempt": 1, "patch_path": "patches/repair-1.patch", "patch_sha256": workflow.sha(patch),
        "provider_receipt": receipt, "applied": applied, "pre_apply_source": proof, "post_apply_source": proof, "tests_unchanged": True}]
    failed = fixture.report["checks"][0]
    raw = b"running 547 tests\ntest result: FAILED. 529 passed; 1 failed; 17 ignored\n"
    fixture.files[failed["log_path"]] = raw
    failed.update(exit_code=101, passed=False, log_bytes=len(raw), log_sha256=workflow.sha(raw), test_summaries=worker.summaries(raw))
    return failed


def test_failed_generated_but_unapplied_patch_is_retained_without_invented_retest(fixture):
    with_repair(fixture, False)
    fixture.report["status"] = "failed"
    fixture.report["checks"] = fixture.report["checks"][:1]
    assert len(workflow.validate_report(fixture.record, fixture.report, fixture.files)) == 1
    fixture.private["autonomous:run:" + fixture.id] = workflow.encode(fixture.record)
    fixture.management["conclusion"] = "failure"
    result = complete(fixture)
    assert result["status"] == "failed" and result["checks"]["failed"] == 1
    assert fixture.tasks.call_count == 0
    assert "0 applied" in next(row for row in result["stages"] if row["id"] == "repair")["detail"]


def test_success_cannot_claim_unapplied_patch_or_missing_retest(fixture):
    with_repair(fixture, False)
    fixture.report["status"] = "passed"
    with pytest.raises(workflow.WorkflowError, match="unapplied"):
        workflow.validate_report(fixture.record, fixture.report, fixture.files)
    fixture.report["repairs"][0]["applied"] = True
    with pytest.raises(workflow.WorkflowError, match="sequence"):
        workflow.validate_report(fixture.record, fixture.report, fixture.files)


def test_generated_patch_receipt_or_bytes_cannot_be_replaced(fixture):
    with_repair(fixture, False)
    fixture.report["status"] = "failed"
    fixture.report["repairs"][0]["provider_receipt"] = {"id": "invented"}
    with pytest.raises(workflow.WorkflowError, match="Groq"):
        workflow.validate_report(fixture.record, fixture.report, fixture.files)


def test_failed_source_guard_is_retained_without_unchanged_test_claim(fixture):
    with_repair(fixture, True)
    fixture.report["status"] = "failed"
    fixture.report["checks"] = fixture.report["checks"][:1]
    entry = fixture.report["repairs"][0]
    del entry["tests_unchanged"]
    del entry["post_apply_source"]
    entry["post_apply_guard_error"] = "Source integrity could not be verified"
    assert len(workflow.validate_report(fixture.record, fixture.report, fixture.files)) == 1


def test_unchanged_test_claim_requires_actual_post_apply_proof(fixture):
    with_repair(fixture, False)
    fixture.report["status"] = "failed"
    del fixture.report["repairs"][0]["post_apply_source"]
    with pytest.raises(workflow.WorkflowError, match="guard proof"):
        workflow.validate_report(fixture.record, fixture.report, fixture.files)


def test_publication_receives_the_expected_normalized_durable_record(fixture, monkeypatch):
    monkeypatch.setattr(publication, "control_connect", lambda port: fixture.control)
    def publish(data, port, identity):
        normalized = publication._run(fixture.control, identity)
        assert normalized["status"] == "succeeded" and isinstance(normalized["checks"], list)
        assert normalized["evidence"]["sha256"] == workflow.sha(fixture.files["report.json"])
        return {"providers": {target: {"status": "verified"} for target in ("jira", "slack")}}
    fixture.publisher.side_effect = publish
    assert complete(fixture)["status"] == "completed"


def test_successful_generated_repair_requires_measured_retest_and_preserves_initial_failure(fixture):
    with_repair(fixture, True)
    fixture.report["status"] = "passed"
    fresh = copy.deepcopy(fixture.report["checks"][0])
    fresh.update(name="graph_library_repair_1", log_path="checks/graph_library_repair_1.log", exit_code=0, passed=True)
    raw = b"running 547 tests\ntest result: ok. 530 passed; 0 failed; 17 ignored\n"
    fresh.update(log_sha256=workflow.sha(raw), log_bytes=len(raw), test_summaries=worker.summaries(raw))
    fixture.files[fresh["log_path"]] = raw
    fixture.report["checks"].insert(1, fresh)
    assert len(workflow.validate_report(fixture.record, fixture.report, fixture.files)) == 7
    final = workflow._final_checks(fixture.report["checks"])
    workflow._validate_success(fixture.record, fixture.report, final)
    assert len(final) == 6 and final[0]["name"] == "graph_library_repair_1"
    fixture.private["autonomous:run:" + fixture.id] = workflow.encode(fixture.record)
    result = complete(fixture)
    assert result["status"] == "completed" and len(result["checks"]["results"]) == 7
    assert result["checks"]["failed"] == 0 and result["checks"]["results"][0]["exit_code"] == 101


def test_failed_bootstrap_with_no_executed_tests_stays_failed_and_never_completes_tasks(fixture):
    fixture.report["status"] = "failed"
    fixture.report["checks"] = []
    fixture.management["conclusion"] = "failure"
    result = complete(fixture)
    assert result["status"] == "failed" and result["checks"]["total"] == 0
    assert result["checks"]["results"] == []
    fixture.tasks.assert_not_called()
