"""Execute KAN-2's pinned upstream checks in an already isolated Docker runner.

No credentials are passed to the container. Raw logs stay in ignored artifacts;
the JSON manifest records exact commands, output hashes and measured outcomes.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/kan2"
CONTAINER = "baton-kan2-executor"
HEAD = "d8190da5a99b4207e847e2fa2547911d96bd9e61"
IMAGE = "ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7"
TESTS = {
    "debug_resize": (False, "graph::graphblas::tensor::tests::resize_asserts_it_never_shrinks"),
    "debug_restore": (False, "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"),
    "release_resize": (True, "graph::graphblas::tensor::tests::resize_never_shrinks"),
    "release_restore": (True, "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"),
}


def command(args):
    return ["docker", "exec", "--workdir", "/work", CONTAINER, *args]


def capture(args):
    return subprocess.check_output(command(args), text=True).strip()


def verify_source_bytes(expected_mismatches=()):
    # A copied Windows Git index can retain stale stat metadata on Linux.
    # Verify every tracked blob against the pinned commit instead of trusting it.
    script = """import subprocess,pathlib,hashlib,os,json
bad=[];files=0
for row in subprocess.check_output(['git','ls-tree','-rz','HEAD']).split(b'\\0'):
 if not row:continue
 meta,name=row.split(b'\\t',1);mode,kind,oid=meta.split()
 if kind!=b'blob':continue
 data=pathlib.Path(os.fsdecode(name)).read_bytes();files+=1
 actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\\0'+data).hexdigest().encode()
 if actual!=oid:bad.append(os.fsdecode(name))
print(json.dumps({'tracked_blobs':files,'mismatches':bad}))
"""
    result = json.loads(capture(["python3", "-c", script]))
    assert sorted(result["mismatches"]) == sorted(expected_mismatches), result
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    live = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER], text=True))[0]
    assert live["Config"]["Image"] == IMAGE, "Unexpected runner image"
    env = dict(item.split("=", 1) for item in live["Config"]["Env"] if "=" in item)
    assert env.get("CARGO_BUILD_JOBS") == "2" and env.get("CARGO_PROFILE_RELEASE_LTO") == "false"
    assert capture(["git", "rev-parse", "HEAD"]) == HEAD
    source_verification = verify_source_bytes()
    report = {"task": "KAN-2", "executor": "Codex isolated Docker runner", "source_repository": "https://github.com/FalkorDB/FalkorDB",
        "source_commit": HEAD, "source_verification": source_verification, "image": IMAGE, "rustc": capture(["rustc", "--version"]),
        "cargo": capture(["cargo", "--version"]),
        "environment": {"CARGO_BUILD_JOBS": "2", "CARGO_PROFILE_RELEASE_LTO": "false"},
        "baseline": "Parent 660bf015 resize/restore behavior with HEAD regression tests and read-only dimension accessors retained",
        "baseline_patch_sha256": hashlib.sha256((ROOT / "docs/evidence/kan2-fixtures/before-grow-only.patch").read_bytes()).hexdigest(),
        "checks": [], "status": "running"}
    initial_path = OUT / "initial-execution.json"
    initial = json.loads(initial_path.read_text(encoding="utf-8")) if initial_path.exists() else {"checks": []}
    report["initial_failures"] = [check for check in initial["checks"] if not check["matched_expectation"]]
    for failure in report["initial_failures"]:
        failure["retained_log"] = "initial_graph_library.log"
        assert hashlib.sha256((OUT / failure["retained_log"]).read_bytes()).hexdigest() == failure["log_sha256"]
    fix_path = ROOT / "docs/evidence/kan2-fixtures/cap-clamp.patch"
    report["applied_patch"] = {"path": "docs/evidence/kan2-fixtures/cap-clamp.patch",
        "sha256": hashlib.sha256(fix_path.read_bytes()).hexdigest(),
        "reason": "Equivalent explicit clamp avoids the observed rustc 1.99 optimized aggregate-return failure; existing regression tests are unchanged"}
    report["container_patch_sha256"] = {}
    for path, expected in (("/before-grow-only.patch", report["baseline_patch_sha256"]), ("/cap-clamp.patch", report["applied_patch"]["sha256"])):
        actual = capture(["sha256sum", path]).split()[0]
        assert actual == expected, "Container patch differs from the reviewed fixture"
        report["container_patch_sha256"][path] = actual

    def save():
        (OUT / "execution.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def run(name, args, expectation="success"):
        path = OUT / (name + ".log")
        started = time.monotonic()
        print("Running " + name + ": " + " ".join(args), flush=True)
        with path.open("wb") as log:
            process = subprocess.run(command(args), stdout=log, stderr=subprocess.STDOUT)
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        matches = re.findall(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", text)
        result = {"name": name, "command": command(args), "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 2), "expectation": expectation,
            "log_sha256": hashlib.sha256(raw).hexdigest(), "log_bytes": len(raw),
            "test_summaries": [{"status": m[0], "passed": int(m[1]), "failed": int(m[2]), "ignored": int(m[3])} for m in matches]}
        if expectation == "regression_failure":
            result["matched_expectation"] = process.returncode != 0 and bool(matches) and matches[-1][1:3] == ("0", "1") and "running 1 test" in text
            reason = "test did not panic as expected" if name.endswith("debug_resize") else ("resize shrank the tensor" if name.endswith("release_resize") else "below the saved size")
            result["expected_failure_reason"] = reason
            result["matched_expectation"] = result["matched_expectation"] and reason in text
        else:
            result["matched_expectation"] = process.returncode == 0 and (not name.endswith(tuple(TESTS)) or "running 1 test" in text)
            if name.endswith(tuple(TESTS)):
                result["matched_expectation"] = result["matched_expectation"] and bool(matches) and matches[-1][1:] == ("1", "0", "0")
            if name == "head_graph_library":
                result["matched_expectation"] = result["matched_expectation"] and bool(matches) and matches[-1][1:] == ("530", "0", "17")
        report["checks"].append(result)
        save()
        print(json.dumps(result), flush=True)
        if not result["matched_expectation"]:
            print(text[-5000:], flush=True)
            raise RuntimeError("Unexpected check outcome: " + name)

    def test(name, prefix="head", expectation="success"):
        release, identity = TESTS[name]
        args = ["cargo", "test", "--locked"] + (["--release"] if release else []) + ["-p", "graph", "--lib", identity, "--", "--exact", "--nocapture", "--test-threads=1"]
        run(prefix + "_" + name, args, expectation)

    save()
    patch_applied = False
    completed = False
    try:
        run("cap_clamp_apply", ["git", "apply", "/cap-clamp.patch"])
        patch_applied = True
        report["patched_source_verification"] = verify_source_bytes(["graph/src/runtime/ops/batched_result_emitter.rs"])
        for name in TESTS:
            test(name)
        run("head_graph_library", ["cargo", "test", "--locked", "-p", "graph", "--lib", "--", "--test-threads=1"])
        run("head_format", ["cargo", "fmt", "--all", "--check"])
        run("baseline_apply", ["git", "apply", "/before-grow-only.patch"])
        try:
            for name in TESTS:
                test(name, "before_grow_only", "regression_failure")
        finally:
            run("baseline_restore", ["git", "apply", "-R", "/before-grow-only.patch"])
        for name in TESTS:
            test(name, "restored_head")
        completed = True
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        try:
            if patch_applied:
                run("cap_clamp_restore", ["git", "apply", "-R", "/cap-clamp.patch"])
            report["restored_source_verification"] = verify_source_bytes()
            report["status"] = "passed" if completed else "failed"
        except Exception:
            report["status"] = "failed"
            raise
        finally:
            save()


if __name__ == "__main__":
    main()
