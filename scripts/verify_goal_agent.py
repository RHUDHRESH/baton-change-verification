"""Read-only public-record audit of two actual model-authored goal plans.

No credentials, model calls, provider writes or cloud mutations. Public protocol
receipts are checked for consistency, not independently authenticated with Groq.
Direct provider and native graph reads are separate CloudShell proofs.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import goal_contract as C

ORIGIN = "https://baton-workspace.vercel.app"
SOURCE = Path(__file__).resolve().parents[1] / "server/goal_graph.py"
READ_NAMES = {"search_company_graph", "inspect_graph_entity", "traverse_company_graph", "read_company_source", "recall_goal_memory"}


class ProofError(ValueError):
    pass


def _json_offered_catalog(value, catalog, current, plans, done):
    """Independently check authority-bearing schemas, including ready-step enums."""
    def obj(properties, required=None):
        return {"type":"object","properties":properties,"required":list(properties) if required is None else required,"additionalProperties":False}
    def string(limit=400):return {"type":"string","minLength":1,"maxLength":limit}
    def strings(limit=6):return {"type":"array","items":string(),"maxItems":limit}
    step=obj({"id":string(80),"title":string(160),"tool_name":string(80),"args":{"type":"object","additionalProperties":True},
              "why":string(600),"evidence_ids":strings(12),"depends_on":strings(),"expected_result":string(600)})
    plan=obj({"summary":string(1200),"success_criteria":strings(),"assumptions":strings(),"questions":strings(),
              "steps":{"type":"array","items":step,"minItems":1,"maxItems":6},"limitations":strings()})
    expected={t["name"]:t for t in catalog if t["name"] in READ_NAMES}
    require(isinstance(value,list) and len(value) in {6,7}, "JSON decision catalog has an unexpected capability count")
    named={t.get("name"):t for t in value}
    require(len(named)==len(value) and set(named).issubset(READ_NAMES|{"propose_goal_plan","select_plan_step","finish_goal"}) and
            all(named.get(name)==tool for name,tool in expected.items()) and named.get("propose_goal_plan",{}).get("inputSchema")==plan,
            "JSON decision catalog substituted a read or planning capability schema")
    ready=[s["id"] for s in plans[current]["steps"] if s["id"] not in done[current] and set(s["depends_on"]).issubset(done[current])] if current else []
    if "select_plan_step" in named:
        require(current and ready and named["select_plan_step"].get("inputSchema")==obj({"step_id":{"type":"string","enum":ready}}),
                "JSON decision step-selection schema differs from graph-ready sealed steps")
    if "finish_goal" in named:
        require(current and not ready and done[current]=={s["id"] for s in plans[current]["steps"]}, "JSON finish offered before actual plan completion")
        schema=obj({"summary":{"type":"string","minLength":15,"maxLength":1200},"criteria_assessment":{"type":"array","minItems":1,"maxItems":6,"items":obj({
            "criterion":{"type":"string","enum":plans[current]["success_criteria"]},"status":{"type":"string","enum":["supported","not_met","unknown"]},
            "reason":string(300),"evidence_ids":strings(12),"action_ids":strings(6)})}})
        require(named["finish_goal"].get("inputSchema")==schema,"JSON finish schema substituted criterion authority")
    return named


def require(value, message):
    if not value:
        raise ProofError(message)


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value), "Invalid goal identity")
    return value


def catalog_from_source(path=SOURCE):
    """Read the trusted source catalog without importing Redis or executing it."""
    raw = Path(path).read_bytes()
    tree = ast.parse(raw)
    constants, entries, descriptions = {}, None, None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"STRING", "LIMIT"}:
                constants[name] = ast.literal_eval(node.value)
            elif name == "TOOLS":
                entries = node.value
        if isinstance(node, ast.FunctionDef) and node.name == "_tool":
            returned = next(n for n in node.body if isinstance(n, ast.Return)).value
            for key, value in zip(returned.keys, returned.values):
                if ast.literal_eval(key) == "description":
                    descriptions = ast.literal_eval(value.value)
    def literal(node):
        if isinstance(node, ast.Name):
            return constants[node.id]
        if isinstance(node, ast.Dict):
            return {literal(k): literal(v) for k, v in zip(node.keys, node.values)}
        return ast.literal_eval(node)
    require(isinstance(entries, ast.List) and isinstance(descriptions, dict), "Catalog source structure is not recognized")
    tools = []
    for entry in entries.elts:
        require(isinstance(entry, ast.Call) and isinstance(entry.func, ast.Name) and entry.func.id == "_tool" and len(entry.args) == 3 and not entry.keywords,
                "Catalog contains an unsupported declaration")
        name, properties, required = [literal(arg) for arg in entry.args]
        tools.append({"name": name, "description": descriptions[name], "inputSchema": {
            "type": "object", "properties": properties, "required": required, "additionalProperties": False}})
    require({t["name"] for t in tools} == READ_NAMES and len(tools) == 5, "Read catalog differs from the approved five tools")
    return tools + C.EFFECTS, C.sha(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Reader:
    def __init__(self, origin=ORIGIN):
        parsed = urllib.parse.urlsplit(origin)
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and parsed.port in {None, 443} and
                parsed.path in {"", "/"} and not parsed.query and not parsed.fragment, "An exact HTTPS origin is required")
        self.origin = parsed.scheme + "://" + parsed.netloc
        self.opener = urllib.request.build_opener(NoRedirect())

    def raw(self, id):
        identity(id)
        request = urllib.request.Request(self.origin + "/api/public/goals/" + id, method="GET", headers={"Accept": "application/json", "User-Agent": "Baton-ReadOnly-Goal-Proof"})
        try:
            with self.opener.open(request, timeout=35) as response:
                raw = response.read(400001)
            require(len(raw) <= 400000, "Public goal record exceeds its bound")
            return raw
        except ProofError:
            raise
        except Exception:
            raise ProofError("Public goal GET was not confirmed; no URL or provider body was printed") from None


def binding(evidence):
    return C.sha(C.encode(sorted(set((e["id"], e["sha256"]) for e in evidence))))


def _text(record, proposal, step, evidence):
    args = step["args"]
    sources = {e["source_id"]: e for e in evidence if e.get("kind") == "source"}
    lines = [args["description"], "", "Baton AI-authored work proposal", "Goal: " + record["goal"],
             "Goal run: " + record["id"], "Plan hash: " + proposal["hash"], "Step: " + step["id"],
             "Success criteria: " + "; ".join(proposal["success_criteria"]), "Evidence inspected by the agent:"]
    for id in args["source_ids"]:
        source = sources[id]
        lines.append(id + " | " + str(source.get("url") or "captured graph evidence") + " | Captured evidence record SHA-256 " + source["sha256"])
    lines += ["Goal evidence: " + ORIGIN + "/api/public/goals/" + record["id"],
              "Creating this task/report does not complete the proposed work or establish an upstream fix.",
              "Public contribution evidence does not establish employment or internal ownership."]
    return "\n".join(lines)


def _action(record, proposal, step, result, evidence):
    require(isinstance(result, dict) and isinstance(result.get("id"), str) and result["id"] and result.get("step_id") == step["id"] and
            result.get("kind") == step["tool_name"] and type(result.get("read_back_verified")) is bool, "Action result lacks its exact step identity")
    if step["tool_name"] == "publish_task":
        require(result["id"] == "goal-action-" + C.sha(C.encode([record["id"], proposal["hash"], step["id"]])), "Publication action identity changed")
        pubs = result.get("result", {}).get("publications", {})
        require(set(pubs) == {"jira", "slack"} and result["result"].get("work_completion_claimed") is False, "Paired publication receipts or honest work status are missing")
        text = _text(record, proposal, step, evidence)
        all_verified = True
        for target, receipt in pubs.items():
            require(receipt.get("goal_id") == record["id"] and receipt.get("plan_hash") == proposal["hash"] and receipt.get("step_id") == step["id"] and
                    receipt.get("target") == target and receipt.get("title") == step["args"]["title"] and receipt.get("evidence_text") == text and
                    digest(receipt.get("contract_sha256")) and receipt.get("write_retry_allowed") is False,
                    "Publication receipt changed goal, step, title, evidence text or intent policy")
            expected_id = "goal-publication-" + C.sha(C.encode([record["id"], proposal["hash"], step["id"], target]))
            require(receipt.get("id") == expected_id, "Publication intent identity changed")
            if target == "slack":
                require(receipt.get("message_text") == text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), "Slack message differs from the sealed task evidence")
            ok = receipt.get("status") == "verified" and receipt.get("read_back_verified") is True and receipt.get("graph_linked") is True
            if ok:
                require(isinstance(receipt.get("url"), str) and receipt["url"].startswith("https://"), "Verified publication has no HTTPS readback URL")
                require(isinstance(receipt.get("remote_id"), str) and bool(re.fullmatch(r"KAN-[0-9]+" if target == "jira" else r"[0-9]{10,16}\.[0-9]{6}", receipt["remote_id"])), "Publication identity is outside the configured record type")
            all_verified = all_verified and ok
        require((result.get("status") == "verified" and result.get("read_back_verified") is True) == all_verified, "Action success contradicts its independent target receipts")
    else:
        measurement = result.get("result", {})
        id = identity(measurement.get("run_id"))
        require(result["id"] == "goal-verification-" + id and result.get("url") == ORIGIN + "/api/public/release-runs/" + id,
                "Verification action references another execution")
        if result.get("read_back_verified") is True:
            require(result.get("status") == "verified" and measurement.get("evidence_status") == "verified" and measurement.get("decision") in {"passed", "blocked"}, "Unconfirmed verification was relabeled as completed")


def verify_record(record, catalog):
    """Check public evidence consistency; never claim a direct native graph GET."""
    try:
        return _verify_record(record, catalog)
    except ProofError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError):
        raise ProofError("Malformed or misbound goal evidence was rejected") from None


def _verify_record(record, catalog):
    identity(record.get("id"))
    require(record.get("status") in {"proposed", "acting", "needs_continuation", "answered", "completed", "blocked"}, "Goal has no completed investigation record")
    reads = {t["name"]: t for t in catalog if t["name"] in READ_NAMES}
    receipts, generations = record.get("provider_receipts"), {}
    require(isinstance(receipts, list) and receipts, "No actual provider generation receipts")
    measured = 0
    for receipt in receipts:
        if receipt.get("http_status"):
            require(digest(receipt.get("response_sha256")) or digest(receipt.get("response_prefix_sha256")), "Provider error lacks captured response hash")
            continue
        id = receipt.get("id")
        require(isinstance(id, str) and id.strip() and id not in generations and isinstance(receipt.get("model"), str) and receipt["model"].strip(), "Provider identity/model is missing or duplicated")
        require(digest(receipt.get("response_sha256")) and digest(receipt.get("request_sha256")) and receipt.get("transport") in {"native_chat_completions","json_decision"}, "Provider request/response protocol binding is missing")
        usage = receipt.get("usage", {})
        require(all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens")) and
                usage["completion_tokens"] > 0 and usage["total_tokens"] >= usage["prompt_tokens"] + usage["completion_tokens"], "Provider token usage is absent or contradictory")
        measured += usage["total_tokens"]
        generations[id] = receipt
    require(generations and type(record.get("provider_calls")) is int and record["provider_calls"] >= len(receipts) and record.get("total_tokens") == measured,
            "Goal call counts or measured token totals differ from receipts")
    events = record.get("events")
    require(isinstance(events, list) and events and [e.get("seq") for e in events] == list(range(len(events))), "Goal observation sequence is incomplete")
    rejected_events = {(e.get("receipt_id"), e.get("tool_call_id")): e for e in events if e.get("type") == "tool_rejected"}
    calls, active_evidence, plans, done, reconstructed_actions = {}, {}, {}, {}, []
    pending_proposal, current, reflections = None, None, []
    revision_count, called_receipts, response_events, rejected_calls = 0, set(), set(), set()
    json_decisions = {}
    selected_tools, read_arguments, observations = [], [], 0
    for event in events:
        kind = event.get("type")
        if kind == "replan_required":
            active_evidence = {}
        elif kind == "provider_response":
            r = generations.get(event.get("receipt_id"))
            require(r and r["finish_reason"] == event.get("finish_reason") and event["receipt_id"] not in response_events, "Provider event differs from its actual generation receipt")
            response_events.add(event["receipt_id"])
        elif kind == "assistant_final":
            r = generations.get(event.get("receipt_id"))
            require(r and r.get("transport")=="native_chat_completions" and r["finish_reason"] == "stop", "Native final content was fabricated as a tool response")
            pending_proposal = json.loads(event["result"])
        elif kind == "assistant_json_decision":
            r=generations.get(event.get("receipt_id"))
            require(r and r.get("transport")=="json_decision" and r["finish_reason"]=="stop" and r["id"] in response_events and r["id"] not in json_decisions,
                    "JSON decision has no unique actual assistant stop generation")
            content=event.get("result");offered=event.get("offered_catalog")
            require(isinstance(content,str) and r.get("assistant_content_sha256")==C.sha(content) and
                    event.get("catalog_sha256")==r.get("offered_catalog_sha256")==C.sha(C.encode(offered)),"JSON decision content/catalog differs from its provider receipt")
            expected_id="host-json-"+C.sha(C.encode([r["id"],r["response_sha256"],content]))
            require(event.get("selection_id")==expected_id and event.get("id_origin")=="host_assigned_json_decision","JSON decision invocation ID is not explicitly host-bound")
            offered_names=_json_offered_catalog(offered,catalog,current,plans,done)
            decision=json.loads(content)
            require(isinstance(decision,dict),"JSON decision is not one object")
            json_decisions[r["id"]]=(event,decision,offered_names)
            if set(decision)!={"tool_name","args"}:
                C.validate_arguments(decision,offered_names["propose_goal_plan"]["inputSchema"])
                pending_proposal=decision;called_receipts.add(r["id"])
        elif kind in {"tool_call","tool_selection"}:
            r = generations.get(event.get("receipt_id"))
            key = (event.get("receipt_id"), event.get("tool_call_id"))
            require(r and isinstance(key[1], str) and key[1] and key not in calls and key[0] not in called_receipts, "Tool call lacks a unique provider selection")
            if kind=="tool_selection":
                decision_event,decision,offered=json_decisions.get(key[0],(None,None,None))
                require(r.get("transport")=="json_decision" and r["finish_reason"]=="stop" and decision_event and
                        set(decision)=={"tool_name","args"} and decision=={"tool_name":event.get("tool_name"),"args":event.get("args")} and
                        event.get("tool_call_id")==event.get("invocation_id")==decision_event["selection_id"] and event.get("id_origin")=="host_assigned_json_decision",
                        "Host invocation differs from the actual JSON decision or claims a native ID")
                require(event.get("tool_name") in offered,"JSON decision selected an unoffered capability")
                try:C.validate_arguments(event.get("args"),offered[event["tool_name"]]["inputSchema"])
                except ValueError:
                    require(event.get("tool_name") in reads and rejected_events.get(key,{}).get("category")=="invalid_read_arguments","JSON selection violates its offered schema")
            else:
                require(r.get("transport")=="native_chat_completions" and r["finish_reason"]=="tool_calls" and "invocation_id" not in event,
                        "Tool call lacks a unique native provider selection")
            calls[key] = event
            called_receipts.add(key[0])
            name = event.get("tool_name")
            require(name in READ_NAMES | {"propose_goal_plan", "select_plan_step", "finish_goal"}, "Unknown tool was executed")
            if name in reads:
                try:
                    C.validate_arguments(event.get("args"), reads[name]["inputSchema"])
                except ValueError:
                    rejected = rejected_events.get(key, {})
                    require(rejected.get("category") == "invalid_read_arguments" and rejected.get("args") == event.get("args"), "Invalid native read arguments have no actual rejected-selection event")
            elif name == "propose_goal_plan":
                pending_proposal = event.get("args")
            elif name == "select_plan_step":
                require(current and set(event.get("args", {})) == {"step_id"}, "Selection has no current sealed plan")
                step = next((s for s in plans[current]["steps"] if s["id"] == event["args"]["step_id"]), None)
                require(step and step["id"] not in done[current] and set(step["depends_on"]).issubset(done[current]), "Model selected a step before dependencies completed")
        elif kind == "tool_result":
            key = (event.get("receipt_id"), event.get("tool_call_id"));call = calls.get(key)
            require(call and key not in rejected_calls and event.get("status") == "succeeded", "Observation lacks an actual successful selected tool")
            name, args = event.get("tool_name"), event.get("args")
            require(name in reads, "Only actual graph reads may create source observations")
            C.validate_arguments(args, reads[name]["inputSchema"])
            if event.get("step_id"):
                require(current == event.get("plan_hash") and call["tool_name"] == "select_plan_step" and call["args"]["step_id"] == event["step_id"], "Planned read lost its model selection or revision binding")
                step = next(s for s in plans[current]["steps"] if s["id"] == event["step_id"])
                require(step["tool_name"] == name and step["args"] == args, "Actual planned read differs from the sealed command")
                done[current].add(step["id"])
            else:
                require(call["tool_name"] == name and call["args"] == args, "Actual investigation read differs from model arguments")
            result = event.get("result", {})
            evidence = result.get("evidence")
            require(isinstance(result.get("observation"), dict) and isinstance(evidence, list) and result.get("binding", {}).get("fingerprint") == binding(evidence), "Graph read observation/evidence binding differs")
            require(event.get("evidence_ids") == [e["id"] for e in evidence], "Observation evidence member IDs changed")
            for e in evidence:
                require(isinstance(e.get("id"), str) and digest(e.get("sha256")) and e.get("kind") in {"source", "entity", "model_proposal"}, "Observation has invalid evidence metadata")
                require((e["kind"] == "source") == (name == "read_company_source"), "Search/entity result forged a raw source inspection")
                if e["kind"] == "source":
                    require(e.get("source_id") == args["source_id"], "Source inspection ID differs from selected captured source")
                active_evidence[e["id"]] = {**e, "observed_by_tool_call": key[1]}
            selected_tools.append(name);read_arguments.append([name, args]);observations += 1
        elif kind == "tool_rejected":
            key = (event.get("receipt_id"), event.get("tool_call_id"));call = calls.get(key)
            prior_seq = event.get("previous_observation_seq")
            require(call and key not in rejected_calls and isinstance(event.get("error"), str) and event["error"] and "result" not in event,
                    "Rejected selection has no actual native selection or forged an execution result")
            category = event.get("category")
            if category in {"invalid_read_arguments", "unknown_captured_source", "unknown_graph_entity"}:
                require(event.get("tool_name") in reads, "Recoverable rejection was not a read-only capability")
                if event.get("step_id"):
                    require(current == event.get("plan_hash") and call.get("tool_name") == "select_plan_step" and call.get("args", {}).get("step_id") == event["step_id"], "Rejected planned read lost its actual selected step")
                    step = next(s for s in plans[current]["steps"] if s["id"] == event["step_id"])
                    require(step["tool_name"] == event["tool_name"] and step["args"] == event.get("args"), "Rejected planned read differs from the sealed read")
                else:
                    require(call.get("tool_name") == event.get("tool_name") and call.get("args") == event.get("args"), "Rejected read differs from the actual selected arguments")
                if category == "unknown_captured_source":
                    require(event["tool_name"] == "read_company_source", "Unknown-source rejection was attached to another capability")
                if category == "unknown_graph_entity":
                    require(event["tool_name"] in {"inspect_graph_entity", "traverse_company_graph"}, "Unknown-entity rejection was attached to another capability")
            else:
                require(category is None and call.get("tool_name") == event.get("tool_name") == "search_company_graph" and call.get("args") == event.get("args"), "Unknown or substituted rejection category")
                require(type(prior_seq) is int and 0 <= prior_seq < event["seq"], "Rejected search has no preceding actual empty observation")
                prior = events[prior_seq]
                require(prior.get("type") == "tool_result" and prior.get("status") == "succeeded" and prior.get("tool_name") == "search_company_graph" and
                        prior.get("result", {}).get("observation", {}).get("entities") == [] and
                        prior.get("args", {}).get("query", "").lower() == event["args"].get("query", "").lower() and
                        prior.get("result", {}).get("observation", {}).get("search_version") == event.get("search_version"),
                        "Search rejection differs from its actual exhausted query or retrieval version")
            require(not any(e.get("type") == "tool_result" and (e.get("receipt_id"), e.get("tool_call_id")) == key for e in events),
                    "Rejected search was falsely counted as an actual read")
            rejected_calls.add(key)
        elif kind == "plan_proposed":
            require(pending_proposal is not None and active_evidence, "Plan was not generated by a model after actual evidence inspection")
            p = C.validate_proposal(pending_proposal, record["goal"], list(active_evidence.values()), catalog, binding(list(active_evidence.values())))
            revision_count += 1
            require(event.get("plan_hash") == p["hash"] and event.get("revision") == revision_count, "Plan revision differs from the actual model proposal")
            current = p["hash"];plans[current] = p;done.setdefault(current, set());pending_proposal = None
        elif kind == "action_result":
            call = calls.get((event.get("receipt_id"), event.get("tool_call_id")))
            require(current == event.get("plan_hash") and call and call["tool_name"] == "select_plan_step" and call["args"]["step_id"] == event.get("step_id"), "Effect has no exact actual model selection")
            step = next(s for s in plans[current]["steps"] if s["id"] == event["step_id"])
            require(step["tool_name"] in C.EFFECT_TOOLS and step["tool_name"] in record.get("approved_actions", []), "Effect was not a sealed approved capability")
            result = event.get("result")
            _action(record, plans[current], step, result, list(active_evidence.values()))
            reconstructed_actions.append({**result, "step_id": step["id"], "kind": step["tool_name"], "plan_hash": current})
            if result.get("status") == "verified" and result.get("read_back_verified") is True:
                done[current].add(step["id"])
        elif kind == "goal_reflection":
            call = calls.get((event.get("receipt_id"), event.get("tool_call_id")))
            require(current and call and call["tool_name"] == "finish_goal" and done[current] == {s["id"] for s in plans[current]["steps"]}, "Goal completion bypassed actual model reflection or verified step receipts")
            assessment = event.get("result", {}).get("criteria_assessment")
            require(assessment == call.get("args", {}).get("criteria_assessment") and event["result"].get("summary") == call["args"].get("summary"), "Reflection differs from model-authored criterion assessment")
            criteria = plans[current]["success_criteria"]
            require(isinstance(assessment, list) and len(assessment) == len(criteria) and {x["criterion"] for x in assessment} == set(criteria), "Reflection omitted or substituted success criteria")
            action_ids = {a["id"] for a in reconstructed_actions}
            for item in assessment:
                require(item.get("status") in {"supported", "not_met", "unknown"} and set(item.get("evidence_ids", [])).issubset(active_evidence) and
                        set(item.get("action_ids", [])).issubset(action_ids), "Criterion cites an unknown observation or action")
                require(item["status"] != "supported" or item.get("evidence_ids") or item.get("action_ids"), "Supported criterion has no observed backing")
            reflections.append((current, all(item["status"] == "supported" for item in assessment)))
        else:
            require(kind == "blocked", "Unknown execution episode type")
    require(current and observations and record.get("proposal") == plans[current], "Current public proposal differs from the model-authored DAG")
    require(record.get("revision") == revision_count and record.get("actions") == reconstructed_actions, "Public revision/actions differ from actual execution episodes")
    require(all(r["finish_reason"] not in {"stop", "tool_calls"} or id in response_events for id, r in generations.items()), "Successful generation has no matching response event")
    require(all(r.get("transport")!="json_decision" or r["finish_reason"]!="stop" or id in json_decisions and id in called_receipts for id,r in generations.items()),"JSON generation lacks its actual decision or validated invocation")
    require(record.get("model") == list(generations.values())[-1]["model"], "Public model differs from its latest actual generation")
    require(record.get("evidence") == list(active_evidence.values()), "Public evidence differs from actual inspected evidence episodes")
    sealed = record.get("plan_evidence", record["evidence"])
    require(record.get("evidence_binding") == binding(sealed), "Sealed evidence fingerprint differs")
    C.validate_proposal(record["proposal"], record["goal"], sealed, catalog, record["evidence_binding"])
    if record["status"] in {"answered", "completed"}:
        require(reflections and reflections[-1] == (current, True), "Terminal success has no current supported model reflection")
        require((record["status"] == "completed") == any(s["tool_name"] in C.EFFECT_TOOLS for s in plans[current]["steps"]), "Terminal goal status contradicts the sealed capability types")
    return {"goal_id": record["id"], "goal_sha256": C.sha(record["goal"]), "status": record["status"], "plan_hash": current,
            "revision": revision_count, "step_count": len(plans[current]["steps"]), "plan_tools": [s["tool_name"] for s in plans[current]["steps"]],
            "model_selected_read_tools": selected_tools, "actual_read_observations": observations, "provider_generations": len(generations),
            "native_selections_rejected_without_execution": sum(generations[key[0]]["transport"]=="native_chat_completions" for key in rejected_calls),
            "selections_rejected_without_execution": len(rejected_calls),
            "selection_transports": sorted({r["transport"] for r in generations.values()}),
            "json_decisions": len(json_decisions), "host_assigned_json_invocations": sum(e["type"]=="tool_selection" for e in events),
            "provider_attempts": record["provider_calls"], "measured_tokens": measured, "model_ids": sorted({r["model"] for r in generations.values()}),
            "provider_response_hashes": [r["response_sha256"] for r in generations.values()], "evidence_count": len(active_evidence),
            "verified_effect_receipts": sum(a.get("status") == "verified" and a.get("read_back_verified") is True for a in reconstructed_actions),
            "current_criteria_reflection": bool(reflections and reflections[-1] == (current, True)),
            "plan_structure": [[s["tool_name"], [next(i for i, t in enumerate(plans[current]["steps"]) if t["id"] == dep) for dep in s["depends_on"]]] for s in plans[current]["steps"]],
            "read_arguments_sha256": C.sha(C.encode(read_arguments))}


def verify_pair(ids, reader, catalog=None):
    require(len(ids) == 2 and len(set(ids)) == 2, "Provide exactly two different goal identities")
    catalog, source_sha = catalog_from_source() if catalog is None else (catalog, None)
    summaries = []
    for id in ids:
        raw = reader.raw(identity(id));record = json.loads(raw)
        require(record.get("id") == id, "Public endpoint returned another goal identity")
        summary = verify_record(record, catalog)
        require(reader.raw(id) == raw, "Goal record changed during independent reads; retry after it stabilizes")
        summary["public_record_sha256"] = C.sha(raw);summaries.append(summary)
    require(summaries[0]["goal_sha256"] != summaries[1]["goal_sha256"], "The two records repeat the same goal")
    structure = summaries[0]["plan_structure"] != summaries[1]["plan_structure"]
    tools = summaries[0]["model_selected_read_tools"] != summaries[1]["model_selected_read_tools"]
    require(structure and tools, "Two materially different plan structures AND selected tool sequences are not established")
    return {"status": "verified_distinct_goal_records", "read_only": True, "goals": summaries, "catalog_source_sha256": source_sha,
            "catalog_sha256": C.sha(C.encode(catalog)), "different_plan_structures": structure, "different_selected_tool_sequences": tools,
            "provider_get_performed": False, "direct_graph_get_performed": False, "semantic_entailment_certified": False,
            "limitations": ["Provider identities and request/response hashes are public backend receipts; Groq responses were not independently fetched or cryptographically authenticated.",
                            "Native graph integrity/freshness is claimed by the public GET route; direct GRAPH.RO_QUERY and Jira/Slack readback are separate CloudShell audits.",
                            "Structural variation demonstrates these observed model selections, not general goal competence, ten completed features, or semantic criterion entailment.",
                            "No code repair, task Done transition, upstream merge, model call or provider write was performed by this verifier."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal-id", action="append", required=True)
    parser.add_argument("--origin", default=ORIGIN)
    parser.add_argument("--output", default="artifacts/goal-agent-independent-proof.json")
    args = parser.parse_args(argv)
    try:
        for id in args.goal_id: identity(id)
        result = verify_pair(args.goal_id, Reader(args.origin))
    except ProofError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True, "error": "Goal proof stopped; no credential, private URL or raw provider output was printed"}
    target = Path(args.output);target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(C.encode(result))
    return 0 if result["status"] == "verified_distinct_goal_records" else 1


if __name__ == "__main__":
    raise SystemExit(main())
