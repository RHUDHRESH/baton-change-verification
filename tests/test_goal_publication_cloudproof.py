"""GET-only provider verifier contracts; fake responses are not live proof."""
import copy
import json
from pathlib import Path
import sys
import urllib.parse

import pytest

from test_goal_actions import record
from server import goal_actions as A

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import verify_goal_publication_cloud as V


@pytest.fixture
def publication(record, monkeypatch):
    settings = {"JIRA_SITE_URL": "https://example.atlassian.net", "JIRA_PROJECT_KEY": "KAN", "JIRA_CLOUD_ID": "",
                "JIRA_EMAIL": "test@example.test", "JIRA_API_TOKEN": "test-only-api-key", "SLACK_CHANNEL_ID": "C123456", "SLACK_BOT_TOKEN": "test-only-bot-key"}
    step = record["proposal"]["steps"][0]
    title, text = A._text(record, step)
    receipts = {}
    for target in ("jira", "slack"):
        destination = settings["JIRA_SITE_URL"] + "/KAN" if target == "jira" else settings["SLACK_CHANNEL_ID"]
        material = {"goal_id": record["id"], "plan_hash": record["proposal"]["hash"], "step_id": step["id"], "target": target,
                    "destination": destination, "cloud_id": "" if target == "jira" else None, "title": title, "text": text}
        receipt = {"id": "goal-publication-" + V.sha(V.encode([record["id"], record["proposal"]["hash"], step["id"], target])), "goal_id": record["id"], "step_id": step["id"], "plan_hash": record["proposal"]["hash"], "target": target,
                   "destination": destination, "title": title, "evidence_text": text, "contract_sha256": V.sha(V.encode(material)), "status": "verified", "read_back_verified": True, "graph_linked": True,
                   "remote_id": "KAN-100" if target == "jira" else "1792368000.123456", "url": "https://example.atlassian.net/browse/KAN-100" if target == "jira" else "https://example.slack.com/archives/C123456/p1792368000123456"}
        if target == "slack": receipt["message_text"] = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        receipts[target] = receipt
    action = {"id": "test-action", "kind": "publish_task", "step_id": step["id"], "plan_hash": record["proposal"]["hash"], "status": "verified", "read_back_verified": True, "result": {"publications": receipts, "work_completion_claimed": False}}
    record["actions"] = [action]
    responses = {"jira": {"key": "KAN-100", "fields": {"project": {"key": "KAN"}, "summary": title, "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}, "issuetype": {"name": "Task"}, "status": {"name": "To Do", "statusCategory": {"key": "new"}}, "resolution": None}},
                 "slack": {"ok": True, "messages": [{"ts": receipts["slack"]["remote_id"], "text": receipts["slack"]["message_text"]}]},
                 "permalink": {"ok": True, "permalink": receipts["slack"]["url"]}}
    gets = []
    def get(url, authorization=None):
        gets.append(url)
        assert url.startswith((settings["JIRA_SITE_URL"], "https://slack.com/api/"))
        if "/rest/api/3/issue/" in url: key = "jira"
        elif "conversations.history" in url: key = "slack"
        elif "chat.getPermalink" in url: key = "permalink"
        else: pytest.fail("Unexpected provider request")
        assert authorization
        return json.dumps(responses[key]).encode()
    monkeypatch.setattr(V, "get", get)
    return record, step, action, settings, responses, gets


def test_exact_model_task_provider_reads_and_open_state(publication):
    record, step, action, settings, _, gets = publication
    assert V.expected_text(record, step) == A._text(record, step)
    assert V.selected_action(record) == (step, action)
    result = V.provider_audit(settings, record, step, action)
    assert len(gets) == 3 and result["jira"]["status_category"] == "new"
    assert result["slack"]["exact_literal_message"] and result["work_completion_claimed"] is False
    assert result["audit_sent_messages"] is result["audit_sent_transitions"] is False


@pytest.mark.parametrize("fault", ["title", "description", "type", "done", "resolution", "slack_text", "slack_ts", "permalink", "contract", "goal_id", "missing_target"])
def test_independent_provider_audit_rejects_drift(publication, fault):
    record, step, action, settings, responses, gets = publication
    if fault == "title": responses["jira"]["fields"]["summary"] += " changed"
    elif fault == "description": responses["jira"]["fields"]["description"] = {}
    elif fault == "type": responses["jira"]["fields"]["issuetype"]["name"] = "Story"
    elif fault == "done": responses["jira"]["fields"]["status"]["statusCategory"]["key"] = "done"
    elif fault == "resolution": responses["jira"]["fields"]["resolution"] = {"name": "Done"}
    elif fault == "slack_text": responses["slack"]["messages"][0]["text"] += " changed"
    elif fault == "slack_ts": responses["slack"]["messages"][0]["ts"] = "1792368000.999999"
    elif fault == "permalink": responses["permalink"]["permalink"] = "https://attacker.invalid"
    elif fault == "contract": action["result"]["publications"]["jira"]["contract_sha256"] = "a" * 64
    elif fault == "goal_id": action["result"]["publications"]["jira"]["goal_id"] = "f" * 32
    else: action["result"]["publications"].pop("slack")
    with pytest.raises(V.AuditError): V.provider_audit(settings, record, step, action)


def test_native_publication_links_checked_without_mutating_graph(publication):
    record, step, action, _, _, _ = publication
    def read(state, text, params=None):
        assert text.startswith("MATCH ") and "HAS_ACTION" in text and "EXECUTED_AS" in text
        assert params["goal"] == record["id"] and params["step"].endswith(":" + step["id"])
        return [[r["id"], V.encode({k: v for k, v in r.items() if k != "graph_linked"}), r["status"], r["url"]] for r in action["result"]["publications"].values()]
    assert V.graph_links(read, "state", record, step, action)["native_publication_receipts"] == 2
    with pytest.raises(V.AuditError): V.graph_links(lambda *a: [], "state", record, step, action)


@pytest.mark.parametrize("fault", ["unapproved", "unverified", "work_done", "old_plan"])
def test_cannot_audit_unapproved_or_misbound_publication(publication, fault):
    record, _, action, _, _, _ = publication
    if fault == "unapproved": record["approved_actions"] = []
    if fault == "unverified": action["read_back_verified"] = False
    if fault == "work_done": action["result"]["work_completion_claimed"] = True
    if fault == "old_plan": action["plan_hash"] = "b" * 64
    with pytest.raises(V.AuditError): V.selected_action(record)
