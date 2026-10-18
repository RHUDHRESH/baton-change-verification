"""Explicit, receipt-backed writes to a configured company Jira/Slack destination.

No account discovery, history ingestion, background posting, or secret persistence.
A durable intent is recorded before a write. Ambiguous writes are never repeated.
"""
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import public_workspace as workspace
from .control import connect as control_connect


class ConnectionError(ValueError):
    """Sanitized configuration or provider failure."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectionError("Provider redirect refused")


def _site(value=None):
    value = os.environ.get("JIRA_SITE_URL", "").strip() if value is None else value
    if not re.fullmatch(r"https://[a-z0-9][a-z0-9-]{0,62}\.atlassian\.net/?", value):
        raise ConnectionError("Configure an exact HTTPS Jira Cloud site")
    return value.rstrip("/")


def _config(target):
    if target == "jira":
        result = {"site": _site(), "email": os.environ.get("JIRA_EMAIL", ""),
                  "token": os.environ.get("JIRA_API_TOKEN", ""),
                  "project": os.environ.get("JIRA_PROJECT_KEY", "")}
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", result["project"]):
            raise ConnectionError("Configure a Jira project key")
        if not result["email"] or not result["token"]:
            raise ConnectionError("Jira credentials are not configured")
        return result
    if target == "slack":
        result = {"token": os.environ.get("SLACK_BOT_TOKEN", ""),
                  "channel": os.environ.get("SLACK_CHANNEL_ID", "")}
        if not result["token"] or not re.fullmatch(r"[CG][A-Z0-9]{5,30}", result["channel"]):
            raise ConnectionError("Configure a Slack bot and channel ID")
        return result
    raise ConnectionError("Target must be jira or slack")


def status():
    """Configuration presence only; does not claim authentication or connectivity."""
    result = {}
    for target in ("jira", "slack"):
        try:
            c = _config(target)
            result[target] = {"configured": True, "verified": False,
                              "destination": c["site"] + "/projects/" + c["project"] if target == "jira" else c["channel"]}
        except ConnectionError as exc:
            result[target] = {"configured": False, "verified": False, "message": str(exc)}
    return result


def _request(target, method, path, config, payload=None):
    """Fixed provider endpoints, no redirects, bounded response and timeout, no retries."""
    if target == "jira":
        if not re.fullmatch(r"/rest/api/3/issue(?:/[A-Z][A-Z0-9_]*-[0-9]+\?fields=summary,description,project)?", path):
            raise ConnectionError("Invalid Jira API operation")
        if method != ("POST" if path == "/rest/api/3/issue" else "GET"):
            raise ConnectionError("Invalid Jira API operation")
        url = _site(config["site"]) + path
        auth = "Basic " + base64.b64encode((config["email"] + ":" + config["token"]).encode()).decode()
    elif target == "slack":
        if not any(path == name or path.startswith(name + "?") for name in
                   ("chat.postMessage", "conversations.history", "chat.getPermalink")):
            raise ConnectionError("Invalid Slack API operation")
        if method != ("POST" if path == "chat.postMessage" else "GET"):
            raise ConnectionError("Invalid Slack API operation")
        url = "https://slack.com/api/" + path
        auth = "Bearer " + config["token"]
    else:
        raise ConnectionError("Target must be jira or slack")
    req = urllib.request.Request(url, method=method,
          data=json.dumps(payload).encode() if payload is not None else None,
          headers={"Authorization": auth, "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            raw = response.read(512_001)
            if len(raw) > 512_000:
                raise ConnectionError("Provider response exceeds limit")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ConnectionError("Invalid provider response")
            if target == "slack" and result.get("ok") is not True:
                raise ConnectionError("Slack rejected the operation; check bot permissions and destination")
            return result
    except ConnectionError:
        raise
    except Exception:
        # Provider bodies, URLs from exceptions and credentials must never escape.
        raise ConnectionError("Provider request failed; inspect the destination before any new action") from None


def _link_graph(port, task, receipt):
    from baton import graph as G
    result = G.connect(port).select_graph(task["graph"]).query(
        "MATCH (t:LocalTask {id:$task}), (w:WorkItem {id:$item}) "
        "MERGE (a:ExternalArtifact {id:$id}) SET a.target=$target,a.url=$url,a.verified_at=$at,a.source_hash=$hash,a.contract_hash=$contract "
        "MERGE (t)-[:PUBLISHED_AS]->(a) MERGE (a)-[:EVIDENCED_BY]->(w) RETURN a.id",
        {"task": task["id"], "item": task["item_id"], "id": receipt["id"],
         "target": receipt["target"], "url": receipt["url"], "at": receipt["verified_at"], "hash": receipt["source_sha256"],
         "contract": receipt["contract_sha256"]})
    if result.result_set != [[receipt["id"]]]:
        raise ConnectionError("Workspace graph did not confirm artifact linkage")


def _adf(text):
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _load_task(data, task_id):
    """Only a stored task bound to a captured public snapshot can authorize a write."""
    if not isinstance(task_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", task_id):
        raise ConnectionError("Select an existing workspace task")
    tasks = workspace.read(data, "tasks.json", [])
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task or not isinstance(task.get("title"), str) or not 1 <= len(task["title"]) <= 240:
        raise ConnectionError("Select an existing task with a title of 1–240 characters")
    snapshot_id = task.get("snapshot_id", "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", snapshot_id):
        raise ConnectionError("Task snapshot identity is invalid")
    snapshot = workspace.read(data, "snapshots/" + snapshot_id + ".json")
    item = next((i for i in (snapshot or {}).get("items", []) if i.get("id") == task.get("item_id")), None)
    sources = {s["id"] for s in (snapshot or {}).get("sources", [])}
    if (not item or snapshot.get("id") != snapshot_id or snapshot.get("graph") != task.get("graph") or
            not item.get("source_ids") or not set(item["source_ids"]).issubset(sources) or
            not re.fullmatch(r"https://github\.com/FalkorDB/(?:FalkorDB|falkordb-py)/(?:issues|pull)/[0-9]+", item.get("url", ""))):
        raise ConnectionError("Only captured public FalkorDB work items can be published")
    return task, item


def _contract(task, item, target, destination):
    # Bind the material effect to the task and source version; free-form text
    # cannot change destination, provider operation, or authority.
    return workspace.sha(json.dumps({"task_id": task["id"], "title": task["title"], "snapshot_id": task["snapshot_id"],
        "graph": task["graph"], "item": item, "target": target, "destination": destination}, sort_keys=True))


def _finish_graph(data, path, port, task, receipt):
    try:
        _link_graph(port, task, receipt)
        receipt["graph_linked"] = True
        receipt["message"] = "Created artifact verified by a separate provider read-back."
    except Exception:
        receipt["graph_linked"] = False
        receipt["message"] = "Provider artifact verified; workspace graph linkage is pending. Repeat checks without creating again."
    workspace.write(data, path, receipt)
    return receipt


def _verify(target, config, receipt, task):
    if target == "jira":
        key = receipt["remote_id"]
        if not re.fullmatch(re.escape(config["project"]) + r"-[0-9]+", key):
            raise ConnectionError("Jira returned an unexpected issue identity")
        result = _request(target, "GET", "/rest/api/3/issue/" + key + "?fields=summary,description,project", config)
        fields = result.get("fields", {})
        if (result.get("key") != key or fields.get("summary") != task["title"] or
                fields.get("project", {}).get("key") != config["project"] or
                fields.get("description") != _adf(receipt["evidence_text"])):
            raise ConnectionError("Jira read-back did not verify the created task and evidence")
        return config["site"] + "/browse/" + key
    ts = receipt["remote_id"]
    if not re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", ts):
        raise ConnectionError("Slack returned an unexpected message identity")
    params = urllib.parse.urlencode({"channel": config["channel"], "oldest": ts, "latest": ts, "inclusive": "true", "limit": 1})
    result = _request(target, "GET", "conversations.history?" + params, config)
    messages = result.get("messages", [])
    if len(messages) != 1 or messages[0].get("ts") != ts or messages[0].get("text") != receipt["message_text"]:
        raise ConnectionError("Slack read-back did not verify the posted task")
    result = _request(target, "GET", "chat.getPermalink?" + urllib.parse.urlencode({"channel": config["channel"], "message_ts": ts}), config)
    url = result.get("permalink", "")
    if not re.fullmatch(r"https://[a-zA-Z0-9-]+\.slack\.com/archives/" + re.escape(config["channel"]) + "/p" + re.escape(ts.replace(".", "")), url):
        raise ConnectionError("Slack returned an invalid permalink")
    return url


def publish_task(data, port, task_id, target):
    """Explicit action. Return persisted sanitized receipt; repeat calls never repeat POST.

    States: pending (write uncertain), remote_created (read-back needed), verified,
    verification_pending (artifact known but verification failed). A repeat only
    retries read-back/graph linkage when the remote identity is already known.
    """
    _config(target)
    _load_task(data, task_id)
    # One destination per task/target; config changes require explicit reconciliation.
    identity = hashlib.sha256((task_id + ":" + target).encode()).hexdigest()
    path = "connections/" + identity + ".json"
    with control_connect(port).lock("publish:" + identity, timeout=100, blocking_timeout=1):
        config = _config(target)
        task, item = _load_task(data, task_id)
        destination = config["site"] + "/" + config["project"] if target == "jira" else config["channel"]
        contract = _contract(task, item, target, destination)
        receipt = workspace.read(data, path)
        if receipt:
            if receipt.get("contract_sha256") != contract:
                raise ConnectionError("Action destination, task or evidence changed; reconcile the existing artifact first")
            if receipt["status"] == "verified":
                return _finish_graph(data, path, port, task, receipt)
            if not receipt.get("remote_id"):
                return receipt  # An interrupted/ambiguous write must never be repeated.
        else:
            text = "Baton task: " + task["title"] + "\nPublic evidence: " + item["url"] + "\nWorkspace task: " + task_id
            receipt = {"id": "artifact-" + identity, "target": target, "task_id": task_id,
                       "title": task["title"], "destination": destination, "status": "pending", "created_at": workspace.now(),
                       "source_url": item["url"], "source_sha256": workspace.sha(json.dumps(item, sort_keys=True)),
                       "contract_sha256": contract, "evidence_text": text, "write_retry_allowed": False,
                       "source_admissibility": {"status": "admissible", "snapshot_id": task["snapshot_id"],
                                                "source_ids": item["source_ids"], "scope": "captured_public_falkordb"},
                       "readback_retry_allowed": False, "graph_linked": False,
                       "message": "Write outcome unknown. Inspect the destination; do not create a replacement automatically."}
            if target == "slack":
                receipt["message_text"] = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            workspace.write(data, path, receipt)  # Must succeed before any network mutation.
            intent = dict(receipt)
            # Recheck the version-bound effect immediately before dispatch.
            current_task, current_item = _load_task(data, task_id)
            if _contract(current_task, current_item, target, destination) != contract or _config(target) != config:
                receipt["status"] = "error"
                receipt["message"] = "Task, evidence or configuration changed before dispatch; no provider write was attempted."
                workspace.write(data, path, receipt)
                return receipt
            try:
                if target == "jira":
                    payload = {"fields": {"project": {"key": config["project"]}, "summary": task["title"],
                        "issuetype": {"name": os.environ.get("JIRA_ISSUE_TYPE", "Task")},
                        "description": _adf(text)}}
                    result = _request(target, "POST", "/rest/api/3/issue", config, payload)
                    remote_id = result.get("key", "")
                    if not isinstance(remote_id, str) or not re.fullmatch(re.escape(config["project"]) + r"-[0-9]+", remote_id):
                        raise ConnectionError("Jira returned an unexpected issue identity")
                else:
                    result = _request(target, "POST", "chat.postMessage", config,
                        {"channel": config["channel"], "text": receipt["message_text"], "mrkdwn": False, "parse": "none", "link_names": False,
                         "unfurl_links": False, "unfurl_media": False})
                    if result.get("channel") != config["channel"]:
                        raise ConnectionError("Slack returned an unexpected channel")
                    remote_id = result.get("ts", "")
                    if not isinstance(remote_id, str) or not re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", remote_id):
                        raise ConnectionError("Slack returned an unexpected message identity")
                receipt["remote_id"] = remote_id
                receipt["status"] = "remote_created"
                receipt["readback_retry_allowed"] = bool(receipt.get("remote_id"))
                workspace.write(data, path, receipt)
            except Exception:
                return intent  # Persisted pending intent prevents duplicate writes after timeout/crash.
        try:
            receipt["url"] = _verify(target, config, receipt, task)
            receipt["status"] = "verified"
            receipt["verified_at"] = workspace.now()
            receipt["message"] = "Created artifact verified by a separate provider read-back."
        except Exception:
            receipt["status"] = "verification_pending"
            receipt["message"] = "Artifact identity received, but read-back is unverified. Repeat checks without creating again."
        workspace.write(data, path, receipt)
        if receipt["status"] == "verified":
            return _finish_graph(data, path, port, task, receipt)
        return receipt
