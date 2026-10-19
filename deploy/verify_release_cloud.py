"""Read-only CloudShell proof of new release publications and graph bindings.

Existing Lambda configuration stays in memory. Only provider/public HTTPS GETs,
Lambda GetFunctionConfiguration, and GRAPH.RO_QUERY are allowed. The approved
Lambda ZIP supplies its pure Python Redis client; no dependencies are installed.
Redis 8.0.0/8.1.0 below name Python client dependencies, not database servers.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path
import re
import ssl
import sys
import urllib.parse
import urllib.request

ORIGIN = "https://baton-workspace.vercel.app"
COMMIT = "207000da70ca183ab02990a98bdd97d0a3e3bb1b"
CHANGE = "FalkorDB/falkordb-py#212"
CHANGE_URL = "https://github.com/FalkorDB/falkordb-py/pull/212"
ARCHIVE_SHA = "cb2057288440cfc977da4bcfbf3770a3a577511f6ef5d3b5b79cf4006ea1a499"
PYTHON_IMAGE = "python@sha256:a7cb177dc60dfa77b223192cd0d9e6ce1aac7cf9a569023d68e7c91b6371a718"
SERVER_IMAGE = "falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a"
GRAPH = "baton_release_py211_" + COMMIT[:12]
SCOPE = CHANGE + "@" + COMMIT
REGISTRY, POLICY = "py211-v1", "required-redis-800-810-v1"
CHECKS = (
    "tests/test_graph.py::test_param_non_identifier_keys",
    "tests/test_graph.py::test_param_invalid_keys_rejected",
    "tests/test_async_graph.py::test_param_non_identifier_keys",
    "tests/test_async_graph.py::test_param_invalid_keys_rejected",
)
ENVIRONMENTS = [{"id": "redis-" + version, "redis_version": version, "required": True} for version in ("8.0.0", "8.1.0")]
SOURCE_HASHES = {
    "falkordb/graph.py": "a14f09fb7322d3e7e2e808d97f4103e460a62c39212d9fb76769223227e85036",
    "falkordb/helpers.py": "a97d54c480b98e550af3b2dfd324e82669266ddf07547e9fedc5aaf50285c6a1",
    "falkordb/asyncio/graph.py": "41fc523886a2b40e2874dfba13387306ef853cfe098b0a54683722b66fb47f0f",
    "tests/test_graph.py": "f9f4be99d4887cd4f1c989fe3f145eb74d05a8deae583b2209cd192522cf3197",
    "tests/test_async_graph.py": "8d59ac14963d1e8131ada191292ee2f241da933645d3feed9fa9dfcd12b8eecc",
}
BINDING_FIELDS = (
    "schema_version", "registry_version", "policy_version", "change_id", "title", "source_commit",
    "source_archive_sha256", "source_hashes", "python_image", "python_version", "falkordb_image", "graph", "plan_status",
    "required_checks", "environments", "source_versions", "witness_paths", "binding_fingerprint",
)


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuditError("Read-only redirect refused")


def get(url, authorization=None):
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    try:
        request = urllib.request.Request(url, method="GET", headers=headers)
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(request, timeout=25) as response:
            raw = response.read(4_000_001)
        require(len(raw) <= 4_000_000, "Read-only response exceeded its bound")
        return raw
    except AuditError:
        raise
    except Exception:
        raise AuditError("Read-only GET was not confirmed; no private URL or provider body was printed") from None


def approved_archive(path, digest):
    require(isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest), "Approved dependency archive hash is invalid")
    target = Path(path)
    require(target.is_file() and target.stat().st_size <= 49 * 1024 * 1024 and sha(target.read_bytes()) == digest,
            "Dependency archive differs from its approved hash")
    return target.resolve()


def load_redis(path, digest):
    archive = approved_archive(path, digest)
    prefix = str(archive).replace("\\", "/") + "/"
    for name, module in tuple(sys.modules.items()):
        if name == "redis" or name.startswith("redis."):
            require(str(getattr(module, "__file__", "")).replace("\\", "/").startswith(prefix + "redis/"),
                    "A Redis client outside the approved archive is already loaded")
    sys.path.insert(0, str(archive))
    module = importlib.import_module("redis")
    require(str(getattr(module, "__file__", "")).replace("\\", "/").startswith(prefix + "redis/") and
            re.fullmatch(r"[A-Za-z0-9.+_-]{1,40}", getattr(module, "__version__", "")),
            "Redis client was not imported from the approved archive")
    return module


def lambda_environment():
    import boto3
    from botocore.config import Config
    response = boto3.client("lambda", region_name="ap-south-1", config=Config(connect_timeout=3, read_timeout=10,
        retries={"total_max_attempts": 1})).get_function_configuration(FunctionName="baton-workspace")
    environment = response.get("Environment", {}).get("Variables", {})
    require(isinstance(environment, dict), "Existing Lambda environment is unavailable")
    keys = ("JIRA_SITE_URL", "JIRA_PROJECT_KEY", "JIRA_CLOUD_ID", "JIRA_EMAIL", "JIRA_API_TOKEN", "SLACK_CHANNEL_ID", "SLACK_BOT_TOKEN",
            "FALKORDB_HOST", "FALKORDB_PORT", "FALKORDB_USERNAME", "FALKORDB_PASSWORD", "FALKORDB_TLS")
    # Nothing from this private dictionary is serialized, printed, or written.
    return {key: environment.get(key, "") for key in keys}


def public_evidence(identity):
    require(isinstance(identity, str) and re.fullmatch(r"[a-f0-9]{32}", identity), "Run identity must be 32 lowercase hex characters")
    path = ORIGIN + "/api/public/release-runs/" + identity
    record = json.loads(get(path))
    require(record.get("id") == identity and record.get("status") == "completed" and record.get("evidence_status") == "verified" and
            record.get("evidence_verified") is True and record.get("runner", {}).get("verified") is True,
            "App does not expose a complete verified release run")
    runner = record["runner"]
    require(runner.get("provider") == "GitHub Actions" and re.fullmatch(r"[0-9]{1,20}", str(runner.get("run_id", ""))) and
            runner.get("run_url") == "https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/" + str(runner["run_id"]),
            "Public GitHub runner link is outside the approved repository")
    plan_id = record.get("plan_id", "")
    require(re.fullmatch(r"[a-f0-9]{32}", plan_id), "Public plan identity is invalid")
    plan = json.loads(get(ORIGIN + "/api/public/release-plans/" + plan_id))
    require(plan.get("id") == plan_id and plan.get("plan_hash") == record.get("plan_hash") ==
            sha(encode({key: plan.get(key) for key in BINDING_FIELDS})), "Public sealed plan hash differs")
    policy = {"schema_version": 1, "registry_version": REGISTRY, "policy_version": POLICY, "change_id": CHANGE,
              "source_commit": COMMIT, "source_archive_sha256": ARCHIVE_SHA, "python_image": PYTHON_IMAGE,
              "python_version": "3.13.5", "falkordb_image": SERVER_IMAGE, "graph": GRAPH, "plan_status": "ready",
              "environments": ENVIRONMENTS, "source_hashes": SOURCE_HASHES}
    require(all(plan.get(key) == value for key, value in policy.items()) and
            [row.get("id") for row in plan.get("required_checks", [])] == list(CHECKS), "Public plan differs from approved release policy")
    raw = get(path + "/evidence")
    require(record.get("evidence", {}).get("sha256") == sha(raw) and record["evidence"].get("url") == path + "/evidence",
            "Public report hash or evidence URL differs")
    report = json.loads(raw)
    require(report.get("schema_version") == 1 and report.get("run_id") == identity and report.get("plan_id") == plan_id and
            report.get("plan_hash") == plan["plan_hash"] and report.get("source_commit") == record.get("source_commit") == COMMIT and
            report.get("source_archive_sha256") == ARCHIVE_SHA and report.get("workflow_sha") == record["runner"].get("workflow_sha") and
            re.fullmatch(r"[a-f0-9]{40}", report.get("workflow_sha", "")) and report.get("source_unchanged") is True,
            "Public report does not bind the exact run, plan and unchanged source")
    source_hashes = report.get("source_hashes")
    require(isinstance(source_hashes, dict) and all(source_hashes.get(key) == value for key, value in SOURCE_HASHES.items()) and
            all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in source_hashes.values()),
            "Public source blob hashes differ from the approved source")
    environments = record.get("environments", [])
    actual = report.get("environments", [])
    require([row.get("id") for row in environments] == [row["id"] for row in ENVIRONMENTS] and len(actual) == 2,
            "Public required Python Redis client matrix is incomplete")
    graph_results, flat_results = [], []
    for normalized, observed, approved in zip(environments, actual, ENVIRONMENTS):
        require(observed.get("id") == normalized["id"] == approved["id"] and
                observed.get("redis_version") == normalized.get("redis_version") == approved["redis_version"] and
                observed.get("python_version") == "3.13.5" and observed.get("python_image") == PYTHON_IMAGE and
                observed.get("falkordb_image") == SERVER_IMAGE and observed.get("dependencies", {}).get("redis") == approved["redis_version"] and
                observed.get("source_hashes_before") == observed.get("source_hashes_after") == report.get("source_hashes"),
                "Public test source or environment bindings differ")
        checks = normalized.get("checks", [])
        require([row.get("id") for row in checks] == list(CHECKS) and observed.get("test_results") == checks and
                all(row.get("status") in {"passed", "failed", "error"} for row in checks), "Public exact per-test outcomes differ from the report")
        counts = {"passed": sum(row["status"] == "passed" for row in checks), "failed": sum(row["status"] == "failed" for row in checks),
                  "errors": sum(row["status"] == "error" for row in checks), "skipped": 0, "total": 4}
        batch = observed.get("checks", [])
        require(len(batch) == 1 and batch[0].get("id") == "py211-regressions" and
                batch[0].get("argv") == ["python", "-m", "pytest", "-v", "-o", "addopts=", "-p", "no:cacheprovider", "--junitxml=/out/junit.xml", *CHECKS] and
                all(type(normalized.get(key)) is int and type(batch[0].get(key)) is int and normalized[key] == value == batch[0].get(key) for key, value in counts.items()) and
                type(batch[0].get("exit_code")) is int and batch[0]["exit_code"] == (1 if counts["failed"] or counts["errors"] else 0),
                "Public counts or approved command contradict the per-test matrix")
        graph_results.extend({**check, "check_id": check["id"], "environment_id": normalized["id"]} for check in checks)
        flat_results.extend({"check_id": check["id"], "environment_id": normalized["id"], **{k: v for k, v in check.items() if k != "id"}} for check in checks)
    passed = all(row["status"] == "passed" for row in graph_results)
    expected_receipt = {"verified": True, "run_id": identity, "plan_hash": plan["plan_hash"], "source_commit": COMMIT,
        "release_passed": passed, "checks": 8, "policy_version": POLICY, "registry_version": REGISTRY,
        "evidence_sha256": sha(raw), "results_sha256": sha(encode(graph_results)), "binding_fingerprint": plan.get("binding_fingerprint")}
    require(record.get("graph_receipt") == expected_receipt and re.fullmatch(r"[a-f0-9]{64}", plan.get("binding_fingerprint", "")) and
            record.get("decision") == ("passed" if passed else "blocked") and record.get("verification_status") == ("passed" if passed else "failed") and
            encode(record.get("results")) == encode(flat_results), "Public graph receipt or decision contradicts the exact test matrix")
    return plan, record, report, graph_results


def expected_publication(plan, record):
    title = ("Investigate verified compatibility failure: " if record["decision"] == "blocked" else "Verification record: ") + "FalkorDB-py #212"
    lines = [title, "Verification outcome: " + ("blocked" if record["decision"] == "blocked" else "passed for the declared matrix"),
             "Source: " + CHANGE_URL, "Source commit: " + COMMIT, "Plan: " + plan["id"], "Plan hash: " + plan["plan_hash"],
             "App run: " + record["id"], "GitHub run: " + record["runner"]["run_url"]]
    for environment in record["environments"]:
        lines.append("redis-py " + environment["redis_version"] + ": " + str(environment["passed"]) + " passed, " + str(environment["failed"]) +
                     " failed, " + str(environment["errors"]) + " errors, " + str(environment["skipped"]) + " skipped")
        lines.extend("Failed obligation: " + check["id"] for check in environment["checks"] if check["status"] in {"failed", "error"})
    lines += ["Evidence: " + record["evidence"]["url"], "Evidence SHA-256: " + record["evidence"]["sha256"],
              "The graph requires both sync and inherited async checks. Both environments are required.",
              "This verifies an existing merged change; no source repair or upstream merge was performed.",
              "This remediation/report artifact is not marked Done by publication."]
    return title, "\n".join(lines)


def provider_audit(environment, plan, record):
    site, project, channel = environment.get("JIRA_SITE_URL", "").rstrip("/"), environment.get("JIRA_PROJECT_KEY", ""), environment.get("SLACK_CHANNEL_ID", "")
    cloud_id = environment.get("JIRA_CLOUD_ID", "")
    require(re.fullmatch(r"https://[a-z0-9][a-z0-9-]{0,62}\.atlassian\.net", site) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", project) and
            re.fullmatch(r"[CG][A-Z0-9]{5,30}", channel) and (not cloud_id or re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", cloud_id)) and
            all(environment.get(key) for key in ("JIRA_EMAIL", "JIRA_API_TOKEN", "SLACK_BOT_TOKEN")), "Existing configured provider destinations or credentials are unavailable")
    title, text = expected_publication(plan, record)
    receipts = record.get("publication", {})
    require(set(receipts) == {"jira", "slack"}, "New publication receipts are incomplete")
    for target, receipt in receipts.items():
        require(receipt.get("status") == "verified" and receipt.get("graph_linked") is True and receipt.get("target") == target and
                receipt.get("run_id") == record["id"] and receipt.get("plan_id") == plan["id"] and
                receipt.get("id") == "publication-" + sha(record["id"] + ":" + target) and
                receipt.get("title") == title and receipt.get("evidence_text") == text and
                re.fullmatch(r"[a-f0-9]{64}", receipt.get("contract_sha256", "")), "Provider receipt does not bind the new run and exact report")
        destination = site + "/" + project if target == "jira" else channel
        material = {"run_id": record["id"], "plan_id": plan["id"], "plan_hash": plan["plan_hash"], "target": target,
                    "destination": destination, "cloud_id": cloud_id if target == "jira" else None,
                    "evidence": record["evidence"], "title": title, "text": text, "decision": record["decision"]}
        require(receipt.get("destination") == destination and receipt["contract_sha256"] == sha(encode(material)),
                "Private configured destination and publication contract differ")
    jira_receipt, slack_receipt = receipts["jira"], receipts["slack"]
    key, ts = jira_receipt.get("remote_id", ""), slack_receipt.get("remote_id", "")
    require(re.fullmatch(re.escape(project) + r"-[0-9]+", key) and re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", ts),
            "New provider artifact identities are invalid")
    jira_base = "https://api.atlassian.com/ex/jira/" + cloud_id if cloud_id else site
    auth = "Basic " + base64.b64encode((environment["JIRA_EMAIL"] + ":" + environment["JIRA_API_TOKEN"]).encode()).decode()
    issue = json.loads(get(jira_base + "/rest/api/3/issue/" + key + "?fields=summary,description,project", auth))
    adf = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}
    require(issue.get("key") == key and issue.get("fields", {}).get("project", {}).get("key") == project and
            issue["fields"].get("summary") == title and issue["fields"].get("description") == adf and
            jira_receipt.get("url") == site + "/browse/" + key, "Direct Jira GET does not match the exact new issue and evidence")
    expected_message = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    require(slack_receipt.get("message_text") == expected_message, "Stored Slack material differs from the independently reconstructed text")
    headers = "Bearer " + environment["SLACK_BOT_TOKEN"]
    history = "https://slack.com/api/conversations.history?" + urllib.parse.urlencode({"channel": channel, "oldest": ts, "latest": ts, "inclusive": "true", "limit": 1})
    messages = json.loads(get(history, headers))
    require(messages.get("ok") is True and len(messages.get("messages", [])) == 1 and messages["messages"][0].get("ts") == ts and
            messages["messages"][0].get("text") == expected_message, "Direct Slack GET does not match the exact new message and evidence")
    permalink = json.loads(get("https://slack.com/api/chat.getPermalink?" + urllib.parse.urlencode({"channel": channel, "message_ts": ts}), headers))
    require(permalink.get("ok") is True and permalink.get("permalink") == slack_receipt.get("url") and
            re.fullmatch(r"https://[a-zA-Z0-9-]+\.slack\.com/archives/" + re.escape(channel) + "/p" + re.escape(ts.replace(".", "")), permalink.get("permalink", "")),
            "Direct Slack permalink GET differs from the saved new message")
    return {"provider_get_performed": True, "jira": {"remote_id": key, "exact_summary": True, "exact_description": True,
        "evidence_text_sha256": sha(text), "task_completion_claimed": False}, "slack": {"remote_id": ts,
        "exact_message": True, "message_sha256": sha(expected_message), "permalink_sha256": sha(permalink["permalink"])}}


def graph_audit(environment, archive, archive_sha, plan, record, results):
    require(plan.get("graph") == GRAPH and re.fullmatch(r"[a-f0-9]{32}", record.get("id", "")), "Read-only graph identity is outside the approved scope")
    redis = load_redis(archive, archive_sha)
    setting, host, port = environment.get("FALKORDB_TLS"), environment.get("FALKORDB_HOST", ""), environment.get("FALKORDB_PORT") or "6379"
    require(isinstance(setting, str) and (setting == "0" or setting.lower() in {"1", "true", "yes"}) and
            re.fullmatch(r"[A-Za-z0-9_.-]{1,253}", host) and re.fullmatch(r"[0-9]{1,5}", str(port)) and 1 <= int(port) <= 65535,
            "Explicit graph transport mode or configured address is invalid")
    transport = {"ssl": setting != "0"}
    if transport["ssl"]:
        transport.update(ssl_cert_reqs="required", ssl_check_hostname=True)
    connection = redis.Redis(host=host, port=int(port), username=environment.get("FALKORDB_USERNAME") or None,
        password=environment.get("FALKORDB_PASSWORD") or None, socket_connect_timeout=3, socket_timeout=15, decode_responses=True, **transport)
    identity, receipt = record["id"], record["graph_receipt"]
    def query(text):
        response = connection.execute_command("GRAPH.RO_QUERY", GRAPH, text, "TIMEOUT", 10000)
        require(isinstance(response, list) and len(response) >= 2 and isinstance(response[1], list) and len(response[1]) <= 20,
                "Direct graph GET returned malformed or unbounded rows")
        return response[1]
    try:
        rows = query("MATCH (r:ReleaseExecution {id:'" + identity + "'})-[:VERIFIES]->(c:ReleaseEvidence {id:'" + SCOPE + ":change'}) RETURN r.json,c.id LIMIT 20")
        require(len(rows) == 1 and len(rows[0]) == 2 and json.loads(rows[0][0]) == receipt and rows[0][1] == SCOPE + ":change",
                "Direct graph execution receipt or change relationship differs")
        rows = query("MATCH (r:ReleaseExecution {id:'" + identity + "'})-[:MEASURED]->(m:ReleaseMeasurement)-[:CHECKED]->(c:ReleaseEvidence),"
                     "(m)-[:IN_ENVIRONMENT]->(e:ReleaseEvidence) RETURN r.json,m.id,m.json,c.id,c.json,e.id,e.json LIMIT 20")
        expected = {identity + ":" + sha(encode([row["check_id"], row["environment_id"]]))[:20]: row for row in results}
        require(len(rows) == 8 and len(expected) == 8, "Direct graph does not contain exactly eight measurements")
        seen = set()
        for row in rows:
            require(len(row) == 7 and row[1] in expected and row[1] not in seen, "Direct graph measurement identity is missing or duplicated")
            observed = expected[row[1]]
            check, env = json.loads(row[4]), json.loads(row[6])
            require(json.loads(row[0]) == receipt and json.loads(row[2]) == observed and
                    row[3] == check.get("id") == SCOPE + ":" + observed["check_id"] and check.get("kind") == "RequiredCheck" and check.get("registry_version") == REGISTRY and
                    row[5] == env.get("id") == SCOPE + ":" + observed["environment_id"] and env.get("kind") == "RequiredEnvironment" and
                    env.get("redis_version") == observed["environment_id"].removeprefix("redis-") and env.get("required") is True and env.get("policy_version") == POLICY,
                    "Direct graph measurement result or required check/environment link differs")
            seen.add(row[1])
        rows = query("MATCH (r:ReleaseExecution {id:'" + identity + "'})-[:PUBLISHED_AS]->(p:ReleasePublication) RETURN p.id,p.target,p.url,p.contract_sha256,p.run_id LIMIT 20")
        expected_publications = [[value["id"], target, value["url"], value["contract_sha256"], identity] for target, value in record["publication"].items()]
        require(len(rows) == 2 and sorted(rows) == sorted(expected_publications), "Direct graph publication links or contract hashes differ")
    finally:
        connection.close()
    return {"direct_graph_get_performed": True, "read_only_command": "GRAPH.RO_QUERY", "execution_nodes": 1,
        "measurement_nodes": 8, "required_checks": 4, "python_redis_client_environments": 2, "publication_links": 2,
        "results_sha256": receipt["results_sha256"], "evidence_sha256": receipt["evidence_sha256"],
        "configured_graph_tls": transport["ssl"], "audit_python_redis_client_version": redis.__version__}


def verify(identity, archive, archive_sha):
    approved_archive(archive, archive_sha)
    plan, record, report, results = public_evidence(identity)
    environment = lambda_environment()
    try:
        providers = provider_audit(environment, plan, record)
        graph = graph_audit(environment, archive, archive_sha, plan, record, results)
    finally:
        environment.clear()
    counts = {key: sum(row[key] for row in record["environments"]) for key in ("total", "passed", "failed", "errors", "skipped")}
    return {"status": "verified_failure" if record["decision"] == "blocked" else "verified", "read_only": True,
        "run_id": identity, "plan_hash": plan["plan_hash"], "report_sha256": record["evidence"]["sha256"],
        "release_decision": record["decision"], **counts, "providers": providers, "graph": graph,
        "python_redis_client_versions": [row["redis_version"] for row in ENVIRONMENTS],
        "isolated_test_falkordb_server_image": SERVER_IMAGE, "approved_dependency_archive_sha256": archive_sha,
        "task_completion_claimed": False,
        "limits": ["Only existing Lambda configuration reads, HTTPS GETs, and GRAPH.RO_QUERY were issued; no provider or graph writes were sent.",
            "Independent GitHub artifact/raw-JUnit proof is separate in scripts/verify_release_gate.py.",
            "Python redis dependency versions are separate from the disposable test server image; the managed graph server image/version was not inferred.",
            "These new remediation/report artifacts do not claim a completed repair, task Done transition, or upstream merge."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--lambda-archive", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = verify(args.run_id, args.lambda_archive, args.archive_sha256)
    except AuditError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True,
                  "error": "Read-only cloud audit stopped; no private configuration, credential, or provider body was printed"}
    encoded = encode(result)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] in {"verified", "verified_failure"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
