"""Independent read-only goal graph audit for an actual app GoalRun.

Upload beside verify_release_cloud.py. Uses only public HTTPS GET,
GetFunctionConfiguration and GRAPH.RO_QUERY. Credentials remain in memory.
No model, dispatch, provider write, graph mutation, or package installation.
"""
import argparse
import ast
import base64
import json
from pathlib import Path
import re
import sys
import zipfile

from verify_release_cloud import AuditError, approved_archive, encode, get, load_redis, require, sha

ORIGIN = "https://baton-workspace.vercel.app"
REPOSITORY = "RHUDHRESH/baton-change-verification"
RELEASE_GRAPH = "baton_release_py211_207000da70ca"
SOURCE_KEY = "release/sources/207000da70ca183ab02990a98bdd97d0a3e3bb1b.json"
MODULES = ("server/goal_graph.py", "server/goal_agent.py", "server/goal_contract.py", "server/goal_actions.py", "server/app.py")


def environment():
    import boto3
    from botocore.config import Config
    response = boto3.client("lambda", region_name="ap-south-1", config=Config(connect_timeout=3, read_timeout=10,
        retries={"total_max_attempts": 1})).get_function_configuration(FunctionName="baton-workspace")
    values = response.get("Environment", {}).get("Variables", {})
    names = ("FALKORDB_HOST", "FALKORDB_PORT", "FALKORDB_USERNAME", "FALKORDB_PASSWORD", "FALKORDB_TLS", "BATON_CLOUD_STATE_GRAPH")
    return {name: values.get(name, "") for name in names}, response.get("CodeSha256")


def runtime_sources(archive, digest, commit, deployed_digest):
    approved_archive(archive, digest)
    require(re.fullmatch(r"[a-f0-9]{40}", commit), "Reviewed source commit is invalid")
    require(deployed_digest == base64.b64encode(bytes.fromhex(digest)).decode(), "Approved archive is not the deployed Lambda code")
    sources, hashes = {}, {}
    with zipfile.ZipFile(archive) as bundle:
        for name in MODULES:
            raw = bundle.read(name)
            public = get("https://raw.githubusercontent.com/" + REPOSITORY + "/" + commit + "/" + name)
            require(raw == public, "Deployed runtime source differs from the reviewed public commit")
            hashes[name] = sha(raw)
            sources[name] = raw.decode()
    return sources, hashes


def catalog_from_sources(sources):
    """Extract only literal schema data; never execute imported runtime code."""
    graph = ast.parse(sources["server/goal_graph.py"])
    contract = ast.parse(sources["server/goal_contract.py"])
    assignments = {node.targets[0].id: node.value for node in graph.body if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    literals = {name: ast.literal_eval(assignments[name]) for name in ("STRING", "LIMIT")}
    def literal(node):
        if isinstance(node, ast.Name): return literals[node.id]
        if isinstance(node, ast.Dict): return {literal(k): literal(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.List): return [literal(v) for v in node.elts]
        return ast.literal_eval(node)
    function = next(node for node in graph.body if isinstance(node, ast.FunctionDef) and node.name == "_tool")
    descriptions = next(ast.literal_eval(node) for node in ast.walk(function) if isinstance(node, ast.Dict)
                        and len(node.keys) == 5 and all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in node.keys))
    tools = []
    for node in assignments["TOOLS"].elts:
        require(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_tool" and len(node.args) == 3, "Reviewed tool catalog format changed")
        name, properties, required = [literal(arg) for arg in node.args]
        tools.append({"name": name, "description": descriptions[name], "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}})
    values = {node.targets[0].id: node.value for node in contract.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    return tools + ast.literal_eval(values["EFFECTS"]), ast.literal_eval(values["CATALOG_VERSION"])


def protocol_audit(record, catalog):
    """Check explicit JSON decisions without relabeling them as native calls.

Historical native-only audits retain their existing graph/receipt checks. JSON
records additionally require the independent public protocol verifier and its
goal_contract dependency from the reviewed source checkout/upload package.
"""
    json_receipts = any(r.get("transport") == "json_decision" for r in record.get("provider_receipts", []))
    json_events = any(e.get("type") in {"assistant_json_decision", "tool_selection"} for e in record.get("events", []))
    if not (json_receipts or json_events):
        return {"json_decision_protocol_checked": False}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scripts import verify_goal_agent as protocol
    except ImportError:
        raise AuditError("JSON decision proof requires the reviewed public protocol verifier and goal contract") from None
    try:
        result = protocol.verify_record(record, catalog)
    except protocol.ProofError:
        raise AuditError("Actual JSON decision, offered schema, host invocation or provider receipt binding differs") from None
    return {"json_decision_protocol_checked": True, "selection_transports": result["selection_transports"],
            "json_decisions": result["json_decisions"], "host_assigned_json_invocations": result["host_assigned_json_invocations"],
            "id_provenance": "JSON invocation IDs are host-assigned correlations; no native provider tool_call is claimed"}


def graph_connection(settings, archive, digest):
    redis = load_redis(archive, digest)
    host, port, tls = settings.get("FALKORDB_HOST", ""), settings.get("FALKORDB_PORT") or "6379", settings.get("FALKORDB_TLS")
    require(re.fullmatch(r"[A-Za-z0-9_.-]{1,253}", host) and re.fullmatch(r"[0-9]{1,5}", str(port)) and 1 <= int(port) <= 65535, "Configured graph address is invalid")
    require(tls in ("0", "1", "true", "yes"), "Explicit graph TLS configuration is required")
    transport = {"ssl": tls != "0"}
    if transport["ssl"]: transport.update(ssl_cert_reqs="required", ssl_check_hostname=True)
    return redis.Redis(host=host, port=int(port), username=settings.get("FALKORDB_USERNAME") or None,
                       password=settings.get("FALKORDB_PASSWORD") or None, socket_connect_timeout=3,
                       socket_timeout=12, decode_responses=True, **transport)


def query(connection, graph, text, params=None):
    require(re.fullmatch(r"[A-Za-z0-9_:-]{1,150}", graph), "Configured graph name is invalid")
    require(text.startswith("MATCH "), "Only fixed read-query templates are allowed")
    header = "CYPHER " + " ".join(key + "=" + encode(value) for key, value in (params or {}).items()) + " " if params else ""
    response = connection.execute_command("GRAPH.RO_QUERY", graph, header + text, "TIMEOUT", 10000)
    require(isinstance(response, list) and len(response) >= 2 and isinstance(response[1], list) and len(response[1]) <= 200, "Direct graph read exceeded its bound")
    return response[1]


def audit_record(record, read, graph):
    identity = record.get("id", "")
    require(re.fullmatch(r"[a-f0-9]{32}", identity), "Goal identity is invalid")
    proposal = record.get("proposal")
    require(isinstance(proposal, dict) and re.fullmatch(r"[a-f0-9]{64}", proposal.get("hash", "")), "A sealed model proposal is required")
    revision = identity + ":" + proposal["hash"]
    require(read(graph, "MATCH (g:Goal {id:$id}) RETURN g.json,g.origin LIMIT 2", {"id": identity}) == [[encode(record), "model_proposal"]], "Native Goal differs from public app readback")
    require(read(graph, "MATCH (:Goal {id:$goal})-[:CURRENT_PLAN]->(p:PlanRevision) RETURN p.id,p.hash,p.json,p.origin LIMIT 2", {"goal": identity}) == [[revision, proposal["hash"], encode(proposal), "model_proposal"]], "Native current plan revision differs")
    steps = proposal.get("steps", [])
    require(1 <= len(steps) <= 6 and len({s["id"] for s in steps}) == len(steps), "Model step set is invalid")
    rows = read(graph, "MATCH (:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep) OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:GoalStep) RETURN s.step_id,s.json,s.status,collect(DISTINCT d.step_id) ORDER BY s.step_id LIMIT 10", {"plan": revision})
    require(len(rows) == len(steps), "Native step count differs")
    proposed = {s["id"]: s for s in steps}
    remaining, sorted_steps = {s["id"]: set(s["depends_on"]) for s in steps}, set()
    require(all(deps.issubset(proposed) and identity not in deps for identity, deps in remaining.items()), "Unknown or self dependency")
    while remaining:
        available = {identity for identity, deps in remaining.items() if deps.issubset(sorted_steps)}
        require(available, "Native proposal dependency graph is cyclic")
        sorted_steps.update(available)
        remaining = {identity: deps for identity, deps in remaining.items() if identity not in available}
    events, actions = record.get("events", []), record.get("actions", [])
    receipt_ids = {r["id"] for r in record.get("provider_receipts", []) if r.get("id") and re.fullmatch(r"[a-f0-9]{64}", r.get("response_sha256", "")) and type(r.get("usage", {}).get("total_tokens")) is int and r["usage"]["total_tokens"] > 0}
    require(receipt_ids, "Actual hashed provider generation receipts are missing")
    tool_events = [event for event in events if event.get("type") == "tool_result" and event.get("status") == "succeeded"]
    require(tool_events and all(event.get("tool_call_id") and event.get("receipt_id") in receipt_ids for event in tool_events), "Observed graph tools do not link to actual provider receipts")
    reads = {"search_company_graph", "inspect_graph_entity", "traverse_company_graph", "read_company_source", "recall_goal_memory"}
    done = {e.get("step_id") for e in events if e.get("type") == "tool_result" and e.get("status") == "succeeded" and e.get("plan_hash") == proposal["hash"] and e.get("tool_call_id") and e.get("receipt_id") in receipt_ids and proposed.get(e.get("step_id"), {}).get("tool_name") in reads}
    done.update(a.get("step_id") for a in actions if a.get("status") == "verified" and a.get("read_back_verified") is True and a.get("plan_hash") == proposal["hash"] and proposed.get(a.get("step_id"), {}).get("tool_name") in {"publish_task", "verify_release"})
    for step_id, raw, status, dependencies in rows:
        require(step_id in proposed and json.loads(raw) == proposed[step_id] and sorted(dependencies) == sorted(proposed[step_id]["depends_on"]) and status == ("completed" if step_id in done else "pending"), "Native step/dependency/completion differs")
    citations = read(graph, "MATCH (:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep) OPTIONAL MATCH (s)-[:CITES]->(e:GoalEvidence) RETURN s.step_id,collect(DISTINCT e.id) LIMIT 10", {"plan": revision})
    require({row[0]: sorted(row[1]) for row in citations} == {s["id"]: sorted(s["evidence_ids"]) for s in steps}, "Native citations differ")
    episodes = read(graph, "MATCH (:Goal {id:$id})-[:OBSERVED]->(e:GoalEpisode) RETURN e.id,e.json LIMIT 200", {"id": identity})
    expected = {identity + ":event:" + str(e.get("seq", n)): encode(e) for n, e in enumerate(events)}
    require(len(episodes) == len(expected) and dict(episodes) == expected, "Native observed episodes differ")
    effects = read(graph, "MATCH (:Goal {id:$id})-[:OBSERVED]->(a:GoalAction) RETURN a.id,a.json LIMIT 100", {"id": identity})
    require(dict(effects) == {identity + ":action:" + str(n): encode(a) for n, a in enumerate(actions)}, "Native action observations differ")
    revisions = read(graph, "MATCH (:Goal {id:$id})-[:HAS_PLAN]->(p:PlanRevision) RETURN p.id,p.hash LIMIT 100", {"id": identity})
    supersedes = read(graph, "MATCH (:Goal {id:$id})-[:HAS_PLAN]->(p:PlanRevision)-[:SUPERSEDES]->(old:PlanRevision) RETURN p.id,old.id LIMIT 100", {"id": identity})
    revision_ids = {r[0] for r in revisions}
    require(revision in revision_ids and all(a in revision_ids and b in revision_ids and a != b for a, b in supersedes), "Revision history crosses goal scope")
    eligible = sorted(s["id"] for s in steps if s["id"] not in done and set(s["depends_on"]).issubset(done))
    ready = read(graph, "MATCH (:Goal {id:$goal})-[:CURRENT_PLAN]->(:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep) WHERE s.status<>'completed' OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:GoalStep) WITH s,collect(d.status) AS states WHERE all(state IN states WHERE state='completed') RETURN s.step_id ORDER BY s.step_id LIMIT 10", {"goal": identity, "plan": revision})
    require([r[0] for r in ready] == eligible, "Native readiness differs from actual dependency observations")
    return {"goal_id": identity, "goal_sha256": sha(record["goal"]), "proposal_hash": proposal["hash"], "steps": len(steps),
            "dependency_edges": sum(len(s["depends_on"]) for s in steps), "citation_edges": sum(len(s["evidence_ids"]) for s in steps),
            "observation_episodes": len(episodes), "action_observations": len(effects), "native_revisions": len(revisions),
            "supersedes_edges": len(supersedes), "ready_step_ids": eligible, "provider_generation_receipts": len(receipt_ids),
            "provider_receipt_tool_links": len(tool_events),
            "observed_tools": [e.get("tool_name") for e in events if e.get("type") == "tool_result"]}


def audit_bindings(record, read, state, catalog, catalog_version):
    evidence = record.get("plan_evidence", record.get("evidence", []))
    selected = []
    source_cache = None
    for item in evidence:
        rows = read(state, "MATCH (e:GoalEvidence {id:$id}) RETURN e.json,e.locator,e.digest LIMIT 2", {"id": item["id"]})
        require(len(rows) == 1 and json.loads(rows[0][0]) == {k: item.get(k) for k in json.loads(rows[0][0])}, "Inspected evidence binding differs")
        locator = json.loads(rows[0][1])
        if locator["type"] == "entity":
            graph = locator["graph"]
            require(graph != state and (graph == RELEASE_GRAPH or re.fullmatch(r"baton_public_falkordb_[a-f0-9]{24}", graph)), "Evidence points outside public graph scope")
            node = read(graph, "MATCH (n {id:$id}) RETURN labels(n),properties(n) LIMIT 2", {"id": locator["id"]})
            require(len(node) == 1, "Selected public entity is missing")
            edges = read(graph, "MATCH (a {id:$id})-[r]-(b) WHERE b.id IS NOT NULL RETURN a.id,type(r),b.id,properties(r),id(startNode(r))=id(a) ORDER BY type(r),b.id LIMIT 100", {"id": locator["id"]})
            payload = {"labels": node[0][0], "properties": node[0][1], "adjacency": edges}
        elif locator["type"] == "source":
            if source_cache is None:
                source_cache = {}
                captured = read(state, "MATCH (s:WorkspaceRecord {id:$id}) RETURN s.json LIMIT 1", {"id": SOURCE_KEY})
                if captured: source_cache.update({s["id"]: s for s in json.loads(captured[0][0])})
                pointer = read(state, "MATCH (s:WorkspaceRecord {id:'current.json'}) RETURN s.json LIMIT 1")
                if pointer:
                    pointer_id = json.loads(pointer[0][0]).get("id", "")
                    require(re.fullmatch(r"[a-f0-9]{24}", pointer_id), "Public snapshot pointer is invalid")
                    snapshot = read(state, "MATCH (s:WorkspaceRecord {id:$id}) RETURN s.json LIMIT 1", {"id": "snapshots/" + pointer_id + ".json"})
                    if snapshot:
                        snap = json.loads(snapshot[0][0])
                        require(snap.get("id") == pointer_id and snap.get("graph") == "baton_public_falkordb_" + pointer_id and snap["graph"] != state, "Public snapshot graph is invalid")
                        # Match production override precedence: pinned release captures win.
                        source_cache = {**{s["id"]: s for s in snap.get("sources", [])}, **source_cache}
            payload = source_cache.get(locator["id"])
            require(payload is not None, "Inspected captured source is missing")
            require(any(payload.get("url", "").startswith("https://api.github.com/repos/" + repo + "/") or payload.get("url") == "https://api.github.com/repos/" + repo for repo in ("FalkorDB/FalkorDB", "FalkorDB/falkordb-py")), "Captured source is outside approved public scope")
        elif locator["type"] == "memory":
            rows_goal = read(state, "MATCH (g:Goal {id:$id}) RETURN g.json LIMIT 2", {"id": locator["id"]})
            require(len(rows_goal) == 1, "Recalled goal memory is missing")
            payload = json.loads(rows_goal[0][0])
        else:
            raise AuditError("Unknown inspected evidence locator")
        digest = sha(encode(payload))
        require(digest == rows[0][2], "Relevant selected source or graph fact changed")
        selected.append((item["id"], digest))
    binding = sha(encode(sorted(set(selected))))
    require(binding == record.get("evidence_binding"), "Sealed evidence fingerprint differs")
    proposal = record["proposal"]
    refs = sorted(({k: e.get(k) for k in ("id", "source_id", "sha256", "kind")} for e in evidence), key=lambda x: x["id"])
    material = {"goal": record["goal"], "proposal": {k: v for k, v in proposal.items() if k != "hash"}, "catalog_version": catalog_version,
                "catalog_sha256": sha(encode(catalog)), "evidence": refs, "binding": binding}
    require(sha(encode(material)) == proposal["hash"], "Independent proposal/catalog/source hash differs")
    source_count = sum(e.get("kind") == "source" for e in evidence)
    return {"selected_evidence": len(evidence), "raw_source_evidence": source_count, "evidence_fingerprint": binding,
            "independent_proposal_hash": True, "selected_evidence_facts_reread": True, "source_content_reread": source_count > 0}


def verify(identity, archive, archive_sha, commit):
    require(re.fullmatch(r"[a-f0-9]{32}", identity), "Goal identity is invalid")
    approved_archive(archive, archive_sha)
    record = json.loads(get(ORIGIN + "/api/public/goals/" + identity))
    require(record.get("id") == identity, "Public GoalRun identity differs")
    settings, deployed = environment()
    connection = None
    try:
        sources, source_hashes = runtime_sources(archive, archive_sha, commit, deployed)
        catalog, version = catalog_from_sources(sources)
        protocol = protocol_audit(record, catalog)
        state = settings.get("BATON_CLOUD_STATE_GRAPH") or "baton_goal_memory"
        connection = graph_connection(settings, archive, archive_sha)
        read = lambda graph, text, params=None: query(connection, graph, text, params)
        native = audit_record(record, read, state)
        bindings = audit_bindings(record, read, state, catalog, version)
        return {"status": "verified", "read_only": True, "source_commit": commit, "lambda_archive_sha256": archive_sha,
                "deployed_runtime_matches_public_source": source_hashes, "graph_command": "GRAPH.RO_QUERY", **native, **bindings, **protocol,
                "limits": ["Native plan, dependencies, selected facts, source hashes and actual event bindings were checked; semantic usefulness/entailment is not certified.",
                           "Model/provider receipt hashes are preserved evidence, not an independent request to Groq.",
                           "External Jira/Slack/GitHub effect readbacks require their separate provider audit; this helper makes no effect-completion claim."]}
    finally:
        if connection is not None: connection.close()
        settings.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal-id", required=True)
    parser.add_argument("--lambda-archive", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = verify(args.goal_id, args.lambda_archive, args.archive_sha256, args.source_commit)
    except AuditError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True, "error": "Read-only goal audit stopped; private configuration and provider bodies were not printed"}
    encoded = encode(result)
    if args.output: Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
