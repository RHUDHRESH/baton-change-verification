"""Independent audit contracts; mock provider receipts are not live AI proof."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from test_goal_graph import workspace, live, sources, release_engine
from server import goal_graph as Q, goal_contract as C

DEPLOY = Path(__file__).parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY))
import verify_goal_cloud as V


@pytest.fixture
def native(workspace):
    source_id = next(s["id"] for s in workspace.sources if s.get("path") == "falkordb/graph.py")
    observed = Q.call_tool(workspace.data, workspace.port, "read_company_source", {"source_id": source_id})
    evidence = observed["evidence"]
    proposal = {"summary": "Investigate the observed parameter serializer with a source-backed plan.", "success_criteria": ["Read the exact captured implementation"], "assumptions": [], "questions": [], "limitations": [],
                "steps": [{"id": "inspect", "title": "Inspect source", "tool_name": "read_company_source", "args": {"source_id": source_id}, "why": "Resolve implementation evidence before any action", "evidence_ids": [evidence[0]["id"]], "depends_on": [], "expected_result": "Actual captured implementation observed"}]}
    binding = Q.evidence_binding(workspace.data, workspace.port, evidence)
    proposal = C.validate_proposal(proposal, "Investigate parameter serialization", evidence, Q.TOOLS + C.EFFECTS, binding)
    record = {"id": "1" * 32, "goal": "Investigate parameter serialization", "proposal": proposal, "revision": 1, "evidence": evidence, "plan_evidence": copy.deepcopy(evidence), "evidence_binding": binding,
              "actions": [], "events": [{"seq": 1, "type": "tool_result", "tool_name": "read_company_source", "tool_call_id": "test-call", "receipt_id": "test-generation", "status": "succeeded"}],
              "provider_receipts": [{"id": "test-generation", "response_sha256": "a" * 64, "usage": {"total_tokens": 100}}]}
    Q.create_goal(workspace.data, workspace.port, record)
    graph = Q._graph(workspace.port)
    graph.query("MERGE (s:WorkspaceRecord {id:$id}) SET s.json=$json", {"id": V.SOURCE_KEY, "json": C.encode(workspace.sources)})
    db = Q._connect(workspace.port)
    read = lambda name, text, params=None: db.select_graph(name).ro_query(text, params or {}).result_set
    return workspace, record, read, graph


def test_independent_native_dag_episodes_sources_and_hashes(native):
    workspace, record, read, graph = native
    result = V.audit_record(record, read, graph.name)
    assert result["steps"] == result["citation_edges"] == result["observation_episodes"] == 1
    assert result["provider_receipt_tool_links"] == 1 and result["ready_step_ids"] == ["inspect"]
    binding = V.audit_bindings(record, read, graph.name, Q.TOOLS + C.EFFECTS, C.CATALOG_VERSION)
    assert binding["independent_proposal_hash"] and binding["raw_source_evidence"] == 1


@pytest.mark.parametrize("mutation", ["step", "citation", "episode", "provider_link", "source", "proposal_hash"])
def test_independent_verifier_denies_substitution(native, mutation):
    workspace, record, read, graph = native
    if mutation == "step": graph.query("MATCH (s:GoalStep) SET s.json='{}'")
    elif mutation == "citation": graph.query("MATCH ()-[r:CITES]->() DELETE r")
    elif mutation == "episode": graph.query("MATCH ()-[r:OBSERVED]->(:GoalEpisode) DELETE r")
    elif mutation == "provider_link":
        record["events"][0]["receipt_id"] = "not-an-actual-receipt"
        graph.query("MATCH (g:Goal) SET g.json=$json", {"json": C.encode(record)})
    elif mutation == "source": graph.query("MATCH (s:WorkspaceRecord) SET s.json='[]'")
    else: record["proposal"]["hash"] = "b" * 64
    with pytest.raises(V.AuditError):
        V.audit_record(record, read, graph.name)
        V.audit_bindings(record, read, graph.name, Q.TOOLS + C.EFFECTS, C.CATALOG_VERSION)


def test_catalog_extraction_matches_reviewed_runtime_without_importing_it():
    root = Path(__file__).parents[1]
    sources = {name: (root / name).read_text() for name in V.MODULES}
    catalog, version = V.catalog_from_sources(sources)
    assert catalog == Q.TOOLS + C.EFFECTS and version == C.CATALOG_VERSION


def test_runtime_archive_must_match_deployed_hash_and_public_source(tmp_path, monkeypatch):
    root = Path(__file__).parents[1]
    archive = tmp_path / "lambda.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in V.MODULES: bundle.writestr(name, (root / name).read_bytes())
    digest = V.sha(archive.read_bytes())
    monkeypatch.setattr(V, "get", lambda url: (root / url.split("/" + "a" * 40 + "/", 1)[1]).read_bytes())
    deployed = base64.b64encode(bytes.fromhex(digest)).decode()
    _, hashes = V.runtime_sources(archive, digest, "a" * 40, deployed)
    assert set(hashes) == set(V.MODULES)
    with pytest.raises(V.AuditError, match="deployed"):
        V.runtime_sources(archive, digest, "a" * 40, "mismatch")


def test_raw_transport_can_only_issue_graph_ro_query():
    class Connection:
        def execute_command(self, *args):
            assert args[0] == "GRAPH.RO_QUERY" and args[-2:] == ("TIMEOUT", 10000)
            assert args[2].startswith('CYPHER id="')
            return [[], [["observed"]], []]
    assert V.query(Connection(), "approved_graph", "MATCH (g:Goal {id:$id}) RETURN g.id LIMIT 1", {"id": "a" * 32}) == [["observed"]]
    with pytest.raises(V.AuditError, match="read-query"):
        V.query(Connection(), "approved_graph", "CREATE (:Goal)")


def test_invalid_goal_id_rejected_before_any_network(monkeypatch):
    monkeypatch.setattr(V, "get", lambda *args: pytest.fail("must not fetch"))
    with pytest.raises(V.AuditError, match="identity"):
        V.verify("x' MATCH(n) DELETE n", "not-used", "not-used", "not-used")


@pytest.mark.parametrize("mixed,direct,terminal", [(False, False, False), (True, False, False), (False, True, False), (False, False, True)])
def test_cloud_protocol_audit_preserves_truthful_json_and_native_history(mixed, direct, terminal):
    from test_verify_goal_agent import json_fixture
    record = json_fixture(mixed=mixed, direct=direct, terminal=terminal)
    result = V.protocol_audit(record, Q.TOOLS + C.EFFECTS)
    assert result["json_decision_protocol_checked"] is True
    assert result["json_decisions"] >= 1 and result["host_assigned_json_invocations"] >= 1
    assert "host-assigned" in result["id_provenance"]
    assert ("native_chat_completions" in result["selection_transports"]) == mixed


@pytest.mark.parametrize("fault", ["content", "host_id", "native_claim", "missing_decision", "schema"])
def test_cloud_protocol_audit_rejects_json_provenance_or_catalog_substitution(fault):
    from test_verify_goal_agent import json_fixture
    record = json_fixture()
    decision = next(e for e in record["events"] if e["type"] == "assistant_json_decision")
    selection = next(e for e in record["events"] if e["type"] == "tool_selection")
    if fault == "content": decision["result"] += " "
    elif fault == "host_id": selection["invocation_id"] = "invented-native-looking-id"
    elif fault == "native_claim": selection["type"] = "tool_call"
    elif fault == "missing_decision": record["events"].remove(decision)
    else:
        decision["offered_catalog"][0]["inputSchema"] = {"type": "object", "additionalProperties": True}
        receipt = next(r for r in record["provider_receipts"] if r["id"] == decision["receipt_id"])
        decision["catalog_sha256"] = receipt["offered_catalog_sha256"] = C.sha(C.encode(decision["offered_catalog"]))
    with pytest.raises(V.AuditError, match="JSON decision"):
        V.protocol_audit(record, Q.TOOLS + C.EFFECTS)


def test_json_native_episode_tampering_still_rejected_by_real_graph_audit(workspace):
    from test_verify_goal_agent import json_fixture
    record = json_fixture()
    # Protocol data and plan are test-authored. Native graph operations are real;
    # this checks stored episode integrity, not live provider/source provenance.
    graph = Q._graph(workspace.port)
    for evidence in record["evidence"]:
        graph.query("MERGE (:GoalEvidence {id:$id})", {"id": evidence["id"]})
    Q.create_goal(workspace.data, workspace.port, record)
    db = Q._connect(workspace.port)
    read = lambda name, text, params=None: db.select_graph(name).ro_query(text, params or {}).result_set
    assert V.protocol_audit(record, Q.TOOLS + C.EFFECTS)["json_decision_protocol_checked"]
    assert V.audit_record(record, read, graph.name)["provider_receipt_tool_links"] == 1
    event = next(e for e in record["events"] if e["type"] == "assistant_json_decision")
    graph.query("MATCH (e:GoalEpisode {id:$id}) SET e.json='{}'", {"id": record["id"] + ":event:" + str(event["seq"])})
    with pytest.raises(V.AuditError, match="episodes"):
        V.audit_record(record, read, graph.name)
