"""Pinned public evidence, live FalkorDB obligations and adversarial bindings.

Provider tests mock only the provider; graph integration exercises real Cypher.
No production code reads the public capture fixture.
"""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid

import pytest

from server import release_graph as R
from server import release_contract as C


@pytest.fixture
def sources():
    return json.loads((Path(__file__).parents[1] / "fixtures/release_py211/public_sources.json").read_text(encoding="utf-8"))


@pytest.fixture
def live(tmp_path, monkeypatch, sources, release_engine):
    port, db = release_engine
    name = "test_release_py211_" + uuid.uuid4().hex
    monkeypatch.setattr(R, "GRAPH_NAME", name)
    monkeypatch.setattr(R, "_connect", lambda _port, **_: db)
    storage = {R.SOURCE_KEY: sources}
    monkeypatch.setattr(R.public, "read", lambda data, key, default=None: copy.deepcopy(storage.get(key, default)))
    monkeypatch.setattr(R.public, "write", lambda data, key, value: storage.__setitem__(key, copy.deepcopy(value)))
    plan = R.build_plan(tmp_path, port, C.CHANGE_ID, investigate=False)
    plan["id"] = "plan-" + uuid.uuid4().hex
    graph = db.select_graph(name)
    yield SimpleNamespace(data=tmp_path, port=port, graph=graph, plan=plan, sources=sources, storage=storage)
    graph.delete()


@pytest.fixture(scope="session")
def release_engine(tmp_path_factory):
    """Own an isolated official engine in Docker; optionally use local test port.

    Absence/failure is a test failure, never a skipped graph proof. Every test
    writes a fresh named graph and deletes only that graph during teardown.
    """
    process = None
    binary, module = os.environ.get("BATON_TEST_REDIS"), os.environ.get("BATON_TEST_MODULE")
    if binary or module:
        assert binary and module, "Both BATON_TEST_REDIS and BATON_TEST_MODULE are required"
        directory = tmp_path_factory.mktemp("release-engine")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        process = subprocess.Popen([binary, "--port", str(port), "--dir", str(directory), "--loadmodule", module,
                                    "--save", "", "--logfile", str(directory / "redis.log")])
    else:
        port = int(os.environ.get("BATON_TEST_FALKORDB_PORT", "6379"))
    # Explicitly local: cloud graph credentials/configuration must not redirect
    # integration tests to a managed workspace graph.
    local_env = {"FALKORDB_HOST": "127.0.0.1", "FALKORDB_TLS": "0", "FALKORDB_USERNAME": "", "FALKORDB_PASSWORD": ""}
    try:
        deadline = time.monotonic() + (15 if process else 1)
        while True:
            try:
                with patch.dict(os.environ, local_env):
                    db = R.G.connect(port)
                break
            except R.G.Unreachable:
                if time.monotonic() >= deadline:
                    pytest.fail("Real release graph proof requires a reachable local FalkorDB test engine")
                time.sleep(.1)
        yield port, db
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)


def measured(plan, failed=False):
    return {"id": "run-" + uuid.uuid4().hex, "plan_id": plan["id"], "plan_hash": plan["plan_hash"],
            "source_commit": C.SOURCE_COMMIT, "evidence_status": "verified", "runner": {"verified": True},
            "evidence": {"sha256": "a" * 64}, "verification_status": "failed" if failed else "passed",
            "decision": "blocked" if failed else "passed", "environments": [
                {**environment, "checks": [{"id": check, "status": "failed" if failed and i == 0 and j == 0 else "passed"}
                                            for j, check in enumerate(C.CHECK_IDS)]}
                for i, environment in enumerate(C.ENVIRONMENTS)]}


def test_real_public_capture_is_pinned_and_bounded(sources):
    R._validate_sources(sources)
    assert len(C.encode(sources).encode()) < 900_000
    assert {s["path"]: s["content_sha256"] for s in sources if s.get("path") in C.SOURCE_HASHES} == C.SOURCE_HASHES
    pull = next(s for s in sources if s["url"].endswith("/pulls/212"))["payload"]
    assert pull["merged"] and pull["merge_commit_sha"] == C.SOURCE_COMMIT


def test_real_graph_derives_four_checks_and_inherited_async_witness(live):
    plan = live.plan
    assert plan["plan_status"] == "ready"
    assert C.selected_ids(plan) == list(C.CHECK_IDS)
    assert R.revalidate(live.data, live.port, plan)
    assert plan["plan_hash"] == C.plan_hash(plan)
    assert {w["surface"] for w in plan["witness_paths"]} == {"sync", "async"}
    for witness in plan["witness_paths"]:
        assert "RECURSES" in witness["relations"]
        assert witness["test_span"]["source_sha256"] in C.SOURCE_HASHES.values()
        assert witness["test_span"]["start_line"] <= witness["test_span"]["end_line"]
        assert {s["symbol"] for s in witness["source_spans"]} >= {"Graph._build_params_header", "stringify_param_value"}
        if witness["surface"] == "async":
            assert "INHERITS" in witness["relations"]
            assert "AsyncGraph._query" in witness["nodes"]
            assert {"source": "AsyncGraph", "relation": "INHERITS", "target": "Graph"} in witness["edges"]
    behavior = live.graph.ro_query("MATCH (n:ReleaseEvidence {id:$id}) RETURN n.json", {"id": R._id("behavior")}).result_set
    assert "reject" in json.loads(behavior[0][0])["accepted"].lower()


def test_unrelated_graph_changes_do_not_invalidate_plan(live):
    live.graph.query("CREATE (:Unrelated {id:$id,value:$value})", {"id": "other-work", "value": "updated"})
    live.graph.query("CREATE (:Account {id:$id})", {"id": "not-a-release-contributor"})
    assert R.revalidate(live.data, live.port, live.plan)


def test_unrelated_edges_do_not_change_scoped_release_binding(live):
    fingerprint, plan_hash = live.plan["binding_fingerprint"], live.plan["plan_hash"]
    live.graph.query("CREATE (a:Unrelated {id:'outside-a'})-[:UNRELATED]->(b:Unrelated {id:'outside-b'})")
    live.graph.query("MATCH (c:ReleaseEvidence {id:$change}),(a:Unrelated {id:'outside-a'}) CREATE (c)-[:UNRELATED]->(a)",
                     {"change": R._id("change")})
    assert live.graph.ro_query("MATCH ()-[r:UNRELATED]->() RETURN count(r)").result_set == [[2]]
    assert R._fingerprint(live.graph) == fingerprint
    assert R.revalidate(live.data, live.port, live.plan)
    checks, witnesses = R._traverse(live.graph)
    assert checks == live.plan["required_checks"] and witnesses == live.plan["witness_paths"]
    assert C.plan_hash(live.plan) == plan_hash


@pytest.mark.parametrize("relation", ["INHERITS", "RECURSES", "CALLS", "BOUND_TO", "REQUIRES_ENVIRONMENT"])
def test_relevant_graph_binding_removal_invalidates_plan(live, relation):
    assert relation in {"INHERITS", "RECURSES", "CALLS", "BOUND_TO", "REQUIRES_ENVIRONMENT"}
    live.graph.query("MATCH (:ReleaseEvidence {binding_scope:$scope})-[r:" + relation + "]->(:ReleaseEvidence) DELETE r", {"scope": R.SCOPE})
    with pytest.raises(ValueError, match="graph binding"):
        R.revalidate(live.data, live.port, live.plan)


def test_missing_inheritance_cannot_silently_degrade_to_two_checks(live):
    live.graph.query("MATCH (:ReleaseEvidence)-[r:INHERITS]->(:ReleaseEvidence) DELETE r")
    checks, _ = R._traverse(live.graph)
    assert len(checks) == 2 and {c["surface"] for c in checks} == {"sync"}
    with pytest.raises(ValueError):
        R.revalidate(live.data, live.port, live.plan)


def test_missing_source_inheritance_produces_explicit_incomplete_plan(live, monkeypatch):
    altered = copy.deepcopy(live.sources)
    source = next(s for s in altered if s.get("path") == "falkordb/asyncio/graph.py")
    source["content"] = source["content"].replace("class AsyncGraph(Graph):", "class AsyncGraph:")
    # Exercise extractor semantics in isolation: production hash validation would
    # reject this altered source before extraction.
    nodes, edges, missing = R._derive(altered)
    assert not any(e["kind"] == "INHERITS" for e in edges)
    assert any("inheritance" in problem for problem in missing)
    fresh_name = "test_incomplete_" + uuid.uuid4().hex
    monkeypatch.setattr(R, "GRAPH_NAME", fresh_name)
    monkeypatch.setattr(R, "_capture_sources", lambda data, **_: altered)
    try:
        plan = R.build_plan(live.data, live.port, C.CHANGE_ID, investigate=False)
        assert plan["plan_status"] == "incomplete"
        assert any("Expected four" in limit for limit in plan["limitations"])
        with pytest.raises(ValueError, match="incomplete"):
            R.revalidate(live.data, live.port, plan)
    finally:
        R._connect(live.port).select_graph(fresh_name).delete()


@pytest.mark.parametrize("mutation", ["payload", "content", "version", "missing"])
def test_source_mutation_invalidates_plan(live, mutation):
    sources = live.storage[R.SOURCE_KEY]
    if mutation == "payload":
        sources[0]["payload"]["body"] = "untrusted changed text"
    elif mutation == "content":
        next(s for s in sources if "content" in s)["content"] += "\n# changed"
    elif mutation == "version":
        sources[0]["sha256"] = "b" * 64
    else:
        sources.pop()
    with pytest.raises(ValueError):
        R.revalidate(live.data, live.port, live.plan)


@pytest.mark.parametrize("field", ["required_checks", "environments", "source_hashes", "python_image", "policy_version", "source_commit"])
def test_mutated_plan_even_with_recomputed_hash_is_denied(live, field):
    plan = copy.deepcopy(live.plan)
    if isinstance(plan[field], list):
        plan[field].pop()
    elif isinstance(plan[field], dict):
        plan[field] = {}
    else:
        plan[field] = "changed"
    plan["plan_hash"] = C.plan_hash(plan)
    with pytest.raises(ValueError):
        R.revalidate(live.data, live.port, plan)


@pytest.mark.parametrize("failed", [False, True])
def test_real_graph_records_complete_pass_or_blocked_matrix(live, failed):
    run = measured(live.plan, failed)
    receipt = R.record_result(live.data, live.port, live.plan, run)
    assert receipt["verified"] is True and receipt["release_passed"] is (not failed)
    assert receipt["checks"] == 8 and receipt["plan_hash"] == live.plan["plan_hash"]
    assert R.record_result(live.data, live.port, live.plan, run) == receipt
    assert R.revalidate(live.data, live.port, live.plan)  # results are outside source bindings
    rows = live.graph.ro_query("MATCH (r:ReleaseExecution {id:$id})-[:MEASURED]->(m)-[:CHECKED]->(c),"
                               "(m)-[:IN_ENVIRONMENT]->(e) RETURN m.json,c.json,e.json", {"id": run["id"]}).result_set
    assert len(rows) == 8


@pytest.mark.parametrize("mutation", ["missing_check", "duplicate_check", "missing_env", "wrong_env", "wrong_plan", "wrong_source", "unverified", "false_pass", "unknown_check"])
def test_incomplete_or_misbound_measurements_cannot_certify(live, mutation):
    run = measured(live.plan)
    if mutation == "missing_check":
        run["environments"][0]["checks"].pop()
    elif mutation == "duplicate_check":
        run["environments"][0]["checks"][0] = run["environments"][0]["checks"][1].copy()
    elif mutation == "missing_env":
        run["environments"].pop()
    elif mutation == "wrong_env":
        run["environments"][0]["redis_version"] = "7.1.0"
    elif mutation == "wrong_plan":
        run["plan_hash"] = "b" * 64
    elif mutation == "wrong_source":
        run["source_commit"] = "0" * 40
    elif mutation == "unverified":
        run["runner"]["verified"] = False
    elif mutation == "false_pass":
        run["environments"][0]["checks"][0]["status"] = "failed"
    else:
        run["environments"][0]["checks"][0]["id"] = "tests/invented.py::test_whatever"
    with pytest.raises(ValueError):
        R.record_result(live.data, live.port, live.plan, run)
    assert not live.graph.ro_query("MATCH (r:ReleaseExecution) RETURN r.id").result_set


def test_result_graph_readback_must_match_every_check_and_environment(live):
    original = live.graph.ro_query
    def damaged_readback(query, params=None):
        result = original(query, params)
        if "RETURN m.id,m.json,c.id,c.json,e.id,e.json" in query:
            return SimpleNamespace(result_set=result.result_set[:-1])
        return result
    with patch.object(live.graph, "ro_query", side_effect=damaged_readback), patch.object(R._connect(live.port), "select_graph", return_value=live.graph):
        with pytest.raises(RuntimeError, match="readback"):
            R.record_result(live.data, live.port, live.plan, measured(live.plan))


def test_tools_reject_cross_scope_arbitrary_queries_and_unpinned_sources(live):
    for name, arguments in [("execute_cypher", {"query": "MATCH (n) DELETE n"}),
                            ("release_follow_impact", {"change_id": "other/repo#1"}),
                            ("release_read_change", {"change_id": C.CHANGE_ID, "query": "anything"}),
                            ("release_read_source", {"source_id": "not-captured"})]:
        with pytest.raises(ValueError):
            R.call_tool(live.data, live.port, name, arguments, plan=live.plan)
    result = R.call_tool(live.data, live.port, "release_follow_impact", {"change_id": C.CHANGE_ID}, plan=live.plan)
    assert len(json.loads(result["content"][0]["text"])["required_checks"]) == 4


def test_cloud_failure_never_falls_back_to_fixture(tmp_path):
    with patch.object(R.public, "read", side_effect=RuntimeError("cloud unavailable")), patch.object(R.public, "fetch") as fetch:
        with pytest.raises(RuntimeError, match="cloud unavailable"):
            R.build_plan(tmp_path, 6379, C.CHANGE_ID, investigate=False)
        fetch.assert_not_called()


def test_provider_absence_is_explicit_failure_with_no_fake_ai(live, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = R._investigate(live.data, live.port, live.plan)
    assert result["status"] == "failed" and result["summary"] == ""
    assert not result["receipts"] and not result["trace"]
    assert len(live.plan["required_checks"]) == 4


@pytest.mark.parametrize("order", [("impact", "source", "change"), ("change", "source", "impact")])
def test_actual_tool_loop_uses_adaptive_provider_selections(live, monkeypatch, order):
    from contextlib import nullcontext
    from server import graph_agent, control
    source_id = next(s["id"] for s in live.sources if s.get("path") == "falkordb/helpers.py")
    inspections = {"impact": ("release_follow_impact", {"change_id": C.CHANGE_ID}),
                   "source": ("release_read_source", {"source_id": source_id}),
                   "change": ("release_read_change", {"change_id": C.CHANGE_ID})}
    selections = [inspections[name] for name in order] + [
        ("release_explain", {"summary": "Both public surfaces invoke the inherited header and recursive map serializer; empty and backtick keys are rejected.", "source_ids": [source_id]})]
    calls = []
    def provider(messages, tools, timeout, tool_choice, allow_final):
        assert allow_final == (len(calls) >= 3)
        assert tool_choice == ("auto" if allow_final else "required")
        assert "release_explain" not in messages[0]["content"]
        assert "rejects literal backticks" not in messages[0]["content"]
        runtime = messages[1]["content"]
        state = json.JSONDecoder().raw_decode(runtime.split(": ", 1)[1])[0]
        expected_seen = set(order[:len(calls)])
        assert state["observed"] == {"change": "change" in expected_seen, "impact": "impact" in expected_seen,
                                     "production-source": "source" in expected_seen}
        assert state["missing"] == [name for name, seen in state["observed"].items() if not seen]
        assert state["offered_tools"] == [tool["function"]["name"] for tool in tools]
        source_tool = next(tool["function"] for tool in tools if tool["function"]["name"] == "release_read_source")
        offered_source_ids = source_tool["parameters"]["properties"]["source_id"]["enum"]
        production = [s for s in live.plan["source_versions"] if s.get("path", "").startswith("falkordb/")]
        if "source" not in expected_seen:
            assert offered_source_ids == [s["id"] for s in production]
            assert state["required_production_sources"] == [{"id": s["id"], "path": s["path"]} for s in production]
        else:
            assert offered_source_ids == [s["id"] for s in live.plan["source_versions"]]
            assert "required_production_sources" not in state
        assert ("release_explain" in runtime) == (len(calls) == 3)
        assert ("no ordinary prose" in runtime) == (len(calls) < 3)
        name, args = selections[len(calls)]
        calls.append((name, tools))
        return {"content": None, "tool_calls": [{"id": str(len(calls)), "function": {"name": name, "arguments": json.dumps(args)}}]}, {
            "id": "actual-protocol-test-" + str(len(calls)), "model": "mock-provider-only", "usage": {"total_tokens": 100}, "response_sha256": "c" * 64}
    fake_control = SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext())
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: fake_control)
    monkeypatch.setattr(graph_agent, "completion", provider)
    result = R._investigate(live.data, live.port, live.plan)
    assert result["status"] == "succeeded", result
    assert [row["request"]["params"]["name"] for row in result["trace"]] == [name for name, _ in selections]
    assert len(result["receipts"]) == result["provider_calls"] == 4
    assert live.storage["quotas/" + R.public.now()[:10] + ".json"]["used"] == 4
    assert C.selected_ids(live.plan) == list(C.CHECK_IDS)


def test_provider_projection_preserves_all_obligations_and_archives_full_graph(live):
    result = R.call_tool(live.data, live.port, "release_follow_impact", {"change_id": C.CHANGE_ID}, plan=live.plan)
    projection = R._provider_view("release_follow_impact", result, 2)
    assert [c["id"] for c in projection["observation"]["required_checks"]] == list(C.CHECK_IDS)
    assert {p["surface"] for p in projection["observation"]["paths"]} == {"sync", "async"}
    assert "INHERITS" in next(p for p in projection["observation"]["paths"] if p["surface"] == "async")["relations"]
    assert projection["archive"]["result_sha256"] == C.sha(C.encode(result))
    assert len(C.encode(projection)) < len(C.encode(result)) / 2


@pytest.mark.parametrize("prefix", [(), ("change", "impact"), ("change", "source"), ("impact", "source")])
def test_ai_cannot_drop_checks_or_finish_before_graph_inspection(live, monkeypatch, prefix):
    from contextlib import nullcontext
    from server import graph_agent, control
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    source_id = next(s["id"] for s in live.sources if s.get("path") == "falkordb/helpers.py")
    inspections = {"change": ("release_read_change", {"change_id": C.CHANGE_ID}),
                   "impact": ("release_follow_impact", {"change_id": C.CHANGE_ID}),
                   "source": ("release_read_source", {"source_id": source_id})}
    selections = [inspections[name] for name in prefix] + [("release_explain", {})]
    calls = []
    def provider(messages, tools, **kwargs):
        assert "release_explain" not in {tool["function"]["name"] for tool in tools}
        name, args = selections[len(calls)]
        calls.append(name)
        return {"tool_calls": [{"id": str(len(calls)), "function": {"name": name, "arguments": C.encode(args)}}]}, {"id": "provider-test", "model": "test", "usage": {"total_tokens": 100}}
    monkeypatch.setattr(graph_agent, "completion", provider)
    result = R._investigate(live.data, live.port, live.plan)
    assert result["status"] == "failed" and "premature" in result["error"]
    assert C.selected_ids(live.plan) == list(C.CHECK_IDS)


@pytest.mark.parametrize("mutation", ["missing", "status", "contents", "check_edge", "environment_edge", "root_certificate", "change_edge", "extra"])
def test_publication_rechecks_live_complete_measurements_not_stored_certificate(live, mutation):
    run = measured(live.plan, failed=True)
    run["graph_receipt"] = R.record_result(live.data, live.port, live.plan, run)
    assert R.verify_result(live.data, live.port, live.plan, run) == run["graph_receipt"]
    result = {**run["environments"][0]["checks"][0], "check_id": C.CHECK_IDS[0], "environment_id": C.ENVIRONMENTS[0]["id"]}
    identity = R._measurement_id(run["id"], result)
    if mutation == "missing":
        live.graph.query("MATCH (m:ReleaseMeasurement {id:$id}) DETACH DELETE m", {"id": identity})
    elif mutation in {"status", "contents"}:
        changed = {**result, "status": "passed"} if mutation == "status" else {**result, "failure_excerpt": "altered despite unchanged status"}
        live.graph.query("MATCH (m:ReleaseMeasurement {id:$id}) SET m.json=$json", {"id": identity, "json": C.encode(changed)})
    elif mutation == "check_edge":
        live.graph.query("MATCH (m:ReleaseMeasurement {id:$id})-[r:CHECKED]->() DELETE r", {"id": identity})
    elif mutation == "environment_edge":
        live.graph.query("MATCH (m:ReleaseMeasurement {id:$id})-[r:IN_ENVIRONMENT]->() DELETE r", {"id": identity})
        live.graph.query("MATCH (m:ReleaseMeasurement {id:$id}),(e:ReleaseEvidence {id:$environment}) CREATE (m)-[:IN_ENVIRONMENT]->(e)",
                         {"id": identity, "environment": R._id(C.ENVIRONMENTS[1]["id"])})
    elif mutation == "root_certificate":
        live.graph.query("MATCH (r:ReleaseExecution {id:$id}) SET r.json=$json", {"id": run["id"], "json": C.encode({**run["graph_receipt"], "release_passed": True})})
    elif mutation == "change_edge":
        live.graph.query("MATCH (r:ReleaseExecution {id:$id})-[e:VERIFIES]->() DELETE e", {"id": run["id"]})
    else:
        live.graph.query("MATCH (r:ReleaseExecution {id:$id}) CREATE (r)-[:MEASURED]->(:ReleaseMeasurement {id:'extra',json:'{}'})", {"id": run["id"]})
    with pytest.raises((ValueError, RuntimeError), match="graph"):
        R.verify_result(live.data, live.port, live.plan, run)
    # A failed readonly check must not silently restore the expected graph data.
    with pytest.raises((ValueError, RuntimeError)):
        R.verify_result(live.data, live.port, live.plan, run)


def test_release_connection_has_bounded_read_and_connect_timeouts(monkeypatch):
    import falkordb
    monkeypatch.setattr(R.time, "monotonic", lambda: 100)
    with patch.object(falkordb, "FalkorDB") as client:
        R._connect(6379, deadline=102)
        assert client.call_args.kwargs["socket_timeout"] == 2
        assert client.call_args.kwargs["socket_connect_timeout"] == 2
        client.return_value.connection.ping.assert_called_once()


def test_release_cold_capture_has_one_total_deadline(tmp_path, sources, monkeypatch):
    clock = [0]
    monkeypatch.setattr(R.time, "monotonic", lambda: clock[0])
    calls = []
    by_url = {s["url"]: s for s in sources}
    def fetch(path, deadline):
        calls.append(path)
        clock[0] += 10
        R._remaining(deadline)
        return copy.deepcopy(by_url["https://api.github.com" + path])
    monkeypatch.setattr(R, "_fetch_source", fetch)
    with patch.object(R.public, "read", return_value=None), patch.object(R.public, "write") as store:
        with pytest.raises(RuntimeError, match="deadline"):
            R._capture_sources(tmp_path, deadline=100)
        assert len(calls) == 4
        store.assert_not_called()


def test_trickled_source_body_cannot_extend_total_capture_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr(R.time, "monotonic", lambda: clock[0])
    class Response:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read1(self, size):
            clock[0] += 1
            return b" "
    with patch.object(R.urllib.request, "urlopen", return_value=Response()) as request:
        with pytest.raises(RuntimeError, match="deadline"):
            R._fetch_source("/repos/" + C.REPOSITORY + "/issues/211", deadline=3)
        assert clock[0] == 3
        assert request.call_args.kwargs["timeout"] == 3


def test_total_build_deadline_stops_before_graph_writes(live, monkeypatch):
    clock = [0]
    monkeypatch.setattr(R.time, "monotonic", lambda: clock[0])
    def expired_capture(data, **kwargs):
        clock[0] = R.MAX_BUILD_SECONDS + 1
        return live.sources
    monkeypatch.setattr(R, "_capture_sources", expired_capture)
    with patch.object(live.graph, "query") as query:
        with pytest.raises(RuntimeError, match="deadline"):
            R.build_plan(live.data, live.port, C.CHANGE_ID, investigate=False)
        query.assert_not_called()


def test_provider_timeout_uses_remaining_budget_and_late_tool_is_rejected(live, monkeypatch):
    from contextlib import nullcontext
    from server import graph_agent, control
    clock = [100]
    monkeypatch.setattr(R.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    timeouts = []
    def late_provider(messages, tools, timeout, tool_choice, allow_final):
        assert tool_choice == "required"
        assert allow_final is False
        timeouts.append(timeout)
        clock[0] += 5
        return {"tool_calls": [{"id": "1", "function": {"name": "release_read_change", "arguments": C.encode({"change_id": C.CHANGE_ID})}}]}, {"id": "test", "model": "test", "usage": {"total_tokens": 100}}
    monkeypatch.setattr(graph_agent, "completion", late_provider)
    with patch.object(R, "call_tool") as tool:
        result = R._investigate(live.data, live.port, live.plan, deadline=103)
        assert result["status"] == "failed" and "deadline" in result["error"]
        assert timeouts == [3]
        tool.assert_not_called()


def test_actual_second_turn_no_tool_diagnostic_stays_failed_with_updated_runtime_state(live, monkeypatch):
    from contextlib import nullcontext
    from server import graph_agent, control
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    # Observed production shape: no evidence of an undeclared terminal call.
    diagnostics = {"provider": "Groq", "http_status": 400, "error": {"type": "invalid_request_error", "code": "tool_use_failed", "param": "tool_choice", "message": "Tool choice is required, but model did not call a tool"},
                   "response_sha256": "b" * 64, "failed_generation_tool_names": []}
    calls = []
    def provider(messages, tools, timeout, tool_choice, allow_final):
        calls.append(tool_choice)
        assert allow_final is False
        if len(calls) == 2:
            runtime = messages[1]["content"]
            state = json.loads(runtime.split(": ", 1)[1].split(". Return exactly", 1)[0])
            assert state["observed"] == {"change": True, "impact": False, "production-source": False}
            assert state["missing"] == ["impact", "production-source"]
            assert "release_explain" not in runtime
            assert "ONE offered tool call" in runtime and "no ordinary prose" in runtime
            raise graph_agent.ProviderHTTPError("Groq tool selection returned HTTP 400; diagnostics recorded", diagnostics)
        return {"tool_calls": [{"id": "1", "function": {"name": "release_read_change", "arguments": C.encode({"change_id": C.CHANGE_ID})}}]}, {
            "id": "provider-test", "model": "test", "finish_reason": "tool_calls", "usage": {"total_tokens": 564}}
    monkeypatch.setattr(graph_agent, "completion", provider)
    result = R._investigate(live.data, live.port, live.plan)
    assert result["status"] == "failed" and result["summary"] == ""
    assert calls == ["required", "required"] and result["provider_calls"] == 2
    assert len(result["trace"]) == 1 and result["trace"][0]["request"]["params"]["name"] == "release_read_change"
    assert result["receipts"][-1] == diagnostics and result["used_tokens"] == 564
    assert result["model"] == "test"  # HTTP errors do not invent a generation model/usage.


def test_runtime_state_is_included_in_provider_input_budget(live, monkeypatch):
    from contextlib import nullcontext
    from server import graph_agent, control
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    monkeypatch.setattr(R, "_investigation_state", lambda *a: "trusted state " * 5000)
    with patch.object(graph_agent, "completion") as provider:
        result = R._investigate(live.data, live.port, live.plan)
        provider.assert_not_called()
    assert result["status"] == "failed" and "token budget" in result["error"]
    assert result["provider_calls"] == 0 and not result["receipts"]


def test_documentation_observation_never_satisfies_production_source_gate(live):
    production_ids = {s["id"] for s in live.plan["source_versions"] if s.get("path", "").startswith("falkordb/")}
    docs = next(s for s in live.plan["source_versions"] if s.get("path") == "docs/source/falkordb.asyncio.rst")
    runtime = R._investigation_state({"release_read_change", "release_follow_impact", "release_read_source"},
                                    {docs["id"]}, production_ids, R.TOOLS, live.plan["source_versions"])
    state = json.JSONDecoder().raw_decode(runtime.split(": ", 1)[1])[0]
    assert state["observed"] == {"change": True, "impact": True, "production-source": False}
    assert state["missing"] == ["production-source"]
    assert {s["id"] for s in state["required_production_sources"]} == production_ids
    assert "release_explain" not in state["offered_tools"] and "no ordinary prose" in runtime


def test_agent_cannot_select_documentation_outside_initial_production_enum(live, monkeypatch):
    from contextlib import nullcontext
    from server import graph_agent, control
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    docs = next(s for s in live.plan["source_versions"] if s.get("path") == "docs/source/falkordb.asyncio.rst")
    def provider(messages, tools, timeout, tool_choice, allow_final):
        source = next(t["function"] for t in tools if t["function"]["name"] == "release_read_source")
        assert docs["id"] not in source["parameters"]["properties"]["source_id"]["enum"]
        assert tool_choice == "required" and allow_final is False
        return {"tool_calls": [{"id": "1", "function": {"name": "release_read_source", "arguments": C.encode({"source_id": docs["id"]})}}]}, {
            "id": "provider-test", "model": "test", "finish_reason": "tool_calls", "usage": {"total_tokens": 100}}
    monkeypatch.setattr(graph_agent, "completion", provider)
    with patch.object(R, "call_tool") as tool:
        result = R._investigate(live.data, live.port, live.plan)
        tool.assert_not_called()
    assert result["status"] == "failed" and "offered production source" in result["error"]
    assert result["provider_calls"] == 1 and result["trace"][0]["result"]["isError"] is True


@pytest.mark.parametrize("extra_inspection", [False, True])
def test_ready_native_final_preserves_actual_text_receipt_and_context_provenance(live, monkeypatch, extra_inspection):
    from contextlib import nullcontext
    from server import graph_agent, control
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    source_id = next(s["id"] for s in live.sources if s.get("path") == "falkordb/helpers.py")
    inspections = [("release_read_change", {"change_id": C.CHANGE_ID}),
                   ("release_follow_impact", {"change_id": C.CHANGE_ID}),
                   ("release_read_source", {"source_id": source_id})]
    if extra_inspection:
        inspections.append(("release_read_source", {"source_id": source_id}))
    text = "The inspected graph links both query surfaces to the inherited parameter header and recursive serializer, requiring both regression pairs."
    final_message = {"role": "assistant", "content": text}
    final_receipt = {"id": "actual-final-test", "model": "mock-provider-only", "finish_reason": "stop",
                     "response_sha256": "a" * 64, "usage": {"total_tokens": 120}}
    requests = []
    def provider(messages, tools, timeout, tool_choice, allow_final):
        turn = len(requests)
        requests.append(messages)
        assert allow_final == (turn >= 3)
        assert tool_choice == ("auto" if turn >= 3 else "required")
        if turn >= 3:
            assert "normal final answer" in messages[1]["content"] and source_id in messages[1]["content"]
        if turn == len(inspections):
            return final_message, final_receipt
        name, arguments = inspections[turn]
        return {"tool_calls": [{"id": str(turn), "function": {"name": name, "arguments": C.encode(arguments)}}]}, {
            "id": "inspected-" + str(turn), "model": "mock-provider-only", "finish_reason": "tool_calls", "usage": {"total_tokens": 100}}
    monkeypatch.setattr(graph_agent, "completion", provider)
    result = R._investigate(live.data, live.port, live.plan)
    assert result["status"] == "succeeded" and result["summary"] == text
    assert result["final_protocol"] == "native_assistant_stop"
    assert result["actual_final_response"] == {"message": final_message, "receipt": final_receipt}
    assert result["receipts"][-1] == final_receipt
    assert result["observed_source_ids"] == result["source_ids"] == [source_id]
    assert result["source_binding"] == "runtime-observed context; not model-selected citations"
    assert len(result["trace"]) == len(inspections)  # No invented terminal MCP call.
    assert all(row["request"]["params"]["name"] != "release_explain" for row in result["trace"])
    assert result["provider_calls"] == len(inspections) + 1
    assert C.selected_ids(live.plan) == list(C.CHECK_IDS)


@pytest.mark.parametrize("fault", ["premature", "short", "oversize", "refusal", "length", "missing_receipt", "nonassistant"])
def test_native_final_cannot_bypass_inspections_bounds_or_receipt(live, monkeypatch, fault):
    from contextlib import nullcontext
    from server import graph_agent, control
    monkeypatch.setenv("GROQ_API_KEY", "provider-test-only")
    monkeypatch.setattr(control, "connect", lambda port: SimpleNamespace(set=lambda *a, **k: True, lock=lambda *a, **k: nullcontext()))
    source_id = next(s["id"] for s in live.sources if s.get("path") == "falkordb/helpers.py")
    inspections = [("release_read_change", {"change_id": C.CHANGE_ID}),
                   ("release_follow_impact", {"change_id": C.CHANGE_ID}),
                   ("release_read_source", {"source_id": source_id})]
    calls = []
    def provider(messages, tools, timeout, tool_choice, allow_final):
        turn = len(calls)
        calls.append(turn)
        receipt = {"id": "provider-test", "model": "test", "finish_reason": "tool_calls", "response_sha256": "a" * 64, "usage": {"total_tokens": 100}}
        if fault != "premature" and turn < 3:
            name, args = inspections[turn]
            return {"tool_calls": [{"id": str(turn), "function": {"name": name, "arguments": C.encode(args)}}]}, receipt
        message = {"role": "assistant", "content": "Provider final answer must stay bounded and backed by completed observations."}
        receipt["finish_reason"] = "stop"
        if fault == "short": message["content"] = "Too short"
        if fault == "oversize": message["content"] = "x" * 1801
        if fault == "refusal": message["refusal"] = "Refused"
        if fault == "length": receipt["finish_reason"] = "length"
        if fault == "missing_receipt": receipt.pop("response_sha256")
        if fault == "nonassistant": message["role"] = "tool"
        return message, receipt
    monkeypatch.setattr(graph_agent, "completion", provider)
    result = R._investigate(live.data, live.port, live.plan)
    assert result["status"] == "failed" and result["summary"] == ""
    assert "actual_final_response" not in result
    assert len(calls) == (1 if fault == "premature" else 4)
    assert C.selected_ids(live.plan) == list(C.CHECK_IDS)
