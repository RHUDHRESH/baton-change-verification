"""Read-only CloudShell audit of one successful app run, Jira, Slack and FalkorDB.

Credentials remain private in memory. Only GET and GRAPH.RO_QUERY are issued.
Pass the reviewed Lambda ZIP and its SHA-256 to use its existing Redis client.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import ssl
import sys
import urllib.parse
import urllib.request

ORIGIN = "https://baton-workspace.vercel.app"
SITE = "https://rhudhresh3697.atlassian.net"
TASK = "task-agent-c108922c16a39ceaa82623d5748c4df0"
ITEM = "FalkorDB/FalkorDB#3246"
SOURCE = "https://github.com/FalkorDB/FalkorDB/issues/3246"
CHANNEL, TS = "C0CA7B1BYTT", "1792334785.098199"


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuditError("Read-only redirect refused")


def get(url, authorization=None):
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    request = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())).open(request, timeout=25) as response:
            raw = response.read(4_000_001)
        require(len(raw) <= 4_000_000, "Read-only response exceeded its bound")
        return raw
    except AuditError:
        raise
    except Exception:
        raise AuditError("Read-only request failed; no credentials or provider body were printed") from None


def flatten(value):
    if isinstance(value, dict):
        return value.get("text", "") + "".join(flatten(child) for child in value.get("content", []))
    return ""


def publication_text(record, report):
    libraries = [check for check in report["checks"] if check["name"].startswith("graph_library_")]
    final = libraries[-1:] + [check for check in report["checks"] if not check["name"].startswith("graph_library_")]
    require(len(final) == 6 and all(check.get("passed") is True and check["exit_code"] == 0 for check in final), "Final executed checks are not passing")
    counts = [sum(summary["passed"] + summary["failed"] for summary in check["test_summaries"]) for check in final]
    require(sum(counts) == 534, "Measured test execution counts differ")
    evidence = record["evidence"][0]
    lines = ["[Baton autonomous run " + record["id"] + "]", "Workspace KAN-2 cloud verification succeeded.",
        "Executor: GitHub Actions; verified runner conclusion: success", "Runner: " + record["runner"]["run_url"],
        "Source commit: " + record["runner"]["source_commit"], "Pinned image: " + record["runner"]["image_digest"],
        "Evidence: " + evidence["url"], "Evidence SHA-256: " + evidence["sha256"],
        "Test executions (includes targeted reruns): " + str(sum(counts)),
        "This reports the isolated workspace run; it does not claim an upstream issue resolution or merge."]
    for check, count in zip(final, counts):
        lines.append(check["name"] + ": passed; exit=0; tests=" + str(count))
    return "\n".join(lines), "\n".join(lines[:9]) + "\nNo upstream fix or merge is claimed."


def provider_audit(environment, record, report):
    require(environment.get("JIRA_SITE_URL", "").rstrip("/") == SITE and environment.get("JIRA_PROJECT_KEY") == "KAN" and
            environment.get("SLACK_CHANNEL_ID") == CHANNEL, "Configured connected destinations differ")
    cloud_id = environment.get("JIRA_CLOUD_ID", "")
    require(not cloud_id or re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", cloud_id), "Jira Cloud identity is invalid")
    require(all(environment.get(key) for key in ("JIRA_EMAIL", "JIRA_API_TOKEN", "SLACK_BOT_TOKEN")), "Existing private provider credentials are unavailable")
    jira = "https://api.atlassian.com/ex/jira/" + cloud_id if cloud_id else SITE
    auth = "Basic " + base64.b64encode((environment["JIRA_EMAIL"] + ":" + environment["JIRA_API_TOKEN"]).encode()).decode()
    issue = json.loads(get(jira + "/rest/api/3/issue/KAN-2?fields=description,status,project", auth))
    fields = issue.get("fields", {})
    require(issue.get("key") == "KAN-2" and fields.get("project", {}).get("key") == "KAN" and TASK in flatten(fields.get("description")) and
            SOURCE in flatten(fields.get("description")) and fields.get("status", {}).get("statusCategory", {}).get("key") == "done", "Actual Jira issue identity or Done readback differs")
    comment_id = record.get("publication", {}).get("jira", {}).get("comment", {}).get("id")
    require(isinstance(comment_id, str) and re.fullmatch(r"[0-9]{1,20}", comment_id), "Actual Jira comment identity is unavailable")
    comment = json.loads(get(jira + "/rest/api/3/issue/KAN-2/comment/" + comment_id, auth))
    expected, block = publication_text(record, report)
    adf = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": expected}]}]}
    require(comment.get("id") == comment_id and comment.get("body") == adf, "Actual Jira comment does not exactly match the new run and report hash")
    path = "https://slack.com/api/conversations.history?" + urllib.parse.urlencode({"channel": CHANNEL, "oldest": TS, "latest": TS, "inclusive": "true", "limit": 1})
    slack = json.loads(get(path, "Bearer " + environment["SLACK_BOT_TOKEN"]))
    messages = slack.get("messages", [])
    require(slack.get("ok") is True and len(messages) == 1 and messages[0].get("ts") == TS and messages[0].get("bot_id") and
            TASK in messages[0].get("text", "") and SOURCE in messages[0].get("text", "") and messages[0]["text"].endswith("\n\n" + block),
            "Actual original Slack bot message does not exactly contain the new run evidence block")
    return {"jira_comment_id": comment_id, "jira_done": True, "jira_exact_comment": True, "slack_exact_run_block": True,
            "slack_channel": CHANNEL, "slack_message_ts": TS}


def graph_audit(environment, archive, archive_sha, record, report):
    require(re.fullmatch(r"[a-f0-9]{64}", archive_sha) and sha(Path(archive).read_bytes()) == archive_sha, "Dependency archive differs from its approved hash")
    sys.path.insert(0, str(Path(archive).resolve()))
    import redis
    identity, graph, agent = record["id"], record.get("graph"), record.get("investigation", {}).get("id")
    require(re.fullmatch(r"[a-f0-9]{32}", identity) and isinstance(graph, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", graph) and
            isinstance(agent, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", agent), "Read-only graph identities are invalid")
    setting = environment.get("FALKORDB_TLS")
    require(isinstance(setting, str) and (setting == "0" or setting.lower() in ("1", "true", "yes")), "Explicit approved graph transport mode is unavailable")
    transport = {"ssl": setting != "0"}
    if transport["ssl"]:
        transport.update(ssl_cert_reqs="required", ssl_check_hostname=True)
    connection = redis.Redis(host=environment["FALKORDB_HOST"], port=int(environment.get("FALKORDB_PORT", "6379")),
        username=environment.get("FALKORDB_USERNAME") or None, password=environment.get("FALKORDB_PASSWORD") or None,
        socket_connect_timeout=3, socket_timeout=15, decode_responses=True, **transport)
    def query(text):
        result = connection.execute_command("GRAPH.RO_QUERY", graph, text)
        require(isinstance(result, list) and len(result) >= 2 and isinstance(result[1], list), "Direct graph response is malformed")
        return result[1]
    try:
        rows = query("MATCH (t:LocalTask {id:'" + TASK + "'})-[:HAS_AUTONOMOUS_RUN]->(r:AutonomousRun {id:'" + identity +
            "'})-[:VALIDATES]->(w:WorkItem {id:'" + ITEM + "'}),(r)-[:INVESTIGATED_BY]->(a:AgentRun {id:'" + agent +
            "'}) RETURN r.id,r.evidence_sha256,r.runner_url,r.status")
        require(rows == [[identity, record["evidence"][0]["sha256"], record["runner"]["run_url"], "succeeded"]], "Direct graph run/task/source/agent proof differs")
        rows = query("MATCH (r:AutonomousRun {id:'" + identity + "'})-[:HAS_CHECK]->(c:AutonomousCheck) RETURN c.id,c.name,c.exit_code,c.log_sha256")
        expected = [[identity + ":" + str(index), check["name"], check["exit_code"], check["log_sha256"]] for index, check in enumerate(report["checks"])]
        require(sorted(rows) == sorted(expected), "Direct graph check count, outcomes or log hashes differ")
    finally:
        connection.close()
    return {"source_graph": graph, "bound_run_nodes": 1, "check_nodes": len(report["checks"]), "has_check_links": len(report["checks"]),
            "task_source_agent_binding": True, "configured_graph_tls": transport["ssl"]}


def verify(identity, archive, archive_sha):
    require(re.fullmatch(r"[a-f0-9]{32}", identity), "Invalid workflow run ID")
    record = json.loads(get(ORIGIN + "/api/public/workflows/" + identity))
    require(record.get("id") == identity and record.get("task_id") == TASK and record.get("status") == "completed" and
            record.get("runner", {}).get("verified") is True, "App has no completed verified run")
    raw = get(ORIGIN + "/api/public/workflows/" + identity + "/evidence")
    require(len(record.get("evidence", [])) == 1 and record["evidence"][0].get("sha256") == sha(raw), "Exact public report hash differs")
    report = json.loads(raw)
    import boto3
    from botocore.config import Config
    config = boto3.client("lambda", region_name="ap-south-1", config=Config(connect_timeout=3, read_timeout=10,
        retries={"total_max_attempts": 1})).get_function_configuration(FunctionName="baton-workspace")
    environment = config.get("Environment", {}).get("Variables", {})
    providers = provider_audit(environment, record, report)
    graph = graph_audit(environment, archive, archive_sha, record, report)
    del environment, config
    return {"status": "verified", "run_id": identity, "report_sha256": sha(raw), "providers": providers, "graph": graph,
        "limits": ["Only provider GET requests and GRAPH.RO_QUERY were issued; no provider messages or state updates were sent.",
            "Independent GitHub artifact, raw-log and model-edit proof is recorded by verify_autonomous_release.py."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--lambda-archive", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = verify(args.run_id, args.lambda_archive, args.archive_sha256)
    except AuditError as error:
        result = {"status": "failed", "error": str(error)}
    except Exception:
        result = {"status": "failed", "error": "Read-only cloud audit stopped; no private configuration or provider body was printed"}
    encoded = json.dumps(result, sort_keys=True)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
