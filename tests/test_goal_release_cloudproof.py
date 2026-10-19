"""Adversarial composition contracts; mocked reads are not live goal proof."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import verify_goal_release_cloud as V


@pytest.fixture
def bundle():
    step = {"id": "verify", "tool_name": "verify_release", "args": {"change_id": V.release.CHANGE}, "evidence_ids": ["e1"]}
    record = {"id": "1" * 32, "proposal": {"hash": "a" * 64, "steps": [step]}, "approved_actions": ["verify_release"],
              "plan_evidence": [{"id": "e1", "source_id": "src-actual", "kind": "source"}]}
    plan = {"id": "2" * 32, "plan_hash": "b" * 64, "latest_run_id": "3" * 32,
            "source_versions": [{"id": "src-actual"}], "investigation": {"status": "succeeded", "origin": "goal_agent",
            "goal_id": record["id"], "goal_plan_hash": record["proposal"]["hash"]}}
    run = {"id": "3" * 32, "plan_id": plan["id"], "plan_hash": plan["plan_hash"], "status": "completed",
           "evidence_status": "verified", "evidence_verified": True, "graph_receipt": {"verified": True},
           "publish_targets": ["jira", "slack"], "decision": "blocked", "verification_status": "failed",
           "environments": [{"id": "redis-8.1.0", "failed": 2}], "publication": {"jira": {"id": "j"}, "slack": {"id": "s"}},
           "evidence": {"sha256": "d" * 64}}
    action = {"id": "goal-verification-" + run["id"], "step_id": step["id"], "kind": "verify_release",
              "plan_hash": record["proposal"]["hash"], "status": "verified", "read_back_verified": True,
              "url": V.goal.ORIGIN + "/api/public/release-runs/" + run["id"],
              "result": {"run_id": run["id"], "decision": run["decision"], "evidence_status": "verified",
              "verification_status": "failed", "environments": copy.deepcopy(run["environments"]), "run_status": "completed",
              "evidence_graph_verified": True, "publication_graph_verified": True, "publication_state": "verified",
              "publications": copy.deepcopy(run["publication"])}}
    record["actions"] = [action]
    return record, step, action, plan, run


def test_exact_goal_step_intent_and_release_binding_accepts_verified_failure(bundle):
    record, step, action, plan, run = bundle
    assert V.selected_action(record) == (step, action)
    proof = V.binding_audit(record, step, action, plan, run, plan["id"], copy.deepcopy(plan),
                            {**run, "expected_workflow_sha": "e" * 40, "last_sequence": 5})
    assert proof["release_run_id"] == run["id"] and proof["durable_intent_and_records_reread"]
    assert run["decision"] == "blocked"  # Verified effect does not turn failure into code success.


@pytest.mark.parametrize("fault", ["unapproved", "old_revision", "pending", "latest_partial", "missing_evidence_flag",
                                   "missing_publication_flag", "unconfirmed_delivery", "different_run", "unknown_profile", "duplicate_steps"])
def test_action_selection_rejects_unverified_or_ambiguous_effect(bundle, fault):
    record, step, action, _, _ = bundle
    if fault == "unapproved": record["approved_actions"] = []
    elif fault == "old_revision": action["plan_hash"] = "f" * 64
    elif fault == "pending": action["read_back_verified"] = False
    elif fault == "latest_partial": record["actions"].append({**copy.deepcopy(action), "status": "partial"})
    elif fault == "missing_evidence_flag": action["result"]["evidence_graph_verified"] = False
    elif fault == "missing_publication_flag": action["result"]["publication_graph_verified"] = False
    elif fault == "unconfirmed_delivery": action["result"]["publication_state"] = "unconfirmed"
    elif fault == "different_run": record["actions"].insert(0, {**copy.deepcopy(action), "result": {"run_id": "f" * 32}})
    elif fault == "unknown_profile": step["args"]["change_id"] = "unknown"
    else: record["proposal"]["steps"].append({**copy.deepcopy(step), "id": "verify-again"})
    with pytest.raises(V.AuditError): V.selected_action(record)


@pytest.mark.parametrize("fault", ["intent", "goal_id", "goal_plan", "origin", "latest_run", "durable_plan",
                                   "durable_run", "stale_environment", "stale_delivery", "not_completed", "entity_only", "uncited_source"])
def test_binding_rejects_swaps_stale_results_and_uninspected_source(bundle, fault):
    record, step, action, plan, run = bundle
    intent = plan["id"]
    durable_plan, durable_run = copy.deepcopy(plan), copy.deepcopy(run)
    if fault == "intent": intent = "f" * 32
    elif fault == "goal_id": plan["investigation"]["goal_id"] = "f" * 32
    elif fault == "goal_plan": plan["investigation"]["goal_plan_hash"] = "f" * 64
    elif fault == "origin": plan["investigation"]["origin"] = "release_agent"
    elif fault == "latest_run": plan["latest_run_id"] = "f" * 32
    elif fault == "durable_plan": durable_plan["plan_hash"] = "f" * 64
    elif fault == "durable_run": durable_run["decision"] = "passed"
    elif fault == "stale_environment": action["result"]["environments"] = []
    elif fault == "stale_delivery": action["result"]["publications"] = {}
    elif fault == "not_completed": run["status"] = "running"
    elif fault == "entity_only": record["plan_evidence"][0]["kind"] = "entity"
    else: step["evidence_ids"] = []
    with pytest.raises(V.AuditError): V.binding_audit(record, step, action, plan, run, intent, durable_plan, durable_run)


def composition(bundle, monkeypatch):
    record, step, action, plan, run = bundle
    native = {"status": "verified", "goal_id": record["id"], "proposal_hash": record["proposal"]["hash"]}
    proof = {"status": "verified_failure", "run_id": run["id"], "plan_hash": plan["plan_hash"], "report_sha256": run["evidence"]["sha256"],
             "release_decision": "blocked", "total": 8, "passed": 6, "failed": 2, "errors": 0, "skipped": 0}
    github, cloud = copy.deepcopy(proof), copy.deepcopy(proof)
    gets, settings = [], {"BATON_GITHUB_TOKEN": "test-only-credential"}
    monkeypatch.setattr(V.goal, "verify", lambda *a: native)
    def get(url): gets.append(url); return json.dumps(record).encode()
    monkeypatch.setattr(V, "get", get)
    monkeypatch.setattr(V.release, "public_evidence", lambda *a: (plan, run, {}, []))
    monkeypatch.setattr(V, "private_environment", lambda: settings)
    def durable(key):
        if key.startswith("goal:verification:"): return plan["id"]
        return json.dumps(plan if key.startswith("release:plan:") else run)
    monkeypatch.setattr(V, "durable_reader", lambda *a: durable)
    monkeypatch.setattr(V, "github_audit", lambda *a: github)
    monkeypatch.setattr(V.release, "verify", lambda *a: cloud)
    return native, github, cloud, gets, settings


def test_composed_readonly_proofs_preserve_failing_matrix(bundle, monkeypatch):
    _, github, cloud, gets, settings = composition(bundle, monkeypatch)
    result = V.verify(bundle[0]["id"], "approved.zip", "a" * 64, "b" * 40)
    assert result["status"] == "verified_failure" and result["code_matrix_passed"] is False
    assert result["github_artifact_proof"] == github and result["release_cloud_proof"] == cloud
    assert len(gets) == 2 and settings == {}


@pytest.mark.parametrize("fault", ["native_revision", "github_status", "cloud_run", "report", "counts", "goal_changed"])
def test_composition_fails_closed_on_independent_proof_disagreement(bundle, monkeypatch, fault):
    native, github, cloud, _, settings = composition(bundle, monkeypatch)
    if fault == "native_revision": native["proposal_hash"] = "f" * 64
    elif fault == "github_status": github["status"] = "verified"
    elif fault == "cloud_run": cloud["run_id"] = "f" * 32
    elif fault == "report": cloud["report_sha256"] = "f" * 64
    elif fault == "counts": github["failed"] = 0
    else:
        reads = []
        def get(url):
            reads.append(True)
            return json.dumps({**bundle[0], **({"status": "changed"} if len(reads) > 1 else {})}).encode()
        monkeypatch.setattr(V, "get", get)
    with pytest.raises(V.AuditError): V.verify(bundle[0]["id"], "approved.zip", "a" * 64, "b" * 40)
    if fault != "native_revision": assert settings == {}


def test_durable_reader_issues_only_consistent_scoped_gets(monkeypatch):
    calls = []
    def get_item(**kwargs): calls.append(kwargs); return {"Item": {"value": {"S": "2" * 32}}}
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *a, **k: SimpleNamespace(get_item=get_item)))
    read = V.durable_reader({"BATON_CONTROL_DYNAMODB_TABLE": "test-control-table"})
    assert read("goal:verification:" + "a" * 64) == "2" * 32
    assert calls[0]["ConsistentRead"] is True
    with pytest.raises(V.AuditError): read("release:callback:" + "a" * 32)
    assert len(calls) == 1
