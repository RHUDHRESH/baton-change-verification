"""Audit completed KAN-2 execution artifacts without rerunning Rust checks.

Only post-run evidence metadata is added. Recorded commands, outcomes, counts
and historical failures are never manufactured or changed. No provider calls.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deploy.complete_kan2 import FULL_SUITE, REQUIRED, TARGET_CHECKS, verify_command
from verify_kan2 import CONTAINER, HEAD, IMAGE, OUT, capture, verify_source_bytes

PATCHED_SOURCE = "graph/src/runtime/ops/batched_result_emitter.rs"
SUMMARY = re.compile(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_summaries(text):
    return [{"status": status, "passed": int(passed), "failed": int(failed), "ignored": int(ignored)}
            for status, passed, failed, ignored in SUMMARY.findall(text)]


def failure_reason(name, text):
    if name == "before_grow_only_debug_resize":
        require("resize_asserts_it_never_shrinks" in text and "test did not panic as expected" in text,
                "Baseline debug resize failed for an unknown reason")
        return "The parent implementation did not produce the required debug panic on a shrink request."
    if name.endswith("_restore"):
        require("restore_never_shrinks_the_saved_matrices" in text and "node_cap 16384 below the saved size" in text,
                "Baseline restore failed for an unknown reason")
        return "The parent restore retained node_cap 16384 instead of the saved matrix dimension 40960."
    require(name == "before_grow_only_release_resize" and "resize shrank the tensor" in text and
            re.search(r"left:\s*\(4, 4\)\s+right:\s*\(8, 8\)", text),
            "Baseline release resize failed for an unknown reason")
    return "The parent implementation shrank tensor dimensions to (4, 4), violating the expected (8, 8) dimensions."


def verify_raw_check(check, raw, historical=False):
    name = check["name"]
    require(digest(raw) == check.get("log_sha256") and len(raw) == check.get("log_bytes"),
            "Raw log hash/size mismatch: " + name)
    verify_command(name, check.get("command"))
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    summaries = parse_summaries(text)
    require(summaries == check.get("test_summaries"), "Raw test summaries differ from the manifest: " + name)
    if historical:
        require(name == "head_graph_library" and check.get("exit_code") == 101 and
                check.get("matched_expectation") is False and
                summaries == [{"status": "FAILED", "passed": 529, "failed": 1, "ignored": 17}] and
                "cap_at_or_above_batch_size_is_ignored" in text and
                re.search(r"left:\s*1025\s+right:\s*1024", text), "Unexpected historical graph-library failure")
        return None
    require(check.get("matched_expectation") is True, "A recorded check did not match its expectation")
    if name.startswith("before_grow_only_"):
        require(check.get("exit_code") == 101 and check.get("expectation") == "regression_failure" and
                summaries == [{"status": "FAILED", "passed": 0, "failed": 1, "ignored": 0}] and
                re.search(r"(?m)^running 1 test$", text), "Baseline did not execute exactly one failing regression")
        return failure_reason(name, text)
    require(check.get("exit_code") == 0 and check.get("expectation") == "success", "A success check failed")
    if name in TARGET_CHECKS:
        identity = check["command"][check["command"].index("--lib") + 1]
        require(summaries == [{"status": "ok", "passed": 1, "failed": 0, "ignored": 0}] and
                re.search(r"(?m)^running 1 test$", text) and identity in text,
                "Targeted check did not execute its one passing test")
    elif name == "head_graph_library":
        require(summaries == [FULL_SUITE] and re.search(r"(?m)^running 547 tests$", text),
                "The full raw graph suite does not report 530 passed / 0 failed / 17 ignored")
    else:
        require(summaries == [], "A non-test command contains unexpected test summaries")
    return None


def patched_bytes(original, patch):
    """Reconstruct the approved one-file diff in memory, not in the runner."""
    lines = patch.decode().splitlines(keepends=True)
    require(lines.count("diff --git a/" + PATCHED_SOURCE + " b/" + PATCHED_SOURCE + "\n") == 1 and
            sum(line.startswith("diff --git ") for line in lines) == 1, "Unexpected workaround patch scope")
    source = original.decode().splitlines(keepends=True)
    result, cursor, index = [], 0, 0
    while index < len(lines):
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[index])
        if not match:
            index += 1
            continue
        start = int(match[1]) - 1
        require(start >= cursor, "Overlapping patch hunks")
        result.extend(source[cursor:start])
        cursor = start
        old_count = new_count = 0
        index += 1
        while index < len(lines) and lines[index][:1] in (" ", "+", "-"):
            prefix, value = lines[index][0], lines[index][1:]
            if prefix in (" ", "-"):
                require(cursor < len(source) and source[cursor] == value, "Patch context differs from pinned source")
                cursor += 1
                old_count += 1
            if prefix in (" ", "+"):
                result.append(value)
                new_count += 1
            index += 1
        require(old_count == int(match[2] or 1) and new_count == int(match[4] or 1), "Patch hunk counts differ")
    result.extend(source[cursor:])
    return "".join(result).encode()


def verify_roundtrip(raw, check):
    evidence = json.loads(raw)
    require(check.get("round_trips") == check.get("nodes_preserved") == check.get("parallel_edges_preserved") == 2,
            "RDB manifest does not record two round trips/two nodes/two edges")
    require(check["command"][5:] == evidence.get("server_command"), "RDB server argv differs from raw evidence")
    queries = evidence.get("queries", [])
    require(len(queries) == 12, "RDB evidence has an unexpected query inventory")
    setup = ["UNWIND range(0,90000) AS i CREATE (:KAN2 {i:i})",
             "MATCH (a:KAN2),(b:KAN2) WHERE id(a)=0 AND id(b)=1 CREATE (a)-[:R {tag:'first'}]->(b),(a)-[:R {tag:'second'}]->(b)",
             "MATCH (n:KAN2) WHERE id(n)>=2 DELETE n"]
    require([query.get("query") for query in queries[:3]] == setup, "RDB growth/deletion setup differs")
    expected = ["MATCH (n:KAN2) RETURN id(n),n.i ORDER BY id(n)",
                "MATCH (a)-[r:R]->(b) RETURN id(a),id(b),id(r),r.tag ORDER BY id(r)",
                "MATCH ()-[r:R]->() RETURN count(r)"]
    for offset in (3, 6, 9):
        require([q.get("query") for q in queries[offset:offset+3]] == expected, "RDB snapshot queries differ")
    keys = ("nodes", "edges", "edge_count")
    before = {key: queries[3+index]["result"][1] for index, key in enumerate(keys)}
    require(before["nodes"] == [[0, 0], [1, 1]] and before["edge_count"] == [[2]], "Unexpected pre-reload graph")
    edges = before["edges"]
    require(len(edges) == 2 and all(len(edge) == 4 and edge[:2] == [0, 1] for edge in edges) and
            len({edge[2] for edge in edges}) == 2 and {edge[3] for edge in edges} == {"first", "second"},
            "Pre-reload parallel edges do not match the claimed data")
    trips = evidence.get("round_trips", [])
    require(len(trips) == 2, "Raw evidence does not contain two RDB reloads")
    for index, trip in enumerate(trips):
        after = {key: queries[6+3*index+position]["result"][1] for position, key in enumerate(keys)}
        require(trip == {"iteration": index+1, "equal": True, "snapshot": before} and after == before,
                "RDB reload did not preserve the exact captured graph")


def audit(path=OUT / "execution.json"):
    path = Path(path)
    original = path.read_bytes()
    report = json.loads(original)
    require(report.get("status") == "passed" and report.get("task") == "KAN-2", "Refusing a failed/running report")
    require(report.get("source_commit") == HEAD and report.get("image") == IMAGE and
            report.get("source_repository") == "https://github.com/FalkorDB/FalkorDB" and
            report.get("executor") == "Codex isolated Docker runner", "Unapproved execution provenance")
    require(report.get("applied_patch", {}).get("path") == "docs/evidence/kan2-fixtures/cap-clamp.patch",
            "Unexpected workaround patch path")
    checks = report.get("checks", [])
    names = [check.get("name") for check in checks]
    require(len(names) == len(set(names)) and set(names) == REQUIRED | {"cap_clamp_apply", "cap_clamp_restore"},
            "Completed execution check inventory differs from the approved contract")
    verified = []
    for check in checks:
        filename = "rdb_roundtrip.json" if check["name"] == "head_real_rdb_roundtrip" else check["name"] + ".log"
        raw = (OUT / filename).read_bytes()
        reason = verify_raw_check(check, raw)
        if reason:
            check["expected_failure_reason"] = reason
        if check["name"] == "head_real_rdb_roundtrip":
            verify_roundtrip(raw, check)
        verified.append({"name": check["name"], "file": filename, "sha256": digest(raw)})
    history = report.get("initial_failures", [])
    require(len(history) == 1, "The original graph-library failure must remain visible")
    raw = (OUT / "initial_graph_library.log").read_bytes()
    verify_raw_check(history[0], raw, historical=True)
    history[0]["retained_log"] = "initial_graph_library.log"
    live = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER], text=True))[0]
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True))[0]
    require(live["Config"]["Image"] == IMAGE and live["Image"] == image["Id"], "Runner image identity differs")
    env = dict(item.split("=", 1) for item in live["Config"]["Env"] if "=" in item)
    expected_env = {"CARGO_BUILD_JOBS": "2", "CARGO_PROFILE_RELEASE_LTO": "false"}
    require(all(env.get(key) == value for key, value in expected_env.items()) and report.get("environment") == expected_env,
            "Runner environment differs from the reported configuration")
    require(capture(["git", "rev-parse", "HEAD"]) == HEAD, "Runner HEAD changed")
    for key in ("source_verification", "restored_source_verification"):
        require(report.get(key) == {"tracked_blobs": 957, "mismatches": []}, "Missing original/restored source verification")
    require(report.get("patched_source_verification") == {"tracked_blobs": 957, "mismatches": [PATCHED_SOURCE]},
            "Historical patched-source scope differs")
    restored = verify_source_bytes()
    require(restored == {"tracked_blobs": 957, "mismatches": []}, "Runner source is not restored")
    hashes = {}
    for container_path, fixture, declared in (
        ("/before-grow-only.patch", "before-grow-only.patch", report.get("baseline_patch_sha256")),
        ("/cap-clamp.patch", "cap-clamp.patch", report.get("applied_patch", {}).get("sha256")),
    ):
        local = (ROOT / "docs/evidence/kan2-fixtures" / fixture).read_bytes()
        actual = capture(["sha256sum", container_path]).split()[0]
        require(actual == digest(local) == declared, "Applied patch artifact hash differs: " + fixture)
        hashes[container_path] = actual
    prior_hashes = report.get("container_patch_sha256")
    require(prior_hashes is None or prior_hashes == hashes, "Recorded container patch hashes disagree")
    report["container_patch_sha256"] = hashes
    source = subprocess.check_output(["docker", "exec", "--workdir", "/work", CONTAINER,
                                      "git", "show", HEAD + ":" + PATCHED_SOURCE])
    expected_patched = patched_bytes(source, (ROOT / "docs/evidence/kan2-fixtures/cap-clamp.patch").read_bytes())
    proof_raw = (OUT / "patched-source-proof.json").read_bytes()
    proof = json.loads(proof_raw)
    require(proof.get("container") == CONTAINER and proof.get("source_commit") == HEAD and
            proof.get("path") == PATCHED_SOURCE and proof.get("sha256") == digest(expected_patched) and
            proof.get("patch_path") == "docs/evidence/kan2-fixtures/cap-clamp.patch" and
            proof.get("patch_sha256") == hashes["/cap-clamp.patch"] and proof.get("pinned_source_sha256") == digest(source),
            "Observed patched-source snapshot differs from pinned source plus reviewed patch")
    require(datetime.fromisoformat(proof["observed_at"]).tzinfo is not None and isinstance(proof.get("scope"), str),
            "Patched-source observation has no timestamp or scope")
    report["post_run_audit"] = {"status": "verified", "at": datetime.now(timezone.utc).isoformat(),
        "method": "Verified raw logs, exact commands, known baseline failure reasons, actual runner image/environment, patch artifacts and restored source bytes after execution.",
        "log_inventory": verified, "initial_failure_log_sha256": digest(raw), "runner_image_id": live["Image"],
        "restored_source_verification": restored, "expected_patched_source_sha256": digest(expected_patched),
        "observed_patched_source": proof, "patched_source_proof_sha256": digest(proof_raw),
        "patched_source_hash_scope": "Actual patched file observed during the RDB module-build stage and independently matched to pinned source plus reviewed patch. No earlier unit-test file-hash measurement is claimed.",
        "timing_scope": "Post-run verification; does not claim these additional checks ran before patch application.",
        "rdb_server_log_sha256": digest((OUT / "rdb-server.log").read_bytes())}
    require(path.read_bytes() == original, "Execution manifest changed while it was being audited")
    temporary = path.with_name(path.name + ".audit.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return report["post_run_audit"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT / "execution.json")
    args = parser.parse_args()
    try:
        result = audit(args.report)
        print(json.dumps({"status": result["status"], "checks": len(result["log_inventory"]), "method": result["method"]}))
    except Exception as error:
        print(json.dumps({"status": "refused", "error": str(error)}))
        raise SystemExit(1)
