"""Goal-plan authority and external-write fault injection, not live proof."""
import copy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from server import goal_actions as A, goal_contract as C, goal_graph as G


@pytest.fixture
def record():
    evidence = [{"id": "ev-source", "source_id": "src-pinned", "kind": "source", "sha256": "a" * 64,
                 "url": "https://github.com/FalkorDB/falkordb-py/pull/212"}]
    goal = "Prepare a source-backed investigation task for the observed failure"
    proposal = {"summary": "Create an investigation task with the observed public evidence",
        "success_criteria": ["A new investigation task and report have independent readbacks"],
        "steps": [{"id": "publish", "title": "Publish investigation work", "tool_name": "publish_task",
            "args": {"title": "Investigate the observed async compatibility failure", "description": "Review the observed public evidence and investigate the compatibility failure.", "source_ids": ["src-pinned"]},
            "why": "The observed failure needs evidence-backed follow-up work", "evidence_ids": ["ev-source"],
            "depends_on": [], "expected_result": "A new task and a report with exact source evidence"}]}
    proposal = C.validate_proposal(proposal, goal, evidence, G.TOOLS + C.EFFECTS, "b" * 64)
    return {"id": "1" * 32, "goal": goal, "model": "provider-test-only", "proposal": proposal,
            "evidence": evidence, "plan_evidence": copy.deepcopy(evidence), "evidence_binding": "b" * 64,
            "approved_actions": ["publish_task"], "provider_receipts": [{"id": "actual-provider-test-receipt", "response_sha256": "c" * 64}], "actions": [], "events": []}


@pytest.mark.parametrize("fault", ["cycle", "unknown_tool", "uninspected_source", "uninspected_evidence", "hash", "goal_swap"])
def test_model_proposal_cannot_expand_authority_or_rebind_its_goal(record, fault):
    plan = copy.deepcopy(record["proposal"])
    goal = record["goal"]
    if fault == "cycle": plan["steps"][0]["depends_on"] = ["publish"]
    if fault == "unknown_tool": plan["steps"][0]["tool_name"] = "run_arbitrary_shell"
    if fault == "uninspected_source": plan["steps"][0]["args"]["source_ids"] = ["unknown"]
    if fault == "uninspected_evidence": plan["steps"][0]["evidence_ids"] = ["unknown"]
    if fault == "hash": plan["summary"] += " changed material"
    if fault == "goal_swap": goal = "A completely different goal requesting unrelated work"
    with pytest.raises(ValueError):
        C.validate_proposal(plan, goal, record["evidence"], G.TOOLS + C.EFFECTS, record["evidence_binding"])


@pytest.mark.parametrize("fault", ["not_ready", "stale", "not_approved", "changed_step", "missing_provider"])
def test_goal_effect_is_rejected_before_any_provider_call(record, monkeypatch, fault):
    stored, step = copy.deepcopy(record), copy.deepcopy(record["proposal"]["steps"][0])
    if fault == "not_approved": stored["approved_actions"] = []
    if fault == "missing_provider": stored["provider_receipts"] = []
    if fault == "changed_step": step["args"]["title"] += " modified"
    monkeypatch.setattr(G, "get_goal", lambda *a: stored)
    monkeypatch.setattr(G, "evidence_binding", lambda *a: "d" * 64 if fault == "stale" else "b" * 64)
    monkeypatch.setattr(G, "ready_steps", lambda *a: [] if fault == "not_ready" else ["publish"])
    calls = []
    monkeypatch.setattr(A.provider, "_config", lambda *a: calls.append(a))
    with pytest.raises(ValueError): A.execute(None, 0, record, step)
    assert calls == []


class Control:
    def __init__(self): self.values = {}
    def lock(self, *a, **k): return nullcontext()
    def get(self, key): return self.values.get(key)
    def set(self, key, value, **kwargs): self.values[key] = value; return True


def test_unknown_goal_publication_outcome_is_never_posted_twice(record, monkeypatch):
    control, calls = Control(), []
    monkeypatch.setattr(A, "connect", lambda *a: control)
    monkeypatch.setattr(A, "_current", lambda *a: record)
    monkeypatch.setattr(A.provider, "_config", lambda *a: {"site": "https://example.atlassian.net", "project": "KAN"})
    def request(*args):
        calls.append(args[:3])
        raise A.provider.ConnectionError("Unknown write outcome")
    monkeypatch.setattr(A.provider, "_request", request)
    step = record["proposal"]["steps"][0]
    one = A._publish_target(None, 0, record, step, "jira", "Approved title", "Approved public evidence")
    two = A._publish_target(None, 0, record, step, "jira", "Approved title", "Approved public evidence")
    assert one == two and one["status"] == "pending" and one["read_back_verified"] is False
    assert calls == [("jira", "POST", "/rest/api/3/issue")]


def test_known_goal_artifact_retries_only_readback(record, monkeypatch):
    control, writes, reads = Control(), [], []
    monkeypatch.setattr(A, "connect", lambda *a: control)
    monkeypatch.setattr(A, "_current", lambda *a: record)
    monkeypatch.setattr(A, "_link", lambda *a: True)
    monkeypatch.setattr(A.provider, "_config", lambda *a: {"site": "https://example.atlassian.net", "project": "KAN"})
    monkeypatch.setattr(A.provider, "_request", lambda *a: writes.append(a) or {"key": "KAN-101"})
    def verify(*args):
        reads.append(args)
        if len(reads) == 1: raise A.provider.ConnectionError("Readback not confirmed")
        return "https://example.atlassian.net/browse/KAN-101"
    monkeypatch.setattr(A.provider, "_verify", verify)
    step = record["proposal"]["steps"][0]
    one = A._publish_target(None, 0, record, step, "jira", "Approved title", "Approved public evidence")
    two = A._publish_target(None, 0, record, step, "jira", "Approved title", "Approved public evidence")
    assert one["status"] == "verification_pending" and two["status"] == "verified" and two["read_back_verified"] is True
    assert len(writes) == 1 and len(reads) == 2


def test_plan_evidence_is_not_silently_expanded_after_a_new_read(record, monkeypatch):
    record["evidence"].append({"id": "new-observation", "source_id": "other", "sha256": "d" * 64, "kind": "entity"})
    monkeypatch.setattr(G, "get_goal", lambda *a: record)
    observed = []
    monkeypatch.setattr(G, "evidence_binding", lambda data, port, refs: observed.append(refs) or "b" * 64)
    monkeypatch.setattr(G, "ready_steps", lambda *a: ["publish"])
    assert A._current(None, 0, record, record["proposal"]["steps"][0]) == record
    assert observed == [record["plan_evidence"]]


def test_goal_verification_bridge_preserves_actual_ai_origin_and_replays_same_intent(record, monkeypatch):
    from server import release_gate as gate, release_graph as release, release_contract as policy
    control, saved, dispatched = Control(), [], []
    source = {"plan_hash": "e" * 64, "id": "f" * 32, "plan_status": "ready",
              "source_versions": [{"id": "src-pinned"}], "latest_run_id": "old-run", "investigation": {"status": "succeeded", "summary": "old"}}
    monkeypatch.setattr(A, "connect", lambda *a: control)
    monkeypatch.setattr(gate, "read_plan", lambda port, identity=None: next((p for p in saved if p["id"] == identity), source))
    monkeypatch.setattr(release, "revalidate", lambda *a: True)
    monkeypatch.setattr(policy, "plan_hash", lambda p: p["plan_hash"])
    monkeypatch.setattr(gate, "_save", lambda port, kind, plan: saved.append(copy.deepcopy(plan)))
    def execute(*args):
        dispatched.append(args)
        return {"id": "9" * 32, "plan_id": args[2], "plan_hash": args[3], "status": "queued", "decision": "unconfirmed", "evidence_status": "unconfirmed", "verification_status": "running", "environments": []}
    monkeypatch.setattr(gate, "execute", execute)
    step = {"id": "verify", "tool_name": "verify_release", "why": "The model selected the approved verification capability"}
    one = A._verify_release(None, 0, record, step)
    two = A._verify_release(None, 0, record, step)
    assert one == two and one["status"] == "running" and one["read_back_verified"] is False
    assert len(saved) == 1 and len(dispatched) == 2 and dispatched[0] == dispatched[1]
    assert saved[0]["latest_run_id"] is None
    assert saved[0]["investigation"]["origin"] == "goal_agent"
    assert saved[0]["investigation"]["receipts"] == record["provider_receipts"]
    assert saved[0]["investigation"]["goal_plan_hash"] == record["proposal"]["hash"]
    assert "no additional" in saved[0]["investigation"]["source_binding"].lower()


def test_verification_bridge_requires_inspection_of_this_pinned_change(record, monkeypatch):
    from server import release_gate as gate, release_graph as release
    control = Control()
    monkeypatch.setattr(A, "connect", lambda *a: control)
    monkeypatch.setattr(gate, "read_plan", lambda *a: {"source_versions": [{"id": "another-source"}]})
    monkeypatch.setattr(release, "revalidate", lambda *a: True)
    calls = []
    monkeypatch.setattr(gate, "execute", lambda *a: calls.append(a))
    with pytest.raises(ValueError, match="Inspect this pinned change"):
        A._verify_release(None, 0, record, {"id": "verify", "why": "Need verification"})
    assert calls == []


@pytest.fixture
def pending_verification(record, monkeypatch):
    from server import release_gate as gate, release_graph as release
    step = {"id": "verify", "title": "Verify the merged change", "tool_name": "verify_release",
            "args": {"change_id": "FalkorDB/falkordb-py#212"}, "why": "Collect actual compatibility evidence",
            "evidence_ids": ["ev-source"], "depends_on": [], "expected_result": "Recorded execution and publication receipts"}
    raw = {"summary": "Verify the inspected change", "success_criteria": ["Read actual execution and publication receipts"], "steps": [step]}
    record["proposal"] = C.validate_proposal(raw, record["goal"], record["evidence"], G.TOOLS + C.EFFECTS, record["evidence_binding"])
    record["approved_actions"] = ["verify_release"]
    run_id, plan_id = "9" * 32, "f" * 32
    record["actions"] = [{"id": "goal-verification-" + run_id, "step_id": "verify", "kind": "verify_release",
                          "plan_hash": record["proposal"]["hash"], "status": "running", "read_back_verified": False, "result": {"run_id": run_id}}]
    plan = {"id": plan_id, "plan_hash": "e" * 64, "latest_run_id": run_id, "graph": "actual-release-graph-test",
            "investigation": {"origin": "goal_agent", "goal_id": record["id"], "goal_plan_hash": record["proposal"]["hash"]}}
    run = {"id": run_id, "plan_id": plan_id, "plan_hash": plan["plan_hash"], "status": "running",
           "evidence_status": "unconfirmed", "decision": "unconfirmed", "verification_status": "running", "environments": [],
           "publication": {}, "publish_targets": ["jira", "slack"]}
    control, reads = Control(), []
    key = "goal:verification:" + C.sha(C.encode([record["id"], record["proposal"]["hash"], step["id"]]))
    control.values[key] = plan_id
    monkeypatch.setattr(A, "connect", lambda *a: control)
    monkeypatch.setattr(G, "get_goal", lambda *a: record)
    monkeypatch.setattr(G, "evidence_binding", lambda *a: record["evidence_binding"])
    monkeypatch.setattr(G, "ready_steps", lambda *a: ["verify"])
    monkeypatch.setattr(gate, "read_plan", lambda port, identity: reads.append(("plan", identity)) or plan)
    monkeypatch.setattr(gate, "read_run", lambda port, identity: reads.append(("run", identity)) or run)
    monkeypatch.setattr(gate, "_current", lambda *a: reads.append(("fresh-plan", a[-1]["id"])))
    monkeypatch.setattr(release, "verify_result", lambda *a: reads.append(("certificate", a[-1]["id"])) or run["graph_receipt"])
    def forbidden(*args, **kwargs): raise AssertionError("Readonly continuation attempted an effect")
    def native_read(query, params):
        assert query.startswith("MATCH ") and not any(word in query for word in ("MERGE ", " SET ", "CREATE "))
        reads.append(("native-publication", params["target"]))
        return SimpleNamespace(result_set=[[params["id"], params["target"], params["url"], params["hash"], params["run"]]])
    native = SimpleNamespace(ro_query=native_read, query=forbidden)
    monkeypatch.setattr(release, "_connect", lambda *a: SimpleNamespace(select_graph=lambda name: native))
    for module, name in [(gate, "execute"), (gate, "_save"), (gate, "github"), (release, "record_result"), (A.provider, "_request"), (A.provider, "_verify"), (control, "set")]:
        monkeypatch.setattr(module, name, forbidden)
    return record, step, plan, run, control, reads


def test_resume_reads_only_known_durable_run_without_dispatch_or_provider_write(pending_verification):
    record, step, plan, run, _, reads = pending_verification
    receipt = A.resume(None, 0, record, step)
    assert receipt["status"] == "running" and receipt["read_back_verified"] is False
    assert receipt["result"]["run_id"] == run["id"]
    assert reads == [("plan", plan["id"]), ("fresh-plan", plan["id"]), ("run", run["id"])]


@pytest.mark.parametrize("fault", ["no_action", "different_hash", "different_step", "different_kind", "unknown_run", "no_intent", "intent_run_mismatch", "intent_goal_mismatch", "run_plan_mismatch", "not_approved", "not_ready", "stale_evidence"])
def test_resume_cannot_start_new_effect_or_rebind_pending_run(pending_verification, monkeypatch, fault):
    record, step, plan, run, control, _ = pending_verification
    if fault == "no_action": record["actions"] = []
    if fault == "different_hash": record["actions"][0]["plan_hash"] = "old"
    if fault == "different_step": record["actions"][0]["step_id"] = "other"
    if fault == "different_kind": record["actions"][0]["kind"] = "publish_task"
    if fault == "unknown_run": record["actions"][0]["result"] = {}
    if fault == "no_intent": control.values.clear()
    if fault == "intent_run_mismatch": plan["latest_run_id"] = "8" * 32
    if fault == "intent_goal_mismatch": plan["investigation"]["goal_id"] = "8" * 32
    if fault == "run_plan_mismatch": run["plan_hash"] = "old"
    if fault == "not_approved": record["approved_actions"] = []
    if fault == "not_ready": monkeypatch.setattr(G, "ready_steps", lambda *a: [])
    if fault == "stale_evidence": monkeypatch.setattr(G, "evidence_binding", lambda *a: "changed")
    with pytest.raises(ValueError): A.resume(None, 0, record, step)


def test_resume_never_publishes_a_new_task(pending_verification):
    record, step, *_ = pending_verification
    step["tool_name"] = "publish_task"
    with pytest.raises(ValueError, match="cannot start or publish"): A.resume(None, 0, record, step)


def verified_run(plan, run):
    run.update(status="completed", evidence_status="verified", decision="blocked", verification_status="failed",
               graph_receipt={"verified": True, "run_id": run["id"]},
               publication={target: {"target": target, "status": "verified", "graph_linked": True,
                                    "id": "publication-" + target, "contract_sha256": "c" * 64,
                                    "run_id": run["id"], "plan_id": plan["id"], "url": "https://example.invalid/actual-receipt"} for target in ("jira", "slack")})


@pytest.mark.parametrize("fault", ["missing", "pending", "not_linked", "other_run", "other_plan", "other_target"])
def test_verified_matrix_without_both_actual_deliveries_never_marks_action_complete(pending_verification, fault):
    record, step, plan, run, *_ = pending_verification
    verified_run(plan, run)
    if fault == "missing": del run["publication"]["slack"]
    if fault == "pending": run["publication"]["slack"]["status"] = "pending"
    if fault == "not_linked": run["publication"]["slack"]["graph_linked"] = False
    if fault == "other_run": run["publication"]["slack"]["run_id"] = "8" * 32
    if fault == "other_plan": run["publication"]["slack"]["plan_id"] = "8" * 32
    if fault == "other_target": run["publication"]["slack"]["target"] = "jira"
    result = A.resume(None, 0, record, step)
    assert result["status"] == "partial" and result["read_back_verified"] is False
    assert result["result"]["publications"] == run["publication"]
    assert result["result"]["decision"] == "blocked" and result["result"]["evidence_graph_verified"] is True
    assert result["result"]["publication_state"] == "unconfirmed"


def test_verified_failing_matrix_with_both_deliveries_verifies_action_not_code(pending_verification):
    record, step, plan, run, *_ = pending_verification
    verified_run(plan, run)
    result = A.resume(None, 0, record, step)
    assert result["status"] == "verified" and result["read_back_verified"] is True
    assert result["result"]["decision"] == "blocked" and result["result"]["verification_status"] == "failed"
    assert result["result"]["publications"] == run["publication"]
    assert result["result"]["publication_graph_verified"] is True


def test_resume_rejects_stale_native_execution_certificate(pending_verification, monkeypatch):
    from server import release_graph as release
    record, step, plan, run, *_ = pending_verification
    verified_run(plan, run)
    monkeypatch.setattr(release, "verify_result", lambda *a: {"verified": True, "run_id": "other"})
    result = A.resume(None, 0, record, step)
    assert result["status"] == "partial" and result["read_back_verified"] is False
    assert result["result"]["evidence_graph_verified"] is False


@pytest.mark.parametrize("fault", ["missing", "wrong_target", "wrong_url", "wrong_hash", "wrong_run"])
def test_cached_publication_json_cannot_replace_native_bindings(pending_verification, monkeypatch, fault):
    from server import release_graph as release
    record, step, plan, run, *_ = pending_verification
    verified_run(plan, run)
    def read(query, params):
        row = [params["id"], params["target"], params["url"], params["hash"], params["run"]]
        if fault == "missing": return SimpleNamespace(result_set=[])
        row[{"wrong_target": 1, "wrong_url": 2, "wrong_hash": 3, "wrong_run": 4}[fault]] = "different-native-binding"
        return SimpleNamespace(result_set=[row])
    monkeypatch.setattr(release, "_connect", lambda *a: SimpleNamespace(select_graph=lambda name: SimpleNamespace(ro_query=read)))
    result = A.resume(None, 0, record, step)
    assert result["status"] == "partial" and result["read_back_verified"] is False
    assert result["result"]["publication_graph_verified"] is False
    assert result["result"]["publications"] == run["publication"]
