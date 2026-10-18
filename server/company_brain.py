"""Source-backed company context from a bounded public contribution graph.

Accounts are public contributors, never inferred employees or company owners.
Two bulk read-only queries provide explainable paths without per-item reads.
"""
from collections import defaultdict

from baton import graph as G
from . import public_workspace as public


CONTRIBUTION_QUERY = (
    "MATCH (a:Account)-[:AUTHORED]->(w:WorkItem)-[:IN_REPOSITORY]->(r:Repository) "
    "OPTIONAL MATCH (w)-[:EVIDENCED_BY]->(s:Source) "
    # Group and sort scalar IDs before creating output maps. FalkorDB rejects
    # ORDER BY w.id after an aggregate RETURN that projects only {id:w.id}.
    "WITH a.id AS author_id,w.id AS work_id,r.id AS repository_id,"
    "collect(DISTINCT s.id) AS source_ids ORDER BY work_id LIMIT 100 "
    "RETURN {id:author_id},{id:work_id},repository_id,source_ids,[]"
)

CONTRIBUTION_LIMIT = 100
SHARED_PATH_LIMIT = 50


def _file_evidence(item, evidence_ids, path, sources):
    """Only an actually captured files endpoint can prove a TOUCHES edge."""
    if path not in {entry["path"] for entry in item.get("files", [])}:
        return []
    endpoint = "https://api.github.com/repos/" + item["repo"] + "/pulls/" + str(item["number"]) + "/files"
    return sorted({identity for identity in evidence_ids
                   if sources[identity]["url"].split("?")[0] == endpoint})


def _prioritize_gaps(gaps, observed):
    """Present varied, source-supported next steps before repeating work.

    This is a transparent display policy, not an estimate of business impact or
    urgency. Keep the complete queue; diversity only affects its presentation.
    """
    order = {"no_reviews_in_capture": 0, "unassigned_open_work": 1,
             "review_evidence_missing": 2}
    reasons = {"no_reviews_in_capture": "The captured review endpoint contains no review records.",
               "unassigned_open_work": "The captured open item lists no GitHub assignee.",
               "review_evidence_missing": "Review status is unknown because its endpoint was not captured."}
    pending = [gap for gap in gaps if gap["kind"] != "review_recorded"]
    ranked, seen_items, seen_kinds, seen_repositories = [], set(), set(), set()
    while pending:
        # All IDs/kinds come from validated graph rows and pinned source data.
        chosen = min(pending, key=lambda gap: (
            gap["item_id"] in seen_items,
            gap["kind"] in seen_kinds,
            observed[gap["item_id"]]["repo"] in seen_repositories,
            order.get(gap["kind"], 3), gap["item_id"], gap["kind"]))
        pending.remove(chosen)
        work = observed[chosen["item_id"]]
        ranked.append({**chosen, "triage_rank": len(ranked) + 1, "repo": work["repo"],
                       "work_url": work["url"],
                       "ranking_basis": reasons.get(chosen["kind"], "Captured evidence supports this next step.")
                           + " Display order covers different work, gap kinds, and repositories; it does not establish urgency.",
                       "context_path": {"nodes": [work["author"], chosen["item_id"], work["repo"]],
                                        "relations": ["AUTHORED", "IN_REPOSITORY"],
                                        "source_ids": work["source_ids"]}})
        seen_items.add(chosen["item_id"])
        seen_kinds.add(chosen["kind"])
        seen_repositories.add(work["repo"])
    return ranked


SHARED_FILE_QUERY = (
    "MATCH (a:Account)-[:AUTHORED]->(w:WorkItem)-[:TOUCHES]->(f:File)"
    "<-[:TOUCHES]-(other:WorkItem)<-[:AUTHORED]-(b:Account) "
    "WHERE w.id<other.id "
    "RETURN w.id,other.id,f.path,a.id,b.id ORDER BY w.id,other.id,f.path LIMIT 50"
)


def overview(data, port):
    """Return current public company context; propagate unavailable graph errors.

    Query output is intersected with the pinned import snapshot. Uncaptured
    reviews are unknown, not proof that a change has no reviewers.
    """
    snap = public.snapshot(data)
    graph = G.connect(port).select_graph(snap["graph"])
    rows = graph.ro_query(CONTRIBUTION_QUERY).result_set
    shared = graph.ro_query(SHARED_FILE_QUERY).result_set
    sources = {source["id"]: source for source in snap["sources"]}
    items = {item["id"]: item for item in snap["items"]}
    repositories = {repo["id"]: repo for repo in snap["repositories"] if repo["id"] in public.REPOS}

    def refs(ids):
        return [{key: sources[identity].get(key) for key in ("id", "url", "sha256", "fetched_at")}
                for identity in sorted(set(ids)) if identity in sources]

    accounts, observed, paths, gaps = {}, {}, [], []
    rejected = {"contributions": 0, "shared_file_paths": 0}
    repo_items = defaultdict(list)
    for account, work, repository, source_ids, assignees in rows[:CONTRIBUTION_LIMIT]:
        identity = work["id"]
        if identity not in items or repository not in repositories:
            rejected["contributions"] += 1
            continue
        item = items[identity]
        if repository != item["repo"] or account["id"] != item["author"]:
            rejected["contributions"] += 1
            continue
        evidence_ids = sorted(set(source_ids) & set(item["source_ids"]) & sources.keys())
        # Unproven graph records must not become presented company facts.
        if not evidence_ids:
            rejected["contributions"] += 1
            continue
        if identity in observed:
            continue
        # Values come from this snapshot, not potentially changed graph properties.
        observed[identity] = {"item_id": identity, "title": item["title"], "url": item["url"],
                              "kind": item["kind"], "state": item["state"], "repo": repository,
                              "author": account["id"], "source_ids": evidence_ids}
        repo_items[repository].append(identity)
        person = accounts.setdefault(account["id"], {"login": account["id"], "url": "https://github.com/" + account["id"],
                    "account_type": item.get("author_type", "unknown"), "authored_items": [],
                    "repositories": [], "source_ids": []})
        person["authored_items"].append(identity)
        person["repositories"].append(repository)
        person["source_ids"].extend(evidence_ids)
        paths.append({"nodes": [account["id"], identity, repository],
                      "relations": ["AUTHORED", "IN_REPOSITORY"], "source_ids": evidence_ids})
        if item["state"] == "open" and not item.get("assignees"):
            gaps.append({"kind": "unassigned_open_work", "item_id": identity,
                         "title": item["title"], "action": "Confirm who should triage this public work item.",
                         "detail": "No GitHub assignee in this captured sample; this does not establish internal ownership.",
                         "source_ids": evidence_ids})
        if item["kind"] == "pull_request" and item["state"] == "open":
            endpoint = "https://api.github.com/repos/" + repository + "/pulls/" + str(item["number"]) + "/reviews"
            captured_reviews = [s for s in evidence_ids if sources[s]["url"].split("?")[0] == endpoint]
            gaps.append({"kind": "review_evidence_missing" if not captured_reviews else
                                  "review_recorded" if item.get("reviewers") else "no_reviews_in_capture",
                         "item_id": identity, "title": item["title"],
                         "action": "Inspect current pull request review status before assigning review work.",
                         "detail": "Review endpoint was not captured." if not captured_reviews else
                                   "Captured review records are historical and may have changed.",
                         "source_ids": captured_reviews or evidence_ids})

    shared_paths, seen_shared = [], set()
    for first, second, path, author, other_author in shared[:SHARED_PATH_LIMIT]:
        if (first not in observed or second not in observed
                or items[first]["repo"] != items[second]["repo"]
                or author != observed[first]["author"] or other_author != observed[second]["author"]):
            rejected["shared_file_paths"] += 1
            continue
        first_refs = _file_evidence(items[first], observed[first]["source_ids"], path, sources)
        second_refs = _file_evidence(items[second], observed[second]["source_ids"], path, sources)
        if not first_refs or not second_refs:
            rejected["shared_file_paths"] += 1
            continue
        key = (first, second, path)
        if key in seen_shared:
            continue
        seen_shared.add(key)
        evidence_ids = sorted(set(first_refs + second_refs))
        # A local source-deletion ablation, not an attack/retriever reproduction.
        # Each endpoint needs one retained source; removing its last source cuts
        # this particular evidence path. Report fragility instead of certainty.
        cut_sources = [identity for identity in evidence_ids
                       if not set(first_refs) - {identity} or not set(second_refs) - {identity}]
        shared_paths.append({"item_ids": [first, second], "file": path,
                             "repo": items[first]["repo"],
                             "contributors": sorted({author, other_author}),
                             "relations": ["AUTHORED", "TOUCHES", "TOUCHES_REVERSE", "AUTHORED_REVERSE"],
                             "source_ids": evidence_ids,
                             "evidence_robustness": {"endpoint_source_counts": [len(first_refs), len(second_refs)],
                                "single_source_cuts": cut_sources,
                                "survives_any_single_source_loss": not cut_sources,
                                "basis": "Local deletion of captured file evidence; not independent corroboration."},
                             "action": "Compare overlapping changes and ask the recorded contributors for context.",
                             "limit": "Shared file changes suggest review context; they do not prove a dependency or ownership."})

    for person in accounts.values():
        for key in ("authored_items", "repositories", "source_ids"):
            person[key] = sorted(set(person[key]))
    cited = {s for work in observed.values() for s in work["source_ids"]}
    cited.update(identity for repo in repositories.values() for identity in repo.get("source_ids", [])
                 if identity in sources)
    return {"company": {"name": "FalkorDB", "basis": "Public repositories and public contributor activity"},
            "snapshot_id": snap["id"], "captured_at": snap["captured_at"], "graph": snap["graph"],
            "repositories": [{**repo, "sampled_items": sorted(set(repo_items[identity]))}
                             for identity, repo in repositories.items()],
            "people": sorted(accounts.values(), key=lambda p: (-len(p["authored_items"]), p["login"])),
            "work": sorted(observed.values(), key=lambda work: work["item_id"]),
            "paths": paths, "shared_file_paths": shared_paths,
            "gaps": _prioritize_gaps(gaps, observed),
            "sources": refs(cited), "queries": [CONTRIBUTION_QUERY, SHARED_FILE_QUERY],
            "query_count": 2, "bounds": {"contribution_rows": 100, "shared_file_paths": 50},
            "diagnostics": {"rejected_rows": rejected,
                            "contribution_limit_reached": len(rows) >= CONTRIBUTION_LIMIT,
                            "shared_path_limit_reached": len(shared) >= SHARED_PATH_LIMIT,
                            "gap_ordering": "Distinct work first; then cover gap kinds and repositories; "
                                            "captured review gaps precede generic unassigned-work ties. "
                                            "Presentation order is not business urgency.",
                            "limit_semantics": "Bounds cap returned rows, not database scan work."},
            "scope": snap["scope"],
            "limits": ["Contributor accounts do not establish employment, team membership, or internal ownership.",
                       "Only imported public samples are covered; absent evidence is not evidence of absence.",
                       "No internal Jira, Slack, documents, decisions, or company-wide dependency inventory is inferred."]}
