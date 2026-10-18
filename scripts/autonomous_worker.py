"""Bounded, app-dispatched GitHub Actions worker for one reviewed FalkorDB profile.

This creates a fresh Docker checkout, executes the original tests, and requests
at most two model repairs from the app after real failures. No fixture patch or
previous execution manifest is an input. Credentials remain on the trusted host.
The finalize job submits only an artifact identity; the app independently checks
the GitHub job and downloads this report and its raw logs before accepting it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request


API_BASE = "https://kdeokfokg2d4jygx4ul3xwso5a0injxf.lambda-url.ap-south-1.on.aws"
REPOSITORY = "https://github.com/FalkorDB/FalkorDB.git"
COMMIT = "d8190da5a99b4207e847e2fa2547911d96bd9e61"
IMAGE = "ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7"
EDITABLE = "graph/src/runtime/ops/batched_result_emitter.rs"
TEST_MARKER = b"#[cfg(test)]"
MAX_SECONDS = 2100
MAX_REPAIRS = 2
MAX_LOG_BYTES = 16 * 1024 * 1024
FULL_SUMMARY = {"status": "ok", "passed": 530, "failed": 0, "ignored": 17}
TARGET_SUMMARY = {"status": "ok", "passed": 1, "failed": 0, "ignored": 0}
TESTS = {
    "debug_resize": (False, "graph::graphblas::tensor::tests::resize_asserts_it_never_shrinks"),
    "debug_restore": (False, "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"),
    "release_resize": (True, "graph::graphblas::tensor::tests::resize_never_shrinks"),
    "release_restore": (True, "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"),
}
LIBRARY_ARGV = ["cargo", "test", "--locked", "-p", "graph", "--lib", "--", "--test-threads=1"]
# Only application-owned static diagnostics may cross into the public report.
# Unknown JSON, provider text, HTML and request URLs stay out of artifacts.
SAFE_CALLBACK_DETAILS = frozenset({
    "Groq repair failed; no substitute patch was supplied",
    "Groq repair response exceeds its bound",
    "Groq repair has no provider generation receipt",
    "Groq repair was incomplete",
    "Groq did not return a unique bounded production edit",
    "Groq repair returned invalid JSON",
    "Groq repair returned invalid JSON; no patch was applied",
    "Groq repair returned malformed JSON",
    "Groq repair was truncated",
    "Daily repair model allowance exhausted",
    "Repair attempt limit reached",
    "Repair attempts must be ordered",
    "Repair source is outside the approved production file",
    "Runner repair source differs from the pinned source and prior model edits",
    "Repair requires an observed failed check",
    "Upstream test region does not match the immutable source",
    "Invalid or expired runner callback",
    "Workflow already finalized",
})


def callback_http_diagnostic(error: urllib.error.HTTPError, token: str) -> str:
    status = str(error.code) if type(error.code) is int and 100 <= error.code <= 599 else "unknown"
    message = "App callback returned HTTP " + status
    try:
        payload = json.loads(error.read(4096))
        detail = payload.get("detail") if isinstance(payload, dict) else None
        allowed = isinstance(detail, str) and (detail in SAFE_CALLBACK_DETAILS or re.fullmatch(
            r"Groq repair returned HTTP [1-5][0-9]{2}; no substitute patch was supplied", detail))
        if allowed and (not token or token not in detail):
            message += ": " + detail
    except Exception:
        pass
    finally:
        error.close()
    return message


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def target_argv(name: str) -> list[str]:
    release, identity = TESTS[name]
    return ["cargo", "test", "--locked"] + (["--release"] if release else []) + [
        "-p", "graph", "--lib", identity, "--", "--exact", "--nocapture", "--test-threads=1"]


def summaries(raw: bytes) -> list[dict]:
    return [{"status": status, "passed": int(passed), "failed": int(failed), "ignored": int(ignored)}
            for status, passed, failed, ignored in re.findall(
                r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", raw.decode("utf-8", "replace"))]


def passed_check(name: str, exit_code: int, raw: bytes) -> bool:
    results = summaries(raw)
    if name.startswith("graph_library_"):
        return exit_code == 0 and results == [FULL_SUMMARY] and b"running 547 tests" in raw
    if name in TESTS:
        return exit_code == 0 and results == [TARGET_SUMMARY] and b"running 1 test" in raw
    return name == "format" and exit_code == 0


def split_source(source: bytes) -> tuple[bytes, bytes]:
    prefix, marker, suffix = source.partition(TEST_MARKER)
    if not marker or not prefix or not suffix:
        raise ValueError("Reviewed test boundary is missing")
    return prefix, marker + suffix


def validate_patch(patch: str) -> bytes:
    if not isinstance(patch, str) or not patch or len(patch.encode("utf-8")) > 12000:
        raise ValueError("Repair must be a bounded unified diff")
    lines = patch.splitlines()
    expected = "diff --git a/" + EDITABLE + " b/" + EDITABLE
    if [line for line in lines if line.startswith("diff --git ")] != [expected]:
        raise ValueError("Repair must change only the approved production file")
    if [line for line in lines if line.startswith("--- ")] != ["--- a/" + EDITABLE] or [line for line in lines if line.startswith("+++ ")] != ["+++ b/" + EDITABLE]:
        raise ValueError("Repair file headers do not match the approved path")
    if any(line.startswith(("new file", "deleted file", "old mode", "new mode", "rename ", "copy ", "GIT binary", "Binary files")) for line in lines):
        raise ValueError("Repair file operations are not allowed")
    changes = [line[1:] for line in lines if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))]
    if not changes or len(changes) > 120 or not any(line.startswith("@@ ") for line in lines):
        raise ValueError("Repair exceeds the reviewed line-change limit")
    if any("#[cfg" in line or "#[test]" in line or "#[ignore" in line for line in changes):
        raise ValueError("Repair may not add or alter test or build-condition attributes")
    if any(re.search(r"\bunsafe\b", line[1:]) for line in lines if line.startswith("+") and not line.startswith("+++")):
        raise ValueError("Repair may not introduce unsafe Rust")
    return (patch.rstrip("\n") + "\n").encode("utf-8")


def guard_source(original: bytes, current: bytes, changed_paths: list[str]) -> dict:
    before, tests = split_source(original)
    after, after_tests = split_source(current)
    if after_tests != tests:
        raise ValueError("Repair modified the original regression tests")
    if changed_paths not in ([], [EDITABLE]):
        raise ValueError("Tracked files outside the approved production path changed")
    if not after or len(after) > len(before) + 12000:
        raise ValueError("Production change exceeds the bounded repair scope")
    return {"production_before_sha256": sha(before), "production_after_sha256": sha(after),
            "test_region_sha256": sha(tests), "tests_unchanged": True}


def measured_receipt(receipt) -> bool:
    if not isinstance(receipt, dict) or not receipt.get("id") or receipt.get("model") != "openai/gpt-oss-20b":
        return False
    usage = receipt.get("usage", {})
    return (all(type(usage.get(key)) is int and usage[key] > 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
            and usage["total_tokens"] >= usage["prompt_tokens"] + usage["completion_tokens"])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Runner callback redirects are refused")


class Worker:
    def __init__(self, run_id: str, out: Path):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid execution identity")
        if os.environ.get("BATON_API_BASE", API_BASE) != API_BASE:
            raise ValueError("Unapproved callback origin")
        self.token = os.environ.get("BATON_CALLBACK_TOKEN", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", self.token):
            raise ValueError("Missing per-run callback capability")
        self.started = time.monotonic()
        self.out = out.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / "checks").mkdir()
        (self.out / "patches").mkdir()
        self.container = "baton-cloud-" + run_id
        self.sequence = 0
        self.original = b""
        self.report = {"schema_version": 1, "execution_id": run_id, "status": "running",
            "executor": "GitHub Actions isolated Docker runner",
            "github": {"run_id": os.environ.get("GITHUB_RUN_ID", ""), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                       "repository": os.environ.get("GITHUB_REPOSITORY", ""), "workflow_sha": os.environ.get("GITHUB_SHA", "")},
            "source": {"repository": REPOSITORY, "commit": COMMIT, "image": IMAGE},
            "limits": {"max_repairs": MAX_REPAIRS, "timeout_seconds": MAX_SECONDS,
                       "rdb": "Not run in this profile; no RDB result is claimed."},
            "checks": [], "repairs": []}
        self.save()

    def save(self):
        temporary = self.out / "report.pending"
        temporary.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.out / "report.json")

    def remaining(self):
        remaining = MAX_SECONDS - (time.monotonic() - self.started)
        if remaining < 1:
            raise TimeoutError("Cloud execution reached its hard deadline")
        return remaining

    def callback(self, route: str, body: dict) -> dict:
        raw = json.dumps(body, ensure_ascii=False).encode()
        if len(raw) > 65536:
            raise ValueError("Callback body exceeds the approved limit")
        request = urllib.request.Request(API_BASE + "/api/public/workflows/" + self.report["execution_id"] + "/" + route,
            data=raw, headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=min(95, self.remaining())) as response:
                result = response.read(65537)
            if len(result) > 65536:
                raise ValueError("Callback response exceeds the approved limit")
            return json.loads(result)
        except urllib.error.HTTPError as error:
            raise RuntimeError(callback_http_diagnostic(error, self.token)) from None
        except Exception:
            # HTTP errors may include request metadata. Never print credentials.
            raise RuntimeError("App callback failed; inspect this run's saved artifact") from None

    def event(self, stage: str, **data):
        self.sequence += 1
        self.callback("events", {"stage": stage, "sequence": self.sequence,
            "github_run_id": self.report["github"]["run_id"], "data": data})

    def command(self, argv: list[str], *, docker=True, timeout=900) -> bytes:
        if docker:
            argv = ["docker", "exec", "--workdir", "/work", self.container, *argv]
        result = subprocess.run(argv, capture_output=True, timeout=min(timeout, self.remaining()), check=False)
        if result.returncode:
            raise RuntimeError("Trusted runner setup command failed: " + argv[0])
        if len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError("Runner capture exceeds its limit")
        return result.stdout

    def source_state(self) -> dict:
        script = """import subprocess,pathlib,hashlib,json,os
rows=[];bad=[]
for row in subprocess.check_output(['git','ls-tree','-rz','HEAD']).split(b'\\0'):
 if not row:continue
 meta,name=row.split(b'\\t',1);mode,kind,oid=meta.split()
 if kind!=b'blob':continue
 path=os.fsdecode(name);data=pathlib.Path(path).read_bytes()
 actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\\0'+data).hexdigest()
 rows.append([path,actual])
 if actual!=oid.decode():bad.append(path)
print(json.dumps({'tracked_blobs':len(rows),'changed_paths':sorted(bad),'blob_hashes_sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()}))
"""
        state = json.loads(self.command(["python3", "-c", script]))
        if state["tracked_blobs"] != 957:
            raise ValueError("Pinned source inventory differs from the reviewed commit")
        return state

    def verify_current_source(self) -> dict:
        state = self.source_state()
        current = self.command(["cat", EDITABLE])
        proof = guard_source(self.original, current, state["changed_paths"])
        return {**state, **proof}

    def bootstrap(self):
        self.event("bootstrapping", source_commit=COMMIT, image=IMAGE)
        self.command(["docker", "pull", IMAGE], docker=False, timeout=300)
        self.command(["docker", "run", "--detach", "--name", self.container, "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--cpus=2", "--memory=6g", "--pids-limit=1024",
            "--env", "CARGO_BUILD_JOBS=2", "--env", "CARGO_PROFILE_RELEASE_LTO=false",
            "--workdir", "/work", IMAGE, "sleep", "infinity"], docker=False)
        for argv in (["git", "init"], ["git", "remote", "add", "origin", REPOSITORY],
                     ["git", "fetch", "--depth=1", "origin", COMMIT],
                     ["git", "-c", "core.autocrlf=false", "checkout", "--detach", "FETCH_HEAD"]):
            self.command(argv, timeout=300)
        actual = self.command(["git", "rev-parse", "HEAD"]).decode().strip()
        if actual != COMMIT:
            raise ValueError("Cloud source commit differs from the requested profile")
        self.original = self.command(["cat", EDITABLE])
        state = self.verify_current_source()
        if state["changed_paths"]:
            raise ValueError("Original cloud checkout was modified before execution")
        self.report["source"].update(initial_blob_hashes_sha256=state["blob_hashes_sha256"],
            tracked_blobs=state["tracked_blobs"], test_region_sha256=state["test_region_sha256"],
            original_source_sha256=sha(self.original), initial_production_sha256=sha(split_source(self.original)[0]),
            rustc=self.command(["rustc", "--version"]).decode().strip(), cargo=self.command(["cargo", "--version"]).decode().strip())
        self.restore_dependency_cache()
        self.save()

    def restore_dependency_cache(self):
        cache = os.environ.get("BATON_DEPENDENCY_CACHE")
        if not cache:
            return
        # Only GitHub's dependency-cache directories, never host targets/source.
        for name in ("registry", "git"):
            path = Path(cache) / name
            if path.is_dir():
                self.command(["docker", "cp", str(path), self.container + ":/root/.cargo/"], docker=False, timeout=120)

    def save_dependency_cache(self):
        cache = os.environ.get("BATON_DEPENDENCY_CACHE")
        if not cache:
            return
        path = Path(cache)
        path.mkdir(parents=True, exist_ok=True)
        for name in ("registry", "git"):
            # Docker copy errors here are cache misses, never verification passes.
            subprocess.run(["docker", "cp", self.container + ":/root/.cargo/" + name, str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)

    def check(self, name: str, argv: list[str]) -> dict:
        self.event("checking", check=name)
        relative = "checks/" + name + ".log"
        path = self.out / relative
        started = time.monotonic()
        args = ["docker", "exec", "--workdir", "/work", self.container, *argv]
        with path.open("xb") as log:
            process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
            try:
                while process.poll() is None:
                    if time.monotonic() - started > 1200 or path.stat().st_size > MAX_LOG_BYTES:
                        raise TimeoutError("Check exceeded its time or output limit")
                    self.remaining()
                    time.sleep(0.25)
            except BaseException:
                process.kill()
                process.wait(timeout=10)
                raise
        if path.stat().st_size > MAX_LOG_BYTES:
            raise ValueError("Check output exceeded the raw-log size limit")
        raw = path.read_bytes()
        if self.token.encode() in raw:
            path.write_bytes(b"Log withheld because unexpected credential bytes were detected.\n")
            self.report.setdefault("withheld_logs", []).append(relative)
            raise ValueError("Unexpected credential bytes in container output; artifact withheld")
        check = {"name": name, "argv": argv, "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 3), "log_path": relative,
            "log_sha256": sha(raw), "log_bytes": len(raw), "test_summaries": summaries(raw),
            "passed": passed_check(name, process.returncode, raw)}
        self.report["checks"].append(check)
        self.save()
        self.verify_current_source()
        self.event("check_finished", check=check, log_tail=raw[-12000:].decode("utf-8", "replace"))
        return check

    def repair(self, failed: dict, attempt: int):
        prefix, tests = split_source(self.command(["cat", EDITABLE]))
        log = (self.out / failed["log_path"]).read_bytes()
        response = self.callback("repair", {"attempt": attempt, "github_run_id": self.report["github"]["run_id"],
            "source_commit": COMMIT, "failed_check": {**failed, "log_tail": log[-16000:].decode("utf-8", "replace")},
            "editable_source": {"path": EDITABLE, "sha256": sha(prefix), "text": prefix.decode("utf-8")},
            "test_region_sha256": sha(tests)})
        text = response.get("patch")
        if not isinstance(text, str) or len(text.encode()) > 20000:
            raise ValueError("Repair response contains no bounded patch")
        patch = (text.rstrip("\n") + "\n").encode()
        if response.get("patch_sha256") != sha(patch) or not measured_receipt(response.get("provider_receipt")):
            raise ValueError("Repair has no matching patch hash and measured model receipt")
        relative = "patches/repair-" + str(attempt) + ".patch"
        with (self.out / relative).open("xb") as output:
            output.write(patch)
        entry = {"attempt": attempt, "patch_path": relative, "patch_sha256": sha(patch),
                 "provider_receipt": response["provider_receipt"], "applied": False,
                 "pre_apply_source": self.verify_current_source()}
        self.report["repairs"].append(entry)
        self.save()
        try:
            validate_patch(text)
            destination = "/tmp/baton-repair-" + str(attempt) + ".patch"
            self.command(["docker", "cp", str(self.out / relative), self.container + ":" + destination], docker=False)
            self.command(["git", "apply", "--check", destination])
            self.command(["git", "apply", destination])
            entry["applied"] = True
            proof = self.verify_current_source()
            entry.update(post_apply_source=proof, **proof)
        except Exception as error:
            entry["apply_error"] = str(error) if isinstance(error, (RuntimeError, ValueError)) else "Patch application failed"
            try:
                proof = self.verify_current_source()
                entry.update(post_apply_source=proof, **proof)
            except Exception:
                entry["post_apply_guard_error"] = "Source or test integrity could not be verified after patch rejection"
            self.save()
            raise
        self.save()
        self.event("repair_applied", attempt=attempt, patch_sha256=sha(patch), tests_unchanged=True)

    def execute(self) -> int:
        try:
            self.bootstrap()
            latest = self.check("graph_library_initial", LIBRARY_ARGV)
            for attempt in range(1, MAX_REPAIRS + 1):
                if latest["passed"]:
                    break
                self.repair(latest, attempt)
                latest = self.check("graph_library_repair_" + str(attempt), LIBRARY_ARGV)
            if not latest["passed"]:
                raise RuntimeError("Repair budget exhausted with a real failing graph library check")
            for name in TESTS:
                if not self.check(name, target_argv(name))["passed"]:
                    raise RuntimeError("Targeted regression check failed: " + name)
            if not self.check("format", ["cargo", "fmt", "--all", "--check"])["passed"]:
                raise RuntimeError("Formatting check failed")
            final = self.verify_current_source()
            self.report["source"].update(final_changed_paths=final["changed_paths"],
                final_blob_hashes_sha256=final["blob_hashes_sha256"], final_test_region_sha256=final["test_region_sha256"],
                final_source_sha256=sha(self.command(["cat", EDITABLE])))
            self.report["status"] = "passed" if self.report["repairs"] else "passed_no_fix"
        except Exception as error:
            self.report["status"] = "failed"
            self.report["error"] = str(error) if isinstance(error, (RuntimeError, ValueError, TimeoutError)) else "Runner infrastructure failed; inspect immutable logs"
        finally:
            self.report["duration_seconds"] = round(time.monotonic() - self.started, 3)
            self.save()
            try:
                self.save_dependency_cache()
            except Exception:
                pass
            subprocess.run(["docker", "rm", "--force", self.container], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False, timeout=30)
        return 0 if self.report["status"] in {"passed", "passed_no_fix"} else 1


def finalize(run_id: str):
    token = os.environ.get("BATON_CALLBACK_TOKEN", "")
    if not re.fullmatch(r"[a-f0-9]{32}", run_id) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise ValueError("Missing finalization identity")
    body = json.dumps({"github_run_id": os.environ["GITHUB_RUN_ID"], "artifact_name": "baton-run-" + run_id}).encode()
    request = urllib.request.Request(API_BASE + "/api/public/workflows/" + run_id + "/complete", data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
    # Never relay a provider response or request exception containing a capability.
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=150) as response:
            if response.status not in (200, 201, 202):
                raise RuntimeError("Completion was not accepted")
    except Exception:
        raise RuntimeError("Independent app finalization failed; run artifact remains available") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", default="autonomous-artifact")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize(args.run_id)
        return 0
    return Worker(args.run_id, Path(args.out)).execute()


if __name__ == "__main__":
    raise SystemExit(main())
