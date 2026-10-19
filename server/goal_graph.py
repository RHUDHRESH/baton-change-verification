"""Native goal DAG and selected evidence bindings over real workspace graphs.

Model proposals stay separate from captured source facts. No fixture import,
network source fallback, model-generated Cypher or credential graph is exposed.
"""
import copy
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import os
import re
import time

from . import public_workspace as public
from . import release_contract as C
from . import release_graph as release

GRAPH_NAME = "baton_goal_memory"
SEARCH_VERSION = "native-terms-v1"
MAX_RECORD_BYTES = 340_000
ALLOWED_LABELS = ["WorkItem", "Repository", "Account", "File", "Source", "LocalTask",
                  "ReleaseEvidence", "ReleaseExecution", "ReleaseMeasurement", "PublicationReceipt",
                  "ReleasePublication", "ExternalArtifact"]
_DEADLINE = ContextVar("goal_graph_deadline", default=None)


@contextmanager
def graph_deadline(deadline):
    prior = _DEADLINE.get()
    token = _DEADLINE.set(min(prior, deadline) if prior is not None else deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


deadline_scope = graph_deadline


def _bounded(function):
    @wraps(function)
    def run(*args, **kwargs):
        with graph_deadline(time.monotonic() + 20):
            return function(*args, **kwargs)
    return run


class _CheckedGraph:
    def __init__(self, graph):
        self.graph = graph

    def __getattr__(self, name):
        return getattr(self.graph, name)

    def _query(self, method, query, params=None):
        deadline = _DEADLINE.get()
        timeout = min(4000, max(1, int(release._remaining(deadline) * 1000)))
        return getattr(self.graph, method)(query, params or {}, timeout=timeout)

    def query(self, query, params=None):
        return self._query("query", query, params)

    def ro_query(self, query, params=None):
        return self._query("ro_query", query, params)


def _connect(port):
    return release._connect(port, deadline=_DEADLINE.get())


def _graph(port):
    db = _connect(port)
    graph = _CheckedGraph(db.select_graph(os.environ.get("BATON_CLOUD_STATE_GRAPH") or GRAPH_NAME))
    if not os.environ.get("BATON_CLOUD_STATE_GRAPH"):
        try:
            graph.ro_query("MATCH (n:GoalMemoryStore) RETURN n.id LIMIT 1")
        except Exception as error:
            if "Invalid graph operation on empty key" not in str(error):
                raise
            graph.query("MERGE (:GoalMemoryStore {id:'native-goals-v1'})")
    return graph


def _text(value, bound=200):
    if not isinstance(value, str) or not value.strip() or len(value) > bound:
        raise ValueError("Expected a bounded nonempty string")
    return value


def _rows(graph, query, params=None):
    return graph.ro_query(query, params or {}).result_set


def _graphs(data, port):
    db = _connect(port)
    names = []
    state = os.environ.get("BATON_CLOUD_STATE_GRAPH")
    pointer = release._workspace_read(data, port, "current.json", deadline=_DEADLINE.get())
    if pointer and re.fullmatch(r"[a-f0-9]{24}", str(pointer.get("id", ""))):
        snapshot = release._workspace_read(data, port, "snapshots/" + pointer["id"] + ".json", deadline=_DEADLINE.get())
        if snapshot and snapshot.get("id") == pointer["id"] and snapshot.get("graph") == "baton_public_falkordb_" + pointer["id"] and snapshot["graph"] != state:
            names.append(snapshot["graph"])
    if release.GRAPH_NAME != state:
        names.append(release.GRAPH_NAME)
    found = []
    for name in dict.fromkeys(names):
        graph = _CheckedGraph(db.select_graph(name))
        try:
            graph.ro_query("MATCH (n) RETURN n.id LIMIT 1")
        except Exception as error:
            if "Invalid graph operation on empty key" in str(error):
                continue
            raise
        found.append((name, graph))
    return found


def _sources(data, port):
    result = {}
    pointer = release._workspace_read(data, port, "current.json", deadline=_DEADLINE.get())
    if pointer and re.fullmatch(r"[a-f0-9]{24}", str(pointer.get("id", ""))):
        snapshot = release._workspace_read(data, port, "snapshots/" + pointer["id"] + ".json", deadline=_DEADLINE.get())
        if snapshot and snapshot.get("id") == pointer["id"] and snapshot.get("graph") == "baton_public_falkordb_" + pointer["id"] and snapshot["graph"] != os.environ.get("BATON_CLOUD_STATE_GRAPH"):
            for source in snapshot.get("sources", []):
                result[source["id"]] = source
    for source in release._workspace_read(data, port, release.SOURCE_KEY, [], deadline=_DEADLINE.get()) or []:
        result[source["id"]] = source
    if any(not any(source.get("url", "").startswith("https://api.github.com/repos/" + repo + "/") or source.get("url") == "https://api.github.com/repos/" + repo for repo in public.REPOS) for source in result.values()):
        raise ValueError("Captured source is outside the approved public repositories")
    return result


def _entity_snapshot(graph, identity):
    found = _rows(graph, "MATCH (n {id:$id}) RETURN labels(n),properties(n)", {"id": identity})
    if len(found) != 1 or not set(found[0][0]).intersection(ALLOWED_LABELS):
        raise ValueError("Selected public graph entity is missing or ambiguous")
    # New execution observations refer back to immutable source facts. Exclude
    # only these incoming typed bookkeeping links from a source entity's seal;
    # selected executions/measurements and every source decision edge stay bound.
    adjacency = _rows(graph, "MATCH (a {id:$id})-[r]-(b) WHERE b.id IS NOT NULL AND NOT "
                      "('ReleaseEvidence' IN labels(a) AND id(endNode(r))=id(a) AND "
                      "((type(r)='VERIFIES' AND 'ReleaseExecution' IN labels(b)) OR "
                      "(type(r) IN ['CHECKED','IN_ENVIRONMENT'] AND 'ReleaseMeasurement' IN labels(b)))) "
                      "RETURN a.id,type(r),b.id,properties(r),id(startNode(r))=id(a) "
                      "ORDER BY type(r),b.id LIMIT 100", {"id": identity})
    return {"labels": found[0][0], "properties": found[0][1], "adjacency": adjacency}


def _remember_evidence(port, locator, payload, kind, source_id, url=None):
    digest = C.sha(C.encode(payload))
    identity = "gev-" + C.sha(C.encode([locator, digest]))[:24]
    evidence = {"id": identity, "source_id": source_id, "url": url,
                "sha256": digest, "kind": kind}
    _graph(port).query("MERGE (e:GoalEvidence {id:$id}) SET e.json=$json,e.locator=$locator,e.digest=$digest,e.origin=$origin",
                       {"id": identity, "json": C.encode(evidence), "locator": C.encode(locator),
                        "digest": digest, "origin": "captured_source" if kind == "source" else "observed_graph"})
    return evidence


def _entity(data, port, graph_name, graph, identity, source_catalog=None):
    payload = _entity_snapshot(graph, identity)
    props = payload["properties"]
    evidence = _remember_evidence(port, {"type": "entity", "graph": graph_name, "id": identity},
                                  payload, "entity", identity, props.get("url"))
    from .graph_agent import bounded_excerpt
    properties = copy.deepcopy(props)
    if isinstance(properties.get("json"), str):
        try:
            properties["record"] = json.loads(properties.pop("json"))
        except ValueError:
            pass
    record_url = properties["record"].get("url") if isinstance(properties.get("record"), dict) else None
    urls = {value for value in (properties.get("url"), record_url)
                               if isinstance(value, str)}
    catalog = source_catalog or {}
    declared_ids = set()
    for owner in (properties, properties.get("record")):
        if not isinstance(owner, dict):
            continue
        candidates = [owner.get("source_id")]
        if isinstance(owner.get("source_ids"), list):
            candidates.extend(owner["source_ids"])
        declared_ids.update(value for value in candidates if isinstance(value, str) and value in catalog)
    source_ids = sorted(declared_ids | {source["id"] for source in catalog.values() if source.get("url") in urls})
    encoded, truncated = bounded_excerpt(properties, limit=1600)
    relationships = [{"source": row[0] if row[4] else row[2], "relation": row[1],
                      "target": row[2] if row[4] else row[0]} for row in payload["adjacency"][:15]]
    return {"id": identity, "graph": graph_name, "labels": payload["labels"], "properties": json.loads(encoded),
            "source_ids": source_ids, "directed_relationships": relationships, "truncated": truncated or len(payload["adjacency"]) > 15}, evidence


@_bounded
def evidence_binding(data, port, evidence):
    """Reread selected facts; an unrelated graph node cannot change this seal."""
    if not isinstance(evidence, list) or len(evidence) > 100:
        raise ValueError("Evidence list exceeds the selected binding scope")
    known = dict(_graphs(data, port))
    current_sources = None
    selected = []
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Unknown evidence identity")
        rows = _rows(_graph(port), "MATCH (e:GoalEvidence {id:$id}) RETURN e.json,e.locator,e.digest", {"id": item["id"]})
        if len(rows) != 1 or json.loads(rows[0][0]) != {k: item.get(k) for k in json.loads(rows[0][0])}:
            raise ValueError("Evidence was not actually inspected or its binding changed")
        locator = json.loads(rows[0][1])
        if locator["type"] == "source":
            current_sources = _sources(data, port) if current_sources is None else current_sources
            payload = current_sources.get(locator["id"])
            if payload is None:
                raise ValueError("Captured source disappeared")
        elif locator["type"] == "entity":
            if locator["graph"] not in known:
                raise ValueError("Evidence graph is no longer available")
            payload = _entity_snapshot(known[locator["graph"]], locator["id"])
        else:
            payload = get_goal(data, port, locator["id"])
            if payload is None:
                raise ValueError("Goal memory disappeared")
        digest = C.sha(C.encode(payload))
        if digest != rows[0][2]:
            raise ValueError("Relevant inspected evidence changed")
        selected.append((item["id"], digest))
    return C.sha(C.encode(sorted(set(selected))))


def _tool(name, properties, required):
    return {"name": name, "description": {
        "search_company_graph": "Search actual public graph facts using bounded multi-term substring retrieval ranked by matched-term count. Punctuation splits terms, dotted versions stay intact, and words of six or more letters also match their first four characters. Common English words are ignored. Results report matched terms; this is not embedding or full-text-index search. Broaden empty queries. Contributor activity is not employment.",
        "inspect_graph_entity": "Inspect one discovered public entity and its actual directed relationships.",
        "traverse_company_graph": "Follow bounded actual public graph relationships from an inspected entity.",
        "read_company_source": "Read an actual captured source by discovered source ID; only this tool supplies raw source evidence.",
        "recall_goal_memory": "Recall persisted model-proposed goals, plans and observed episodes; these are not source facts."}[name],
            "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}


STRING = {"type": "string", "minLength": 1, "maxLength": 200}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 20}
TOOLS = [
    _tool("search_company_graph", {"query": STRING, "limit": LIMIT}, ["query"]),
    _tool("inspect_graph_entity", {"entity_id": STRING}, ["entity_id"]),
    _tool("traverse_company_graph", {"entity_id": STRING, "depth": {"type": "integer", "minimum": 1, "maximum": 2}, "limit": LIMIT}, ["entity_id"]),
    _tool("read_company_source", {"source_id": STRING}, ["source_id"]),
    _tool("recall_goal_memory", {"query": STRING, "limit": LIMIT}, ["query"]),
]


def _search_terms(query, max_terms=12):
    """Literal retrieval terms, not goal interpretation or a query language."""
    stopwords = {"a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "do", "does",
                 "for", "from", "has", "have", "how", "i", "in", "into", "is", "it", "its", "me", "my", "not",
                 "of", "on", "or", "our", "please", "show", "that", "the", "their", "then", "this", "to", "us",
                 "was", "we", "were", "what", "when", "where", "which", "why", "will", "with", "would", "you"}
    terms, seen = [], set()
    for term in re.findall(r"[^\W_]+(?:\.[^\W_]+)*", query.lower(), flags=re.UNICODE):
        if term in stopwords or len(term) < 2:
            continue
        pattern = term[:4] if term.isalpha() and len(term) >= 6 else term
        if pattern not in seen:
            seen.add(pattern)
            terms.append({"term": term, "match": pattern})
        if len(terms) == max_terms:
            break
    return terms


@_bounded
def call_tool(data, port, name, args, record=None):
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if tool is None or not isinstance(args, dict) or not set(tool["inputSchema"]["required"]).issubset(args) or set(args) - set(tool["inputSchema"]["properties"]):
        raise ValueError("Tool or arguments are outside the goal read catalog")
    for key, value in args.items():
        schema = tool["inputSchema"]["properties"][key]
        if schema["type"] == "string":
            _text(value)
        elif type(value) is not int or not schema["minimum"] <= value <= schema["maximum"]:
            raise ValueError("Read tool integer is outside its bound")
    evidence, observation = [], {}
    limit = args.get("limit", 5)
    graphs = _graphs(data, port)
    if name == "read_company_source":
        source = _sources(data, port).get(args["source_id"])
        if source is None:
            raise ValueError("Source is not in the real captured workspace")
        evidence.append(_remember_evidence(port, {"type": "source", "id": source["id"]}, source,
                                           "source", source["id"], source.get("url")))
        from .graph_agent import bounded_excerpt
        text, truncated = bounded_excerpt(source.get("content", source.get("payload")), limit=5500)
        observation = {"source_id": source["id"], "url": source.get("url"), "captured_sha256": source.get("sha256"),
                       "excerpt": json.loads(text), "truncated": truncated}
    elif name == "recall_goal_memory":
        rows = _rows(_graph(port), "MATCH (g:Goal) WHERE toLower(g.goal) CONTAINS $query AND g.id<>$exclude RETURN g.id,g.json ORDER BY g.updated_at DESC LIMIT $limit",
                     {"query": args["query"].lower(), "limit": limit, "exclude": (record or {}).get("id", "")})
        memories = []
        for identity, raw in rows:
            payload = json.loads(raw)
            from .graph_agent import bounded_excerpt
            episodes = _rows(_graph(port), "MATCH (:Goal {id:$id})-[:OBSERVED]->(e:GoalEpisode) RETURN e.json ORDER BY e.id DESC LIMIT 5", {"id": identity})
            projected = {key: payload.get(key) for key in ("id", "goal", "status", "revision", "proposal")}
            projected["observed_episodes"] = [json.loads(row[0]) for row in episodes]
            text, truncated = bounded_excerpt(projected, limit=3000)
            memories.append({**json.loads(text), "truncated": truncated})
            evidence.append(_remember_evidence(port, {"type": "memory", "id": identity}, payload, "model_proposal", identity))
        observation = {"memories": memories, "origin": "model proposals and actual observation records; not source facts"}
    else:
        entities = []
        source_catalog = _sources(data, port)
        terms = _search_terms(args["query"]) if name == "search_company_graph" else []
        candidates = []
        for graph_name, graph in graphs:
            if name == "search_company_graph":
                rows = _rows(graph, "MATCH (n) WHERE any(label IN labels(n) WHERE label IN $labels) "
                             "WITH n,toLower(coalesce(n.id,'')+' '+coalesce(n.title,'')+' '+coalesce(n.name,'')+' '+coalesce(n.json,'')) AS text "
                             "WITH n,[term IN $terms WHERE text CONTAINS term] AS matched WHERE size(matched)>0 "
                             "RETURN n.id,matched,size(matched) AS score ORDER BY score DESC,n.id LIMIT $limit",
                             {"labels": ALLOWED_LABELS, "terms": [term["match"] for term in terms], "limit": 20}) if terms else []
                candidates.extend((row[2], graph_name, row[0], graph, row[1]) for row in rows)
                continue
            else:
                identities = [args["entity_id"]] if _rows(graph, "MATCH (n {id:$id}) RETURN n.id", {"id": args["entity_id"]}) else []
                if name == "traverse_company_graph" and identities:
                    query = ("MATCH (a {id:$id})-[*1..2]-(b) WHERE b.id IS NOT NULL RETURN DISTINCT b.id ORDER BY b.id LIMIT $limit"
                             if args.get("depth", 1) == 2 else
                             "MATCH (a {id:$id})-[]-(b) WHERE b.id IS NOT NULL RETURN DISTINCT b.id ORDER BY b.id LIMIT $limit")
                    identities += [row[0] for row in _rows(graph, query, {"id": args["entity_id"], "limit": limit})]
            for identity in identities:
                if len(entities) >= limit:
                    break
                entity, proof = _entity(data, port, graph_name, graph, identity, source_catalog)
                entities.append(entity)
                evidence.append(proof)
        if name == "search_company_graph":
            for score, graph_name, identity, graph, matched in sorted(candidates, key=lambda row: (-row[0], row[1], row[2]))[:limit]:
                entity, proof = _entity(data, port, graph_name, graph, identity, source_catalog)
                entity["matched_search_terms"] = [term["term"] for term in terms if term["match"] in matched]
                entity["matched_substrings"] = matched
                entity["term_overlap_score"] = score
                entities.append(entity)
                evidence.append(proof)
        observation = {"entities": entities, "scope": "Captured public work and verified release records. Public contribution does not establish employment or ownership."}
        if name == "search_company_graph":
            observation.update(search_version=SEARCH_VERSION,
                               search_strategy="bounded_native_term_overlap; OR substrings, four-character prefixes for long words; global matched-term ranking; no embeddings/index",
                               search_terms=terms, candidate_limit_per_graph=20, query_terms_truncated=len(_search_terms(args["query"], max_terms=13)) > 12)
    return {"observation": observation, "evidence": evidence,
            "binding": {"fingerprint": evidence_binding(data, port, evidence)}}


def _proposal_graph(graph, record, create=False):
    proposal = record.get("proposal")
    if not proposal:
        return
    steps = proposal["steps"]
    if len(steps) > 6 or len({s["id"] for s in steps}) != len(steps):
        raise ValueError("Invalid step DAG")
    revision = record["id"] + ":" + proposal["hash"]
    expected = {s["id"]: sorted(s.get("depends_on", [])) for s in steps}
    if any(dep not in expected or dep == identity for identity, deps in expected.items() for dep in deps):
        raise ValueError("Unknown or self dependency")
    visited, active = set(), set()
    def visit(identity):
        if identity in active:
            raise ValueError("Cyclic step DAG")
        if identity in visited:
            return
        active.add(identity)
        for dep in expected[identity]: visit(dep)
        active.remove(identity)
        visited.add(identity)
    for identity in expected: visit(identity)
    found = _rows(graph, "MATCH (p:PlanRevision {id:$id})-[:HAS_STEP]->(s:GoalStep) OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:GoalStep) RETURN s.step_id,s.json,collect(d.step_id) ORDER BY s.step_id", {"id": revision})
    if found:
        version = _rows(graph, "MATCH (p:PlanRevision {id:$id}) RETURN p.hash,p.json", {"id": revision})
        if version != [[proposal["hash"], C.encode(proposal)]]:
            raise ValueError("Native plan revision binding changed")
        observed = {row[0]: sorted(x for x in row[2] if x is not None) for row in found}
        if observed != expected or any(json.loads(row[1]) != next(s for s in steps if s["id"] == row[0]) for row in found):
            raise ValueError("Native plan dependency or step binding changed")
        citations = _rows(graph, "MATCH (p:PlanRevision {id:$id})-[:HAS_STEP]->(s:GoalStep) OPTIONAL MATCH (s)-[:CITES]->(e:GoalEvidence) RETURN s.step_id,collect(e.id)", {"id": revision})
        if {row[0]: sorted(x for x in row[1] if x is not None) for row in citations} != {s["id"]: sorted(s.get("evidence_ids", [])) for s in steps}:
            raise ValueError("Native plan citation binding changed")
    elif not create:
        raise ValueError("Native plan DAG is missing")
    if not create:
        return
    graph.query("MATCH (g:Goal {id:$goal}) OPTIONAL MATCH (g)-[r:CURRENT_PLAN]->(old:PlanRevision) DELETE r "
                "MERGE (p:PlanRevision {id:$id}) SET p.hash=$hash,p.json=$json,p.origin='model_proposal' "
                "MERGE (g)-[:HAS_PLAN]->(p) MERGE (g)-[:CURRENT_PLAN]->(p) "
                "WITH p,old WHERE old IS NOT NULL AND old.id<>p.id MERGE (p)-[:SUPERSEDES]->(old)",
                {"goal": record["id"], "id": revision, "hash": proposal["hash"], "json": C.encode(proposal)})
    for step in steps:
        identity = revision + ":" + step["id"]
        graph.query("MATCH (p:PlanRevision {id:$plan}) MERGE (s:GoalStep {id:$id}) SET s.step_id=$step,s.json=$json,s.status='pending' MERGE (p)-[:HAS_STEP]->(s)",
                    {"plan": revision, "id": identity, "step": step["id"], "json": C.encode(step)})
        for evidence_id in step.get("evidence_ids", []):
            if not _rows(graph, "MATCH (e:GoalEvidence {id:$id}) RETURN e.id", {"id": evidence_id}):
                raise ValueError("Plan cites evidence not inspected by a real tool")
            graph.query("MATCH (s:GoalStep {id:$step}),(e:GoalEvidence {id:$evidence}) MERGE (s)-[:CITES]->(e)", {"step": identity, "evidence": evidence_id})
    for step in steps:
        for dep in step.get("depends_on", []):
            graph.query("MATCH (s:GoalStep {id:$step}),(d:GoalStep {id:$dep}) MERGE (s)-[:DEPENDS_ON]->(d)",
                        {"step": revision + ":" + step["id"], "dep": revision + ":" + dep})
    complete = _completed(record)
    for step in steps:
        if step["id"] in complete:
            graph.query("MATCH (s:GoalStep {id:$id}) SET s.status='completed'", {"id": revision + ":" + step["id"]})


def _completed(record):
    proposal = record.get("proposal") or {}
    plan_hash = proposal.get("hash")
    read_tools = {t["name"] for t in TOOLS}
    kinds = {s["id"]: s["tool_name"] for s in proposal.get("steps", [])}
    complete = {a.get("step_id") for a in record.get("actions", [])
                if a.get("plan_hash") == plan_hash and a.get("status") == "verified" and a.get("read_back_verified") is True
                and kinds.get(a.get("step_id")) in {"publish_task", "verify_release"}}
    complete.update(e.get("step_id") for e in record.get("events", [])
                    if e.get("plan_hash") == plan_hash and e.get("type") == "tool_result" and e.get("status") == "succeeded"
                    and e.get("tool_call_id") and e.get("receipt_id") and kinds.get(e.get("step_id")) in read_tools)
    return complete


@_bounded
def save_goal(data, port, record):
    _text(record.get("id"), 120)
    _text(record.get("goal"), 4000)
    raw = C.encode(record)
    if len(raw.encode()) > MAX_RECORD_BYTES:
        raise ValueError("Goal record exceeds its storage bound")
    graph = _graph(port)
    for index, event in enumerate(record.get("events", [])):
        identity = record["id"] + ":event:" + str(event.get("seq", index))
        existing = _rows(graph, "MATCH (e:GoalEpisode {id:$id}) RETURN e.json", {"id": identity})
        if existing and (len(existing) != 1 or existing[0][0] != C.encode(event)):
            raise ValueError("An actual observation episode cannot be rewritten")
    _proposal_graph(graph, record, create=False) if record.get("proposal") and _rows(graph, "MATCH (p:PlanRevision {id:$id}) RETURN p.id", {"id": record["id"] + ":" + record["proposal"]["hash"]}) else None
    graph.query("MERGE (g:Goal {id:$id}) SET g.goal=$goal,g.json=$json,g.updated_at=$at,g.origin='model_proposal'", {"id": record["id"], "goal": record["goal"], "json": raw, "at": record.get("updated_at", public.now())})
    _proposal_graph(graph, record, create=True)
    for index, event in enumerate(record.get("events", [])):
        identity = record["id"] + ":event:" + str(event.get("seq", index))
        graph.query("MATCH (g:Goal {id:$goal}) MERGE (e:GoalEpisode {id:$id}) SET e.json=$json,e.type=$type MERGE (g)-[:OBSERVED]->(e)",
                    {"goal": record["id"], "id": identity, "json": C.encode(event), "type": event.get("type", "observation")})
    for index, action in enumerate(record.get("actions", [])):
        graph.query("MATCH (g:Goal {id:$goal}) MERGE (a:GoalAction {id:$id}) SET a.json=$json MERGE (g)-[:OBSERVED]->(a)",
                    {"goal": record["id"], "id": record["id"] + ":action:" + str(index), "json": C.encode(action)})
    return copy.deepcopy(record)


@_bounded
def create_goal(data, port, record):
    if _rows(_graph(port), "MATCH (g:Goal {id:$id}) RETURN g.id", {"id": record.get("id")}):
        raise ValueError("Goal already exists")
    return save_goal(data, port, record)


@_bounded
def get_goal(data, port, id):
    _text(id, 120)
    rows = _rows(_graph(port), "MATCH (g:Goal {id:$id}) RETURN g.json", {"id": id})
    if not rows:
        return None
    record = json.loads(rows[0][0])
    _proposal_graph(_graph(port), record)
    episodes = _rows(_graph(port), "MATCH (:Goal {id:$id})-[:OBSERVED]->(e:GoalEpisode) RETURN e.id,e.json", {"id": id})
    expected = {id + ":event:" + str(e.get("seq", index)): C.encode(e) for index, e in enumerate(record.get("events", []))}
    if len(episodes) != len(expected) or dict(episodes) != expected:
        raise ValueError("Native observation episode binding changed")
    actions = _rows(_graph(port), "MATCH (:Goal {id:$id})-[:OBSERVED]->(a:GoalAction) RETURN a.id,a.json", {"id": id})
    expected_actions = {id + ":action:" + str(index): C.encode(a) for index, a in enumerate(record.get("actions", []))}
    if len(actions) != len(expected_actions) or dict(actions) != expected_actions:
        raise ValueError("Native action receipt binding changed")
    return record


@_bounded
def latest_goal(data, port):
    rows = _rows(_graph(port), "MATCH (g:Goal) RETURN g.id ORDER BY g.updated_at DESC,g.id DESC LIMIT 1")
    return get_goal(data, port, rows[0][0]) if rows else None


@_bounded
def ready_steps(data, port, id):
    record = get_goal(data, port, id)
    if not record or not record.get("proposal"):
        return []
    evidence_binding(data, port, record.get("evidence", []))
    revision = id + ":" + record["proposal"]["hash"]
    stored_states = _rows(_graph(port), "MATCH (p:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep) RETURN s.step_id,s.status", {"plan": revision})
    complete = _completed(record)
    if any(status != ("completed" if step_id in complete else "pending") for step_id, status in stored_states):
        raise ValueError("Native step completion does not match actual current-plan receipts")
    rows = _rows(_graph(port), "MATCH (g:Goal {id:$goal})-[:CURRENT_PLAN]->(p:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep) "
                 "WHERE s.status<>'completed' OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:GoalStep) "
                 "WITH s,collect(d.status) AS states WHERE all(state IN states WHERE state='completed') "
                 "RETURN s.step_id ORDER BY s.step_id", {"goal": id, "plan": revision})
    return [row[0] for row in rows]
