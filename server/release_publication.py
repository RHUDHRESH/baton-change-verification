"""Run-bound Jira/Slack actions with control-store intents and independent reads."""
import json
import re

from . import company_connections as provider
from . import release_contract as C
from . import public_workspace as public
from .control import connect


def _text(plan, run):
    decision = "blocked" if run["decision"] == "blocked" else "passed for the declared matrix"
    title = ("Investigate verified compatibility failure: " if decision == "blocked" else "Verification record: ") + "FalkorDB-py #212"
    lines = [title, "Verification outcome: " + decision, "Source: " + C.CHANGE_URL,
             "Source commit: " + C.SOURCE_COMMIT, "Plan: " + plan["id"], "Plan hash: " + plan["plan_hash"],
             "App run: " + run["id"], "GitHub run: " + run["runner"]["run_url"]]
    for environment in run["environments"]:
        lines.append("redis-py " + environment["redis_version"] + ": " + str(environment.get("passed", 0)) +
                     " passed, " + str(environment.get("failed", 0)) + " failed, " + str(environment.get("errors", 0)) +
                     " errors, " + str(environment.get("skipped", 0)) + " skipped")
        for check in environment.get("checks", []):
            if check.get("status") in {"failed", "error"}:
                lines.append("Failed obligation: " + check["id"])
    lines += ["Evidence: " + run["evidence"]["url"], "Evidence SHA-256: " + run["evidence"]["sha256"],
              "The graph requires both sync and inherited async checks. Both environments are required.",
              "This verifies an existing merged change; no source repair or upstream merge was performed.",
              "This remediation/report artifact is not marked Done by publication."]
    return title, "\n".join(lines)


def _link(port, plan, run, receipt):
    from . import release_graph
    graph = release_graph._connect(port).select_graph(plan["graph"])
    graph.query("MATCH (r:ReleaseExecution {id:$run}) MERGE (p:ReleasePublication {id:$id}) "
                "SET p.target=$target,p.url=$url,p.contract_sha256=$hash,p.run_id=$run "
                "MERGE (r)-[:PUBLISHED_AS]->(p)",
                {"run": run["id"], "id": receipt["id"], "target": receipt["target"],
                 "url": receipt["url"], "hash": receipt["contract_sha256"]})
    rows = graph.ro_query("MATCH (r:ReleaseExecution {id:$run})-[:PUBLISHED_AS]->(p:ReleasePublication {id:$id}) "
                          "WHERE p.contract_sha256=$hash AND p.url=$url RETURN p.id",
                          {"run": run["id"], "id": receipt["id"], "hash": receipt["contract_sha256"], "url": receipt["url"]}).result_set
    return rows == [[receipt["id"]]]


def publish(data, port, plan, run, target):
    from . import release_gate, release_graph
    release_gate.require(target in {"jira", "slack"}, "Unknown publication target")
    stored = release_gate._read(port, "run", run["id"])
    release_gate.require(stored.get("evidence_status") == "verified" and stored.get("graph_receipt", {}).get("verified") is True and
                         stored.get("plan_id") == plan["id"] and stored.get("plan_hash") == plan["plan_hash"] and
                         stored.get("evidence") == run.get("evidence") and stored.get("decision") == run.get("decision") and
                         run.get("decision") in {"blocked", "passed"}, "Publication requires the stored verified run and graph certificate")
    release_gate._current(data, port, plan)
    certificate = release_graph.verify_result(data, port, plan, stored)
    release_gate.require(isinstance(certificate, dict) and certificate.get("verified") is True and
                         certificate == stored["graph_receipt"],
                         "Current execution graph certificate does not match the verified release evidence")
    config = provider._config(target)
    title, text = _text(plan, stored)
    destination = config["site"] + "/" + config["project"] if target == "jira" else config["channel"]
    material = {"run_id": run["id"], "plan_id": plan["id"], "plan_hash": plan["plan_hash"], "target": target,
                "destination": destination, "cloud_id": config.get("cloud_id"), "evidence": run["evidence"],
                "title": title, "text": text, "decision": run["decision"]}
    contract = C.sha(C.encode(material))
    identity = C.sha(run["id"] + ":" + target)
    key = "release:publication:" + identity
    control = connect(port)
    with control.lock(key, timeout=110, blocking_timeout=2):
        raw = control.get(key)
        receipt = json.loads(raw) if raw else None
        if receipt:
            release_gate.require(receipt.get("contract_sha256") == contract, "Publication material changed; reconcile its existing artifact")
            if receipt.get("status") == "verified":
                try:
                    receipt["graph_linked"] = _link(port, plan, stored, receipt)
                except Exception:
                    receipt["graph_linked"] = False
                control.set(key, C.encode(receipt))
                return receipt
            if not receipt.get("remote_id"):
                return receipt
        else:
            receipt = {"id": "publication-" + identity, "target": target, "run_id": run["id"], "plan_id": plan["id"],
                       "title": title, "destination": destination, "contract_sha256": contract,
                       "evidence_text": text, "source_url": C.CHANGE_URL, "created_at": public.now(),
                       "status": "pending", "write_retry_allowed": False, "readback_retry_allowed": False,
                       "message": "Write outcome unknown; inspect the destination before reconciliation"}
            if target == "slack":
                receipt["message_text"] = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            release_gate.require(control.set(key, C.encode(receipt)), "Durable publication intent was not persisted")
            # No network write occurs before its durable intent. Changed credentials/destination do not authorize a new effect.
            release_gate.require(provider._config(target) == config, "Provider configuration changed before dispatch")
            try:
                if target == "jira":
                    result = provider._request(target, "POST", "/rest/api/3/issue", config,
                        {"fields": {"project": {"key": config["project"]}, "summary": title,
                                    "issuetype": {"name": "Task"}, "description": provider._adf(text)}})
                    remote_id = result.get("key", "")
                    release_gate.require(isinstance(remote_id, str) and re.fullmatch(re.escape(config["project"]) + r"-[0-9]+", remote_id),
                                         "Provider returned an unexpected issue identity")
                else:
                    result = provider._request(target, "POST", "chat.postMessage", config,
                        {"channel": config["channel"], "text": receipt["message_text"], "mrkdwn": False, "parse": "none",
                         "link_names": False, "unfurl_links": False, "unfurl_media": False})
                    remote_id = result.get("ts", "")
                    release_gate.require(result.get("channel") == config["channel"] and isinstance(remote_id, str) and
                                         re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", remote_id), "Provider returned an unexpected message identity")
                receipt.update(remote_id=remote_id, status="remote_created", readback_retry_allowed=True)
                release_gate.require(control.set(key, C.encode(receipt)), "Created identity could not be persisted; inspect the destination")
            except Exception as error:
                if isinstance(error, provider.ProviderFailure):
                    receipt["diagnostic"] = error.diagnostic
                    if error.rejected:
                        receipt["status"] = "rejected"
                control.set(key, C.encode(receipt))
                return receipt
        try:
            receipt["url"] = provider._verify(target, config, receipt, {"title": title})
            receipt.update(status="verified", verified_at=public.now(),
                           message="Publication verified by a separate provider read-back; this does not mean the checks passed")
        except Exception:
            receipt.update(status="verification_pending", message="Known artifact could not be read back; repeat reads only")
        if receipt.get("status") == "verified":
            try:
                receipt["graph_linked"] = _link(port, plan, stored, receipt)
            except Exception:
                receipt["graph_linked"] = False
        release_gate.require(control.set(key, C.encode(receipt)), "Publication read-back could not be persisted")
        return receipt
