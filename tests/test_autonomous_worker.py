"""Pure contract and adversarial tests; no Docker/provider execution."""
import json
import io
from pathlib import Path
import urllib.error
from types import SimpleNamespace

import pytest

from scripts import autonomous_worker as worker


PATH = worker.EDITABLE
DIFF = ("diff --git a/{0} b/{0}\n--- a/{0}\n+++ b/{0}\n@@ -1 +1 @@\n-old\n+new\n").format(PATH)
ORIGINAL = b"fn production() {}\n#[cfg(test)]\nmod tests { unchanged(); }\n"


@pytest.mark.parametrize("name", list(worker.TESTS))
def test_targets_have_exact_identity_and_release_profile(name):
    command = worker.target_argv(name)
    release, identity = worker.TESTS[name]
    assert ("--release" in command) is release
    assert command[-5:] == [identity, "--", "--exact", "--nocapture", "--test-threads=1"]
    assert command[:3] == ["cargo", "test", "--locked"]


def test_full_suite_requires_measured_530_and_547_inventory():
    raw = b"running 547 tests\ntest result: ok. 530 passed; 0 failed; 17 ignored; 0 measured\n"
    assert worker.passed_check("graph_library_initial", 0, raw)
    for broken in [raw.replace(b"530", b"1"), raw.replace(b"547", b"18"), raw.replace(b"17 ignored", b"0 ignored"), b""]:
        assert not worker.passed_check("graph_library_initial", 0, broken)
    assert not worker.passed_check("graph_library_initial", 101, raw)


def test_compilation_success_or_zero_filtered_tests_are_not_a_target_pass():
    assert not worker.passed_check("debug_resize", 0, b"Finished test\ntest result: ok. 0 passed; 0 failed; 0 ignored")
    assert not worker.passed_check("debug_resize", 101, b"running 1 test\ntest result: FAILED. 0 passed; 1 failed; 0 ignored")
    assert worker.passed_check("debug_resize", 0, b"running 1 test\ntest result: ok. 1 passed; 0 failed; 0 ignored")
    assert not worker.passed_check("unknown", 0, b"")


def test_patch_is_canonical_and_one_production_file_only():
    assert worker.validate_patch(DIFF.rstrip("\n")) == DIFF.encode()
    for patch in [DIFF.replace(PATH, "tests/test.rs"), DIFF + DIFF,
                  DIFF.replace("--- a/" + PATH, "--- /dev/null"),
                  DIFF + "new mode 100755\n", DIFF.replace("+new", "+#[cfg(test)]"),
                  DIFF.replace("+new", "+#[ignore]"), DIFF.replace("+new", "+unsafe { bypass(); }")]:
        with pytest.raises(ValueError):
            worker.validate_patch(patch)


def test_patch_scope_and_line_budgets():
    with pytest.raises(ValueError):
        worker.validate_patch(DIFF + "+line\n" * 121)
    with pytest.raises(ValueError):
        worker.validate_patch("x" * 12001)
    with pytest.raises(ValueError):
        worker.validate_patch(None)


def test_model_receipt_requires_real_measured_free_model_usage():
    receipt = {"id": "chatcmpl-real-shape", "model": "openai/gpt-oss-20b",
               "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}
    assert worker.measured_receipt(receipt)
    for broken in [{}, {**receipt, "model": "paid-substitute"}, {**receipt, "usage": {"total_tokens": 30}},
                   {**receipt, "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 1}}]:
        assert not worker.measured_receipt(broken)


def test_source_guard_preserves_original_test_bytes_and_other_files():
    changed = ORIGINAL.replace(b"fn production() {}", b"fn production() { fixed(); }")
    proof = worker.guard_source(ORIGINAL, changed, [PATH])
    assert proof["tests_unchanged"]
    assert proof["test_region_sha256"] == worker.sha(worker.split_source(ORIGINAL)[1])
    for candidate, paths in [(changed.replace(b"unchanged", b"ignored"), [PATH]),
                             (changed, [PATH, "Cargo.toml"]),
                             (b"no test boundary", [PATH])]:
        with pytest.raises(ValueError):
            worker.guard_source(ORIGINAL, candidate, paths)


def make_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_CALLBACK_TOKEN", "a" * 43)
    monkeypatch.setenv("GITHUB_RUN_ID", "123456")
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    return worker.Worker("c" * 32, tmp_path / "artifact")


def test_no_unapproved_callback_origin_or_reused_output(monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_API_BASE", "https://attacker.invalid")
    with pytest.raises(ValueError):
        worker.Worker("c" * 32, tmp_path / "bad")
    monkeypatch.delenv("BATON_API_BASE")
    make_worker(monkeypatch, tmp_path)
    with pytest.raises(FileExistsError):
        make_worker(monkeypatch, tmp_path)


def test_callback_preserves_only_bounded_application_diagnostic(monkeypatch, tmp_path):
    run = make_worker(monkeypatch, tmp_path)
    body = io.BytesIO(json.dumps({"detail": "Groq did not return a unique bounded production edit"}).encode())
    error = urllib.error.HTTPError("https://fixed-app.invalid/?private-query", 422, "private reason", {}, body)
    opener = SimpleNamespace(open=lambda *args, **kwargs: (_ for _ in ()).throw(error))
    monkeypatch.setattr(worker.urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(RuntimeError, match="HTTP 422: Groq did not return a unique bounded production edit") as raised:
        run.callback("repair", {})
    assert "private-query" not in str(raised.value) and "private reason" not in str(raised.value)
    assert body.closed


@pytest.mark.parametrize("detail", ["Groq repair returned HTTP 429; no substitute patch was supplied",
                                   "Groq repair returned invalid JSON; no patch was applied"])
def test_callback_preserves_exact_static_model_failure_diagnostics(detail):
    error = urllib.error.HTTPError("https://private.invalid", 422, "private reason", {},
                                   io.BytesIO(json.dumps({"detail": detail}).encode()))
    assert worker.callback_http_diagnostic(error, "a" * 43) == "App callback returned HTTP 422: " + detail


@pytest.mark.parametrize("payload", [{"detail": "private-provider-response https://provider.invalid?token=secret"},
                                      {"detail": "a" * 43}, {"detail": ["private validation context"]},
                                      {"detail": "Groq repair returned HTTP 429; no substitute patch was supplied private-token"},
                                      "<html>private proxy response</html>"])
def test_callback_diagnostic_does_not_relay_secrets_urls_or_raw_provider_text(payload):
    raw = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
    error = urllib.error.HTTPError("https://private.invalid", 502, "secret reason", {}, io.BytesIO(raw))
    assert worker.callback_http_diagnostic(error, "a" * 43) == "App callback returned HTTP 502"


def test_callback_error_body_read_is_capped_at_four_kib():
    class BoundedBody(io.BytesIO):
        def read(self, size=-1):
            assert size == 4096
            return super().read(size)

    body = BoundedBody(b'{"detail":"' + b"x" * 10000 + b'"}')
    error = urllib.error.HTTPError("https://private.invalid", 413, "private reason", {}, body)
    assert worker.callback_http_diagnostic(error, "a" * 43) == "App callback returned HTTP 413"


@pytest.mark.parametrize("failures,expected_status,expected_repairs", [(0, "passed_no_fix", 0), (1, "passed", 1), (2, "passed", 2), (3, "failed", 2)])
def test_real_failure_drives_bounded_repair_loop(monkeypatch, tmp_path, failures, expected_status, expected_repairs):
    run = make_worker(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(run, "bootstrap", lambda: None)
    monkeypatch.setattr(run, "save_dependency_cache", lambda: None)
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(run, "command", lambda *args, **kwargs: ORIGINAL)
    monkeypatch.setattr(run, "verify_current_source", lambda: {"changed_paths": [], "blob_hashes_sha256": "d" * 64, "test_region_sha256": "e" * 64})

    def check(name, argv):
        calls.append((name, argv))
        passed = not name.startswith("graph_library_") or len([n for n, _ in calls if n.startswith("graph_library_")]) > failures
        value = {"name": name, "passed": passed}
        run.report["checks"].append(value)
        return value

    def repair(failed, attempt):
        assert not failed["passed"]
        run.report["repairs"].append({"attempt": attempt})

    monkeypatch.setattr(run, "check", check)
    monkeypatch.setattr(run, "repair", repair)
    code = run.execute()
    assert code == (1 if failures == 3 else 0)
    assert run.report["status"] == expected_status
    assert len(run.report["repairs"]) == expected_repairs
    assert calls[0] == ("graph_library_initial", worker.LIBRARY_ARGV)
    if failures < 3:
        assert [name for name, _ in calls][-5:] == [*worker.TESTS, "format"]
    assert "Not run" in run.report["limits"]["rdb"]
    assert json.loads((run.out / "report.json").read_text())["status"] == expected_status


def test_patch_requires_measured_model_receipt_before_docker_apply(monkeypatch, tmp_path):
    run = make_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(run, "command", lambda *args, **kwargs: ORIGINAL)
    monkeypatch.setattr(run, "callback", lambda *args: {"patch": DIFF, "patch_sha256": worker.sha(DIFF.encode()), "provider_receipt": {}})
    (run.out / "checks/fail.log").write_bytes(b"actual failure")
    with pytest.raises(ValueError, match="model receipt"):
        run.repair({"log_path": "checks/fail.log"}, 1)
    assert not list((run.out / "patches").iterdir())


def test_failed_git_apply_retains_generated_patch_and_measured_unchanged_tests(monkeypatch, tmp_path):
    run = make_worker(monkeypatch, tmp_path)
    receipt = {"id": "chatcmpl-measured", "model": "openai/gpt-oss-20b",
               "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}
    proof = {"changed_paths": [], "test_region_sha256": worker.sha(worker.split_source(ORIGINAL)[1]), "tests_unchanged": True}
    monkeypatch.setattr(run, "callback", lambda *args: {"patch": DIFF, "patch_sha256": worker.sha(DIFF.encode()), "provider_receipt": receipt})
    monkeypatch.setattr(run, "verify_current_source", lambda: proof)

    def command(argv, **kwargs):
        if argv == ["cat", PATH]:
            return ORIGINAL
        if argv[:3] == ["git", "apply", "--check"]:
            raise RuntimeError("Trusted runner setup command failed: git")
        return b""

    monkeypatch.setattr(run, "command", command)
    (run.out / "checks/fail.log").write_bytes(b"real failure")
    with pytest.raises(RuntimeError):
        run.repair({"log_path": "checks/fail.log"}, 1)
    entry = json.loads((run.out / "report.json").read_text())["repairs"][0]
    assert entry["applied"] is False and entry["provider_receipt"] == receipt
    assert entry["pre_apply_source"] == entry["post_apply_source"] == proof
    assert entry["tests_unchanged"] is True
    assert (run.out / entry["patch_path"]).read_bytes() == DIFF.encode()


def test_unmeasured_failed_apply_guard_never_asserts_tests_unchanged(monkeypatch, tmp_path):
    run = make_worker(monkeypatch, tmp_path)
    receipt = {"id": "chatcmpl-measured", "model": "openai/gpt-oss-20b",
               "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}
    monkeypatch.setattr(run, "callback", lambda *args: {"patch": DIFF, "patch_sha256": worker.sha(DIFF.encode()), "provider_receipt": receipt})
    monkeypatch.setattr(run, "command", lambda *args, **kwargs: ORIGINAL)
    guards = iter([{"tests_unchanged": True}, ValueError("corrupt tests"), ValueError("corrupt tests")])

    def guard():
        value = next(guards)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(run, "verify_current_source", guard)
    (run.out / "checks/fail.log").write_bytes(b"real failure")
    with pytest.raises(ValueError):
        run.repair({"log_path": "checks/fail.log"}, 1)
    entry = run.report["repairs"][0]
    assert entry["applied"] is True and "post_apply_guard_error" in entry
    assert "tests_unchanged" not in entry and "post_apply_source" not in entry


def test_frozen_workflow_host_secret_and_finalization_order():
    content = (Path(__file__).parents[1] / ".github/workflows/baton-execute.yml").read_text()
    assert "workflow_dispatch:" in content and "pull_request:" not in content and "push:" not in content
    assert "persist-credentials: false" in content
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in content
    assert "needs: execute" in content and content.count("if: always()") == 2
    assert "retention-days: 1" in content
    assert "target/" not in content
    assert "--env BATON" not in Path(worker.__file__).read_text()
