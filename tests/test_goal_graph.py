"""Native FalkorDB goal persistence and adversarial evidence/DAG contracts.

Public capture fixture supplies test inputs only. No production fallback or
model/provider request is exercised or claimed by these graph tests.
"""
import copy
import json
import uuid

import pytest

from test_release_graph import live, sources, release_engine, measured
from server import goal_graph as Q
from server import release_graph as R


@pytest.fixture
def workspace(live, monkeypatch):
    name = "test_goal_" + uuid.uuid4().hex
    monkeypatch.setattr(Q, "GRAPH_NAME", name)
    yield live
    Q._graph(live.port).delete()


def goal(evidence=()):
    return {"id": uuid.uuid4().hex, "goal": "Investigate compatibility and propose evidence-backed next work",
            "status": "proposed", "created_at": "2026-10-19T01:00:00Z", "updated_at": "2026-10-19T01:00:00Z",
            "revision": 1, "evidence": list(evidence), "events": [], "actions": [],
            "proposal": {"hash": uuid.uuid4().hex, "summary": "Model-authored proposal under test",
                         "steps": [{"id": "inspect", "title": "Read source", "tool_name": "read_company_source", "args": {}, "why": "Resolve evidence", "evidence_ids": [e["id"] for e in evidence], "depends_on": [], "expected_result": "Source observed"},
                                   {"id": "publish", "title": "Publish proposed task", "tool_name": "publish_task", "args": {}, "why": "Record verified work", "evidence_ids": [e["id"] for e in evidence], "depends_on": ["inspect"], "expected_result": "Independent provider readback"}]}}


def test_real_source_and_typed_entity_search_are_discoverable_and_bound(workspace):
    search = Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": "Graph._build_params_header", "limit": 5})
    assert search["observation"]["entities"] and search["evidence"]
    assert {e["kind"] for e in search["evidence"]} == {"entity"}
    entity = search["observation"]["entities"][0]
    inspected = Q.call_tool(workspace.data, workspace.port, "inspect_graph_entity", {"entity_id": entity["id"]})
    assert inspected["observation"]["entities"][0]["directed_relationships"]
    source_id = next(s["id"] for s in workspace.sources if s.get("path") == "falkordb/graph.py")
    source = Q.call_tool(workspace.data, workspace.port, "read_company_source", {"source_id": source_id})
    assert source["evidence"][0]["kind"] == "source"
    assert source["observation"]["excerpt"]
    assert Q.evidence_binding(workspace.data, workspace.port, source["evidence"]) == source["binding"]["fingerprint"]


def test_native_goal_dag_survives_request_and_only_verified_observation_unlocks(workspace):
    record = goal()
    assert Q.create_goal(workspace.data, workspace.port, record) == record
    assert Q.get_goal(workspace.data, workspace.port, record["id"]) == record
    assert Q.latest_goal(workspace.data, workspace.port)["id"] == record["id"]
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == ["inspect"]
    record["actions"] = [{"step_id": "inspect", "status": "completed", "read_back_verified": False}]
    Q.save_goal(workspace.data, workspace.port, record)
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == ["inspect"]
    record["events"] = [{"seq": 1, "type": "tool_result", "step_id": "inspect", "plan_hash": record["proposal"]["hash"], "status": "succeeded", "tool_call_id": "real-test-call", "receipt_id": "test-provider-receipt"}]
    Q.save_goal(workspace.data, workspace.port, record)
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == ["publish"]
    record["actions"] = [{"step_id": "publish", "plan_hash": record["proposal"]["hash"], "status": "verified", "read_back_verified": True}]
    Q.save_goal(workspace.data, workspace.port, record)
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == []
    g = Q._graph(workspace.port)
    assert g.ro_query("MATCH (:Goal)-[:OBSERVED]->(:GoalEpisode) RETURN count(*)").result_set == [[1]]
    assert g.ro_query("MATCH (:PlanRevision)-[:HAS_STEP]->(:GoalStep)-[:DEPENDS_ON]->(:GoalStep) RETURN count(*)").result_set == [[1]]


@pytest.mark.parametrize("mutation", ["dependency", "step", "source", "citation", "completion"])
def test_selected_native_freshness_cannot_be_replaced_by_json_record(workspace, mutation):
    source_id = workspace.sources[0]["id"]
    evidence = Q.call_tool(workspace.data, workspace.port, "read_company_source", {"source_id": source_id})["evidence"]
    record = goal(evidence)
    Q.create_goal(workspace.data, workspace.port, record)
    if mutation == "dependency":
        Q._graph(workspace.port).query("MATCH ()-[r:DEPENDS_ON]->() DELETE r")
    elif mutation == "step":
        Q._graph(workspace.port).query("MATCH (s:GoalStep {step_id:'inspect'}) SET s.json='{}'")
    elif mutation == "citation":
        Q._graph(workspace.port).query("MATCH ()-[r:CITES]->() DELETE r")
    elif mutation == "completion":
        Q._graph(workspace.port).query("MATCH (s:GoalStep {step_id:'inspect'}) SET s.status='completed'")
    else:
        workspace.storage[R.SOURCE_KEY][0]["payload"] = {"changed": True}
    with pytest.raises(ValueError):
        Q.ready_steps(workspace.data, workspace.port, record["id"])


def test_selected_entity_binding_ignores_unrelated_but_rejects_relevant_change(workspace):
    result = Q.call_tool(workspace.data, workspace.port, "inspect_graph_entity", {"entity_id": R._id("Graph._build_params_header")})
    seal = result["binding"]["fingerprint"]
    workspace.graph.query("CREATE (:Unrelated {id:'irrelevant'})")
    assert Q.evidence_binding(workspace.data, workspace.port, result["evidence"]) == seal
    workspace.graph.query("MATCH (n {id:$id}) SET n.changed=true", {"id": R._id("Graph._build_params_header")})
    with pytest.raises(ValueError, match="Relevant"):
        Q.evidence_binding(workspace.data, workspace.port, result["evidence"])


def test_read_catalog_rejects_raw_queries_urls_and_missing_captured_sources(workspace):
    for name, args in [("execute_cypher", {"query": "MATCH (n) DELETE n"}),
                       ("search_company_graph", {"query": "x", "limit": 1000}),
                       ("traverse_company_graph", {"entity_id": "x", "depth": 9}),
                       ("read_company_source", {"source_id": "https://private.invalid"}),
                       ("inspect_graph_entity", {"entity_id": "x", "graph": "private-control"})]:
        with pytest.raises(ValueError):
            Q.call_tool(workspace.data, workspace.port, name, args)


def test_memory_is_model_proposal_and_revisions_are_native_not_source_facts(workspace):
    record = goal()
    Q.create_goal(workspace.data, workspace.port, record)
    old_hash = record["proposal"]["hash"]
    record["revision"] = 2
    record["proposal"]["hash"] = uuid.uuid4().hex
    record["proposal"]["steps"] = record["proposal"]["steps"][:1]
    Q.save_goal(workspace.data, workspace.port, record)
    assert Q._graph(workspace.port).ro_query("MATCH (:PlanRevision)-[:SUPERSEDES]->(:PlanRevision) RETURN count(*)").result_set == [[1]]
    result = Q.call_tool(workspace.data, workspace.port, "recall_goal_memory", {"query": "compatibility"})
    assert result["evidence"][0]["kind"] == "model_proposal"
    assert result["observation"]["memories"][0]["proposal"]["hash"] != old_hash


def test_revision_reused_step_ids_never_inherit_old_completion(workspace):
    record = goal()
    record["events"] = [{"seq": 1, "type": "tool_result", "step_id": "inspect", "plan_hash": record["proposal"]["hash"], "status": "succeeded", "tool_call_id": "test", "receipt_id": "test"}]
    Q.create_goal(workspace.data, workspace.port, record)
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == ["publish"]
    record["proposal"]["hash"] = uuid.uuid4().hex
    record["revision"] += 1
    Q.save_goal(workspace.data, workspace.port, record)
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == ["inspect"]


def test_verified_release_execution_is_real_discoverable_graph_evidence(workspace):
    run = measured(workspace.plan, failed=True)
    R.record_result(workspace.data, workspace.port, workspace.plan, run)
    result = Q.call_tool(workspace.data, workspace.port, "inspect_graph_entity", {"entity_id": run["id"]})
    entity = result["observation"]["entities"][0]
    assert "ReleaseExecution" in entity["labels"]
    assert any(edge["relation"] == "MEASURED" for edge in entity["directed_relationships"])
    assert result["evidence"][0]["kind"] == "entity"  # A runner receipt is not a raw source read.
    traversed = Q.call_tool(workspace.data, workspace.port, "traverse_company_graph", {"entity_id": run["id"], "depth": 1, "limit": 15})
    assert any("ReleaseMeasurement" in e["labels"] for e in traversed["observation"]["entities"])


@pytest.mark.parametrize("change", ["cycle", "unknown", "duplicate"])
def test_native_storage_rejects_invalid_dags(workspace, change):
    record = goal()
    if change == "cycle": record["proposal"]["steps"][0]["depends_on"] = ["publish"]
    if change == "unknown": record["proposal"]["steps"][0]["depends_on"] = ["not-in-plan"]
    if change == "duplicate": record["proposal"]["steps"][1]["id"] = "inspect"
    with pytest.raises(ValueError):
        Q.create_goal(workspace.data, workspace.port, record)


def test_source_kind_cannot_be_forged_from_entity_evidence(workspace):
    result = Q.call_tool(workspace.data, workspace.port, "inspect_graph_entity", {"entity_id": R._id("Graph._build_params_header")})
    forged = copy.deepcopy(result["evidence"])
    forged[0]["kind"] = "source"
    with pytest.raises(ValueError, match="binding changed"):
        Q.evidence_binding(workspace.data, workspace.port, forged)


def test_goal_memory_never_cites_itself_during_current_revision(workspace):
    record = goal()
    Q.create_goal(workspace.data, workspace.port, record)
    result = Q.call_tool(workspace.data, workspace.port, "recall_goal_memory", {"query": "compatibility"}, record=record)
    assert result["observation"]["memories"] == [] and result["evidence"] == []


@pytest.mark.parametrize("mutation", ["episode_edge", "episode_body", "action_body"])
def test_native_observation_removal_or_mutation_blocks_ready_actions(workspace, mutation):
    record = goal()
    record["events"] = [{"seq": 1, "type": "tool_result", "step_id": "inspect", "plan_hash": record["proposal"]["hash"], "status": "succeeded", "tool_call_id": "test", "receipt_id": "test"}]
    record["actions"] = [{"step_id": "publish", "plan_hash": record["proposal"]["hash"], "status": "pending", "read_back_verified": False}]
    Q.create_goal(workspace.data, workspace.port, record)
    assert Q.ready_steps(workspace.data, workspace.port, record["id"]) == ["publish"]
    if mutation == "episode_edge":
        Q._graph(workspace.port).query("MATCH ()-[r:OBSERVED]->(:GoalEpisode) DELETE r")
    elif mutation == "episode_body":
        Q._graph(workspace.port).query("MATCH (e:GoalEpisode) SET e.json='{}'")
    else:
        Q._graph(workspace.port).query("MATCH (a:GoalAction) SET a.json='{}'")
    with pytest.raises(ValueError, match="Native"):
        Q.ready_steps(workspace.data, workspace.port, record["id"])


def test_cloud_state_graph_reused_but_never_searchable_even_from_tampered_pointer(workspace, monkeypatch):
    state_name = Q.GRAPH_NAME
    state = Q._graph(workspace.port)
    state.query("CREATE (:WorkspaceRecord {id:'operator-private',json:'private-control-data'})")
    monkeypatch.setenv("BATON_CLOUD_STATE_GRAPH", state_name)
    monkeypatch.setattr(R, "_workspace_read", lambda data, port, key, default=None, **_: copy.deepcopy(workspace.storage.get(key, default)))
    pointer = "a" * 24
    workspace.storage["current.json"] = {"id": pointer}
    workspace.storage["snapshots/" + pointer + ".json"] = {"id": pointer, "graph": state_name, "sources": []}
    db = R._connect(workspace.port)
    monkeypatch.setattr(db, "list_graphs", lambda: (_ for _ in ()).throw(AssertionError("GRAPH.LIST must not be required")))
    assert Q._graph(workspace.port).name == state_name
    assert state_name not in dict(Q._graphs(workspace.data, workspace.port))
    result = Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": "private-control-data"})
    assert result["observation"]["entities"] == []


def test_expired_request_deadline_prevents_native_read_and_write(workspace):
    import time
    with Q.deadline_scope(time.monotonic() - 1):
        with pytest.raises(RuntimeError, match="deadline"):
            Q.create_goal(workspace.data, workspace.port, goal())
        with pytest.raises(RuntimeError, match="deadline"):
            Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": "Graph"})
