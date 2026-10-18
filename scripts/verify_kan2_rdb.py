"""After KAN-2 unit regressions, build the module and exercise real RDB reloads."""
import hashlib
import json
import subprocess
import time
import uuid

from verify_kan2 import CONTAINER, OUT, command, verify_source_bytes


def main():
    report_path = OUT / "execution.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed", "Unit and counterfactual checks must pass first"
    verify_source_bytes()
    report["status"] = "running"

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def capture(args):
        return subprocess.check_output(command(args), text=True, stderr=subprocess.STDOUT).strip()

    save()
    patch_applied = False
    completed = False
    try:
        actual_patch = capture(["sha256sum", "/cap-clamp.patch"]).split()[0]
        assert actual_patch == report["applied_patch"]["sha256"]
        capture(["git", "apply", "/cap-clamp.patch"])
        patch_applied = True
        verify_source_bytes(["graph/src/runtime/ops/batched_result_emitter.rs"])
        args = ["cargo", "build", "--locked"]
        started = time.monotonic()
        path = OUT / "head_module_build.log"
        print("Building the actual Redis module", flush=True)
        with path.open("wb") as log:
            result = subprocess.run(command(args), stdout=log, stderr=subprocess.STDOUT)
        raw = path.read_bytes()
        report["checks"].append({"name": "head_module_build", "command": command(args),
            "exit_code": result.returncode, "duration_seconds": round(time.monotonic()-started, 2),
            "expectation": "success", "matched_expectation": result.returncode == 0,
            "log_sha256": hashlib.sha256(raw).hexdigest(), "log_bytes": len(raw), "test_summaries": []})
        save()
        assert result.returncode == 0, "Actual module build failed; inspect head_module_build.log"
        print("Module built; running isolated Redis RDB round trips", flush=True)
        redis_dir = "/work/kan2-rdb-" + uuid.uuid4().hex
        capture(["mkdir", "-p", redis_dir])
        server = ["redis-server", "--bind", "127.0.0.1", "--protected-mode", "yes", "--port", "6387",
            "--dir", redis_dir, "--dbfilename", "kan2.rdb", "--appendonly", "no", "--save", "",
            "--loadmodule", "/work/target/debug/libfalkordb.so", "--enable-debug-command", "yes",
            "--logfile", redis_dir + "/redis.log", "--daemonize", "yes"]
        capture(server)
        evidence = {"server_command": server, "queries": [], "round_trips": []}

        def redis(*args):
            result = capture(["redis-cli", "-h", "127.0.0.1", "-p", "6387", "--json", *args])
            return json.loads(result)

        def query(text, *, rows=True):
            value = redis("GRAPH.QUERY", "kan2-rdb", text)
            assert isinstance(value, list) and len(value) >= (2 if rows else 1), value
            evidence["queries"].append({"query": text, "result": value})
            return value[1] if rows else None

        def snapshot():
            return {"nodes": query("MATCH (n:KAN2) RETURN id(n),n.i ORDER BY id(n)"),
                "edges": query("MATCH (a)-[r:R]->(b) RETURN id(a),id(b),id(r),r.tag ORDER BY id(r)"),
                "edge_count": query("MATCH ()-[r:R]->() RETURN count(r)")}

        try:
            for attempt in range(50):
                try:
                    if redis("PING") == "PONG":
                        break
                except (subprocess.CalledProcessError, json.JSONDecodeError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Isolated Redis did not become ready")
            configured = redis("CONFIG", "GET", "dir")
            assert configured in ({"dir": redis_dir}, ["dir", redis_dir]), "Redis is not the fresh isolated server"
            query("UNWIND range(0,90000) AS i CREATE (:KAN2 {i:i})", rows=False)
            query("MATCH (a:KAN2),(b:KAN2) WHERE id(a)=0 AND id(b)=1 CREATE (a)-[:R {tag:'first'}]->(b),(a)-[:R {tag:'second'}]->(b)", rows=False)
            query("MATCH (n:KAN2) WHERE id(n)>=2 DELETE n", rows=False)
            before = snapshot()
            assert before["nodes"] == [[0, 0], [1, 1]] and before["edge_count"] == [[2]], before
            assert len(before["edges"]) == 2 and {row[3] for row in before["edges"]} == {"first", "second"}, before
            assert all(row[:2] == [0, 1] for row in before["edges"]), before
            assert redis("SAVE") == "OK"
            for iteration in range(2):
                assert redis("DEBUG", "RELOAD") == "OK"
                after = snapshot()
                assert after == before, {"before": before, "after": after}
                evidence["round_trips"].append({"iteration": iteration+1, "equal": True, "snapshot": after})
        finally:
            subprocess.run(command(["redis-cli", "-h", "127.0.0.1", "-p", "6387", "SHUTDOWN", "NOSAVE"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "cp", CONTAINER+":"+redis_dir+"/redis.log", str(OUT / "rdb-server.log")], check=True, stdout=subprocess.DEVNULL)
        raw = (json.dumps(evidence, indent=2) + "\n").encode()
        (OUT / "rdb_roundtrip.json").write_bytes(raw)
        report["checks"].append({"name": "head_real_rdb_roundtrip", "command": command(server),
            "exit_code": 0, "expectation": "success", "matched_expectation": True,
            "log_sha256": hashlib.sha256(raw).hexdigest(), "log_bytes": len(raw), "round_trips": 2,
            "nodes_preserved": 2, "parallel_edges_preserved": 2, "test_summaries": [],
            "scope": "Real RDB persistence and decoding; internal dimensions are independently checked by unit tests"})
        completed = True
        print("Two real RDB reloads preserved exact nodes, parallel-edge IDs, endpoints and properties", flush=True)
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        try:
            if patch_applied:
                capture(["git", "apply", "-R", "/cap-clamp.patch"])
            report["restored_source_verification"] = verify_source_bytes()
            report["status"] = "passed" if completed else "failed"
        except Exception:
            report["status"] = "failed"
            raise
        finally:
            save()


if __name__ == "__main__":
    main()
