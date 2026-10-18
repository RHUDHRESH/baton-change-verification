"""Read-only independent proof of one completed app-dispatched cloud execution.

Uses the existing local Git credential manager for private GitHub GETs only.
No credential, model output, source text, signed download URL or raw log is saved.
"""
import argparse
import base64
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ORIGIN = "https://baton-workspace.vercel.app"
REPO = "RHUDHRESH/baton-graph-workspace"
SOURCE_COMMIT = "d8190da5a99b4207e847e2fa2547911d96bd9e61"
IMAGE = "ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7"
EDITABLE = "graph/src/runtime/ops/batched_result_emitter.rs"
TASK = "task-agent-c108922c16a39ceaa82623d5748c4df0"
TARGETS = {
    "debug_resize": (False, "graph::graphblas::tensor::tests::resize_asserts_it_never_shrinks"),
    "debug_restore": (False, "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"),
    "release_resize": (True, "graph::graphblas::tensor::tests::resize_never_shrinks"),
    "release_restore": (True, "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices")}


class ProofError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProofError(message)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def credential():
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    result = subprocess.run(["git", "-c", "credential.helper=", "-c", "credential.helper=manager", "credential", "fill"],
        input="protocol=https\nhost=github.com\nusername=RHUDHRESH\n\n",
        capture_output=True, text=True, timeout=20, env=environment)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    require(result.returncode == 0 and values.get("password"), "Existing GitHub credential is unavailable")
    return values["password"]


class Reader:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def raw(self, path, github=False, archive=False):
        if github:
            require(path.startswith("/repos/" + REPO + "/actions/") or path ==
                    "/repos/FalkorDB/FalkorDB/contents/" + EDITABLE + "?ref=" + SOURCE_COMMIT, "GitHub read is outside the approved scope")
            url, headers = "https://api.github.com" + path, {"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json"}
        else:
            require(re.fullmatch(r"/api/public/workflows/[a-f0-9]{32}(?:/evidence|/logs/[A-Za-z0-9_.-]{1,140})?", path) or
                    path == "/api/public/workspace", "Public read is outside the approved scope")
            url, headers = ORIGIN + path, {"Accept": "application/json"}
        try:
            request = urllib.request.Request(url, method="GET", headers=headers)
            try:
                with self.opener.open(request, timeout=40) as response:
                    raw = response.read(8_000_001)
            except urllib.error.HTTPError as error:
                if not (github and archive and error.code == 302):
                    raise ProofError("Read-only API request was not confirmed") from None
                destination = urllib.parse.urlsplit(error.headers.get("Location", ""))
                require(destination.scheme == "https" and destination.hostname and not destination.username and not destination.password and
                        destination.port in (None, 443) and not destination.fragment and any(destination.hostname.endswith(suffix) for suffix in
                        (".blob.core.windows.net", ".actions.githubusercontent.com", ".githubusercontent.com")), "Artifact storage redirect was refused")
                # Signed storage URL stays in memory; never forward the GitHub token.
                with self.opener.open(urllib.request.Request(destination.geturl(), method="GET"), timeout=40) as response:
                    raw = response.read(8_000_001)
            require(len(raw) <= 8_000_000, "Read-only response exceeded its bound")
            return raw
        except ProofError:
            raise
        except Exception:
            raise ProofError("Read-only request failed; no private URL or provider body was printed") from None

    def json(self, path, github=False):
        return json.loads(self.raw(path, github=github))


def unpack(raw):
    require(len(raw) <= 2_000_000, "Runner artifact exceeds its compressed bound")
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(len(entries) <= 40 and sum(row.file_size for row in entries) <= 5_000_000, "Runner artifact exceeds its expanded bound")
        for row in entries:
            require(not row.is_dir() and not row.flag_bits & 1 and re.fullmatch(r"(?:checks/|patches/)?[A-Za-z0-9_.-]+", row.filename) and
                    row.filename not in result, "Runner artifact contains an unsafe path")
            result[row.filename] = archive.read(row)
    require("report.json" in result, "Runner artifact has no exact report")
    return result


def check_logs(checks, files, identity, reader):
    require(isinstance(checks, list) and 6 <= len(checks) <= 8 and all(isinstance(c, dict) for c in checks) and
            len({c["name"] for c in checks}) == len(checks), "Runner check inventory is incomplete")
    for check in checks:
        name = check["name"]
        library = re.fullmatch(r"graph_library_(?:initial|repair_[12])", name) is not None
        if library:
            expected = ["cargo", "test", "--locked", "-p", "graph", "--lib", "--", "--test-threads=1"]
        elif name in TARGETS:
            release, test = TARGETS[name]
            expected = ["cargo", "test", "--locked"] + (["--release"] if release else []) + [
                "-p", "graph", "--lib", test, "--", "--exact", "--nocapture", "--test-threads=1"]
        else:
            require(name == "format", "Runner check has an unknown name")
            expected = ["cargo", "fmt", "--all", "--check"]
        path = "checks/" + name + ".log"
        require(check.get("argv") == expected and check.get("log_path") == path, "Named check command or log path differs")
        raw = files[path]
        public = reader.raw("/api/public/workflows/" + identity + "/logs/" + path.replace("/", "_"))
        require(raw == public and len(raw) == check.get("log_bytes") and sha(raw) == check.get("log_sha256"), "Public raw log differs from the immutable runner artifact")
        matches = re.findall(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", raw.decode("utf-8", errors="strict"))
        summaries = [{"status": state, "passed": int(passed), "failed": int(failed), "ignored": int(ignored)} for state, passed, failed, ignored in matches]
        require(summaries == check.get("test_summaries") and type(check.get("exit_code")) is int, "Measured raw test totals differ from the report")
        expected_summary = [{"status": "ok", "passed": 530 if library else 1, "failed": 0, "ignored": 17 if library else 0}]
        passed = check["exit_code"] == 0 and (name == "format" or (summaries == expected_summary and
            (b"running 547 tests" if library else b"running 1 test") in raw))
        require(type(check.get("passed")) is bool and check["passed"] == passed, "Reported success differs from executed test evidence")
    libraries = [check for check in checks if check["name"].startswith("graph_library_")]
    require(libraries and all(not check["passed"] and check["exit_code"] != 0 for check in libraries[:-1]), "Historical library failures are missing or inconsistent")
    final = libraries[-1:] + [check for check in checks if not check["name"].startswith("graph_library_")]
    require(len(final) == 6 and {c["name"] for c in final} == {libraries[-1]["name"], "format", *TARGETS} and
            all(check["passed"] is True for check in final), "Final library, four targeted tests and formatting did not all pass")
    return final


def check_repairs(record, report, files, original):
    prefix, marker, tests = original.partition("#[cfg(test)]")
    require(marker and prefix and tests, "Immutable source test boundary is missing")
    region = sha(marker + tests)
    source = report["source"]
    require(source.get("tracked_blobs") == 957 and source.get("test_region_sha256") == source.get("final_test_region_sha256") == region and
            source.get("final_changed_paths") in ([], [EDITABLE]) and all(isinstance(source.get(key), str) and
            re.fullmatch(r"[a-f0-9]{64}", source[key]) for key in ("initial_blob_hashes_sha256", "final_blob_hashes_sha256")),
            "Immutable tests or source scope differ")
    repairs, model_repairs = report.get("repairs", []), record.get("repairs", [])
    require(isinstance(repairs, list) and len(repairs) <= 2 and len(repairs) == len(model_repairs) and
            (report["status"] == "passed") == bool(repairs), "Generated repair inventory differs from the final run")
    measured = []
    for attempt, (entry, model) in enumerate(zip(repairs, model_repairs), 1):
        require(entry.get("attempt") == model.get("attempt") == attempt and entry.get("applied") is True and entry.get("tests_unchanged") is True,
                "Successful run includes an unapplied or unverified repair")
        raw_output = model.get("raw_model_output")
        require(isinstance(raw_output, str), "Actual raw model edit output is unavailable")
        edit = json.loads(raw_output)
        old, new = edit.get("old"), edit.get("new")
        require(isinstance(old, str) and isinstance(new, str) and old and new and old != new and prefix.count(old) == 1 and
                model.get("model_edit") == {"old": old, "new": new}, "Raw model edit does not identify one unique production replacement")
        updated = prefix.replace(old, new, 1)
        patch = "diff --git a/" + EDITABLE + " b/" + EDITABLE + "\n" + "".join(difflib.unified_diff(
            prefix.splitlines(keepends=True), updated.splitlines(keepends=True), fromfile="a/" + EDITABLE, tofile="b/" + EDITABLE))
        patch = patch.rstrip("\n") + "\n"
        actual = files.get(entry.get("patch_path"))
        receipt = entry.get("provider_receipt", {})
        require(actual == patch.encode() and model.get("diff") == patch and entry.get("patch_sha256") == sha(patch) and
                model.get("provider_receipt") == receipt and model.get("provider_response_id") == receipt.get("id"),
                "Applied runner patch differs from the mechanical reconstruction of raw Groq output")
        require(receipt.get("cached") is False and isinstance(receipt.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,150}", receipt["id"]) and
                isinstance(receipt.get("model"), str) and re.fullmatch(r"[A-Za-z0-9_./:-]{1,150}", receipt["model"]) and
                all(type(receipt.get("usage", {}).get(key)) is int and receipt["usage"][key] > 0 for key in ("prompt_tokens", "completion_tokens")) and
                all(re.fullmatch(r"[a-f0-9]{64}", receipt.get(key, "")) for key in ("input_sha256", "response_sha256")),
                "Repair model generation receipt is incomplete")
        proof = entry.get("post_apply_source", {})
        require(proof.get("tracked_blobs") == 957 and proof.get("tests_unchanged") is True and proof.get("test_region_sha256") == region and
                proof.get("changed_paths") in ([], [EDITABLE]) and proof.get("production_before_sha256") == sha(original.partition("#[cfg(test)]")[0]) and
                proof.get("production_after_sha256") == sha(updated), "Measured post-apply source guard differs from the reconstructed patch")
        prefix = updated
        measured.append({"attempt": attempt, "provider_response_id": receipt["id"], "model": receipt["model"],
            "input_tokens": receipt["usage"]["prompt_tokens"], "output_tokens": receipt["usage"]["completion_tokens"],
            "patch_sha256": sha(patch), "raw_model_output_sha256": sha(raw_output), "applied": True})
    require(source.get("final_source_sha256") == sha(prefix + marker + tests), "Final source bytes differ from the reconstructed model repairs")
    require([c["name"] for c in report["checks"] if c["name"].startswith("graph_library_")] ==
            ["graph_library_initial"] + ["graph_library_repair_" + str(i) for i in range(1, len(repairs) + 1)], "Generated repairs have no corresponding measured full-suite reruns")
    return measured


def verify(identity, reader):
    require(re.fullmatch(r"[a-f0-9]{32}", identity), "Invalid app workflow run ID")
    record = reader.json("/api/public/workflows/" + identity)
    require(record.get("id") == identity and record.get("task_id") == TASK and record.get("status") == "completed" and
            record.get("runner", {}).get("verified") is True and record.get("graph_verified") is True,
            "App has not independently completed this workflow")
    runner = record["runner"]
    run_id = str(runner.get("run_id", ""))
    require(re.fullmatch(r"[0-9]{1,20}", run_id) and runner.get("provider") == "GitHub Actions", "App runner identity is invalid")
    base = "/repos/" + REPO + "/actions/runs/" + run_id
    github = reader.json(base, github=True)
    require(github.get("status") == "completed" and github.get("conclusion") == "success" and github.get("run_attempt") == 1 and
            github.get("event") == "workflow_dispatch" and github.get("display_title") == "Baton execution " + identity and
            github.get("path", "").split("@", 1)[0] == ".github/workflows/baton-execute.yml" and
            github.get("repository", {}).get("full_name") == REPO and re.fullmatch(r"[a-f0-9]{40}", github.get("head_sha", "")),
            "Independent GitHub run identity or terminal success differs")
    jobs = reader.json(base + "/jobs?per_page=30", github=True).get("jobs", [])
    for name in ("execute", "finalization"):
        matching = [job for job in jobs if job.get("name") == name]
        require(len(matching) == 1 and matching[0].get("status") == "completed" and matching[0].get("conclusion") == "success",
                "A required GitHub job did not finish successfully")
    rows = reader.json(base + "/artifacts?per_page=30", github=True).get("artifacts", [])
    matching = [row for row in rows if row.get("name") == "baton-run-" + identity and row.get("expired") is False and
                str(row.get("workflow_run", {}).get("id")) == run_id]
    require(len(matching) == 1 and type(matching[0].get("id")) is int, "Independent GitHub artifact identity is not unique")
    artifact = matching[0]
    raw = reader.raw("/repos/" + REPO + "/actions/artifacts/" + str(artifact["id"]) + "/zip", github=True, archive=True)
    require(artifact.get("digest") == "sha256:" + sha(raw) and runner.get("artifact_sha256") == sha(raw), "GitHub and app artifact digests differ")
    files = unpack(raw)
    report = json.loads(files["report.json"])
    public_raw = reader.raw("/api/public/workflows/" + identity + "/evidence")
    evidence = record.get("evidence", [])
    require(len(evidence) == 1 and evidence[0].get("url") == ORIGIN + "/api/public/workflows/" + identity + "/evidence" and
            files["report.json"] == public_raw and evidence[0].get("sha256") == sha(public_raw), "Public evidence bytes differ from the GitHub artifact")
    require(report.get("execution_id") == identity and report.get("executor") == "GitHub Actions isolated Docker runner" and
            report.get("status") in ("passed", "passed_no_fix") and str(report.get("github", {}).get("run_id")) == run_id and
            report["github"].get("workflow_sha") == github["head_sha"] and report.get("source", {}).get("commit") == SOURCE_COMMIT and
            report["source"].get("image") == IMAGE, "Runner report provenance differs from the independently observed execution")
    final = check_logs(report["checks"], files, identity, reader)
    source = reader.json("/repos/FalkorDB/FalkorDB/contents/" + EDITABLE + "?ref=" + SOURCE_COMMIT, github=True)
    original = base64.b64decode(source["content"]).decode("utf-8")
    repairs = check_repairs(record, report, files, original)
    summaries = [summary for check in final for summary in check["test_summaries"]]
    total = sum(summary["passed"] for summary in summaries)
    require(total == 534 and record.get("checks", {}).get("passed") == total and record["checks"].get("failed") == 0 and
            record["checks"].get("ignored") == 17 and record["checks"].get("verified") is True, "Public measured check counts differ from raw execution evidence")
    expected_urls = {"jira": "https://rhudhresh3697.atlassian.net/browse/KAN-2",
        "slack": "https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199"}
    for target, url in expected_urls.items():
        receipt = record.get("publication", {}).get(target, {})
        require(receipt.get("status") == "verified" and receipt.get("read_back_verified") is True and receipt.get("url") == url,
                "Connected provider publication lacks a verified readback receipt")
    tasks = reader.json("/api/public/workspace").get("tasks", [])
    identities = {TASK, record.get("investigation_task_id")}
    require(None not in identities and all(len([task for task in tasks if task.get("id") == identity and task.get("status") == "done"]) == 1
            for identity in identities), "Actual linked workspace tasks are not independently done")
    return {"status": "verified", "run_id": identity, "github_run_id": run_id, "github_workflow_sha": github["head_sha"],
        "artifact_id": artifact["id"], "artifact_sha256": sha(raw), "report_sha256": sha(public_raw), "source_commit": SOURCE_COMMIT,
        "tracked_blobs": 957, "checks": len(report["checks"]), "final_checks": 6, "passed": total, "failed": 0, "ignored": 17,
        "raw_public_logs_verified": len(report["checks"]), "repairs": repairs, "provider_readbacks": {key: True for key in expected_urls},
        "task_statuses": {task: "done" for task in sorted(identities)}, "limits": [
            "GitHub job/artifact and public app evidence were independently re-read; no writes were issued.",
            "Provider publication proof is the app's saved independent readback receipt; this verifier did not query Jira or Slack directly.",
            "Groq receipt and raw edit output match the applied artifact; the Groq provider API was not independently queried.",
            "Cloud graph database relationships require the separate direct graph audit.",
            "The edited source and immutable test region were independently reconstructed; the 957-file inventory count comes from the verified runner artifact.",
            "Seventeen ignored tests and RDB reload are outside this cloud profile; no upstream merge is claimed."]}


def verify_failure(identity, reader):
    """Prove the first actual failed cloud execution without calling it success."""
    require(re.fullmatch(r"[a-f0-9]{32}", identity), "Invalid app workflow run ID")
    record = reader.json("/api/public/workflows/" + identity)
    require(record.get("id") == identity and record.get("task_id") == TASK and record.get("status") == "failed" and
            record.get("runner", {}).get("verified") is True and record.get("graph_verified") is True,
            "App has not independently finalized this failed workflow")
    runner = record["runner"]
    run_id = str(runner.get("run_id", ""))
    require(re.fullmatch(r"[0-9]{1,20}", run_id) and runner.get("provider") == "GitHub Actions" and runner.get("conclusion") == "failure",
            "Failed runner identity is invalid")
    base = "/repos/" + REPO + "/actions/runs/" + run_id
    observed = reader.json(base, github=True)
    require(observed.get("status") == "completed" and observed.get("conclusion") == "failure" and observed.get("run_attempt") == 1 and
            observed.get("event") == "workflow_dispatch" and observed.get("display_title") == "Baton execution " + identity and
            observed.get("repository", {}).get("full_name") == REPO and
            observed.get("path", "").split("@", 1)[0] == ".github/workflows/baton-execute.yml", "Independent failed GitHub execution differs")
    jobs = reader.json(base + "/jobs?per_page=30", github=True).get("jobs", [])
    for name, conclusion in (("execute", "failure"), ("finalization", "success")):
        matching = [job for job in jobs if job.get("name") == name]
        require(len(matching) == 1 and matching[0].get("status") == "completed" and matching[0].get("conclusion") == conclusion,
                "Failed execution or successful failure-finalization job is unverified")
    artifacts = reader.json(base + "/artifacts?per_page=30", github=True).get("artifacts", [])
    matching = [artifact for artifact in artifacts if artifact.get("name") == "baton-run-" + identity and artifact.get("expired") is False and
                str(artifact.get("workflow_run", {}).get("id")) == run_id]
    require(len(matching) == 1 and type(matching[0].get("id")) is int, "Failed-run artifact identity differs")
    artifact = matching[0]
    raw = reader.raw("/repos/" + REPO + "/actions/artifacts/" + str(artifact["id"]) + "/zip", github=True, archive=True)
    require(artifact.get("digest") == "sha256:" + sha(raw) and runner.get("artifact_sha256") == sha(raw), "Failed-run artifact digest differs")
    files = unpack(raw)
    public = reader.raw("/api/public/workflows/" + identity + "/evidence")
    evidence = record.get("evidence", [])
    require(len(evidence) == 1 and evidence[0].get("url") == ORIGIN + "/api/public/workflows/" + identity + "/evidence" and
            public == files["report.json"] and sha(public) == evidence[0].get("sha256"), "Failed-run public report bytes differ")
    report = json.loads(public)
    require(report.get("status") == "failed" and report.get("execution_id") == identity and
            report.get("executor") == "GitHub Actions isolated Docker runner" and report.get("source", {}).get("commit") == SOURCE_COMMIT and
            report["source"].get("image") == IMAGE and report.get("github", {}).get("workflow_sha") == observed.get("head_sha") and
            str(report["github"].get("run_id")) == run_id, "Failed report provenance differs")
    checks = report.get("checks", [])
    expected_summary = [{"status": "FAILED", "passed": 529, "failed": 1, "ignored": 17}]
    require(len(checks) == 1 and checks[0].get("name") == "graph_library_initial" and checks[0].get("argv") ==
            ["cargo", "test", "--locked", "-p", "graph", "--lib", "--", "--test-threads=1"] and checks[0].get("exit_code") == 101 and
            checks[0].get("passed") is False and checks[0].get("log_path") == "checks/graph_library_initial.log",
            "First cloud failure did not execute the expected full-library command")
    check = checks[0]
    log = files[check["log_path"]]
    public_log = reader.raw("/api/public/workflows/" + identity + "/logs/checks_graph_library_initial.log")
    matches = re.findall(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", log.decode("utf-8"))
    parsed = [{"status": state, "passed": int(passed), "failed": int(failed), "ignored": int(ignored)} for state, passed, failed, ignored in matches]
    require(public_log == log and len(log) == check.get("log_bytes") and sha(log) == check.get("log_sha256") and
            b"running 547 tests" in log and parsed == check.get("test_summaries") == expected_summary,
            "Actual failed raw log bytes or 529/1/17 totals differ")
    require(report.get("repairs") == [] and record.get("repairs") == [] and record.get("checks", {}).get("failed") == 1 and
            record["checks"].get("passed") == 529 and record["checks"].get("ignored") == 17 and not record.get("task_completion"),
            "Failed run claimed an unperformed repair or new task completion")
    expected_urls = {"jira": "https://rhudhresh3697.atlassian.net/browse/KAN-2",
        "slack": "https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199"}
    for target, url in expected_urls.items():
        receipt = record.get("publication", {}).get(target, {})
        require(receipt.get("status") == "verified" and receipt.get("read_back_verified") is True and receipt.get("url") == url,
                "Failed-run provider evidence has no verified saved readback")
    jira = record["publication"]["jira"]
    comment_id = jira.get("comment", {}).get("id")
    require(isinstance(comment_id, str) and re.fullmatch(r"[0-9]{1,20}", comment_id) and jira["comment"].get("status") == "verified" and
            not jira.get("transition"), "Failed-run Jira publication claimed a Done transition or lacks a verified comment")
    return {"status": "verified_failure", "outcome": "failed", "run_id": identity, "github_run_id": run_id,
        "artifact_id": artifact["id"], "artifact_sha256": sha(raw), "report_sha256": sha(public), "log_sha256": sha(log),
        "source_commit": SOURCE_COMMIT, "passed": 529, "failed": 1, "ignored": 17, "exit_code": 101,
        "applied_repairs": 0, "new_task_completion": False, "jira_comment_id": comment_id,
        "provider_readbacks": {target: True for target in expected_urls}, "failure_class": "runner_callback_failed" if
            report.get("error") == "App callback failed; inspect this run's saved artifact" else "runner_failed",
        "limits": ["This proves an actual failed cloud run and automatic failure publication, not a completed fix.",
            "Provider readbacks are the app's saved receipts; Jira and Slack were not queried by this verifier.",
            "Direct Cloud graph relationship audit is separate; no API writes or provider messages were sent."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", default="artifacts/autonomous-release-proof.json")
    parser.add_argument("--expect-failed", action="store_true", help="Verify the first actual 529/1/17 failure rather than a successful release")
    args = parser.parse_args()
    try:
        reader = Reader(credential())
        result = verify_failure(args.run_id, reader) if args.expect_failed else verify(args.run_id, reader)
    except ProofError as error:
        result = {"status": "failed", "error": str(error)}
    except Exception:
        result = {"status": "failed", "error": "Independent release verification stopped; no credential, source or provider body was printed"}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] in ("verified", "verified_failure") else 1


if __name__ == "__main__":
    raise SystemExit(main())
