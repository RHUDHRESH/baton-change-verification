"""Fail-closed execution-report tests; Docker and Rust are never invoked."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["unit", "rdb"])
def runner(request, tmp_path, monkeypatch):
    unit = _load("_kan2_runner_test_unit", "verify_kan2.py")
    fixture = tmp_path / "docs/evidence/kan2-fixtures"
    fixture.mkdir(parents=True)
    patch_hashes = {}
    for name in ("before-grow-only.patch", "cap-clamp.patch"):
        raw = ("mock fixture: " + name).encode()
        (fixture / name).write_bytes(raw)
        patch_hashes["/" + name] = hashlib.sha256(raw).hexdigest()
    out = tmp_path / "execution"
    out.mkdir()
    report_path = out / "execution.json"
    state = SimpleNamespace(fault=None, commands=[], validations=[], statuses=[],
                            baseline=False, cap_applied=False, redis_dir=None)
    monkeypatch.setattr(unit, "ROOT", tmp_path)
    monkeypatch.setattr(unit, "OUT", out)
    monkeypatch.setattr(unit, "command", lambda args: list(args))

    def verify(expected_mismatches=()):
        expected = list(expected_mismatches)
        state.validations.append(expected)
        if expected and state.fault == "patched_source":
            raise AssertionError("injected patched source mismatch")
        if not expected and len(state.validations) > 1 and state.fault == "final_source":
            raise AssertionError("injected final source mismatch")
        return {"tracked_blobs": 957, "mismatches": expected}

    monkeypatch.setattr(unit, "verify_source_bytes", verify)

    def apply(args):
        reverse = "-R" in args
        if args[-1] == "/cap-clamp.patch":
            if reverse and state.fault == "cap_restore":
                return False
            state.cap_applied = not reverse
        else:
            assert args[-1] == "/before-grow-only.patch", args
            state.baseline = not reverse
        return True

    def check_output(args, **kwargs):
        args = list(args)
        state.commands.append(args)
        if args[:2] == ["docker", "inspect"]:
            return json.dumps([{"Config": {"Image": unit.IMAGE,
                "Env": ["CARGO_BUILD_JOBS=2", "CARGO_PROFILE_RELEASE_LTO=false"]}}])
        if args == ["git", "rev-parse", "HEAD"]:
            return unit.HEAD
        if args[:1] in (["rustc"], ["cargo"]):
            assert args[-1] == "--version", args
            return "mock toolchain"
        if args[:1] == ["sha256sum"]:
            return patch_hashes[args[1]] + "  " + args[1]
        if args[:2] == ["git", "apply"]:
            if not apply(args):
                raise subprocess.CalledProcessError(1, args, output="injected cap restore failure")
            return ""
        if args[:2] == ["mkdir", "-p"]:
            return ""
        if args[:1] == ["redis-server"]:
            state.redis_dir = args[args.index("--dir") + 1]
            return ""
        assert args[:1] == ["redis-cli"], args
        redis_args = args[args.index("--json") + 1:]
        if redis_args == ["PING"]:
            return json.dumps("PONG")
        if redis_args == ["CONFIG", "GET", "dir"]:
            return json.dumps({"dir": state.redis_dir})
        if redis_args in (["SAVE"], ["DEBUG", "RELOAD"]):
            return json.dumps("OK")
        assert redis_args[:2] == ["GRAPH.QUERY", "kan2-rdb"], redis_args
        query = redis_args[2]
        if "RETURN" not in query:
            return json.dumps([["mock write statistics"]])
        if "count(r)" in query:
            rows = [[2]]
        elif "r.tag" in query:
            rows = [[0, 1, 0, "first"], [0, 1, 1, "second"]]
        else:
            rows = [[0, 0], [1, 1]]
        return json.dumps([["mock header"], rows, ["mock statistics"]])

    def run(args, **kwargs):
        args = list(args)
        state.commands.append(args)
        output, code = b"", 0
        if args[:2] == ["git", "apply"]:
            if not apply(args):
                output, code = b"injected cap restore failure", 1
        elif args[:2] == ["cargo", "test"]:
            identity = next((identity for _, identity in unit.TESTS.values() if identity in args), None)
            if identity is None:
                output = b"running 547 tests\ntest result: ok. 530 passed; 0 failed; 17 ignored\n"
            elif state.baseline:
                key = next(key for key, (_, value) in unit.TESTS.items() if value == identity)
                reason = ("test did not panic as expected" if key == "debug_resize" else
                          "resize shrank the tensor" if key == "release_resize" else "below the saved size")
                output = ("running 1 test\ntest " + identity + " ... FAILED\n" + reason +
                          "\ntest result: FAILED. 0 passed; 1 failed; 0 ignored\n").encode()
                code = 101
            else:
                output = ("running 1 test\ntest " + identity +
                          " ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored\n").encode()
        else:
            assert (args[:2] in (["cargo", "fmt"], ["cargo", "build"], ["docker", "cp"])
                    or args[:1] == ["redis-cli"]), args
        log = kwargs.get("stdout")
        if hasattr(log, "write"):
            log.write(output)
        return SimpleNamespace(returncode=code)

    monkeypatch.setattr(unit.subprocess, "check_output", check_output)
    monkeypatch.setattr(unit.subprocess, "run", run)
    if request.param == "rdb":
        # The RDB script imports the unit runner by its CLI module name.
        monkeypatch.setitem(sys.modules, "verify_kan2", unit)
        module = _load("_kan2_runner_test_rdb", "verify_kan2_rdb.py")
        report_path.write_text(json.dumps({"status": "passed", "checks": [],
            "applied_patch": {"sha256": patch_hashes["/cap-clamp.patch"]},
            "restored_source_verification": {"mismatches": [], "stage": "prior_unit_run"}}), encoding="utf-8")
    else:
        module = unit

    original_write = Path.write_text

    def record_write(path, text, *args, **kwargs):
        if path == report_path:
            state.statuses.append(json.loads(text)["status"])
        return original_write(path, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", record_write)
    return SimpleNamespace(module=module, state=state,
                           report=lambda: json.loads(report_path.read_text(encoding="utf-8")))


def test_completed_checks_persist_passed_only_after_clean_restoration(runner):
    """Control: mocks exercise the complete successful path before fault tests."""
    runner.module.main()
    assert runner.report()["status"] == "passed"
    assert runner.state.statuses[-1] == "passed"
    assert "passed" not in runner.state.statuses[:-1]
    assert not runner.state.cap_applied
    assert runner.state.validations == [[], ["graph/src/runtime/ops/batched_result_emitter.rs"], []]


@pytest.mark.parametrize("fault", ["final_source", "cap_restore"])
def test_cleanup_failure_cannot_persist_a_passed_execution(runner, fault):
    runner.state.fault = fault
    with pytest.raises((AssertionError, RuntimeError, subprocess.CalledProcessError)):
        runner.module.main()
    assert runner.report()["status"] == "failed"
    assert runner.state.statuses[-1] == "failed"
    assert "passed" not in runner.state.statuses
    assert ["git", "apply", "-R", "/cap-clamp.patch"] in runner.state.commands
    if fault == "final_source":
        assert not runner.state.cap_applied
        assert runner.state.validations[-1] == []
    else:
        # The RDB input may carry an earlier unit run's clean-source evidence.
        # No new cleanup verification ran; that old evidence cannot grant pass.
        assert runner.state.cap_applied
        assert runner.state.validations == [[], ["graph/src/runtime/ops/batched_result_emitter.rs"]]
        assert runner.report().get("restored_source_verification") in (
            None, {"mismatches": [], "stage": "prior_unit_run"})


def test_source_validation_failure_after_apply_still_restores_patch(runner):
    runner.state.fault = "patched_source"
    with pytest.raises(AssertionError, match="injected patched source mismatch"):
        runner.module.main()
    assert runner.report()["status"] == "failed"
    assert "passed" not in runner.state.statuses
    assert not runner.state.cap_applied
    assert ["git", "apply", "-R", "/cap-clamp.patch"] in runner.state.commands
    assert runner.state.validations == [[], ["graph/src/runtime/ops/batched_result_emitter.rs"], []]
    assert runner.report()["restored_source_verification"]["mismatches"] == []
    assert not any(args[:2] == ["cargo", "test"] or args[:2] == ["cargo", "build"]
                   for args in runner.state.commands)
