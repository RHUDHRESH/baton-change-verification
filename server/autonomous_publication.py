"""Finalize a server-verified workflow on its already connected Jira/Slack artifacts.

No runner result is accepted from an API caller. Durable control-store records
bind the operation; pending provider writes are reconciled, never blindly retried.
"""
import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import company_connections as connections
from . import public_workspace as workspace
from .control import connect as control_connect

TASK = "task-agent-c108922c16a39ceaa82623d5748c4df0"
ITEM = "FalkorDB/FalkorDB#3246"
SOURCE = "https://github.com/FalkorDB/FalkorDB/issues/3246"
SITE = "https://rhudhresh3697.atlassian.net"
ISSUE = "KAN-2"
CHANNEL = "C0CA7B1BYTT"
TS = "1792334785.098199"
SLACK_URL = "https://raptorflow.slack.com/archives/" + CHANNEL + "/p" + TS.replace(".", "")
HISTORY = "conversations.history?" + urllib.parse.urlencode({"channel": CHANNEL, "oldest": TS, "latest": TS, "inclusive": "true", "limit": 1})


class PublicationError(ValueError):
    """Static application-owned diagnostics, safe to expose."""


def require(condition, message):
    if not condition:
        raise PublicationError(message)


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _save(control, key, value):
    require(control.set(key, json.dumps(value, sort_keys=True)), "Publication receipt could not be persisted")


def _read(control, key):
    value = control.get(key)
    return json.loads(value) if value else None


def _run(control, run_id):
    require(isinstance(run_id, str) and re.fullmatch(r"[a-f0-9]{32}", run_id), "Select a server-owned workflow run")
    run = _read(control, "autonomous:run:" + run_id)
    require(isinstance(run, dict) and run.get("id") == run_id and run.get("task_id") == TASK and
            run.get("status") in ("succeeded", "failed"), "Workflow is not a completed run for the connected task")
    runner, evidence = run.get("runner", {}), run.get("evidence", {})
    identity = str(runner.get("run_id", ""))
    require(re.fullmatch(r"[0-9]{1,20}", identity) and runner.get("provider") == "GitHub Actions" and runner.get("verified") is True and
            runner.get("run_url") == "https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/" + identity and
            re.fullmatch(r"[a-f0-9]{40}", runner.get("source_commit", "")) and
            re.fullmatch(r"sha256:[a-f0-9]{64}", runner.get("image_digest", "")), "Workflow runner provenance is not verified")
    require(evidence.get("url") == "https://baton-workspace.vercel.app/api/public/workflows/" + run_id + "/evidence" and
            re.fullmatch(r"[a-f0-9]{64}", evidence.get("sha256", "")) and
            run.get("verification", {}).get("read_back_verified") is True, "Workflow evidence retrieval is not verified")
    checks = run.get("checks", [])
    require(isinstance(checks, list) and len(checks) <= 40 and all(isinstance(c, dict) for c in checks) and
            len({c.get("name") for c in checks}) == len(checks), "Workflow check inventory is invalid")
    for check in checks:
        require(isinstance(check, dict) and isinstance(check.get("name"), str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", check["name"]) and
                check.get("status") in ("passed", "failed") and type(check.get("exit_code")) is int and
                -255 <= check["exit_code"] <= 255 and type(check.get("test_count")) is int and check["test_count"] >= 0 and
                (check["status"] == "passed") == (check["exit_code"] == 0), "Workflow check outcome is malformed")
    if run["status"] == "succeeded":
        require(runner.get("conclusion") == "success" and checks and all(c["status"] == "passed" for c in checks) and
                sum(c["test_count"] for c in checks) > 0, "Successful publication requires verified passing executed tests")
    else:
        require(runner.get("conclusion") in ("failure", "cancelled", "timed_out"),
                "Failure publication requires a verified runner failure")
    return run


def _binding(data):
    task, item = connections._load_task(data, TASK)
    require(task.get("item_id") == ITEM and item.get("url") == SOURCE, "Connected task does not track the approved public issue")
    configs = {target: connections._config(target) for target in ("jira", "slack")}
    require(configs["jira"]["site"] == SITE and configs["jira"]["project"] == "KAN" and configs["slack"]["channel"] == CHANNEL,
            "Configured provider destination differs from the connected artifacts")
    for target, remote in (("jira", ISSUE), ("slack", TS)):
        identity = hashlib.sha256((TASK + ":" + target).encode()).hexdigest()
        receipt = workspace.read(data, "connections/" + identity + ".json")
        require(receipt and receipt.get("task_id") == TASK and receipt.get("target") == target and
                receipt.get("status") == "verified" and receipt.get("remote_id") == remote,
                "Existing connected provider artifact has no verified publication receipt")
    return configs


def _call(target, method, path, config, payload=None):
    if target == "jira":
        allowed = (method == "GET" and re.fullmatch(r"/rest/api/3/issue/KAN-2(?:\?fields=description,status,project|/comment\?startAt=[0-9]{1,3}&maxResults=75|/comment/[0-9]{1,20}|/transitions)", path)) or (
            method == "POST" and path in ("/rest/api/3/issue/KAN-2/comment", "/rest/api/3/issue/KAN-2/transitions"))
        require(allowed, "Jira operation is outside the connected artifact scope")
        url = connections._jira_api_base(config) + path
        auth = "Basic " + base64.b64encode((config["email"] + ":" + config["token"]).encode()).decode()
    else:
        require(target == "slack" and ((method == "GET" and path == HISTORY) or (method == "POST" and path == "chat.update" and
                payload.get("channel") == CHANNEL and payload.get("ts") == TS)), "Slack operation is outside the connected artifact scope")
        url, auth = "https://slack.com/api/" + path, "Bearer " + config["token"]
    request = urllib.request.Request(url, method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(connections.NoRedirect()).open(request, timeout=12) as response:
            raw = response.read(512_001)
            require(len(raw) <= 512_000, "Provider response exceeds the verification bound")
            result = json.loads(raw) if raw else {}
            require(isinstance(result, dict), "Provider response is malformed")
            if target == "slack" and result.get("ok") is not True:
                raise connections._slack_failure(result.get("error"))
            return result
    except urllib.error.HTTPError as error:
        failure = connections._http_failure(target, error)
        error.close()
        raise failure from None
    except (PublicationError, connections.ProviderFailure):
        raise
    except Exception:
        raise PublicationError("Provider request outcome is unverified; no automatic write retry is allowed") from None


def _flatten(value):
    if isinstance(value, dict):
        return value.get("text", "") + "".join(_flatten(item) for item in value.get("content", []))
    return ""


def _issue(config):
    issue = _call("jira", "GET", "/rest/api/3/issue/KAN-2?fields=description,status,project", config)
    fields = issue.get("fields", {})
    require(issue.get("key") == ISSUE and fields.get("project", {}).get("key") == "KAN" and TASK in _flatten(fields.get("description")) and
            SOURCE in _flatten(fields.get("description")), "Jira readback does not match the connected task and source")
    return issue


def _slack(config):
    messages = _call("slack", "GET", HISTORY, config).get("messages", [])
    require(isinstance(messages, list) and len(messages) == 1 and messages[0].get("ts") == TS and messages[0].get("bot_id") and
            TASK in messages[0].get("text", "") and SOURCE in messages[0].get("text", ""), "Slack readback does not match the original bot task message")
    return messages[0]["text"]


def _text(run):
    marker = "[Baton autonomous run " + run["id"] + "]"
    lines = [marker, "Workspace KAN-2 cloud verification " + ("succeeded." if run["status"] == "succeeded" else "failed; review the evidence before claiming completion."),
        "Executor: GitHub Actions; verified runner conclusion: " + run["runner"]["conclusion"],
        "Runner: " + run["runner"]["run_url"], "Source commit: " + run["runner"]["source_commit"],
        "Pinned image: " + run["runner"]["image_digest"], "Evidence: " + run["evidence"]["url"],
        "Evidence SHA-256: " + run["evidence"]["sha256"], "Executed tests: " + str(sum(c["test_count"] for c in run["checks"])),
        "This reports the isolated workspace run; it does not claim an upstream issue resolution or merge."]
    for check in run["checks"]:
        lines.append(check["name"] + ": " + check["status"] + "; exit=" + str(check["exit_code"]) + "; tests=" + str(check["test_count"]))
    text = "\n".join(lines)
    require(len(text) <= 12_000, "Workflow publication exceeds its size bound")
    return marker, text


def _jira(run, config, state, save):
    marker, text = _text(run)
    issue = _issue(config)
    found = []
    start = 0
    for _ in range(3):
        page = _call("jira", "GET", "/rest/api/3/issue/KAN-2/comment?startAt=" + str(start) + "&maxResults=75", config)
        rows = page.get("comments", [])
        require(isinstance(rows, list) and len(rows) <= 75 and type(page.get("total")) is int, "Jira comment inventory is malformed")
        found += [row for row in rows if marker in _flatten(row.get("body"))]
        start += len(rows)
        if start >= page["total"]:
            break
        require(rows, "Jira comment inventory did not advance")
    else:
        raise PublicationError("Jira comment reconciliation exceeds its bound")
    require(len(found) <= 1, "Duplicate workflow comments require reconciliation")
    if found:
        comment_id = found[0].get("id")
    else:
        require("comment" not in state, "Prior Jira comment write is uncertain; no duplicate will be sent")
        state["comment"] = {"status": "pending"}
        save()
        result = _call("jira", "POST", "/rest/api/3/issue/KAN-2/comment", config, {"body": connections._adf(text)})
        comment_id = result.get("id")
    require(isinstance(comment_id, str) and re.fullmatch(r"[0-9]{1,20}", comment_id), "Jira comment identity is unverified")
    comment = _call("jira", "GET", "/rest/api/3/issue/KAN-2/comment/" + comment_id, config)
    require(comment.get("id") == comment_id and comment.get("body") == connections._adf(text), "Jira workflow comment failed exact readback")
    state["comment"] = {"status": "verified", "id": comment_id}
    save()
    if run["status"] == "succeeded":
        is_done = lambda value: value.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key") == "done"
        if not is_done(issue):
            require("transition" not in state, "Prior Jira Done transition is uncertain; it will not be repeated")
            transitions = _call("jira", "GET", "/rest/api/3/issue/KAN-2/transitions", config).get("transitions", [])
            candidates = [row for row in transitions if row.get("to", {}).get("statusCategory", {}).get("key") == "done"]
            require(len(candidates) == 1 and re.fullmatch(r"[0-9]{1,20}", candidates[0].get("id", "")), "Jira has no unique Done transition")
            state["transition"] = {"status": "pending"}
            save()
            _call("jira", "POST", "/rest/api/3/issue/KAN-2/transitions", config, {"transition": {"id": candidates[0]["id"]}})
        require(is_done(_issue(config)), "Jira Done transition failed independent readback")
        state["transition"] = {"status": "verified"}
    state.update(status="verified", verified_at=workspace.now(), url=SITE + "/browse/KAN-2")
    state.pop("diagnostic", None)
    save()


def _update_slack(run, config, state, save, control):
    original = _slack(config)
    shared_key = "autonomous:publication:slack-original"
    shared = _read(control, shared_key)
    marker, full = _text(run)
    block = "\n".join(full.splitlines()[:9]) + "\nNo upstream fix or merge is claimed."
    if "wanted_text" in state:
        desired = state["wanted_text"]
        base = state["base_text"]
    else:
        if shared:
            require(hashlib.sha256(original.encode()).hexdigest() == shared.get("text_sha256"), "Slack changed outside the last verified workflow update")
            base = shared["base_text"]
        else:
            require("[Baton autonomous run " not in original, "Existing autonomous Slack block has no durable ownership receipt")
            base = original
        desired = base + "\n\n" + block
        require(len(desired) <= 12_000, "Slack workflow update exceeds its size bound")
    if original != desired:
        require("write" not in state, "Prior Slack update is uncertain; no second update will be sent")
        state.update(write="pending", wanted_text=desired, base_text=base)
        save()
        result = _call("slack", "POST", "chat.update", config, {"channel": CHANNEL, "ts": TS, "text": desired,
            "mrkdwn": False, "parse": "none", "link_names": False, "unfurl_links": False, "unfurl_media": False})
        require(result.get("channel") == CHANNEL and result.get("ts") == TS, "Slack update acknowledgement has an unexpected identity")
    require(_slack(config) == desired, "Slack workflow update failed exact independent readback")
    _save(control, shared_key, {"base_text": base, "text_sha256": hashlib.sha256(desired.encode()).hexdigest(), "run_id": run["id"]})
    state.update(status="verified", verified_at=workspace.now(), url=SLACK_URL)
    state.pop("diagnostic", None)
    save()


def finalize_run(data, port, run_id):
    """Called by the app after runner verification; returns sanitized provider receipts.

    Repeat calls reconcile reads only after any durable write intent. This function
    does not create tasks, run code, publish upstream, or change workspace status.
    """
    control = control_connect(port)
    with control.lock("autonomous:publication:connected-destinations", timeout=300, blocking_timeout=1):
        run = _run(control, run_id)
        configs = _binding(data)
        material = {key: run[key] for key in ("id", "task_id", "status", "runner", "evidence", "checks", "verification")}
        contract = sha(material)
        key = "autonomous:publication:" + run_id
        state = _read(control, key) or {"run_id": run_id, "contract_sha256": contract, "providers": {"jira": {}, "slack": {}}}
        require(state.get("contract_sha256") == contract, "Workflow evidence changed after publication began")
        save = lambda: _save(control, key, state)
        save()
        for target in ("jira", "slack"):
            receipt = state["providers"][target]
            try:
                # Re-read server-owned outcome and current destination immediately before dispatch.
                current = _run(control, run_id)
                require(sha({key: current[key] for key in material}) == contract, "Workflow changed before provider dispatch")
                require(connections._config(target) == configs[target], "Provider configuration changed before dispatch")
                if target == "jira":
                    _jira(run, configs[target], receipt, save)
                else:
                    _update_slack(run, configs[target], receipt, save, control)
            except Exception as error:
                if isinstance(error, connections.ProviderFailure):
                    receipt["status"] = "rejected" if error.rejected else "pending"
                    receipt["diagnostic"] = error.diagnostic
                elif receipt.get("status") != "rejected":
                    receipt["status"] = "pending"
                    receipt["diagnostic"] = {"code": "publication_unconfirmed", "message": str(error) if isinstance(error, PublicationError)
                        else "Provider finalization was not confirmed; inspect the durable receipt before reconciliation"}
                save()
        statuses = [receipt.get("status") for receipt in state["providers"].values()]
        return {"run_id": run_id, "outcome": run["status"], "status": "verified" if statuses == ["verified", "verified"] else "pending",
            "providers": {target: {key: value for key, value in receipt.items() if key in ("status", "url", "verified_at", "diagnostic", "comment", "transition")}
                for target, receipt in state["providers"].items()}}
