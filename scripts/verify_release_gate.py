"""Read-only, independent comparison of app release evidence with GitHub bytes.

GitHub credentials come from the existing Git Credential Manager helper and are
used only for this repository's Actions GET endpoints. Jira/Slack credentials
are not loaded. Saved provider receipts are checked but are not provider GETs.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import urllib.request
import urllib.parse
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_autonomous_release import credential, Reader as GitHubReader, NoRedirect
from server import release_contract as C
from server.release_verifier import verify_artifact

ORIGIN = "https://baton-workspace.vercel.app"
REPO = C.RUNNER_REPOSITORY
PREFIX = "/repos/" + REPO + "/actions/"


class ProofError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProofError(message)


def origin_url(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and
                parsed.port in (None, 443) and parsed.path in ("", "/") and not parsed.query and not parsed.fragment,
                "Origin must be an exact HTTPS origin without credentials or a path")
        return parsed.scheme + "://" + parsed.netloc
    except (ValueError, TypeError):
        raise ProofError("Origin must be an exact HTTPS origin without credentials or a path") from None


class Reader:
    """Separate public reads from repository-scoped authenticated GitHub reads."""
    def __init__(self, token, origin=ORIGIN):
        self.origin = origin_url(origin)
        self.github = GitHubReader(token)
        self.opener = urllib.request.build_opener(NoRedirect())

    def raw(self, path, github=False, archive=False):
        if github:
            require(re.fullmatch(re.escape(PREFIX) + r"(?:runs/[0-9]{1,20}(?:/jobs\?per_page=30|/artifacts\?per_page=30)?|artifacts/[0-9]{1,20}/zip)", path),
                    "GitHub read is outside this verification scope")
            require(not archive or re.fullmatch(re.escape(PREFIX) + r"artifacts/[0-9]{1,20}/zip", path),
                    "Artifact read is outside this verification scope")
            return self.github.raw(path, github=True, archive=archive)
        require(not archive and re.fullmatch(r"/api/public/(?:release-plans/[a-f0-9]{32}|release-runs/[a-f0-9]{32}(?:/evidence|/logs/[a-zA-Z0-9_./-]+)?)", path) and
                ".." not in PurePosixPath(path).parts and "\\" not in path,
                "Public read is outside this verification scope")
        try:
            request = urllib.request.Request(self.origin + path, method="GET", headers={"Accept": "application/json"})
            with self.opener.open(request, timeout=40) as response:
                raw = response.read(4_000_001)
            require(len(raw) <= 4_000_000, "Public evidence exceeded its bound")
            return raw
        except ProofError:
            raise
        except Exception:
            raise ProofError("Public GET was not confirmed; no private URL or response body was printed") from None

    def json(self, path, github=False):
        try:
            return json.loads(self.raw(path, github=github))
        except (json.JSONDecodeError, UnicodeError):
            raise ProofError("Read-only endpoint did not return valid JSON") from None


def unpack(raw):
    require(isinstance(raw, bytes) and len(raw) <= 2_000_000, "Artifact exceeds its compressed bound")
    files = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(len(entries) <= 40 and sum(row.file_size for row in entries) <= 3_000_000,
                    "Artifact exceeds its expanded bound")
            for row in entries:
                path = PurePosixPath(row.filename)
                require(re.fullmatch(r"[A-Za-z0-9_./-]+", row.orig_filename) and not path.is_absolute() and
                        ".." not in path.parts and "\\" not in row.orig_filename and not row.flag_bits & 1 and
                        not stat.S_ISLNK(row.external_attr >> 16) and row.file_size < 300_000,
                        "Artifact contains an unsafe member")
                if row.is_dir():
                    continue
                require(row.filename not in files, "Artifact contains duplicate members")
                files[row.filename] = archive.read(row)
    except (zipfile.BadZipFile, RuntimeError):
        raise ProofError("Artifact is not a valid ZIP document") from None
    require("release-report.json" in files, "Artifact report is missing")
    return files


def graph_receipt(plan, record, verified, report_sha):
    receipt = record.get("graph_receipt", {})
    graph_results = [{**check, "check_id": check["id"], "environment_id": environment["id"]}
                     for environment in verified["environments"] for check in environment["checks"]]
    expected = {"verified": True, "run_id": record["id"], "plan_hash": plan["plan_hash"], "source_commit": C.SOURCE_COMMIT,
                "release_passed": verified["status"] == "passed", "checks": verified["total"],
                "policy_version": C.POLICY_VERSION, "registry_version": C.REGISTRY_VERSION,
                "evidence_sha256": report_sha, "results_sha256": C.sha(C.encode(graph_results)),
                "binding_fingerprint": plan.get("binding_fingerprint")}
    require(receipt.get("verified") is True and type(receipt.get("release_passed")) is bool and type(receipt.get("checks")) is int and
            re.fullmatch(r"[a-f0-9]{64}", plan.get("binding_fingerprint", "")) and receipt == expected,
            "Public graph certificate does not bind the exact evidence and per-test results")
    return {"evidence_sha256": report_sha, "results_sha256": receipt["results_sha256"],
            "binding_fingerprint": receipt["binding_fingerprint"], "checks": receipt["checks"],
            "release_passed": receipt["release_passed"], "direct_graph_get_performed": False}


def publication_text(plan, record, verified):
    blocked = verified["status"] == "blocked"
    title = ("Investigate verified compatibility failure: " if blocked else "Verification record: ") + "FalkorDB-py #212"
    lines = [title, "Verification outcome: " + ("blocked" if blocked else "passed for the declared matrix"),
             "Source: " + C.CHANGE_URL, "Source commit: " + C.SOURCE_COMMIT,
             "Plan: " + plan["id"], "Plan hash: " + plan["plan_hash"], "App run: " + record["id"],
             "GitHub run: " + record["runner"]["run_url"]]
    for environment in verified["environments"]:
        lines.append("redis-py " + environment["redis_version"] + ": " + str(environment["passed"]) + " passed, " +
                     str(environment["failed"]) + " failed, " + str(environment["errors"]) + " errors, " +
                     str(environment["skipped"]) + " skipped")
        for check in environment["checks"]:
            if check["status"] in {"failed", "error"}:
                lines.append("Failed obligation: " + check["id"])
    lines += ["Evidence: " + record["evidence"]["url"], "Evidence SHA-256: " + record["evidence"]["sha256"],
              "The graph requires both sync and inherited async checks. Both environments are required.",
              "This verifies an existing merged change; no source repair or upstream merge was performed.",
              "This remediation/report artifact is not marked Done by publication."]
    return title, "\n".join(lines)


def public_receipts(plan, record, verified):
    require(set(record.get("publish_targets", [])) == {"jira", "slack"} and len(record["publish_targets"]) == 2,
            "Public publication targets differ from the approved destinations")
    receipts = record.get("publication", {})
    require(isinstance(receipts, dict) and set(receipts) == {"jira", "slack"}, "Public publication receipts are incomplete")
    title, text = publication_text(plan, record, verified)
    results = {}
    for target, receipt in receipts.items():
        require(isinstance(receipt, dict) and receipt.get("status") in {"pending", "remote_created", "verification_pending", "verified", "rejected"},
                "Public publication status is invalid")
        if receipt["status"] != "verified":
            require(record["status"] != "completed", "Completed run has an unconfirmed provider receipt")
            results[target] = {"status": receipt["status"], "app_saved_readback_claim": False, "provider_get_performed": False}
            continue
        require(receipt.get("target") == target and receipt.get("run_id") == record["id"] and receipt.get("plan_id") == plan["id"] and
                receipt.get("id") == "publication-" + C.sha(record["id"] + ":" + target) and
                receipt.get("title") == title and receipt.get("evidence_text") == text and
                re.fullmatch(r"[a-f0-9]{64}", receipt.get("contract_sha256", "")) and receipt.get("write_retry_allowed") is False,
                "Public provider receipt belongs to different evidence or publication material")
        if record["status"] == "completed":
            require(receipt.get("graph_linked") is True, "Completed publication lacks the app's graph-link receipt")
        destination, remote_id, url = receipt.get("destination", ""), receipt.get("remote_id", ""), receipt.get("url", "")
        if target == "jira":
            match = re.fullmatch(r"(https://[a-z0-9][a-z0-9-]{0,62}\.atlassian\.net)/([A-Z][A-Z0-9_]{1,39})", destination)
            require(match and re.fullmatch(re.escape(match[2]) + r"-[0-9]+", remote_id) and url == match[1] + "/browse/" + remote_id,
                    "Public Jira destination or saved issue identity differs")
        else:
            require(re.fullmatch(r"[CG][A-Z0-9]{5,30}", destination) and re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", remote_id) and
                    re.fullmatch(r"https://[a-zA-Z0-9-]+\.slack\.com/archives/" + re.escape(destination) + "/p" + re.escape(remote_id.replace(".", "")), url) and
                    receipt.get("message_text") == text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                    "Public Slack destination or saved message material differs")
        results[target] = {"status": "verified", "app_saved_readback_claim": True, "provider_get_performed": False,
                           "graph_linked": receipt.get("graph_linked") is True, "remote_id": remote_id,
                           "contract_sha256": receipt["contract_sha256"]}
    return results


def _verify(identity, reader):
    require(isinstance(identity, str) and re.fullmatch(r"[a-f0-9]{32}", identity), "Run identity must be 32 lowercase hex characters")
    path = "/api/public/release-runs/" + identity
    record = reader.json(path)
    require(record.get("id") == identity and record.get("status") in {"completed", "partial"} and
            record.get("evidence_status") == "verified" and record.get("evidence_verified") is True and
            record.get("source_commit") == C.SOURCE_COMMIT,
            "App run has not completed independent evidence verification")
    plan_id = record.get("plan_id", "")
    require(re.fullmatch(r"[a-f0-9]{32}", plan_id), "Public plan identity is invalid")
    plan = reader.json("/api/public/release-plans/" + plan_id)
    require(plan.get("id") == plan_id and record.get("plan_hash") == plan.get("plan_hash"), "Public plan binding differs from the run")
    runner = record.get("runner", {})
    run_id, workflow_sha = str(runner.get("run_id", "")), runner.get("workflow_sha", "")
    require(re.fullmatch(r"[0-9]{1,20}", run_id) and re.fullmatch(r"[a-f0-9]{40}", workflow_sha) and
            runner.get("provider") == "GitHub Actions" and runner.get("verified") is True,
            "Public runner identity is invalid")
    base = PREFIX + "runs/" + run_id
    github = reader.json(base, github=True)
    expected_url = "https://github.com/" + REPO + "/actions/runs/" + run_id
    require(str(github.get("id")) == run_id and github.get("status") == "completed" and
            github.get("conclusion") in {"success", "failure", "cancelled", "timed_out", "neutral", "skipped", "action_required", "stale"} and
            github.get("event") == "workflow_dispatch" and github.get("run_attempt") == 1 and
            github.get("head_sha") == workflow_sha and github.get("repository", {}).get("full_name") == REPO and
            github.get("display_title") == "Baton verification " + identity and
            github.get("path", "").split("@", 1)[0] == ".github/workflows/" + C.WORKFLOW and
            github.get("html_url") == runner.get("run_url") == expected_url,
            "Independent GitHub workflow identity, head, or completion differs")
    jobs = reader.json(base + "/jobs?per_page=30", github=True).get("jobs", [])
    selected_jobs = {}
    for name in ("execute", "finalization"):
        matching = [job for job in jobs if job.get("name") == name]
        require(len(matching) == 1 and matching[0].get("status") == "completed" and matching[0].get("conclusion") in
                ({"success", "failure"} if name == "execute" else {"success", "failure", "cancelled", "timed_out", "skipped"}),
                "Independent GitHub execution or finalization job is incomplete")
        selected_jobs[name] = matching[0]
    require(selected_jobs["execute"].get("id") == runner.get("job_id") and
            selected_jobs["execute"]["conclusion"] == runner.get("conclusion"), "Public execute-job receipt differs from GitHub")
    artifacts = reader.json(base + "/artifacts?per_page=30", github=True).get("artifacts", [])
    matching = [artifact for artifact in artifacts if artifact.get("name") == "baton-verify-" + identity and
                artifact.get("expired") is False and str(artifact.get("workflow_run", {}).get("id")) == run_id]
    require(len(matching) == 1 and type(matching[0].get("id")) is int and matching[0]["id"] == runner.get("artifact_id"),
            "No unique artifact matches the app and GitHub run")
    artifact = matching[0]
    raw = reader.raw(PREFIX + "artifacts/" + str(artifact["id"]) + "/zip", github=True, archive=True)
    digest = C.sha(raw)
    require(artifact.get("digest") == "sha256:" + digest and runner.get("artifact_sha256") == digest,
            "Independent artifact digest differs from GitHub or the public run")
    require(artifact.get("workflow_run", {}).get("head_sha", workflow_sha) == workflow_sha,
            "Artifact belongs to a different workflow head")
    files = unpack(raw)
    try:
        verified = verify_artifact(plan, record, files)
    except ValueError:
        raise ProofError("Independent raw report, command, source, environment, or JUnit validation failed") from None
    public_report = reader.raw(path + "/evidence")
    report_sha = C.sha(files["release-report.json"])
    require(public_report == files["release-report.json"] and record.get("evidence", {}).get("sha256") == report_sha and
            record["evidence"].get("url") == ORIGIN + path + "/evidence", "Public raw report bytes or report receipt differ")
    raw_hashes = {}
    for name, content in files.items():
        if name == "release-report.json":
            continue
        require(reader.raw(path + "/logs/" + name) == content, "Public evidence bytes differ from the immutable GitHub artifact")
        raw_hashes[name] = C.sha(content)
    require(C.encode(record.get("environments")) == C.encode(verified["environments"]) and C.encode(record.get("results")) == C.encode(verified["results"]) and
            record.get("verification_status") == ("passed" if verified["status"] == "passed" else "failed") and
            record.get("decision") == verified["status"], "Public per-test matrix or release decision contradicts raw evidence")
    graph = graph_receipt(plan, record, verified, report_sha)
    publication = public_receipts(plan, record, verified)
    return {"status": "verified_failure" if verified["status"] == "blocked" else "verified", "read_only": True,
        "run_id": identity, "plan_id": plan_id, "plan_hash": plan["plan_hash"], "source_commit": C.SOURCE_COMMIT,
        "release_decision": verified["status"], "publication_status": record["status"], "source_unchanged": True,
        "version_roles": {"matrix_redis_versions": "Python redis client dependency versions",
                          "isolated_test_falkordb_server_image": C.FALKORDB_IMAGE},
        **{key: verified[key] for key in ("total", "passed", "failed", "errors", "skipped")},
        "environments": [{"python_redis_client_version": environment["redis_version"],
                          **{key: environment[key] for key in ("id", "total", "passed", "failed", "errors", "skipped")}}
                         for environment in verified["environments"]],
        "github": {"run_id": run_id, "workflow_sha": workflow_sha, "conclusion": github["conclusion"],
            "execute_conclusion": selected_jobs["execute"]["conclusion"], "finalization_conclusion": selected_jobs["finalization"]["conclusion"],
            "artifact_id": artifact["id"], "artifact_sha256": digest},
        "report_sha256": report_sha, "public_raw_hashes": raw_hashes, "graph_receipt": graph, "publication": publication,
        "limits": ["Jira and Slack provider GETs were not performed; publication checks inspect the app's saved read-back receipts.",
                   "The graph certificate was checked against evidence hashes; no independent direct graph GET was performed.",
                   "This verifies an existing merged source commit; no source repair, provider write, or upstream merge was performed."]}


def verify(identity, reader):
    try:
        return _verify(identity, reader)
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError):
        raise ProofError("Malformed public release evidence was rejected") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--origin", default=ORIGIN)
    parser.add_argument("--output", default="artifacts/release-gate-proof.json")
    args = parser.parse_args(argv)
    try:
        require(re.fullmatch(r"[a-f0-9]{32}", args.run_id), "Run identity must be 32 lowercase hex characters")
        origin = origin_url(args.origin)
        result = verify(args.run_id, Reader(credential(), origin))
    except ProofError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True,
                  "error": "Independent verification stopped; no credential, signed URL, private environment, or provider body was printed"}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(C.encode(result))
    return 0 if result["status"] in {"verified", "verified_failure"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
