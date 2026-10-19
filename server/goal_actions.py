"""Execute a model-selected, graph-ready approved effect and preserve readbacks."""
import copy
import hmac
import json
import re
import secrets

from . import company_connections as provider
from . import goal_contract as C
from . import goal_graph as graph
from . import public_workspace as public
from .control import connect


def _current(data, port, record, step):
    stored = graph.get_goal(data, port, record["id"])
    C.require(stored and stored.get("proposal") and hmac.compare_digest(stored["proposal"]["hash"], record["proposal"]["hash"]), "The stored goal plan changed")
    sealed_evidence = stored.get("plan_evidence", stored["evidence"])
    binding = graph.evidence_binding(data, port, sealed_evidence)
    C.require(binding == stored.get("evidence_binding"), "Goal evidence changed; replan before acting")
    proposal = C.validate_proposal(stored["proposal"], stored["goal"], sealed_evidence, graph.TOOLS + C.EFFECTS, binding)
    C.require(any(s == step for s in proposal["steps"]), "The selected effect is outside the sealed model plan")
    C.require(step["id"] in graph.ready_steps(data, port, record["id"]), "The selected effect is not graph-ready")
    C.require(step["tool_name"] in stored.get("approved_actions", []), "The selected effect was not approved")
    C.require(any(r.get("id") and r.get("response_sha256") for r in stored.get("provider_receipts", [])), "The goal has no actual model-generation evidence")
    return stored


def _link(port, record, step, receipt):
    identity = record["id"] + ":" + record["proposal"]["hash"] + ":" + step["id"]
    rows = graph._graph(port).query(
        "MATCH (g:Goal {id:$goal})-[:CURRENT_PLAN]->(p:PlanRevision {hash:$hash})-[:HAS_STEP]->(s:GoalStep {id:$step}) "
        "MERGE (a:GoalActionReceipt {id:$id}) SET a.json=$json,a.status=$status,a.url=$url "
        "MERGE (s)-[:EXECUTED_AS]->(a) MERGE (g)-[:HAS_ACTION]->(a) RETURN a.id",
        {"goal": record["id"], "hash": record["proposal"]["hash"], "step": identity,
         "id": receipt["id"], "json": C.encode(receipt), "status": receipt["status"], "url": receipt.get("url", "")}).result_set
    return rows == [[receipt["id"]]]


def _text(record, step):
    args = step["args"]
    sources = {e["source_id"]: e for e in record["evidence"] if e.get("kind") == "source"}
    lines = [args["description"], "", "Baton AI-authored work proposal", "Goal: " + record["goal"],
             "Goal run: " + record["id"], "Plan hash: " + record["proposal"]["hash"], "Step: " + step["id"],
             "Success criteria: " + "; ".join(record["proposal"]["success_criteria"]),
             "Evidence inspected by the agent:"]
    for identity in args["source_ids"]:
        source = sources[identity]
        lines.append(identity + " | " + str(source.get("url") or "captured graph evidence") + " | Captured evidence record SHA-256 " + source["sha256"])
    lines += ["Goal evidence: https://baton-workspace.vercel.app/api/public/goals/" + record["id"],
              "Creating this task/report does not complete the proposed work or establish an upstream fix.",
              "Public contribution evidence does not establish employment or internal ownership."]
    return args["title"], "\n".join(lines)


def _publish_target(data, port, record, step, target, title, text):
    _current(data, port, record, step)
    config = provider._config(target)
    destination = config["site"] + "/" + config["project"] if target == "jira" else config["channel"]
    material = {"goal_id": record["id"], "plan_hash": record["proposal"]["hash"], "step_id": step["id"],
                "target": target, "destination": destination, "cloud_id": config.get("cloud_id"), "title": title, "text": text}
    digest = C.sha(C.encode(material))
    identity = "goal-publication-" + C.sha(C.encode([record["id"], record["proposal"]["hash"], step["id"], target]))
    control, key = connect(port), "goal:publication:" + identity
    with control.lock(key, timeout=110, blocking_timeout=2):
        raw = control.get(key)
        receipt = json.loads(raw) if raw else None
        if receipt:
            C.require(receipt.get("contract_sha256") == digest, "Goal publication material changed; reconcile the existing intent")
            if receipt.get("status") == "verified":
                receipt["graph_linked"] = _link(port, record, step, receipt)
                return receipt
            if not receipt.get("remote_id"):
                return receipt
        else:
            receipt = {"id": identity, "goal_id": record["id"], "step_id": step["id"], "target": target,
                       "plan_hash": record["proposal"]["hash"], "contract_sha256": digest,
                       "destination": destination, "title": title, "evidence_text": text, "status": "pending",
                       "created_at": public.now(), "write_retry_allowed": False, "read_back_verified": False}
            if target == "slack":
                receipt["message_text"] = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            C.require(control.set(key, C.encode(receipt)), "Durable goal publication intent could not be saved")
            _current(data, port, record, step)
            C.require(provider._config(target) == config, "Provider destination changed")
            try:
                if target == "jira":
                    result = provider._request(target, "POST", "/rest/api/3/issue", config, {"fields": {
                        "project": {"key": config["project"]}, "summary": title, "issuetype": {"name": "Task"},
                        "description": provider._adf(text)}})
                    remote = result.get("key", "")
                    C.require(isinstance(remote, str) and re.fullmatch(re.escape(config["project"]) + r"-[0-9]+", remote), "Unexpected Jira task identity")
                else:
                    result = provider._request(target, "POST", "chat.postMessage", config, {
                        "channel": config["channel"], "text": receipt["message_text"], "mrkdwn": False, "parse": "none",
                        "link_names": False, "unfurl_links": False, "unfurl_media": False})
                    remote = result.get("ts", "")
                    C.require(result.get("channel") == config["channel"] and isinstance(remote, str) and re.fullmatch(r"[0-9]{10,16}\.[0-9]{6}", remote), "Unexpected Slack message identity")
                receipt.update(remote_id=remote, status="remote_created")
                C.require(control.set(key, C.encode(receipt)), "Remote goal artifact identity was not saved")
            except Exception as error:
                if isinstance(error, provider.ProviderFailure):
                    receipt["diagnostic"] = error.diagnostic
                    if error.rejected:
                        receipt["status"] = "rejected"
                control.set(key, C.encode(receipt))
                return receipt
        try:
            receipt["url"] = provider._verify(target, config, receipt, {"title": title})
            receipt.update(status="verified", read_back_verified=True, verified_at=public.now())
            receipt["graph_linked"] = _link(port, record, step, receipt)
        except Exception:
            receipt.update(status="verification_pending", read_back_verified=False)
        C.require(control.set(key, C.encode(receipt)), "Goal publication readback could not be saved")
        return receipt


def _verify_release(data, port, record, step):
    """Bridge an actual AI goal investigation to the approved immutable runner."""
    from . import release_contract, release_gate, release_graph
    control = connect(port)
    key = "goal:verification:" + C.sha(C.encode([record["id"], record["proposal"]["hash"], step["id"]]))
    with control.lock(key, timeout=120, blocking_timeout=2):
        identity = control.get(key)
        if identity:
            plan = release_gate.read_plan(port, identity)
        else:
            # The source commit/policy are fixed. Copy the existing independently
            # source-bound contract and reread its graph facts; no second model
            # investigation or imported result is manufactured by this bridge.
            plan = copy.deepcopy(release_gate.read_plan(port))
            C.require(release_graph.revalidate(data, port, plan), "The approved verification contract is stale")
            inspected = {e.get("source_id") for e in record["evidence"] if e.get("kind") == "source"}
            C.require(inspected.intersection(s["id"] for s in plan["source_versions"]), "Inspect this pinned change's source before requesting its runner")
            C.require(plan.get("plan_status") == "ready" and plan.get("plan_hash") == release_contract.plan_hash(plan), "The deterministic verification policy is incomplete")
            plan.update(id=secrets.token_hex(16), created_at=public.now(), latest_run_id=None,
                        investigation={"status": "succeeded", "origin": "goal_agent", "goal_id": record["id"],
                            "goal_plan_hash": record["proposal"]["hash"], "model": record["model"],
                            "summary": step["why"], "receipts": copy.deepcopy(record["provider_receipts"]),
                            "trace": copy.deepcopy(record["events"]),
                            "source_binding": "Actual goal-agent observations; no additional release-model call was performed"})
            release_gate._save(port, "plan", plan)
            C.require(control.set(key, plan["id"]), "Goal verification intent could not be saved")
            control.set("release:latest-plan", plan["id"])
        run = release_gate.execute(data, port, plan["id"], plan["plan_hash"], ["jira", "slack"])
    return _verification_receipt(data, port, plan, run, step)


def _verification_receipt(data, port, plan, run, step):
    """Report execution evidence separately from actual delivery read-backs."""
    from . import release_graph
    C.require(run.get("plan_id") == plan["id"] and run.get("plan_hash") == plan["plan_hash"],
              "The verification run does not match its durable plan")
    evidence_verified = run.get("evidence_status") == "verified" and run.get("graph_receipt", {}).get("verified") is True
    if evidence_verified:
        try:
            certificate = release_graph.verify_result(data, port, plan, run)
            evidence_verified = certificate == run["graph_receipt"] and certificate.get("verified") is True
        except Exception:
            evidence_verified = False
    publications = run.get("publication", {})
    delivered = set(run.get("publish_targets", [])) == {"jira", "slack"} and all(
        isinstance(publications.get(target), dict) and publications[target].get("status") == "verified" and
        publications[target].get("graph_linked") is True and publications[target].get("target") == target and
        publications[target].get("run_id") == run["id"] and publications[target].get("plan_id") == plan["id"]
        for target in ("jira", "slack"))
    publication_graph_verified = bool(delivered and _publication_graph_verified(port, plan, run, publications))
    delivered = delivered and publication_graph_verified
    verified = evidence_verified and delivered
    return {"id": "goal-verification-" + run["id"], "step_id": step["id"], "kind": "verify_release",
            "status": "verified" if verified else "partial" if evidence_verified or run.get("status") in {"completed", "partial", "error"} else "running", "read_back_verified": verified,
            "url": "https://baton-workspace.vercel.app/api/public/release-runs/" + run["id"],
            "result": {"run_id": run["id"], "decision": run["decision"], "evidence_status": run["evidence_status"],
                       "verification_status": run["verification_status"], "environments": copy.deepcopy(run["environments"]),
                       "run_status": run.get("status"), "evidence_graph_verified": evidence_verified,
                       "publication_state": "verified" if delivered else "unconfirmed", "publication_graph_verified": publication_graph_verified,
                       "publications": copy.deepcopy(publications)}}


def _publication_graph_verified(port, plan, run, publications):
    """Read native run-to-publication bindings without creating or repairing them."""
    from . import release_graph
    try:
        native = release_graph._connect(port).select_graph(plan["graph"])
        for target in ("jira", "slack"):
            receipt = publications[target]
            if not all(isinstance(receipt.get(key), str) and receipt[key] for key in ("id", "url", "contract_sha256")):
                return False
            expected = [receipt["id"], target, receipt["url"], receipt["contract_sha256"], run["id"]]
            rows = native.ro_query(
                "MATCH (r:ReleaseExecution {id:$run})-[:PUBLISHED_AS]->(p:ReleasePublication {id:$id}) "
                "WHERE p.target=$target AND p.url=$url AND p.contract_sha256=$hash AND p.run_id=$run "
                "RETURN p.id,p.target,p.url,p.contract_sha256,p.run_id",
                {"run": run["id"], "id": receipt["id"], "target": target,
                 "url": receipt["url"], "hash": receipt["contract_sha256"]}).result_set
            if rows != [expected]:
                return False
        return True
    except Exception:
        return False


def resume(data, port, record, step):
    """Reconcile only a known, previously approved verification; never dispatch or post."""
    from . import release_gate
    C.require(step.get("tool_name") == "verify_release", "Continuation cannot start or publish an effect")
    stored = _current(data, port, record, step)
    pending = [action for action in stored.get("actions", []) if action.get("step_id") == step["id"] and
               action.get("kind") == "verify_release" and action.get("plan_hash") == stored["proposal"]["hash"] and
               action.get("status") in {"running", "partial", "pending", "verification_pending", "error"} and
               action.get("read_back_verified") is not True]
    run_ids = {action.get("result", {}).get("run_id") for action in pending}
    C.require(len(run_ids) == 1, "No unique already-started verification action can be reconciled")
    run_id = next(iter(run_ids))
    C.require(isinstance(run_id, str) and re.fullmatch(r"[a-f0-9]{32}", run_id), "The pending verification has no known run identity")
    key = "goal:verification:" + C.sha(C.encode([stored["id"], stored["proposal"]["hash"], step["id"]]))
    identity = connect(port).get(key)
    C.require(isinstance(identity, str) and re.fullmatch(r"[a-f0-9]{32}", identity), "No durable verification intent exists")
    plan = release_gate.read_plan(port, identity)
    origin = plan.get("investigation", {})
    C.require(plan.get("id") == identity and plan.get("latest_run_id") == run_id and origin.get("origin") == "goal_agent" and
              origin.get("goal_id") == stored["id"] and origin.get("goal_plan_hash") == stored["proposal"]["hash"],
              "The pending verification does not match the goal's durable intent")
    release_gate._current(data, port, plan)
    run = release_gate.read_run(port, run_id)
    C.require(run.get("id") == run_id, "The stored verification run identity changed")
    return _verification_receipt(data, port, plan, run, step)


def execute(data, port, record, step):
    _current(data, port, record, step)
    if step["tool_name"] == "verify_release":
        return _verify_release(data, port, record, step)
    C.require(step["tool_name"] == "publish_task", "Unknown goal effect")
    title, text = _text(record, step)
    receipts = {target: _publish_target(data, port, record, step, target, title, text) for target in ("jira", "slack")}
    verified = all(r.get("status") == "verified" and r.get("read_back_verified") is True and r.get("graph_linked") is True for r in receipts.values())
    return {"id": "goal-action-" + C.sha(C.encode([record["id"], record["proposal"]["hash"], step["id"]])),
            "step_id": step["id"], "kind": "publish_task", "status": "verified" if verified else "partial",
            "read_back_verified": verified, "url": receipts["jira"].get("url"), "result": {"publications": receipts,
                "work_completion_claimed": False}}
