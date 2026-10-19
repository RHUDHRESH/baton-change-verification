"""Adversarial synthetic protocol fixtures; these tests are not live AI proof."""
import copy
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import verify_goal_agent as P
from server import goal_contract as C


def fixture_record(id="a" * 32, extra_search=False, publish=False, terminal=False, native_json=False):
    catalog, _ = P.catalog_from_source()
    record = {"id": id, "goal": "Prepare a source-backed handover task" if publish else "Investigate the observed compatibility condition",
              "status": "proposed", "revision": 1, "provider_receipts": [], "provider_calls": 0, "total_tokens": 0,
              "events": [], "evidence": [], "actions": [], "approved_actions": ["publish_task"] if publish else []}
    def event(type, **fields):
        row = {"seq": len(record["events"]), "type": type, **fields};record["events"].append(row);return row
    def generation(name, args, final=False):
        index = record["provider_calls"]
        receipt = {"id": "chatcmpl-" + id[:4] + "-" + str(index), "model": "openai/gpt-oss-20b", "usage": {
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "finish_reason": "stop" if final else "tool_calls",
            "request_sha256": C.sha("request-" + str(index)), "response_sha256": C.sha("response-" + str(index)), "transport": "native_chat_completions"}
        record["provider_receipts"].append(receipt);record["provider_calls"] += 1;record["total_tokens"] += 150;record["model"] = receipt["model"]
        event("provider_response", receipt_id=receipt["id"], finish_reason=receipt["finish_reason"])
        key = {"receipt_id": receipt["id"], "tool_call_id": "native-call-" + str(index)}
        if final:event("assistant_final", receipt_id=receipt["id"], result=json.dumps(args))
        else:event("tool_call", **key, tool_name=name, args=copy.deepcopy(args))
        return key
    def observe(name, args, key, step=None):
        evidence = {"id": "gev-" + ("1" * 24 if name == "read_company_source" else "2" * 24), "source_id": "src-captured" if name == "read_company_source" else "entity-id",
                    "url": "https://github.com/FalkorDB/falkordb-py/pull/212", "sha256": C.sha("captured" + name),
                    "kind": "source" if name == "read_company_source" else "entity"}
        result = {"observation": {"fact": "Actually returned bounded test observation"}, "evidence": [evidence],
                  "binding": {"fingerprint": P.binding([evidence])}}
        extra = {"step_id": step["id"], "plan_hash": record["proposal"]["hash"]} if step else {}
        event("tool_result", **key, **extra, tool_name=name, args=copy.deepcopy(args), status="succeeded", result=result, evidence_ids=[evidence["id"]])
        by_id = {e["id"]: e for e in record["evidence"]};by_id[evidence["id"]] = {**evidence, "observed_by_tool_call": key["tool_call_id"]};record["evidence"] = list(by_id.values())
    if extra_search:
        args = {"query": "handover", "limit": 2};observe("search_company_graph", args, generation("search_company_graph", args))
    args = {"source_id": "src-captured"};observe("read_company_source", args, generation("read_company_source", args))
    source = next(e for e in record["evidence"] if e["kind"] == "source")
    kinds = ["publish_task"] if publish else (["search_company_graph", "read_company_source"] if extra_search else ["read_company_source"])
    steps = []
    for i, name in enumerate(kinds):
        args = {"source_id": "src-captured"} if name == "read_company_source" else {"query": "handover"}
        if name == "publish_task":args = {"title": "Investigate the actual captured compatibility condition", "description": "Inspect the captured public evidence before making any source repair or assigning ownership.", "source_ids": ["src-captured"]}
        steps.append({"id": "step" + str(i), "title": "Inspect the captured evidence", "tool_name": name, "args": args,
                      "why": "This step supports the requested goal using observed evidence", "evidence_ids": [source["id"]],
                      "depends_on": ["step" + str(i-1)] if i else [], "expected_result": "A source-backed observation or independently read back task"})
    raw = {"summary": "Investigate the observed goal using a model-selected work plan", "success_criteria": ["The proposed work has an observed source-backed outcome"],
           "assumptions": [], "questions": [], "limitations": ["Public evidence does not establish employment"], "steps": steps}
    generation("propose_goal_plan", raw, final=native_json)
    record["evidence_binding"] = P.binding(record["evidence"])
    record["plan_evidence"] = copy.deepcopy(record["evidence"])
    record["proposal"] = C.validate_proposal(raw, record["goal"], record["evidence"], catalog, record["evidence_binding"])
    event("plan_proposed", plan_hash=record["proposal"]["hash"], revision=1)
    if terminal:
        for step in steps:
            key = generation("select_plan_step", {"step_id": step["id"]})
            if step["tool_name"] != "publish_task":observe(step["tool_name"], step["args"], key, step)
            else:
                text = P._text(record, record["proposal"], step, record["evidence"]);pubs = {}
                for target in ("jira", "slack"):
                    r = {"id": "goal-publication-" + C.sha(C.encode([id, record["proposal"]["hash"], step["id"], target])),
                         "goal_id": id, "plan_hash": record["proposal"]["hash"], "step_id": step["id"], "target": target,
                         "title": step["args"]["title"], "evidence_text": text, "contract_sha256": C.sha(target), "write_retry_allowed": False,
                         "status": "verified", "read_back_verified": True, "graph_linked": True,
                         "url": "https://example.atlassian.net/browse/KAN-99" if target == "jira" else "https://example.slack.com/archives/C123456/p1792334785098199",
                         "remote_id": "KAN-99" if target == "jira" else "1792334785.098199"}
                    if target == "slack":r["message_text"] = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    pubs[target] = r
                action = {"id": "goal-action-" + C.sha(C.encode([id, record["proposal"]["hash"], step["id"]])), "step_id": step["id"],
                          "kind": "publish_task", "status": "verified", "read_back_verified": True, "url": pubs["jira"]["url"],
                          "result": {"publications": pubs, "work_completion_claimed": False}}
                event("action_result", **key, step_id=step["id"], plan_hash=record["proposal"]["hash"], result=copy.deepcopy(action))
                record["actions"].append({**action, "plan_hash": record["proposal"]["hash"]})
        assessment = [{"criterion": raw["success_criteria"][0], "status": "supported", "reason": "The actual observation or task receipt was returned",
                       "evidence_ids": [source["id"]], "action_ids": [a["id"] for a in record["actions"]]}]
        args = {"summary": "The proposed steps have observed outcomes; no source repair is claimed", "criteria_assessment": assessment}
        key = generation("finish_goal", args)
        event("goal_reflection", **key, result={**args, "basis": "Model assessment; semantic entailment not independently certified"})
        record["status"] = "completed" if publish else "answered"
    return record


class Reader:
    def __init__(self, records):self.records = {r["id"]: r for r in records};self.calls = []
    def raw(self, id):self.calls.append(id);return json.dumps(self.records[id]).encode()


def pair():return [fixture_record(), fixture_record("b" * 32, extra_search=True, publish=True, terminal=True)]


def json_fixture(*,mixed=False,direct=False,terminal=False):
    """Synthetic successful JSON generations; no failed generation is parsed."""
    from server import goal_agent as A
    r=fixture_record(terminal=terminal,native_json=direct)
    catalog=P.catalog_from_source()[0]
    base=[copy.deepcopy(t) for t in catalog if t["name"] in P.READ_NAMES]+[copy.deepcopy(A.PLAN_TOOL)]
    rebuilt=[];replaced={};plan_seen=False;done=set()
    for e in r['events']:
        if e['type']=='plan_proposed':plan_seen=True
        if e['type'] in {'tool_result','action_result'} and e.get('step_id'):done.add(e['step_id'])
        if e['type'] in {'tool_call','assistant_final'} and not (mixed and e.get('tool_name')=='read_company_source' and not e.get('step_id') and not plan_seen):
            receipt=next(x for x in r['provider_receipts'] if x['id']==e['receipt_id'])
            content=e['result'] if e['type']=='assistant_final' else json.dumps({'tool_name':e['tool_name'],'args':e['args']})
            offered=copy.deepcopy(base)
            if plan_seen:
                ready=[s['id'] for s in r['proposal']['steps'] if s['id'] not in done and set(s['depends_on']).issubset(done)]
                if ready:offered.append({'name':'select_plan_step','description':'Actual test catalog selection','inputSchema':A._object({'step_id':{'type':'string','enum':ready}})})
                else:
                    offered.append({'name':'finish_goal','description':'Actual test catalog reflection','inputSchema':A._object({'summary':{'type':'string','minLength':15,'maxLength':1200},
                        'criteria_assessment':{'type':'array','minItems':1,'maxItems':6,'items':A._object({'criterion':{'type':'string','enum':r['proposal']['success_criteria']},
                        'status':{'type':'string','enum':['supported','not_met','unknown']},'reason':A._string(300),'evidence_ids':A._strings(12),'action_ids':A._strings(6)})}})})
            receipt.update(transport='json_decision',finish_reason='stop',assistant_content_sha256=C.sha(content),offered_catalog_sha256=C.sha(C.encode(offered)))
            invocation='host-json-'+C.sha(C.encode([receipt['id'],receipt['response_sha256'],content]))
            rebuilt.append({'type':'assistant_json_decision','receipt_id':receipt['id'],'result':content,'offered_catalog':offered,'catalog_sha256':receipt['offered_catalog_sha256'],
                            'selection_id':invocation,'id_origin':'host_assigned_json_decision'})
            if e['type']=='tool_call':
                replaced[e['tool_call_id']]=invocation
                e.update(type='tool_selection',tool_call_id=invocation,invocation_id=invocation,id_origin='host_assigned_json_decision')
            else:continue
        rebuilt.append(e)
    for i,e in enumerate(rebuilt):
        e['seq']=i
        if e['type']=='provider_response':e['finish_reason']=next(x['finish_reason'] for x in r['provider_receipts'] if x['id']==e['receipt_id'])
        if e.get('tool_call_id') in replaced:e['tool_call_id']=replaced[e['tool_call_id']]
    for evidence in r['evidence']+r['plan_evidence']:
        if evidence.get('observed_by_tool_call') in replaced:evidence['observed_by_tool_call']=replaced[evidence['observed_by_tool_call']]
    r['events']=rebuilt
    return r


@pytest.mark.parametrize('mixed,direct,terminal',[(False,False,False),(True,False,False),(False,True,False),(False,False,True)])
def test_public_proof_validates_truthful_json_selection_and_mixed_native_history(mixed,direct,terminal):
    r=json_fixture(mixed=mixed,direct=direct,terminal=terminal)
    result=P.verify_record(r,P.catalog_from_source()[0])
    assert result['json_decisions']>=1 and result['host_assigned_json_invocations']>=1
    assert 'json_decision' in result['selection_transports']
    assert ('native_chat_completions' in result['selection_transports'])==mixed
    assert result['current_criteria_reflection']==terminal


def test_historical_incomplete_json_generation_retains_real_usage_without_fake_decision():
    r=json_fixture()
    incomplete={'id':'actual-incomplete-response','model':'openai/gpt-oss-120b','transport':'json_decision','finish_reason':'length',
                'request_sha256':C.sha('actual-incomplete-request'),'response_sha256':C.sha('actual-truncated-response'),
                'usage':{'prompt_tokens':5199,'completion_tokens':1100,'total_tokens':6299}}
    r['provider_receipts'].insert(0,incomplete);r['provider_calls']+=1;r['total_tokens']+=6299
    result=P.verify_record(r,P.catalog_from_source()[0])
    assert result['provider_generations']==3 and result['json_decisions']==2 and result['measured_tokens']==6599
    assert not any(e.get('receipt_id')==incomplete['id'] for e in r['events'])


@pytest.mark.parametrize('fault',['content','catalog_hash','schema','read_schema','selection_id','invocation_id','native_claim','args','unknown_name','finish','missing_decision'])
def test_public_json_proof_rejects_substituted_decision_schema_or_forged_native_identity(fault):
    r=json_fixture();decision=next(e for e in r['events'] if e['type']=='assistant_json_decision')
    selected=next(e for e in r['events'] if e['type']=='tool_selection')
    receipt=next(x for x in r['provider_receipts'] if x['id']==decision['receipt_id'])
    if fault=='content':decision['result']=json.dumps({'tool_name':'read_company_source','args':{'source_id':'substituted'}})
    elif fault=='catalog_hash':decision['catalog_sha256']='a'*64
    elif fault in {'schema','read_schema'}:
        chosen=next(t for t in decision['offered_catalog'] if t['name']==('propose_goal_plan' if fault=='schema' else 'read_company_source'))
        chosen['inputSchema']={'type':'object','additionalProperties':True}
        decision['catalog_sha256']=receipt['offered_catalog_sha256']=C.sha(C.encode(decision['offered_catalog']))
    elif fault=='selection_id':decision['selection_id']='invented'
    elif fault=='invocation_id':selected['invocation_id']='native-looking-invented'
    elif fault=='native_claim':selected['type']='tool_call'
    elif fault=='args':selected['args']={'source_id':'substituted'}
    elif fault=='unknown_name':selected['tool_name']='shell'
    elif fault=='finish':receipt['finish_reason']='tool_calls'
    else:
        r['events'].remove(decision)
        for i,e in enumerate(r['events']):e['seq']=i
    with pytest.raises(P.ProofError):P.verify_record(r,P.catalog_from_source()[0])


def test_two_public_goal_records_have_real_observation_bound_plans_and_structural_variation():
    reader = Reader(pair());result = P.verify_pair(list(reader.records), reader)
    assert result["status"] == "verified_distinct_goal_records" and result["read_only"] is True
    assert result["different_plan_structures"] and result["different_selected_tool_sequences"]
    assert result["provider_get_performed"] is result["direct_graph_get_performed"] is result["semantic_entailment_certified"] is False
    assert len(reader.calls) == 4 and result["goals"][1]["current_criteria_reflection"] is True
    assert result["goals"][1]["verified_effect_receipts"] == 1


def test_static_catalog_matches_actual_shared_catalog_without_import_execution():
    from server import goal_graph
    catalog, digest = P.catalog_from_source()
    assert catalog == goal_graph.TOOLS + C.EFFECTS and P.digest(digest)


@pytest.mark.parametrize("native_json", [False, True])
def test_native_json_final_is_preserved_as_content_not_fabricated_tool_call(native_json):
    r = fixture_record(native_json=native_json)
    result = P.verify_record(r, P.catalog_from_source()[0])
    assert result["step_count"] == 1 and result["actual_read_observations"] == 1


@pytest.mark.parametrize("fault", ["id", "model", "usage", "request_hash", "response_hash", "transport", "missing_provider", "tokens", "count"])
def test_missing_substituted_or_forged_provider_generation_evidence_is_rejected(fault):
    r = fixture_record();receipt = r["provider_receipts"][0]
    if fault == "id":receipt["id"] = ""
    elif fault == "model":receipt["model"] = None
    elif fault == "usage":receipt["usage"]["total_tokens"] = 1
    elif fault == "request_hash":receipt["request_sha256"] = "bad"
    elif fault == "response_hash":receipt["response_sha256"] = "bad"
    elif fault == "transport":receipt["transport"] = "fabricated_native"
    elif fault == "missing_provider":r["provider_receipts"] = []
    elif fault == "tokens":r["total_tokens"] += 1
    else:r["provider_calls"] = 0
    with pytest.raises(P.ProofError):P.verify_record(r, P.catalog_from_source()[0])


@pytest.mark.parametrize("fault", ["proposal", "goal", "hash", "evidence", "call", "finish", "sequence", "invented_terminal", "source_kind", "binding"])
def test_goal_plan_and_actual_tool_episode_substitution_is_rejected(fault):
    r = fixture_record();observation = next(e for e in r["events"] if e["type"] == "tool_result")
    if fault == "proposal":r["proposal"]["steps"][0]["args"]["source_id"] = "other-source"
    elif fault == "goal":r["goal"] = "A completely different goal"
    elif fault == "hash":r["proposal"]["hash"] = "0" * 64
    elif fault == "evidence":r["evidence"][0]["id"] = "unknown"
    elif fault == "call":observation["tool_call_id"] = "invented-call"
    elif fault == "finish":r["provider_receipts"][0]["finish_reason"] = "stop"
    elif fault == "sequence":r["events"][0]["seq"] = 2
    elif fault == "invented_terminal":r["status"] = "answered"
    elif fault == "source_kind":observation["tool_name"] = "search_company_graph";observation["args"] = {"query": "source"}
    else:observation["result"]["binding"]["fingerprint"] = "f" * 64
    with pytest.raises(P.ProofError):P.verify_record(r, P.catalog_from_source()[0])


def test_same_goal_or_only_different_prose_does_not_establish_material_variation():
    a, b = fixture_record(), fixture_record("b" * 32)
    reader = Reader([a,b])
    with pytest.raises(P.ProofError, match="same goal"):P.verify_pair([a["id"],b["id"]],reader)
    b["goal"] += " with a different wording"
    # Rebuild a valid different-goal binding rather than relying on hash tampering.
    raw = next(e for e in b["events"] if e.get("tool_name") == "propose_goal_plan")["args"]
    b["proposal"] = C.validate_proposal(raw,b["goal"],b["plan_evidence"],P.catalog_from_source()[0],b["evidence_binding"])
    next(e for e in b["events"] if e["type"] == "plan_proposed")["plan_hash"] = b["proposal"]["hash"]
    with pytest.raises(P.ProofError, match="materially"):P.verify_pair([a["id"],b["id"]],Reader([a,b]))


@pytest.mark.parametrize("fault", ["missing_reflection", "criterion", "unobserved_action", "unmet", "pending_effect", "action_swap", "publication_text", "unapproved"])
def test_goal_completion_cannot_be_claimed_without_exact_effect_and_criterion_evidence(fault):
    r = fixture_record(publish=True,terminal=True)
    reflection = next(e for e in r["events"] if e["type"] == "goal_reflection")
    finish = next(e for e in r["events"] if e.get("tool_name") == "finish_goal")
    effect = next(e for e in r["events"] if e["type"] == "action_result")
    if fault == "missing_reflection":r["events"].remove(reflection)
    elif fault == "criterion":reflection["result"]["criteria_assessment"][0]["criterion"] = "invented success"
    elif fault == "unobserved_action":reflection["result"]["criteria_assessment"][0]["action_ids"] = ["made-up"]
    elif fault == "unmet":reflection["result"]["criteria_assessment"][0]["status"] = "not_met";finish["args"]["criteria_assessment"][0]["status"] = "not_met"
    elif fault == "pending_effect":effect["result"]["read_back_verified"] = False
    elif fault == "action_swap":r["actions"][0]["id"] = "other-action"
    elif fault == "publication_text":effect["result"]["result"]["publications"]["jira"]["evidence_text"] += " invented work"
    else:r["approved_actions"] = []
    with pytest.raises(P.ProofError):P.verify_record(r,P.catalog_from_source()[0])


def test_exact_publication_text_builder_matches_current_application_contract():
    from server import goal_actions
    r = fixture_record(publish=True)
    step = r["proposal"]["steps"][0]
    assert P._text(r,r["proposal"],step,r["evidence"]) == goal_actions._text(r,step)[1]


def test_two_fresh_public_reads_reject_changed_record_state():
    records=pair();reader=Reader(records);original=reader.raw
    def raw(id):
        value=original(id)
        if len(reader.calls)==2:return value+b" "
        return value
    reader.raw=raw
    with pytest.raises(P.ProofError,match="changed during"):P.verify_pair([r["id"] for r in records],reader)


@pytest.mark.parametrize("origin", ["http://example.com", "https://secret@example.com", "https://example.com/private", "https://example.com?token=private"])
def test_reader_rejects_credentialed_or_non_origin_urls(origin):
    with pytest.raises(P.ProofError):P.Reader(origin)


def test_reader_uses_only_get_and_no_authorization_or_provider_credential(monkeypatch):
    opener=Mock();opener.open.return_value=io.BytesIO(b"{}")
    monkeypatch.setattr(P.urllib.request,"build_opener",Mock(return_value=opener))
    r=P.Reader();assert r.raw("a"*32)==b"{}"
    request=opener.open.call_args.args[0]
    assert request.get_method()=="GET" and "Authorization" not in request.headers
    assert request.full_url==P.ORIGIN+"/api/public/goals/"+"a"*32


def test_invalid_cli_identity_never_reads_network_or_prints_private_origin(monkeypatch,tmp_path,capsys):
    reader=Mock();monkeypatch.setattr(P,"Reader",reader)
    output=tmp_path/"proof.json"
    assert P.main(["--goal-id","bad","--goal-id","b"*32,"--origin","https://secret@example.com","--output",str(output)])==1
    reader.assert_not_called()
    assert "secret" not in capsys.readouterr().out and json.loads(output.read_text())["status"]=="unconfirmed"


def record_with_rejected_search():
    r = fixture_record()
    prefix = []
    def event(type, **fields):
        row = {"seq": len(prefix), "type": type, **fields};prefix.append(row);return row
    receipts = []
    for index in range(2):
        receipt = {"id": "chatcmpl-search-" + str(index), "model": "openai/gpt-oss-20b", "usage": {
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "finish_reason": "tool_calls",
            "request_sha256": C.sha("search-request-" + str(index)), "response_sha256": C.sha("search-response-" + str(index)), "transport": "native_chat_completions"}
        receipts.append(receipt)
        event("provider_response", receipt_id=receipt["id"], finish_reason="tool_calls")
        key = {"receipt_id": receipt["id"], "tool_call_id": "actual-search-" + str(index)}
        args = {"query": "redis-py 8.1.0 failure"}
        event("tool_call", **key, tool_name="search_company_graph", args=args)
        if index == 0:
            event("tool_result", **key, tool_name="search_company_graph", args=args, status="succeeded", evidence_ids=[],
                  result={"observation": {"entities": []}, "evidence": [], "binding": {"fingerprint": P.binding([])}})
        else:
            event("tool_rejected", **key, tool_name="search_company_graph", args=args,
                  error="Repeated empty literal search was not executed", previous_observation_seq=2)
    r["provider_receipts"] = receipts + r["provider_receipts"]
    r["provider_calls"] += 2;r["total_tokens"] += 300
    r["events"] = prefix + [{**e, "seq": e["seq"] + len(prefix)} for e in r["events"]]
    return r


def test_actual_rejected_native_selection_is_not_counted_as_a_successful_graph_read():
    r = record_with_rejected_search()
    proof = P.verify_record(r,P.catalog_from_source()[0])
    assert proof["native_selections_rejected_without_execution"] == 1
    assert proof["actual_read_observations"] == 2
    assert proof["model_selected_read_tools"] == ["search_company_graph", "read_company_source"]
    assert proof["provider_generations"] == 4


@pytest.mark.parametrize("fault", ["receipt", "call", "query", "previous", "fake_result", "fake_observation"])
def test_rejected_selection_cannot_fabricate_observation_or_lose_actual_protocol_binding(fault):
    r = record_with_rejected_search();rejected = next(e for e in r["events"] if e["type"] == "tool_rejected")
    if fault == "receipt":rejected["receipt_id"] = "invented"
    elif fault == "call":rejected["tool_call_id"] = "invented"
    elif fault == "query":rejected["args"] = {"query": "another-query"}
    elif fault == "previous":rejected["previous_observation_seq"] = 0
    elif fault == "fake_result":rejected["result"] = {"observation": {"entities": []}}
    else:
        r["events"].append({"seq":len(r["events"]),"type":"tool_result","receipt_id":rejected["receipt_id"],"tool_call_id":rejected["tool_call_id"],
                            "tool_name":"search_company_graph","args":rejected["args"],"status":"succeeded","evidence_ids":[],
                            "result":{"observation":{"entities":[]},"evidence":[],"binding":{"fingerprint":P.binding([])}}})
    with pytest.raises(P.ProofError):P.verify_record(r,P.catalog_from_source()[0])


@pytest.mark.parametrize("category,args",[("unknown_captured_source",{"source_id":"environment-entity-id"}),
                                           ("invalid_read_arguments",{"source_id":12})])
def test_actual_invalid_read_rejection_preserves_native_selection_without_inventing_source_observation(category,args):
    r=record_with_rejected_search()
    selected=next(e for e in r["events"] if e.get("tool_call_id")=="actual-search-1" and e["type"]=="tool_call")
    rejected=next(e for e in r["events"] if e["type"]=="tool_rejected")
    selected.update(tool_name="read_company_source",args=args)
    rejected.update(tool_name="read_company_source",args=args,category=category,error="Read was rejected before any observation")
    rejected.pop("previous_observation_seq")
    result=P.verify_record(r,P.catalog_from_source()[0])
    assert result["native_selections_rejected_without_execution"]==1
    assert result["actual_read_observations"]==2 and result["model_selected_read_tools"]==["search_company_graph","read_company_source"]
    rejected["category"]="unknown_graph_entity"
    with pytest.raises(P.ProofError):P.verify_record(r,P.catalog_from_source()[0])


def test_unknown_effect_error_category_cannot_be_retried_as_a_safe_read_rejection():
    r=record_with_rejected_search()
    rejected=next(e for e in r["events"] if e["type"]=="tool_rejected")
    rejected["category"]="provider_write_failed"
    with pytest.raises(P.ProofError):P.verify_record(r,P.catalog_from_source()[0])
