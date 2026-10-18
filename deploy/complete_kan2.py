"""One-off, explicitly authorized KAN-2 completion publisher for AWS CloudShell.

Run only after the Codex Docker execution report passes and its evidence document
has been committed. Keep the same --state file across retries. Pending writes
are reconciled by read-back and are never blindly dispatched again. Credentials
are loaded privately from Lambda configuration, never from the execution report.
"""
import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


ISSUE = "KAN-2"
TASK_ID = "task-agent-c108922c16a39ceaa82623d5748c4df0"
CHANNEL = "C0CA7B1BYTT"
MESSAGE_TS = "1792334785.098199"
SITE = "https://rhudhresh3697.atlassian.net"
WORKSPACE = "https://baton-workspace.vercel.app"
SOURCE_COMMIT = "d8190da5a99b4207e847e2fa2547911d96bd9e61"
IMAGE = "ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7"
PATCH_PATH = "docs/evidence/kan2-fixtures/cap-clamp.patch"
PATCHED_SOURCE = "graph/src/runtime/ops/batched_result_emitter.rs"
TEST_SUFFIXES = ("debug_resize", "debug_restore", "release_resize", "release_restore")
TARGET_CHECKS = {prefix + "_" + suffix for prefix in ("head", "before_grow_only", "restored_head") for suffix in TEST_SUFFIXES}
REQUIRED = TARGET_CHECKS | {"head_graph_library", "head_format", "baseline_apply", "baseline_restore", "head_module_build", "head_real_rdb_roundtrip"}
DOCKER_PREFIX = ["docker", "exec", "--workdir", "/work", "baton-kan2-executor"]
FULL_SUITE = {"status": "ok", "passed": 530, "failed": 0, "ignored": 17}


class CompletionError(ValueError):
    """Only application-owned, sanitized error messages are emitted."""


def require(condition, message):
    if not condition:
        raise CompletionError(message)


def verify_command(name, command):
    require(isinstance(command, list) and all(isinstance(arg, str) for arg in command), "Execution command must be an argv list.")
    fixed = {
        "head_graph_library": ["cargo", "test", "--locked", "-p", "graph", "--lib", "--", "--test-threads=1"],
        "head_format": ["cargo", "fmt", "--all", "--check"],
        "head_module_build": ["cargo", "build", "--locked"],
        "baseline_apply": ["git", "apply", "/before-grow-only.patch"],
        "baseline_restore": ["git", "apply", "-R", "/before-grow-only.patch"],
        "cap_clamp_apply": ["git", "apply", "/cap-clamp.patch"],
        "cap_clamp_restore": ["git", "apply", "-R", "/cap-clamp.patch"],
    }
    if name in TARGET_CHECKS:
        suffix = next(suffix for suffix in TEST_SUFFIXES if name.endswith("_" + suffix))
        test_id = {"debug_resize": "graph::graphblas::tensor::tests::resize_asserts_it_never_shrinks",
            "release_resize": "graph::graphblas::tensor::tests::resize_never_shrinks",
            "debug_restore": "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices",
            "release_restore": "graph::graph::restore_tests::restore_never_shrinks_the_saved_matrices"}[suffix]
        args = ["cargo", "test", "--locked"] + (["--release"] if suffix.startswith("release_") else [])
        args += ["-p", "graph", "--lib", test_id, "--", "--exact", "--nocapture", "--test-threads=1"]
    elif name in fixed:
        args = fixed[name]
    elif name == "head_real_rdb_roundtrip":
        directory = command[13] if len(command) > 13 else ""
        require(re.fullmatch(r"/work/kan2-rdb-[0-9a-f]{32}", directory), "RDB execution requires a fresh isolated directory.")
        args = ["redis-server", "--bind", "127.0.0.1", "--protected-mode", "yes", "--port", "6387", "--dir", directory,
            "--dbfilename", "kan2.rdb", "--appendonly", "no", "--save", "", "--loadmodule", "/work/target/debug/libfalkordb.so",
            "--enable-debug-command", "yes", "--logfile", directory + "/redis.log", "--daemonize", "yes"]
    else:
        raise CompletionError("Unknown execution check; its command contract has not been reviewed.")
    require(command == DOCKER_PREFIX + args, "Named execution check does not match its approved argv.")


def read_report(path, report_url):
    require(re.fullmatch(r"https://github\.com/RHUDHRESH/baton-graph-workspace/blob/[0-9a-f]{40}/docs/evidence/KAN-2\.md", report_url), "Evidence URL must reference the committed KAN-2 document at an exact commit.")
    raw = Path(path).read_bytes()
    require(len(raw) <= 512_000, "Execution report exceeds the size limit.")
    report = json.loads(raw)
    require(report.get("status") == "passed" and report.get("task") == ISSUE, "KAN-2 execution is not passed.")
    require(report.get("source_commit") == SOURCE_COMMIT and report.get("source_repository") == "https://github.com/FalkorDB/FalkorDB", "Execution report does not match the approved upstream commit.")
    require(report.get("image") == IMAGE and report.get("executor") == "Codex isolated Docker runner", "Execution provenance does not match the pinned Codex Docker runner.")
    for name in ("source_verification", "restored_source_verification"):
        proof = report.get(name, {})
        require(type(proof.get("tracked_blobs")) is int and proof["tracked_blobs"] > 0 and proof.get("mismatches") == [], "Tracked source bytes were not verified before and after execution.")
    require(report["source_verification"]["tracked_blobs"] == report["restored_source_verification"]["tracked_blobs"], "Restored source inventory differs from the verified head.")
    patch = report.get("applied_patch")
    if "applied_patch" in report:
        require(isinstance(patch, dict) and patch.get("path") == PATCH_PATH and isinstance(patch.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", patch["sha256"]), "The applied source patch path or hash is invalid.")
        require(isinstance(patch.get("reason"), str) and 1 <= len(patch["reason"]) <= 1500 and not any(ord(c) < 32 for c in patch["reason"]), "The source workaround reason is missing or malformed.")
        proof = report.get("patched_source_verification", {})
        require(type(proof.get("tracked_blobs")) is int and proof["tracked_blobs"] == 957 and report["source_verification"]["tracked_blobs"] == 957 and proof.get("mismatches") == [PATCHED_SOURCE], "The patched source must differ only in the approved compiler-workaround file.")
        history = report.get("initial_failures")
        require(isinstance(history, list) and 1 <= len(history) <= 10, "The initial unpatched failures must be retained as historical evidence.")
        for failure in history:
            require(isinstance(failure, dict) and failure.get("matched_expectation") is False and type(failure.get("exit_code")) is int and failure["exit_code"] != 0 and isinstance(failure.get("log_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", failure["log_sha256"]), "Historical failure evidence is malformed.")
            summaries = failure.get("test_summaries", [])
            require(isinstance(summaries, list) and summaries and any(s.get("status") == "FAILED" and type(s.get("passed")) is int and s["passed"] > 0 and type(s.get("failed")) is int and s["failed"] > 0 and type(s.get("ignored")) is int and s["ignored"] >= 0 for s in summaries), "Historical unpatched test failure counts are missing.")
        require(any(f.get("name") in ("head_graph_library", "initial_head_graph_library") for f in history), "The original graph-library failure must remain in the execution report.")
    else:
        require(not report.get("patched_source_verification") and not report.get("initial_failures"), "Patched execution evidence requires an explicit approved source patch.")
    require(re.fullmatch(r"[0-9a-f]{64}", report.get("baseline_patch_sha256", "")), "Baseline patch hash is missing.")
    container_hashes = report.get("container_patch_sha256", {})
    require(isinstance(container_hashes, dict) and container_hashes.get("/before-grow-only.patch") == report["baseline_patch_sha256"], "The container baseline patch hash does not match the approved artifact.")
    if patch:
        require(container_hashes.get("/cap-clamp.patch") == patch["sha256"], "The container workaround patch hash does not match the approved artifact.")
        for failure in report["initial_failures"]:
            require(failure.get("name") == "head_graph_library" and failure.get("exit_code") == 101 and failure.get("test_summaries") == [{"status": "FAILED", "passed": 529, "failed": 1, "ignored": 17}], "Historical failure does not match the original measured graph-library result.")
            verify_command("head_graph_library", failure.get("command"))
    checks = report.get("checks", [])
    require(isinstance(checks, list) and 18 <= len(checks) <= 20, "Execution checks are incomplete or exceed the review limit.")
    names = [check.get("name") for check in checks]
    require(len(set(names)) == len(names) and REQUIRED.issubset(names), "Required execution checks are missing or duplicated.")
    require(set(names) == REQUIRED | ({"cap_clamp_apply", "cap_clamp_restore"} if patch else set()), "Source patch application and restoration checks are incomplete or unexpected.")
    for check in checks:
        require(check.get("matched_expectation") is True and type(check.get("exit_code")) is int, "An execution check did not match its expectation.")
        verify_command(check["name"], check.get("command"))
        require(re.fullmatch(r"[0-9a-f]{64}", check.get("log_sha256", "")), "Execution log hash is missing.")
        summaries = check.get("test_summaries", [])
        require(isinstance(summaries, list), "Execution test summaries are malformed.")
        for summary in summaries:
            require(all(type(summary.get(k)) is int and summary[k] >= 0 for k in ("passed", "failed", "ignored")), "Execution test counts are invalid.")
        if check["name"].startswith("before_grow_only_"):
            require(check.get("expectation") == "regression_failure" and check["exit_code"] == 101 and summaries == [{"status": "FAILED", "passed": 0, "failed": 1, "ignored": 0}], "The baseline must reproduce an expected regression failure, not pass.")
        else:
            require(check.get("expectation") == "success" and check["exit_code"] == 0, "A success check failed.")
            if check["name"] in TARGET_CHECKS:
                require(summaries == [{"status": "ok", "passed": 1, "failed": 0, "ignored": 0}], "A targeted regression check did not execute exactly one passing test.")
            elif check["name"] == "head_graph_library":
                require(summaries == [FULL_SUITE], "The final graph library must report the measured 530 passed, 0 failed and 17 ignored tests.")
            else:
                require(summaries == [], "A non-test check reported unexpected test counts.")
            if check["name"] == "head_real_rdb_roundtrip":
                require(all(type(check.get(key)) is int and check[key] == 2 for key in ("round_trips", "nodes_preserved", "parallel_edges_preserved")), "Real RDB evidence must preserve two nodes and two parallel edges across two round trips.")
    return report, hashlib.sha256(raw).hexdigest()


def flatten_adf(node):
    if isinstance(node, dict):
        return node.get("text", "") + "".join(flatten_adf(child) for child in node.get("content", [])) + ("\n" if node.get("type") == "paragraph" else "")
    return ""


def adf(text):
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise CompletionError("Provider redirect refused.")


class Provider:
    def __init__(self, variables):
        require(variables.get("JIRA_SITE_URL", "").rstrip("/") == SITE and variables.get("JIRA_PROJECT_KEY") == "KAN", "Lambda Jira configuration does not match the approved KAN destination.")
        require(variables.get("SLACK_CHANNEL_ID") == CHANNEL, "Lambda Slack configuration does not match the approved channel.")
        require(all(variables.get(key) for key in ("JIRA_EMAIL", "JIRA_API_TOKEN", "SLACK_BOT_TOKEN", "BATON_OPERATOR_TOKEN")), "Provider or workspace credentials are not configured in Lambda.")
        cloud_id = variables.get("JIRA_CLOUD_ID", "")
        require(not cloud_id or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", cloud_id), "Jira Cloud ID is invalid.")
        self.jira_base = "https://api.atlassian.com/ex/jira/" + cloud_id if cloud_id else SITE
        self.jira_auth = "Basic " + base64.b64encode((variables["JIRA_EMAIL"] + ":" + variables["JIRA_API_TOKEN"]).encode()).decode()
        self.slack_auth = "Bearer " + variables["SLACK_BOT_TOKEN"]
        self.operator_token = variables["BATON_OPERATOR_TOKEN"]
        self.workspace_opener = None

    def workspace_login(self):
        result = self.call("workspace", "POST", "/api/auth/login", {"token": self.operator_token})
        require(result.get("authenticated") is True, "Workspace operator authentication was not confirmed.")
        return result

    def call(self, target, method, path, payload=None):
        if target == "jira":
            allowed = ((method == "GET" and re.fullmatch(r"/rest/api/3/issue/KAN-2(?:\?fields=summary,description,status,project|/comment\?startAt=[0-9]{1,4}&maxResults=100|/comment/[0-9]+|/transitions)?", path)) or
                       (method == "POST" and path in ("/rest/api/3/issue/KAN-2/comment", "/rest/api/3/issue/KAN-2/transitions")))
            require(allowed, "Jira operation is outside the approved completion scope.")
            url, auth = self.jira_base + path, self.jira_auth
        elif target == "slack":
            expected_history = "conversations.history?" + urllib.parse.urlencode({"channel": CHANNEL, "oldest": MESSAGE_TS, "latest": MESSAGE_TS, "inclusive": "true", "limit": 1})
            require((method == "GET" and path == expected_history) or (method == "POST" and path == "chat.update"), "Slack operation is outside the approved completion scope.")
            if method == "POST":
                require(payload.get("channel") == CHANNEL and payload.get("ts") == MESSAGE_TS, "Slack update identity changed.")
            url, auth = "https://slack.com/api/" + path, self.slack_auth
        elif target == "workspace":
            require((method == "POST" and path == "/api/auth/login" and payload == {"token": self.operator_token}) or
                (method == "PATCH" and path == "/api/public/tasks/" + TASK_ID and payload == {"status": "done"}) or
                (method == "GET" and path == "/api/public/workspace"), "Workspace operation is outside the approved completion scope.")
            url, auth = WORKSPACE + path, None
        else:
            raise CompletionError("Unknown provider.")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            headers["Authorization"] = auth
        if target == "workspace":
            headers["Origin"] = WORKSPACE
        request = urllib.request.Request(url, method=method, data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers)
        try:
            if target == "workspace":
                if self.workspace_opener is None:
                    self.workspace_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
                opener = self.workspace_opener
            else:
                opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=20) as response:
                limit = 4_000_000 if target == "workspace" else 512_000
                raw = response.read(limit + 1)
                require(len(raw) <= limit, "Provider response exceeds the size limit.")
                result = json.loads(raw) if raw else {}
                require(isinstance(result, dict), "Provider returned an invalid response.")
                require(target != "slack" or result.get("ok") is True, "Slack refused the operation; review bot scopes, membership and message ownership.")
                return result
        except CompletionError:
            raise
        except urllib.error.HTTPError as error:
            status = error.code if type(error.code) is int and 100 <= error.code <= 599 else None
            try:
                error.close()
            except Exception:
                pass
            raise CompletionError("Provider HTTP request failed" + (" (" + str(status) + ")" if status else "") + "; inspect the durable completion receipt before retrying.") from None
        except Exception:
            raise CompletionError("Provider request outcome is unverified; inspect the durable completion receipt before retrying.") from None


class State:
    def __init__(self, path, report_hash, report_url):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        try:
            self.lock_fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise CompletionError("Completion is locked. Inspect the existing receipt and any interrupted process before removing its lock.") from None
        try:
            self.value = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"report_sha256": report_hash, "report_url": report_url, "task": ISSUE, "steps": {}}
            require(self.value.get("report_sha256") == report_hash and self.value.get("report_url") == report_url and self.value.get("task") == ISSUE, "Completion receipt belongs to different evidence; reconcile it before proceeding.")
            self.save()
        except Exception:
            self.close()
            raise

    def save(self):
        temporary = self.path.with_name(self.path.name + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(self.value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def mark(self, step, status, **metadata):
        self.value["steps"][step] = {"status": status, **metadata}
        self.save()

    def pending(self, step):
        return self.value["steps"].get(step, {}).get("status") == "pending"

    def close(self):
        os.close(self.lock_fd)
        self.lock_path.unlink(missing_ok=True)


def issue_read(provider):
    issue = provider.call("jira", "GET", "/rest/api/3/issue/KAN-2?fields=summary,description,status,project")
    require(issue.get("key") == ISSUE and issue.get("fields", {}).get("project", {}).get("key") == "KAN" and TASK_ID in flatten_adf(issue.get("fields", {}).get("description")), "Jira issue does not match the approved workspace task.")
    return issue


def done(issue):
    return issue.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key") == "done"


def slack_read(provider):
    path = "conversations.history?" + urllib.parse.urlencode({"channel": CHANNEL, "oldest": MESSAGE_TS, "latest": MESSAGE_TS, "inclusive": "true", "limit": 1})
    messages = provider.call("slack", "GET", path).get("messages", [])
    require(len(messages) == 1 and messages[0].get("ts") == MESSAGE_TS and messages[0].get("bot_id") and TASK_ID in messages[0].get("text", ""), "Slack message does not match the approved bot task message.")
    return messages[0]["text"]


def evidence_text(report, digest, url):
    marker = "[Baton KAN-2 completion sha256:" + digest + "]"
    lines = [marker, "Completed by Codex executing code checks in an isolated Docker runner; Groq and Lambda did not execute the code checks.",
        "Base upstream commit: " + SOURCE_COMMIT, "Pinned image: " + IMAGE, "Execution report SHA-256: " + digest,
        "Baseline patch SHA-256: " + report["baseline_patch_sha256"], "Evidence: " + url,
        "Checks (baseline regression failures are expected, not passing baseline tests):"]
    if report.get("applied_patch"):
        patch = report["applied_patch"]
        lines += ["The original unpatched graph-library suite failed. The final successful checks below used a narrowly scoped compiler workaround applied only in the isolated workspace; no upstream fix or merge is claimed.",
            "Workaround patch: " + patch["path"], "Workaround SHA-256: " + patch["sha256"], "Reason: " + patch["reason"],
            "Only changed tracked source during checks: " + PATCHED_SOURCE,
            "The workaround was removed after checks; original source bytes were verified again.", "Historical initial failures (not counted as passing checks):"]
        for failure in report["initial_failures"]:
            lines += [failure["name"] + ": exit=" + str(failure["exit_code"]) + "; " + "; ".join(
                str(s["passed"]) + " passed, " + str(s["failed"]) + " failed, " + str(s["ignored"]) + " ignored" for s in failure["test_summaries"]),
                "Initial failure log SHA-256: " + failure["log_sha256"]]
            if isinstance(failure.get("command"), list):
                lines += ["Initial failure command argv: " + json.dumps(failure["command"])]
    graph_check = next(c for c in report["checks"] if c["name"] == "head_graph_library")
    lines += ["Final graph library: " + "; ".join(str(s["passed"]) + " passed, " + str(s["failed"]) + " failed, " + str(s["ignored"]) + " ignored" for s in graph_check["test_summaries"])]
    for check in report["checks"]:
        summaries = "; ".join(str(s["passed"]) + " passed, " + str(s["failed"]) + " failed, " + str(s["ignored"]) + " ignored" for s in check["test_summaries"])
        lines += [check["name"] + ": " + check["expectation"] + "; exit=" + str(check["exit_code"]) + "; " + summaries,
            "Command argv: " + json.dumps(check["command"]), "Log SHA-256: " + check["log_sha256"]]
    text = "\n".join(lines)
    require(len(text) <= 30_000, "Completion evidence comment exceeds the size limit.")
    return marker, text


def complete(report, digest, report_url, provider, state):
    marker, text = evidence_text(report, digest, report_url)
    issue = issue_read(provider)
    original = slack_read(provider)
    sources = re.findall(r"https://github\.com/FalkorDB/(?:FalkorDB|falkordb-py)/(?:issues|pull)/[0-9]+", flatten_adf(issue["fields"]["description"]))
    require(sources and any(source in original for source in sources), "Jira and Slack do not share the original public evidence link.")
    comments = []
    start = 0
    for _ in range(10):
        page = provider.call("jira", "GET", "/rest/api/3/issue/KAN-2/comment?startAt=" + str(start) + "&maxResults=100")
        rows = page.get("comments", [])
        require(isinstance(rows, list) and len(rows) <= 100, "Jira comment listing is malformed.")
        comments += [row for row in rows if marker in flatten_adf(row.get("body"))]
        start += len(rows)
        if start >= page.get("total", start):
            break
        require(rows, "Jira comment listing did not advance.")
    else:
        raise CompletionError("Jira comment history exceeds the bounded reconciliation limit.")
    require(len(comments) <= 1, "Multiple completion comments exist; reconcile them manually.")
    if comments:
        comment_id = comments[0].get("id", "")
    else:
        require("comment" not in state.value["steps"], "A prior comment write cannot be reconciled. No duplicate comment will be sent; inspect Jira before reconciliation.")
        state.mark("comment", "pending")
        result = provider.call("jira", "POST", "/rest/api/3/issue/KAN-2/comment", {"body": adf(text)})
        comment_id = result.get("id", "")
    require(isinstance(comment_id, str) and re.fullmatch(r"[0-9]+", comment_id), "Jira comment identity is unverified; pending intent retained.")
    comment = provider.call("jira", "GET", "/rest/api/3/issue/KAN-2/comment/" + comment_id)
    require(comment.get("id") == comment_id and comment.get("body") == adf(text), "Jira completion comment failed exact read-back.")
    state.mark("comment", "verified", id=comment_id)
    if not done(issue):
        require("transition" not in state.value["steps"], "A prior Done transition cannot be reconciled. Inspect Jira; the transition will not be repeated.")
        transitions = provider.call("jira", "GET", "/rest/api/3/issue/KAN-2/transitions").get("transitions", [])
        candidates = [t for t in transitions if t.get("name", "").casefold() == "done"]
        if not candidates:
            candidates = [t for t in transitions if t.get("to", {}).get("statusCategory", {}).get("key") == "done"]
        require(len(candidates) == 1 and re.fullmatch(r"[0-9]+", candidates[0].get("id", "")), "Jira has no unique approved Done transition.")
        state.mark("transition", "pending")
        provider.call("jira", "POST", "/rest/api/3/issue/KAN-2/transitions", {"transition": {"id": candidates[0]["id"]}})
    require(done(issue_read(provider)), "Jira Done status failed read-back; pending intent retained.")
    state.mark("transition", "verified")
    graph_check = next(c for c in report["checks"] if c["name"] == "head_graph_library")
    final_counts = "; ".join(str(s["passed"]) + " passed, " + str(s["failed"]) + " failed, " + str(s["ignored"]) + " ignored" for s in graph_check["test_summaries"])
    block = marker + "\nCompleted KAN-2: head and restored-head regression tests passed; all four before-grow-only checks reproduced expected regression failures.\nFinal graph library: " + final_counts + ".\nCode checks executed by Codex in an isolated Docker runner.\nBase upstream commit: " + SOURCE_COMMIT
    if report.get("applied_patch"):
        block += "\nThe original unpatched suite failed. Final checks used an isolated-workspace compiler workaround (" + report["applied_patch"]["path"] + ", SHA-256 " + report["applied_patch"]["sha256"] + "); no upstream fix or merge is claimed."
    block += "\nExecution report SHA-256: " + digest + "\nEvidence: " + report_url + "\nJira: " + SITE + "/browse/KAN-2"
    if "original_slack_text" not in state.value:
        require("[Baton KAN-2 completion sha256:" not in original or original.endswith("\n\n" + block), "Slack already contains different completion evidence.")
        state.value["original_slack_text"] = original.removesuffix("\n\n" + block)
        state.save()
    updated = state.value["original_slack_text"] + "\n\n" + block
    require(len(updated) <= 4000, "Slack completion update exceeds the size limit.")
    if original != updated:
        require(original == state.value["original_slack_text"], "Slack message changed since preflight; refusing to overwrite it.")
        require("slack" not in state.value["steps"], "A prior Slack update cannot be reconciled. No second update will be sent; inspect the original message.")
        state.mark("slack", "pending")
        result = provider.call("slack", "POST", "chat.update", {"channel": CHANNEL, "ts": MESSAGE_TS, "text": updated, "mrkdwn": False, "parse": "none", "link_names": False})
        require(result.get("channel") == CHANNEL and result.get("ts") == MESSAGE_TS, "Slack update identity failed verification.")
    require(slack_read(provider) == updated, "Slack completion update failed exact read-back; pending intent retained.")
    state.mark("slack", "verified")
    provider.workspace_login()
    workspace = provider.call("workspace", "GET", "/api/public/workspace")
    tasks = [task for task in workspace.get("tasks", []) if task.get("id") == TASK_ID]
    require(len(tasks) == 1, "The approved task is missing from the workspace.")
    if tasks[0].get("status") != "done":
        require("workspace" not in state.value["steps"], "A prior workspace update cannot be reconciled. Inspect the task before retrying.")
        state.mark("workspace", "pending")
        provider.call("workspace", "PATCH", "/api/public/tasks/" + TASK_ID, {"status": "done"})
    workspace = provider.call("workspace", "GET", "/api/public/workspace")
    tasks = [task for task in workspace.get("tasks", []) if task.get("id") == TASK_ID]
    require(len(tasks) == 1 and tasks[0].get("status") == "done", "Workspace task completion failed read-back; pending intent retained.")
    state.mark("workspace", "verified")
    return {"status": "completed", "jira_issue": ISSUE, "jira_comment_id": comment_id, "jira_url": SITE + "/browse/KAN-2", "slack_channel": CHANNEL,
        "slack_message_ts": MESSAGE_TS, "workspace_task_id": TASK_ID, "workspace_task_status": "done", "report_url": report_url, "report_sha256": digest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--report-url", required=True)
    parser.add_argument("--state", help="Durable local receipt; reuse this exact file for reconciliation.")
    args = parser.parse_args(argv)
    state = None
    try:
        report, digest = read_report(args.report, args.report_url)
        import boto3
        variables = boto3.client("lambda", region_name="ap-south-1").get_function_configuration(FunctionName="baton-workspace")["Environment"]["Variables"]
        provider = Provider(variables)
        del variables
        state = State(args.state or str(Path(args.report).with_name("completion-state.json")), digest, args.report_url)
        result = complete(report, digest, args.report_url, provider, state)
        print(json.dumps(result))
        return 0
    except CompletionError as error:
        print(json.dumps({"status": "error", "message": str(error)}))
        return 1
    except Exception:
        print(json.dumps({"status": "error", "message": "Completion stopped. Inspect the execution report and durable receipt before retrying."}))
        return 1
    finally:
        if state is not None:
            state.close()


if __name__ == "__main__":
    raise SystemExit(main())
