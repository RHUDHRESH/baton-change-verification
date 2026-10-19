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
    assert all(entity["graph"] != state_name and "private-control-data" not in json.dumps(entity) for entity in result["observation"]["entities"])


def test_expired_request_deadline_prevents_native_read_and_write(workspace):
    import time
    with Q.deadline_scope(time.monotonic() - 1):
        with pytest.raises(RuntimeError, match="deadline"):
            Q.create_goal(workspace.data, workspace.port, goal())
        with pytest.raises(RuntimeError, match="deadline"):
            Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": "Graph"})


@pytest.mark.parametrize("query", ["redis-py 8.1.0 failure", "REDIS\u2011PY / 8.1.0: failures", "Why does redis-py 8.1.0 fail?"])
def test_native_multiterm_search_discovers_actual_failed_measurements(workspace, query):
    run = measured(workspace.plan)
    run.update(verification_status="failed", decision="blocked")
    for check in run["environments"][1]["checks"][2:]:
        check["status"] = "failed"
    R.record_result(workspace.data, workspace.port, workspace.plan, run)
    source_ids = [source["id"] for source in workspace.sources]
    result = Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": query, "limit": 5})
    entities = result["observation"]["entities"]
    failed = [e for e in entities if "ReleaseMeasurement" in e["labels"] and e["properties"]["record"]["status"] == "failed"]
    assert len(failed) == 2
    assert all(e["properties"]["record"]["environment_id"] == "redis-8.1.0" for e in failed)
    assert all("8.1.0" in e["matched_search_terms"] and e["term_overlap_score"] >= 3 for e in failed)
    assert "bounded_native_term_overlap" in result["observation"]["search_strategy"]
    assert result["observation"]["search_version"] == Q.SEARCH_VERSION == "native-terms-v1"
    assert {term["match"] for term in result["observation"]["search_terms"]} >= {"redis", "py", "8.1.0", "fail"}
    assert [source["id"] for source in workspace.sources] == source_ids
    assert {e["kind"] for e in result["evidence"]} == {"entity"}


def test_search_ranks_across_graphs_not_first_graph_first(workspace, monkeypatch):
    graph = workspace.graph
    graph.query("CREATE (:WorkItem {id:'low-match',title:'redis'})")
    run = measured(workspace.plan)
    run.update(verification_status="failed", decision="blocked")
    run["environments"][1]["checks"][2]["status"] = "failed"
    R.record_result(workspace.data, workspace.port, workspace.plan, run)
    # Same real graph under two graph handles exercises global rank/limit rather
    # than allowing the first matching graph to consume the output budget.
    first = Q._CheckedGraph(Q._connect(workspace.port).select_graph("first_search_" + uuid.uuid4().hex))
    first.query("CREATE (:WorkItem {id:'first-low',title:'redis'})")
    monkeypatch.setattr(Q, "_graphs", lambda *a: [(first.name, first), (graph.name, Q._CheckedGraph(graph))])
    try:
        result = Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": "redis-py 8.1.0 failure", "limit": 1})
        assert result["observation"]["entities"][0]["graph"] == graph.name
        assert "ReleaseMeasurement" in result["observation"]["entities"][0]["labels"]
    finally:
        first.delete()


@pytest.mark.parametrize("query", ["quuxzyglorpzzzz", "why is the", "| * @ {}"])
def test_genuinely_empty_multiterm_search_never_fabricates_evidence(workspace, query):
    result = Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": query})
    assert result["observation"]["entities"] == [] and result["evidence"] == []
    assert result["observation"]["search_version"] == Q.SEARCH_VERSION


def test_untrusted_search_operators_are_only_data_not_graph_language(workspace):
    before = workspace.graph.ro_query("MATCH (n) RETURN count(n)").result_set
    result = Q.call_tool(workspace.data, workspace.port, "search_company_graph", {"query": "redis-py 8.1.0 failure' | * ) MATCH (n) DETACH DELETE n //", "limit": 3})
    assert workspace.graph.ro_query("MATCH (n) RETURN count(n)").result_set == before
    assert len(result["observation"]["entities"]) <= 3
    assert len(result["observation"]["search_terms"]) <= 12


def test_source_version_entity_exposes_exact_url_mapped_raw_source_ids(workspace, monkeypatch):
    source = next(s for s in workspace.sources if s.get("path") == "falkordb/graph.py")
    original = Q._sources
    loads = []
    def catalog(*args):
        loads.append(True)
        return original(*args)
    monkeypatch.setattr(Q, "_sources", catalog)
    result = Q.call_tool(workspace.data, workspace.port, "inspect_graph_entity", {"entity_id": R._id(source["id"])})
    entity = result["observation"]["entities"][0]
    assert entity["id"] != source["id"]  # Scoped graph identity is not a source API identity.
    assert entity["source_ids"] == [source["id"]]
    assert len(loads) == 1 and result["evidence"][0]["kind"] == "entity"
    raw = Q.call_tool(workspace.data, workspace.port, "read_company_source", {"source_id": entity["source_ids"][0]})
    assert raw["observation"]["source_id"] == source["id"] and raw["evidence"][0]["kind"] == "source"


def test_entity_source_mapping_uses_exact_urls_not_scoped_id_guessing(workspace):
    identity = "looks-like-src-" + "a" * 16
    workspace.graph.query("CREATE (:ReleaseEvidence {id:$id,json:$json})", {"id": identity, "json": json.dumps({"url": "https://api.github.com/repos/FalkorDB/falkordb-py/unmatched-public-path"})})
    result = Q.call_tool(workspace.data, workspace.port, "inspect_graph_entity", {"entity_id": identity})
    assert result["observation"]["entities"][0]["source_ids"] == []
    assert result["evidence"][0]["kind"] == "entity"
