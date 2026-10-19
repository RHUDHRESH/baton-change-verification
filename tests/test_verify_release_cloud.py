"""Cloud proof boundary tests use synthetic GET/Redis responses, not live proof."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call
import zipfile

import pytest

from test_verify_release_gate import fixture as release_fixture
from server import release_contract as C, release_publication as publisher

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_release_cloud", ROOT / "deploy/verify_release_cloud.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


@pytest.fixture
def evidence(release_fixture, monkeypatch, tmp_path):
    source = release_fixture
    plan, record = source.plan, source.record
    plan["graph"] = A.GRAPH
    plan["plan_hash"] = C.plan_hash(plan)
    record["plan_hash"] = record["graph_receipt"]["plan_hash"] = plan["plan_hash"]
    report = json.loads(source.files["release-report.json"])
    report["plan_hash"] = plan["plan_hash"]
    raw = (C.encode(report) + "\n").encode()
    record["evidence"]["sha256"] = record["graph_receipt"]["evidence_sha256"] = C.sha(raw)
    environment = {"JIRA_SITE_URL": "https://example.atlassian.net", "JIRA_PROJECT_KEY": "KAN", "JIRA_CLOUD_ID": "11111111-1111-1111-1111-111111111111",
        "JIRA_EMAIL": "operator@example.test", "JIRA_API_TOKEN": "DO-NOT-PRINT-JIRA-TOKEN", "SLACK_CHANNEL_ID": "C123456",
        "SLACK_BOT_TOKEN": "DO-NOT-PRINT-SLACK-TOKEN", "FALKORDB_HOST": "approved-free.test", "FALKORDB_PORT": "12345", "FALKORDB_TLS": "0",
        "FALKORDB_USERNAME": "DO-NOT-PRINT-GRAPH-USER", "FALKORDB_PASSWORD": "DO-NOT-PRINT-GRAPH-PASSWORD"}
    title, text = publisher._text(plan, record)
    for target, receipt in record["publication"].items():
        receipt.update(title=title, evidence_text=text)
        if target == "slack":
            receipt["message_text"] = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        material = {"run_id": record["id"], "plan_id": plan["id"], "plan_hash": plan["plan_hash"], "target": target,
            "destination": receipt["destination"], "cloud_id": environment["JIRA_CLOUD_ID"] if target == "jira" else None,
            "evidence": record["evidence"], "title": title, "text": text, "decision": record["decision"]}
        receipt["contract_sha256"] = C.sha(C.encode(material))
    issue = {"key": "KAN-99", "fields": {"project": {"key": "KAN"}, "summary": title,
        "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}}}
    slack = {"ok": True, "messages": [{"ts": record["publication"]["slack"]["remote_id"], "text": record["publication"]["slack"]["message_text"]}]}
    permalink = {"ok": True, "permalink": record["publication"]["slack"]["url"]}
    reads = []
    def get(url, auth=None):
        reads.append((url, auth))
        if url == A.ORIGIN + "/api/public/release-runs/" + record["id"]:
            return C.encode(record).encode()
        if url == A.ORIGIN + "/api/public/release-plans/" + plan["id"]:
            return C.encode(plan).encode()
        if url.endswith("/evidence"):
            return raw
        if "/rest/api/3/issue/" in url:
            return C.encode(issue).encode()
        return C.encode(permalink if "chat.getPermalink" in url else slack).encode()
    monkeypatch.setattr(A, "get", get)
    monkeypatch.setattr(A, "lambda_environment", lambda: dict(environment))
    archive = tmp_path / "approved.zip"
    archive.write_bytes(b"approved dependency boundary fixture")
    results = [{**check, "check_id": check["id"], "environment_id": env["id"]} for env in record["environments"] for check in env["checks"]]
    execution_rows = [[C.encode(record["graph_receipt"]), A.SCOPE + ":change"]]
    measurement_rows = []
    for result in results:
        check = {"id": A.SCOPE + ":" + result["check_id"], "kind": "RequiredCheck", "registry_version": A.REGISTRY}
        env = {"id": A.SCOPE + ":" + result["environment_id"], "kind": "RequiredEnvironment", "redis_version": result["environment_id"].removeprefix("redis-"),
               "required": True, "policy_version": A.POLICY}
        identity = record["id"] + ":" + C.sha(C.encode([result["check_id"], result["environment_id"]]))[:20]
        measurement_rows.append([C.encode(record["graph_receipt"]), identity, C.encode(result), check["id"], C.encode(check), env["id"], C.encode(env)])
    publication_rows = [[receipt["id"], target, receipt["url"], receipt["contract_sha256"], record["id"]] for target, receipt in record["publication"].items()]
    redis = SimpleNamespace(__version__="8.1.0", Redis=MagicMock())
    redis.Redis.return_value.execute_command.side_effect = [[[], execution_rows, []], [[], measurement_rows, []], [[], publication_rows, []]]
    monkeypatch.setattr(A, "load_redis", lambda *args: redis)
    return SimpleNamespace(plan=plan, record=record, report=report, results=results, raw=raw, environment=environment, issue=issue, slack=slack,
        permalink=permalink, reads=reads, archive=archive, archive_sha=C.sha(archive.read_bytes()), redis=redis,
        execution_rows=execution_rows, measurement_rows=measurement_rows, publication_rows=publication_rows)


def test_cloud_proof_matches_new_provider_artifacts_and_eight_graph_measurements(evidence):
    result = A.verify(evidence.record["id"], evidence.archive, evidence.archive_sha)
    assert result["status"] == "verified_failure" and result["release_decision"] == "blocked"
    assert (result["total"], result["passed"], result["failed"]) == (8, 6, 2)
    assert result["providers"]["provider_get_performed"] is True
    assert result["graph"]["direct_graph_get_performed"] is True
    assert result["graph"]["measurement_nodes"] == 8 and result["graph"]["publication_links"] == 2
    assert result["python_redis_client_versions"] == ["8.0.0", "8.1.0"]
    assert result["isolated_test_falkordb_server_image"] == C.FALKORDB_IMAGE
    assert result["task_completion_claimed"] is False
    assert "DO-NOT-PRINT" not in C.encode(result)
    commands = evidence.redis.Redis.return_value.execute_command.call_args_list
    assert len(commands) == 3 and all(call.args[0] == "GRAPH.RO_QUERY" for call in commands)
    assert all(call.args[-2:] == ("TIMEOUT", 10000) for call in commands)
    evidence.redis.Redis.return_value.close.assert_called_once()


def test_direct_provider_gets_use_configured_hosts_channel_and_exact_new_ids(evidence):
    A.provider_audit(evidence.environment, evidence.plan, evidence.record)
    urls = [url for url, _ in evidence.reads]
    assert urls[0] == "https://api.atlassian.com/ex/jira/11111111-1111-1111-1111-111111111111/rest/api/3/issue/KAN-99?fields=summary,description,project"
    assert urls[1] == "https://slack.com/api/conversations.history?channel=C123456&oldest=1792334785.098199&latest=1792334785.098199&inclusive=true&limit=1"
    assert urls[2] == "https://slack.com/api/chat.getPermalink?channel=C123456&message_ts=1792334785.098199"


@pytest.mark.parametrize("mutation", ["jira-summary", "jira-description", "jira-project", "slack-text", "slack-id", "permalink", "contract", "destination", "old-run"])
def test_changed_provider_content_or_scope_cannot_pass(evidence, mutation):
    if mutation == "jira-summary": evidence.issue["fields"]["summary"] = "unrelated title"
    elif mutation == "jira-description": evidence.issue["fields"]["description"]["content"][0]["content"][0]["text"] += "unrelated evidence"
    elif mutation == "jira-project": evidence.issue["fields"]["project"]["key"] = "OTHER"
    elif mutation == "slack-text": evidence.slack["messages"][0]["text"] += "different run"
    elif mutation == "slack-id": evidence.slack["messages"][0]["ts"] = "1792334785.000000"
    elif mutation == "permalink": evidence.permalink["permalink"] += "?different"
    elif mutation == "contract": evidence.record["publication"]["jira"]["contract_sha256"] = "0" * 64
    elif mutation == "destination": evidence.environment["SLACK_CHANNEL_ID"] = "C000000"
    else: evidence.record["publication"]["jira"]["run_id"] = "f" * 32
    with pytest.raises(A.AuditError):
        A.provider_audit(evidence.environment, evidence.plan, evidence.record)


@pytest.mark.parametrize("mutation", ["missing-measurement", "duplicate-measurement", "check-link", "environment-link", "outcome", "execution-hash", "publication-hash"])
def test_direct_graph_must_match_every_result_and_publication_binding(evidence, mutation):
    if mutation == "missing-measurement": evidence.measurement_rows.pop()
    elif mutation == "duplicate-measurement": evidence.measurement_rows[1] = copy.deepcopy(evidence.measurement_rows[0])
    elif mutation == "check-link": evidence.measurement_rows[0][3] = A.SCOPE + ":unapproved-check"
    elif mutation == "environment-link": evidence.measurement_rows[0][5] = A.SCOPE + ":unapproved-environment"
    elif mutation == "outcome":
        changed = json.loads(evidence.measurement_rows[6][2]); changed["status"] = "passed"
        evidence.measurement_rows[6][2] = C.encode(changed)
    elif mutation == "execution-hash":
        changed = json.loads(evidence.execution_rows[0][0]); changed["evidence_sha256"] = "0" * 64
        evidence.execution_rows[0][0] = C.encode(changed)
    else: evidence.publication_rows[0][3] = "0" * 64
    with pytest.raises(A.AuditError):
        A.graph_audit(evidence.environment, evidence.archive, evidence.archive_sha, evidence.plan, evidence.record, evidence.results)
    assert all(call.args[0] == "GRAPH.RO_QUERY" for call in evidence.redis.Redis.return_value.execute_command.call_args_list)
    evidence.redis.Redis.return_value.close.assert_called_once()


@pytest.mark.parametrize("tls", ["0", "1"])
def test_graph_uses_the_explicit_existing_transport_mode(evidence, tls):
    evidence.environment["FALKORDB_TLS"] = tls
    result = A.graph_audit(evidence.environment, evidence.archive, evidence.archive_sha, evidence.plan, evidence.record, evidence.results)
    kwargs = evidence.redis.Redis.call_args.kwargs
    assert result["configured_graph_tls"] is (tls == "1")
    assert kwargs["ssl"] is (tls == "1")
    if tls == "1":
        assert kwargs["ssl_cert_reqs"] == "required" and kwargs["ssl_check_hostname"] is True


def test_missing_transport_or_unapproved_dependency_archive_fails_before_connecting(evidence):
    evidence.environment["FALKORDB_TLS"] = ""
    with pytest.raises(A.AuditError):
        A.graph_audit(evidence.environment, evidence.archive, evidence.archive_sha, evidence.plan, evidence.record, evidence.results)
    evidence.redis.Redis.assert_not_called()
    with pytest.raises(A.AuditError, match="archive"):
        A.verify(evidence.record["id"], evidence.archive, "0" * 64)
    assert evidence.reads == []


def test_redis_loader_reads_only_the_approved_zip_package(monkeypatch, tmp_path):
    archive = tmp_path / "approved-redis.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("redis/__init__.py", "__version__ = '8.1.0'\n")
    for name in tuple(sys.modules):
        if name == "redis" or name.startswith("redis."):
            monkeypatch.delitem(sys.modules, name)
    try:
        module = A.load_redis(archive, C.sha(archive.read_bytes()))
        assert module.__version__ == "8.1.0" and str(archive.resolve()) in module.__file__
    finally:
        sys.path.remove(str(archive.resolve()))


def test_cloud_cli_rejects_without_printing_private_provider_values(monkeypatch, tmp_path, capsys):
    def stopped(*args):
        raise RuntimeError("DO-NOT-PRINT-PRIVATE-ENVIRONMENT")
    monkeypatch.setattr(A, "verify", stopped)
    output = tmp_path / "proof.json"
    assert A.main(["--run-id", "a" * 32, "--lambda-archive", "approved.zip", "--archive-sha256", "b" * 64, "--output", str(output)]) == 1
    assert "DO-NOT-PRINT" not in capsys.readouterr().out + output.read_text()


def test_only_existing_lambda_configuration_is_read_and_unneeded_secrets_are_filtered(monkeypatch):
    client = MagicMock()
    client.get_function_configuration.return_value = {"Environment": {"Variables": {
        "JIRA_API_TOKEN": "private-in-memory-only", "UNRELATED_PRIVATE_SECRET": "not-needed"}}}
    sdk = SimpleNamespace(client=MagicMock(return_value=client))
    monkeypatch.setitem(sys.modules, "boto3", sdk)
    monkeypatch.setitem(sys.modules, "botocore.config", SimpleNamespace(Config=MagicMock()))
    environment = A.lambda_environment()
    assert environment["JIRA_API_TOKEN"] == "private-in-memory-only"
    assert "UNRELATED_PRIVATE_SECRET" not in environment
    assert client.mock_calls == [call.get_function_configuration(FunctionName="baton-workspace")]
