"""GET-only independent proof of an actual goal's published Jira/Slack task.

Upload beside verify_goal_cloud.py and verify_release_cloud.py. No model call,
message send, issue transition, graph mutation, or automatic write retry occurs.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import urllib.parse

import verify_goal_cloud as goal
import verify_release_cloud as release
from verify_release_cloud import AuditError, encode, get, require, sha


def expected_text(record, step):
    sources = {e["source_id"]: e for e in record.get("evidence", []) if e.get("kind") == "source"}
    args = step["args"]
    require(all(identity in sources for identity in args["source_ids"]), "Publication source was not actually inspected")
    lines = [args["description"], "", "Baton AI-authored work proposal", "Goal: " + record["goal"],
             "Goal run: " + record["id"], "Plan hash: " + record["proposal"]["hash"], "Step: " + step["id"],
             "Success criteria: " + "; ".join(record["proposal"]["success_criteria"]), "Evidence inspected by the agent:"]
    for identity in args["source_ids"]:
        source = sources[identity]
        lines.append(identity + " | " + str(source.get("url") or "captured graph evidence") + " | Captured evidence record SHA-256 " + source["sha256"])
    lines += ["Goal evidence: " + goal.ORIGIN + "/api/public/goals/" + record["id"],
              "Creating this task/report does not complete the proposed work or establish an upstream fix.",
              "Public contribution evidence does not establish employment or internal ownership."]
    return args["title"], "\n".join(lines)


def selected_action(record, step_id=None):
    actions = [a for a in record.get("actions", []) if a.get("kind") == "publish_task" and a.get("plan_hash") == record["proposal"]["hash"] and (step_id is None or a.get("step_id") == step_id)]
    require(len(actions) == 1, "Select exactly one current-plan publish_task action")
    action = actions[0]
    require(action.get("status") == "verified" and action.get("read_back_verified") is True, "Publication action is not independently read-back verified")
    steps = [s for s in record["proposal"]["steps"] if s["id"] == action["step_id"] and s["tool_name"] == "publish_task"]
    require(len(steps) == 1 and "publish_task" in record.get("approved_actions", []), "Publication is outside the approved current model plan")
    require(action.get("result", {}).get("work_completion_claimed") is False, "Creating work must not claim its completion")
    return steps[0], action


def provider_audit(settings, record, step, action):
    site, project, channel = settings.get("JIRA_SITE_URL", "").rstrip("/"), settings.get("JIRA_PROJECT_KEY", ""), settings.get("SLACK_CHANNEL_ID", "")
    cloud_id = settings.get("JIRA_CLOUD_ID", "")
    require(re.fullmatch(r"https://[a-z0-9][a-z0-9-]{0,62}\.atlassian\.net", site) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", project) and re.fullmatch(r"[CG][A-Z0-9]{5,30}", channel), "Configured provider destination is invalid")
    require(not cloud_id or re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", cloud_id), "Configured Jira cloud identity is invalid")
    require(all(settings.get(key) for key in ("JIRA_EMAIL", "JIRA_API_TOKEN", "SLACK_BOT_TOKEN")), "Provider credentials are unavailable")
    title, text = expected_text(record, step)
    receipts = action.get("result", {}).get("publications", {})
    require(set(receipts) == {"jira", "slack"}, "Exactly two publication receipts are required")
    for target, receipt in receipts.items():
        destination = site + "/" + project if target == "jira" else channel
        material = {"goal_id": record["id"], "plan_hash": record["proposal"]["hash"], "step_id": step["id"], "target": target,
                    "destination": destination, "cloud_id": cloud_id if target == "jira" else None, "title": title, "text": text}
        expected_id = "goal-publication-" + sha(encode([record["id"], record["proposal"]["hash"], step["id"], target]))
        require(receipt.get("id") == expected_id and receipt.get("target") == target and receipt.get("goal_id") == record["id"] and receipt.get("step_id") == step["id"] and receipt.get("plan_hash") == record["proposal"]["hash"] and
                receipt.get("status") == "verified" and receipt.get("read_back_verified") is True and receipt.get("graph_linked") is True and receipt.get("destination") == destination and receipt.get("title") == title and receipt.get("evidence_text") == text and receipt.get("contract_sha256") == sha(encode(material)), "Publication receipt differs from independently reconstructed model work/source contract")
    jira, slack = receipts["jira"], receipts["slack"]
    key, ts = jira.get("remote_id", ""), slack.get("remote_id", "")
    require(re.fullmatch(re.escape(project) + r"-[0-9]+", key) and re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", ts), "Provider artifact identity is invalid")
    auth = "Basic " + base64.b64encode((settings["JIRA_EMAIL"] + ":" + settings["JIRA_API_TOKEN"]).encode()).decode()
    base = "https://api.atlassian.com/ex/jira/" + cloud_id if cloud_id else site
    issue = json.loads(get(base + "/rest/api/3/issue/" + key + "?fields=summary,description,project,issuetype,status,resolution", auth))
    fields = issue.get("fields", {})
    adf = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}
    require(issue.get("key") == key and fields.get("summary") == title and fields.get("description") == adf and fields.get("project", {}).get("key") == project and fields.get("issuetype", {}).get("name") == "Task" and jira.get("url") == site + "/browse/" + key, "Independent Jira GET differs in task identity/type/content")
    status = fields.get("status", {})
    require(status.get("statusCategory", {}).get("key") == "new" and fields.get("resolution") is None and isinstance(status.get("name"), str) and 1 <= len(status["name"]) <= 80, "Jira task is not in an unresolved new/open state")
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    require(slack.get("message_text") == escaped, "Stored Slack text differs from literal publication content")
    bearer = "Bearer " + settings["SLACK_BOT_TOKEN"]
    history = "https://slack.com/api/conversations.history?" + urllib.parse.urlencode({"channel": channel, "oldest": ts, "latest": ts, "inclusive": "true", "limit": 1})
    messages = json.loads(get(history, bearer))
    require(messages.get("ok") is True and len(messages.get("messages", [])) == 1 and messages["messages"][0].get("ts") == ts and messages["messages"][0].get("text") == escaped, "Independent Slack GET differs in exact message content")
    permalink = json.loads(get("https://slack.com/api/chat.getPermalink?" + urllib.parse.urlencode({"channel": channel, "message_ts": ts}), bearer))
    require(permalink.get("ok") is True and permalink.get("permalink") == slack.get("url") and re.fullmatch(r"https://[a-zA-Z0-9-]+\.slack\.com/archives/" + re.escape(channel) + "/p" + re.escape(ts.replace(".", "")), permalink.get("permalink", "")), "Independent Slack permalink differs")
    return {"provider_get_performed": True, "jira": {"remote_id": key, "exact_model_title": True, "exact_model_description_and_evidence": True,
                "issue_type": "Task", "status_category": "new", "status_name": status["name"], "resolution": None},
            "slack": {"remote_id": ts, "exact_literal_message": True, "exact_permalink": True}, "publication_text_sha256": sha(text),
            "audit_sent_messages": False, "audit_sent_transitions": False, "work_completion_claimed": False}


def graph_links(read, state, record, step, action):
    receipts = action["result"]["publications"]
    step_identity = record["id"] + ":" + record["proposal"]["hash"] + ":" + step["id"]
    rows = read(state, "MATCH (g:Goal {id:$goal})-[:HAS_ACTION]->(a:GoalActionReceipt)<-[:EXECUTED_AS]-(s:GoalStep {id:$step}) RETURN a.id,a.json,a.status,a.url LIMIT 10", {"goal": record["id"], "step": step_identity})
    expected = {r["id"]: r for r in receipts.values()}
    require(len(rows) == 2 and {row[0] for row in rows} == set(expected), "Native publication action links differ")
    for identity, raw, status, url in rows:
        actual = json.loads(raw)
        wanted = expected[identity]
        # Publisher records the link before adding its graph_linked cache flag.
        require({k: v for k, v in actual.items() if k != "graph_linked"} == {k: v for k, v in wanted.items() if k != "graph_linked"} and status == "verified" and url == wanted["url"], "Native publication receipt material differs")
    return {"native_publication_receipts": 2, "goal_HAS_ACTION_and_step_EXECUTED_AS": True}


def verify(identity, archive, archive_sha, commit, step_id=None):
    native = goal.verify(identity, archive, archive_sha, commit)
    record = json.loads(get(goal.ORIGIN + "/api/public/goals/" + identity))
    step, action = selected_action(record, step_id)
    settings, _ = goal.environment()
    providers = release.lambda_environment()
    connection = None
    try:
        direct = provider_audit(providers, record, step, action)
        connection = goal.graph_connection(settings, archive, archive_sha)
        state = settings.get("BATON_CLOUD_STATE_GRAPH") or "baton_goal_memory"
        read = lambda graph, text, params=None: goal.query(connection, graph, text, params)
        links = graph_links(read, state, record, step, action)
        return {"status": "verified_open_task", "read_only": True, "goal_id": identity, "step_id": step["id"], "plan_hash": record["proposal"]["hash"],
                "source_commit": commit, "native_goal_proof": native, "providers": direct, "graph": links,
                "limits": ["This creates source-backed proposed work, not a completed repair or upstream merge.", "Open/unresolved Jira state was observed at audit time; no historical workflow-state claim is made."]}
    finally:
        if connection is not None: connection.close()
        settings.clear()
        providers.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal-id", required=True)
    parser.add_argument("--step-id")
    parser.add_argument("--lambda-archive", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = verify(args.goal_id, args.lambda_archive, args.archive_sha256, args.source_commit, args.step_id)
    except AuditError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True, "error": "Read-only provider audit stopped; private configuration and provider bodies were not printed"}
    encoded = encode(result)
    if args.output: Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "verified_open_task" else 1


if __name__ == "__main__":
    raise SystemExit(main())
