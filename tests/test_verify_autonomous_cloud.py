"""Read-only cloud audit validates actual provider text and graph row contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

from server import autonomous_publication as publication

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_autonomous_cloud", ROOT / "deploy/verify_autonomous_cloud.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture
def fixture(monkeypatch):
    identity = "a" * 32
    names = ["graph_library_repair_1", "debug_resize", "debug_restore", "release_resize", "release_restore", "format"]
    checks = [{"name": name, "exit_code": 0, "passed": True, "log_sha256": "b" * 64,
        "test_summaries": [] if name == "format" else [{"passed": 530 if name.startswith("graph_library") else 1, "failed": 0}]} for name in names]
    report = {"checks": checks}
    record = {"id": identity, "graph": "baton_actual", "investigation": {"id": "c" * 32}, "runner": {
        "run_url": "https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/123", "source_commit": "d" * 40,
        "image_digest": "sha256:" + "e" * 64, "conclusion": "success"},
        "evidence": [{"url": audit.ORIGIN + "/api/public/workflows/" + identity + "/evidence", "sha256": "f" * 64}],
        "publication": {"jira": {"comment": {"id": "10002"}}}}
    normalized = copy.deepcopy(record)
    normalized.update(status="succeeded", checks=[{"name": check["name"], "status": "passed", "exit_code": 0,
        "test_count": sum(summary["passed"] for summary in check["test_summaries"])} for check in checks], evidence=record["evidence"][0])
    _, runtime_text = publication._text(normalized)
    block = "\n".join(runtime_text.splitlines()[:9]) + "\nNo upstream fix or merge is claimed."
    issue = {"key": "KAN-2", "fields": {"project": {"key": "KAN"}, "description": publication.connections._adf(audit.TASK + " " + audit.SOURCE),
        "status": {"statusCategory": {"key": "done"}}}}
    comment = {"id": "10002", "body": publication.connections._adf(runtime_text)}
    slack = {"ok": True, "messages": [{"ts": audit.TS, "bot_id": "B12345", "text": audit.TASK + " " + audit.SOURCE + "\n\n" + block}]}
    get = MagicMock(side_effect=lambda *args: json.dumps([issue, comment, slack][get.call_count - 1]).encode())
    monkeypatch.setattr(audit, "get", get)
    environment = {"JIRA_SITE_URL": audit.SITE, "JIRA_PROJECT_KEY": "KAN", "JIRA_EMAIL": "operator@example.test", "JIRA_API_TOKEN": "synthetic-token",
        "SLACK_CHANNEL_ID": audit.CHANNEL, "SLACK_BOT_TOKEN": "synthetic-slack", "FALKORDB_HOST": "approved-free.test", "FALKORDB_TLS": "0"}
    return record, report, environment, issue, comment, slack, get


def test_exact_provider_get_readbacks_match_the_actual_runtime_text_contract(fixture):
    record, report, environment, _, _, _, get = fixture
    result = audit.provider_audit(environment, record, report)
    assert result["jira_comment_id"] == "10002" and result["slack_exact_run_block"] is True
    assert get.call_count == 3 and all("chat.update" not in call.args[0] for call in get.call_args_list)


@pytest.mark.parametrize("mutation", ["jira-text", "jira-done", "slack-sha", "slack-ts"])
def test_actual_provider_mismatch_cannot_be_called_verified(fixture, mutation):
    record, report, environment, issue, comment, slack, _ = fixture
    if mutation == "jira-text": comment["body"] = publication.connections._adf("different run evidence")
    elif mutation == "jira-done": issue["fields"]["status"]["statusCategory"]["key"] = "new"
    elif mutation == "slack-sha": slack["messages"][0]["text"] = slack["messages"][0]["text"].replace("f" * 64, "0" * 64)
    else: slack["messages"][0]["ts"] = "1792334785.000000"
    with pytest.raises(audit.AuditError): audit.provider_audit(environment, record, report)


@pytest.mark.parametrize("corrupt", [False, True])
def test_direct_graph_is_read_only_and_validates_every_check_hash(fixture, monkeypatch, tmp_path, corrupt):
    record, report, environment, *_ = fixture
    archive = tmp_path / "approved.zip"
    archive.write_bytes(b"dependency fixture")
    rows = [[record["id"] + ":" + str(index), check["name"], check["exit_code"], check["log_sha256"]] for index, check in enumerate(report["checks"])]
    if corrupt: rows[0][-1] = "0" * 64
    redis = MagicMock()
    monkeypatch.setitem(sys.modules, "redis", redis)
    redis.Redis.return_value.execute_command.side_effect = [[[], [[record["id"], "f" * 64, record["runner"]["run_url"], "succeeded"]], []], [[], rows, []]]
    if corrupt:
        with pytest.raises(audit.AuditError, match="log hashes"):
            audit.graph_audit(environment, archive, audit.sha(archive.read_bytes()), record, report)
    else:
        result = audit.graph_audit(environment, archive, audit.sha(archive.read_bytes()), record, report)
        assert result["check_nodes"] == 6 and result["configured_graph_tls"] is False
    assert all(call.args[0] == "GRAPH.RO_QUERY" for call in redis.Redis.return_value.execute_command.call_args_list)
    redis.Redis.return_value.close.assert_called_once()
