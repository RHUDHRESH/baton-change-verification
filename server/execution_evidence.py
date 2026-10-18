"""Import one reviewed public execution artifact into its existing work graph.

The service does not execute code or accept arbitrary attestations. Its approved
digest pins the real, post-run-audited KAN-2 manifest. A future run requires an
explicit review and digest update; provider credentials never enter this route.
"""
from datetime import datetime
import hashlib
import json
import re

from baton import graph as G
from . import public_workspace as public


TASK_ID = "task-agent-c108922c16a39ceaa82623d5748c4df0"
ITEM_ID = "FalkorDB/FalkorDB#3246"
SOURCE_URL = "https://github.com/FalkorDB/FalkorDB/issues/3246"
SOURCE_COMMIT = "d8190da5a99b4207e847e2fa2547911d96bd9e61"
APPROVED_REPORT_SHA256 = "19fd8fbf48e238480400d31e215d13d2b22bf681edbb417137f7a8ab0477bb85"
APPROVED_CHECKS_SHA256 = "cc8ea10ab3a651d3d067effc9d318b432f35a54af7c5235d01f22bd91cd7633e"
APPROVED_RECEIPT_SHA256 = "8b16bd88d5f5914b775e9b537ec686bda6590a05a64e20635cf1908508ffe783"
IMAGE = "ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7"
PATCH_PATH = "docs/evidence/kan2-fixtures/cap-clamp.patch"
PATCHED_SOURCE = "graph/src/runtime/ops/batched_result_emitter.rs"
SCOPE = "Imported audited execution evidence. Codex ran these checks in an isolated Docker runner; Lambda and Groq did not execute them."
TARGET_NAMES = {prefix + "_" + suffix for prefix in ("head", "restored_head", "before_grow_only")
                for suffix in ("debug_resize", "debug_restore", "release_resize", "release_restore")}
CHECK_NAMES = TARGET_NAMES | {"head_graph_library", "head_format", "head_module_build", "head_real_rdb_roundtrip",
    "baseline_apply", "baseline_restore", "cap_clamp_apply", "cap_clamp_restore"}
APPROVED_EVIDENCE_URL = "https://github.com/RHUDHRESH/baton-graph-workspace/blob/1b76598a72bc1ac878dc46389851a995caef7379/docs/evidence/KAN-2.md"
INDEX_PATH = "executions/kan2.json"
PUBLIC_EVIDENCE = "https://baton-workspace.vercel.app/evidence/"

WRITE_QUERY = (
    "MATCH (t:LocalTask {id:$task})-[:TRACKS]->(w:WorkItem {id:$item}) "
    "OPTIONAL MATCH (prior:ExecutionReceipt {id:$id}) "
    "WITH t,w,prior WHERE prior IS NULL OR prior.evidence_url=$url "
    "MERGE (e:ExecutionReceipt {id:$id}) "
    "ON CREATE SET e.receipt_json=$receipt,e.imported_at=$at "
    "SET e.task_id=$task,e.item_id=$item,e.title='KAN-2 audited code checks',e.status='passed',"
    "e.report_sha256=$digest,e.source_commit=$commit,e.executor=$executor,e.evidence_url=$url "
    "MERGE (t)-[:HAS_EXECUTION]->(e) MERGE (e)-[:VALIDATES]->(w) "
    "WITH e UNWIND $checks AS check "
    "MERGE (c:ExecutionCheck {id:check.id}) "
    "SET c.title=check.name,c.name=check.name,c.expectation=check.expectation,c.exit_code=check.exit_code,"
    "c.matched_expectation=true,c.log_sha256=check.log_sha256,c.check_json=check.json "
    "MERGE (e)-[:HAS_CHECK]->(c) RETURN e.receipt_json,count(DISTINCT c)"
)
READ_QUERY = (
    "MATCH (t:LocalTask {id:$task})-[:TRACKS]->(w:WorkItem {id:$item}), "
    "(t)-[:HAS_EXECUTION]->(e:ExecutionReceipt)-[:VALIDATES]->(w), (e)-[:HAS_CHECK]->(c:ExecutionCheck) "
    "WHERE e.task_id=$task AND e.item_id=$item "
    "WITH e,collect({payload:c.check_json,id:c.id,name:c.name,expectation:c.expectation,exit_code:c.exit_code,"
    "matched_expectation:c.matched_expectation,log_sha256:c.log_sha256}) AS checks ORDER BY e.imported_at DESC LIMIT 10 "
    "RETURN e.receipt_json,checks"
)


class ExecutionError(ValueError):
    """Application-owned validation errors; provider failures stay sanitized."""


def _require(condition, message):
    if not condition:
        raise ExecutionError(message)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Execution manifest contains duplicate fields")
        result[key] = value
    return result


def validate_manifest(task_id, manifest_json, evidence_url):
    """Validate the exact reviewed bytes, rather than trusting claimed outcomes."""
    _require(task_id == TASK_ID, "Execution evidence is approved only for the existing KAN-2 task")
    _require(evidence_url == APPROVED_EVIDENCE_URL, "Choose the approved immutable KAN-2 GitHub evidence document")
    _require(isinstance(manifest_json, str) and 1 <= len(manifest_json.encode("utf-8")) <= 50_000, "Execution manifest exceeds the import limit")
    try:
        report = json.loads(manifest_json, object_pairs_hook=_unique_pairs)
    except (json.JSONDecodeError, TypeError):
        raise ExecutionError("Execution manifest must be valid JSON") from None
    _require(isinstance(report, dict) and report.get("status") == "passed" and report.get("task") == "KAN-2", "Only a passed KAN-2 execution can be imported")
    digest = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    _require(digest == APPROVED_REPORT_SHA256, "Execution manifest differs from the reviewed audited artifact")
    # Structural assertions document the approved artifact contract and guard
    # future deliberate digest updates from weakening the import requirements.
    _require(report.get("source_repository") == "https://github.com/FalkorDB/FalkorDB" and report.get("source_commit") == SOURCE_COMMIT and
             report.get("executor") == "Codex isolated Docker runner" and report.get("image") == IMAGE, "Execution provenance does not match the approved source and runner")
    checks = report.get("checks", [])
    _require(isinstance(checks, list) and len(checks) == 20 and {c.get("name") for c in checks} == CHECK_NAMES, "Execution requires the complete reviewed twenty-check inventory")
    for check in checks:
        _require(check.get("matched_expectation") is True and type(check.get("exit_code")) is int and
                 re.fullmatch(r"[a-f0-9]{64}", check.get("log_sha256", "")), "An execution check is unverified")
        baseline = check["name"].startswith("before_grow_only_")
        _require(check.get("expectation") == ("regression_failure" if baseline else "success") and check["exit_code"] == (101 if baseline else 0), "Execution outcomes differ from the approved contract")
        if check["name"] in TARGET_NAMES:
            expected = {"status": "FAILED" if baseline else "ok", "passed": 0 if baseline else 1,
                        "failed": 1 if baseline else 0, "ignored": 0}
            _require(check.get("test_summaries") == [expected], "Targeted checks must execute the expected single test")
    by_name = {check["name"]: check for check in checks}
    _require(by_name["head_graph_library"].get("test_summaries") == [{"status": "ok", "passed": 530, "failed": 0, "ignored": 17}], "The executed graph-library counts do not match")
    rdb = by_name["head_real_rdb_roundtrip"]
    _require(all(type(rdb.get(key)) is int and rdb[key] == 2 for key in ("round_trips", "nodes_preserved", "parallel_edges_preserved")), "The two real RDB reloads are not verified")
    for key in ("source_verification", "restored_source_verification"):
        _require(report.get(key) == {"tracked_blobs": 957, "mismatches": []}, "Original source restoration is unverified")
    _require(report.get("patched_source_verification") == {"tracked_blobs": 957, "mismatches": [PATCHED_SOURCE]}, "The isolated workaround scope is unverified")
    patch = report.get("applied_patch", {})
    _require(patch.get("path") == PATCH_PATH and re.fullmatch(r"[a-f0-9]{64}", patch.get("sha256", "")) and
             report.get("container_patch_sha256", {}).get("/cap-clamp.patch") == patch["sha256"] and
             report.get("container_patch_sha256", {}).get("/before-grow-only.patch") == report.get("baseline_patch_sha256"), "Patch artifacts do not match the audited run")
    history = report.get("initial_failures", [])
    _require(len(history) == 1 and history[0].get("name") == "head_graph_library" and history[0].get("matched_expectation") is False and
             history[0].get("test_summaries") == [{"status": "FAILED", "passed": 529, "failed": 1, "ignored": 17}], "The original unpatched failure must remain visible")
    audit = report.get("post_run_audit", {})
    inventory = audit.get("log_inventory", [])
    _require(audit.get("status") == "verified" and len(inventory) == 20 and
             {entry.get("name"): entry.get("sha256") for entry in inventory} == {c["name"]: c["log_sha256"] for c in checks}, "The post-run raw-log audit is incomplete")
    _require(audit.get("initial_failure_log_sha256") == history[0]["log_sha256"] and audit.get("restored_source_verification") == report["restored_source_verification"], "Historical failure or restored-source audit does not match")
    try:
        _require(datetime.fromisoformat(audit["at"]).tzinfo is not None, "Audit timestamp must include a timezone")
    except (KeyError, TypeError, ValueError):
        raise ExecutionError("Audit timestamp is invalid") from None
    return report, digest


def _task(data, required=True):
    task = next((task for task in public.read(data, "tasks.json", []) if task.get("id") == TASK_ID), None)
    if task is None and not required:
        return None
    _require(task is not None and task.get("item_id") == ITEM_ID, "The existing task must track the public KAN-2 source issue")
    _validate_binding(data, task)
    return task


def _validate_binding(data, task):
    _require(isinstance(task.get("graph"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", task["graph"]), "Task graph binding is invalid")
    snapshot_id = task.get("snapshot_id", "")
    _require(isinstance(snapshot_id, str) and re.fullmatch(r"[a-f0-9]{24}", snapshot_id), "Task snapshot binding is invalid")
    snapshot = public.read(data, "snapshots/" + snapshot_id + ".json", {})
    item = next((item for item in snapshot.get("items", []) if item.get("id") == ITEM_ID), None)
    sources = {source["id"] for source in snapshot.get("sources", [])}
    _require(snapshot.get("id") == snapshot_id and snapshot.get("graph") == task["graph"] and item and item.get("url") == SOURCE_URL and
             item.get("source_ids") and set(item["source_ids"]).issubset(sources), "Task source provenance does not match the captured public issue")


def _index(data):
    value = public.read(data, INDEX_PATH)
    if value is None:
        return None
    _require(isinstance(value, dict) and value.get("task_id") == TASK_ID and value.get("item_id") == ITEM_ID and
             value.get("report_sha256") == APPROVED_REPORT_SHA256 and value.get("evidence_url") == APPROVED_EVIDENCE_URL,
             "Recorded execution binding is invalid")
    _validate_binding(data, value)
    return value


def _receipt(report, digest, evidence_url):
    identity = "execution-kan2-" + digest
    checks = []
    for check in report["checks"]:
        value = {key: check[key] for key in ("name", "command", "expectation", "exit_code", "matched_expectation", "log_sha256", "log_bytes", "test_summaries")}
        value["id"] = identity + ":" + check["name"]
        filename = "rdb_roundtrip.json" if check["name"] == "head_real_rdb_roundtrip" else check["name"] + ".log"
        value["log_url"] = PUBLIC_EVIDENCE + "kan2-logs/" + filename if check["log_bytes"] > 0 else None
        for key in ("round_trips", "nodes_preserved", "parallel_edges_preserved", "expected_failure_reason"):
            if key in check:
                value[key] = check[key]
        checks.append(value)
    return {"id": identity, "task_id": TASK_ID, "root_issue": "KAN-2", "item_id": ITEM_ID, "status": "passed",
        "evidence_url": evidence_url, "public_evidence_url": PUBLIC_EVIDENCE + "KAN-2.md", "manifest_url": PUBLIC_EVIDENCE + "execution.json",
        "report_sha256": digest, "source_repository": report["source_repository"],
        "source_commit": SOURCE_COMMIT, "image": IMAGE, "executor": report["executor"], "imported_at": public.now(),
        "validation": "approved_manifest_digest_and_graph_binding", "scope": SCOPE,
        "summary": {"checks": 20, "graph_library": {"passed": 530, "failed": 0, "ignored": 17},
                    "targeted_checks": 8, "expected_regression_failures": 4,
                    "rdb": {"round_trips": 2, "nodes_preserved": 2, "parallel_edges_preserved": 2}},
        "initial_failure": {"passed": 529, "failed": 1, "ignored": 17, "log_sha256": report["initial_failures"][0]["log_sha256"],
                            "log_url": PUBLIC_EVIDENCE + "kan2-logs/initial_graph_library.log"},
        "workaround": {"path": PATCH_PATH, "sha256": report["applied_patch"]["sha256"],
                       "scope": "Verified only in the isolated workspace; not an upstream merge."},
        "audit": {"status": "verified", "at": report["post_run_audit"]["at"], "method": "Post-run raw-log/source/runner audit",
                  "scope": "Patched-file hash was observed during the RDB module build; no earlier unit-test file-hash observation is claimed."},
        "checks": checks}


def import_execution(data, port, task_id, manifest_json, evidence_url):
    report, digest = validate_manifest(task_id, manifest_json, evidence_url)
    task = _task(data)
    binding = _index(data) or task
    receipt = _receipt(report, digest, evidence_url)
    receipt["task_status"] = task.get("status")
    rows = [{"id": check["id"], "name": check["name"], "expectation": check["expectation"], "exit_code": check["exit_code"],
             "log_sha256": check["log_sha256"], "json": json.dumps(check, sort_keys=True)} for check in receipt["checks"]]
    graph = G.connect(port).select_graph(binding["graph"])
    result = graph.query(WRITE_QUERY, {
        "task": TASK_ID, "item": ITEM_ID, "id": receipt["id"], "url": evidence_url, "digest": digest,
        "commit": SOURCE_COMMIT, "executor": receipt["executor"], "at": receipt["imported_at"],
        "receipt": json.dumps(receipt, sort_keys=True), "checks": rows}).result_set
    if len(result) != 1 or result[0][1] != 20:
        raise RuntimeError("Execution evidence graph write was not confirmed; check the existing task and immutable evidence URL")
    stored = json.loads(result[0][0])
    if stored.get("id") != receipt["id"] or stored.get("evidence_url") != evidence_url:
        raise RuntimeError("Execution evidence graph read-back did not match the imported artifact")
    rows = graph.ro_query(READ_QUERY, {"task": TASK_ID, "item": ITEM_ID}).result_set
    confirmed = _read_receipts(rows, task.get("status"))
    if len(confirmed) != 1 or confirmed[0]["id"] != receipt["id"]:
        raise RuntimeError("Independent execution graph read-back did not confirm the imported artifact")
    public.write(data, INDEX_PATH, {"task_id": TASK_ID, "item_id": ITEM_ID, "graph": binding["graph"],
        "snapshot_id": binding["snapshot_id"], "report_sha256": digest, "evidence_url": evidence_url})
    return confirmed[0]


def _read_receipts(rows, task_status):
    if len(rows) > 10:
        raise RuntimeError("Stored execution inventory exceeds its bound")
    executions = []
    for payload, check_payloads in rows:
        receipt = json.loads(payload)
        checks = []
        for node in check_payloads:
            check = json.loads(node["payload"])
            if any(node.get(key) != check.get(key) for key in ("id", "name", "expectation", "exit_code", "matched_expectation", "log_sha256")):
                raise RuntimeError("Execution check node properties contradict its evidence payload")
            checks.append(check)
        if receipt.get("report_sha256") != APPROVED_REPORT_SHA256 or receipt.get("task_id") != TASK_ID or len(checks) != 20 or {c.get("name") for c in checks} != CHECK_NAMES:
            raise RuntimeError("Stored execution receipt is incomplete; no substitute results are available")
        expected = receipt.get("checks", [])
        ordered = sorted(checks, key=lambda c: c["name"])
        actual_digest = hashlib.sha256(json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (actual_digest != APPROVED_CHECKS_SHA256 or len(expected) != 20 or ordered != sorted(expected, key=lambda c: c["name"]) or
                receipt.get("id") != "execution-kan2-" + APPROVED_REPORT_SHA256 or
                receipt.get("evidence_url") != APPROVED_EVIDENCE_URL or receipt.get("status") != "passed" or
                receipt.get("item_id") != ITEM_ID or receipt.get("source_commit") != SOURCE_COMMIT or
                receipt.get("executor") != "Codex isolated Docker runner" or receipt.get("image") != IMAGE):
            raise RuntimeError("Stored execution graph check read-back contradicts its approved receipt")
        for check in checks:
            baseline = check["name"].startswith("before_grow_only_")
            if check.get("matched_expectation") is not True or check.get("exit_code") != (101 if baseline else 0):
                raise RuntimeError("Stored execution outcome contradicts its approved contract")
        projection = {key: value for key, value in receipt.items() if key not in ("imported_at", "task_status")}
        projection["checks"] = ordered
        projection_digest = hashlib.sha256(json.dumps(projection, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if projection_digest != APPROVED_RECEIPT_SHA256:
            raise RuntimeError("Stored execution summary contradicts its approved receipt")
        receipt["checks"] = sorted(checks, key=lambda check: check["name"])
        receipt["task_status"] = task_status
        executions.append(receipt)
    return executions


def list_executions(data, port):
    binding = _index(data)
    indexed = binding is not None
    task = next((task for task in public.read(data, "tasks.json", []) if task.get("id") == TASK_ID), None)
    if task is not None:
        _require(task.get("item_id") == ITEM_ID, "The existing task must track the public KAN-2 source issue")
    if binding is None:
        binding = _task(data, required=False)
    if binding is None:
        return {"executions": [], "scope": "KAN-2 only; last 10 imported receipts", "limit": 10}
    rows = G.connect(port).select_graph(binding["graph"]).ro_query(READ_QUERY, {"task": TASK_ID, "item": ITEM_ID}).result_set
    executions = _read_receipts(rows, task.get("status") if task else None)
    if indexed and len(executions) != 1:
        raise RuntimeError("Recorded execution graph relationships are unavailable; no substitute results are shown")
    return {"executions": executions, "scope": "KAN-2 only; last 10 imported receipts", "limit": 10}
