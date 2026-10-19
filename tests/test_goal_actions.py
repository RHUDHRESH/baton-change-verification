"""Goal-plan authority and external-write fault injection, not live proof."""
import copy
from contextlib import nullcontext

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
        return {"id": "9" * 32, "decision": "unconfirmed", "evidence_status": "unconfirmed", "verification_status": "running", "environments": []}
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
