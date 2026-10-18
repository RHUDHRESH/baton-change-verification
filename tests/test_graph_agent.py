"""Agent safety and tool protocol contracts; provider responses are mocked."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

import pytest
from server import graph_agent as agent


@pytest.fixture
def investigation(tmp_path):
    graph=MagicMock(name="graph")
    graph.name="test-graph"
    snapshot={"graph":"test-graph","items":[{"id":"repo#1","number":1,"body":"Public issue description","source_ids":["s1"]}]}
    with patch.object(agent.public,"snapshot",return_value=snapshot),patch.object(agent.G,"connect") as connection:
        connection.return_value.select_graph.return_value=graph
        yield agent.Investigation(tmp_path,6379,"repo#1","a"*32),graph


def test_action_denied_before_graph_and_source_inspection(investigation):
    run,graph=investigation
    with pytest.raises(ValueError,match="inspect"):
        run.call("save_verification_task",{"title":"Verify the source report","reason":"Verify it against the public issue evidence","source_ids":["s1"]})
    graph.query.assert_not_called()


def test_unknown_tool_and_cross_item_scope_denied(investigation):
    run,_=investigation
    for name,args in [("execute_cypher",{"query":"DELETE"}),("read_work_item",{"item_id":"other#2"})]:
        with pytest.raises(ValueError):
            run.call(name,args)


def test_multihop_query_result_preserves_limitations(investigation):
    run,graph=investigation
    graph.ro_query.side_effect=[SimpleNamespace(result_set=[["repo#2","Related PR","contributor"]]),
                                SimpleNamespace(result_set=[["file.py",["contributor"],["repo#1","repo#2"]]])]
    result=json.loads(run.call("follow_connections",{"item_id":"repo#1"})["content"][0]["text"])
    assert result["file_coverage"][0]["single_contributor_in_sample"]
    assert "not proof of dependency" in result["paths"][0]["via"]
    assert "ownership" in result["limits"]
    assert all(call.args[1]=={"id":"repo#1"} for call in graph.ro_query.call_args_list)


def test_source_outside_selected_item_denied(investigation):
    run,_=investigation
    with pytest.raises(ValueError,match="not evidence"):
        run.call("read_source",{"source_id":"other-source"})


def test_uninspected_citation_cannot_authorize_action(investigation):
    run,_=investigation
    run.visited={t["name"] for t in agent.TOOLS}
    run.inspected={"s1"}
    with pytest.raises(ValueError,match="every citation"):
        run.call("save_verification_task",{"title":"Verify the source report","reason":"Verify it against the public issue evidence","source_ids":["invented"]})


def test_action_requires_successful_graph_readback(investigation):
    run,graph=investigation
    source={"payload":{"number":1,"title":"Actual issue"},"sha256":"captured-sha","url":"https://api.github.com/repos/test/issues","fetched_at":"2026-10-18"}
    run.observations["source:s1"]={**{k:source[k] for k in ("sha256","url","fetched_at")},"payload_sha256":agent.public.sha(json.dumps(source["payload"],sort_keys=True,ensure_ascii=False))}
    run.visited={t["name"] for t in agent.TOOLS}
    run.inspected={"s1"}
    graph.ro_query.return_value.result_set=[]
    control=MagicMock()
    control.lock.return_value=nullcontext()
    with patch.object(agent,"connect",return_value=control),patch.object(agent.public,"evidence",return_value=source),patch.object(agent.public,"create_task",return_value={"id":"task-test"}):
        with pytest.raises(RuntimeError,match="verified"):
            run.call("save_verification_task",{"title":"Verify the source report","reason":"Verify it against the public issue evidence","source_ids":["s1"]})
    assert run.action is None


def test_tool_arguments_reject_extra_fields_and_bad_types(investigation):
    run,_=investigation
    for args in ({"item_id":"repo#1","query":"anything"},{"item_id":[]},{}):
        with pytest.raises(ValueError):
            run.call("read_work_item",args)


def test_agent_run_identity_cannot_traverse_storage(tmp_path):
    with pytest.raises(ValueError,match="Invalid agent"):
        agent.read_run(tmp_path,"../../secret")


@pytest.mark.parametrize("mutation",["payload","sha256","url","fetched_at","missing"])
def test_independent_source_reread_detects_tampering(investigation,mutation):
    run,_=investigation
    source={"payload":{"number":1,"title":"Actual issue"},"sha256":"captured-sha","url":"https://api.github.com/repos/test/issues","fetched_at":"2026-10-18"}
    with patch.object(agent.public,"evidence",return_value=source):
        run.call("read_source",{"source_id":"s1"})
    changed={**source,mutation:"tampered"}
    if mutation=="payload":
        changed["payload"]={"number":1,"title":"Changed despite unchanged raw hash"}
    with patch.object(agent.public,"evidence",return_value=None if mutation=="missing" else changed):
        with pytest.raises(ValueError,match="independently retrieved"):
            run.verify_sources(["s1"])


def run_harness(investigation,monkeypatch,mode="success"):
    run,graph=investigation
    stored={}
    monkeypatch.setattr(agent.public,"write",lambda data,key,value:stored.update({key:json.loads(json.dumps(value))}))
    monkeypatch.setattr(agent.public,"read",lambda data,key,default=None:stored.get(key,default))
    source={"payload":{"number":1,"title":"Actual issue","body":"Reproduce the reported timeout"},"sha256":"captured-sha","url":"https://api.github.com/repos/test/issues","fetched_at":"2026-10-18"}
    monkeypatch.setattr(agent.public,"evidence",lambda *_:source)
    def read(query,args):
        if query==agent.ITEM_QUERY:
            rows=[[{"id":"repo#1","title":"Actual issue"},"repo"]]
        elif query==agent.PATH_QUERY:
            rows=[["repo#2","Related change","contributor"]]
        elif query==agent.FILE_QUERY:
            rows=[["file.py",["contributor"],["repo#1"]]]
        else:
            rows=[["task-test","repo#1","Reproduce the reported timeout","todo"]]
        return SimpleNamespace(result_set=rows)
    graph.ro_query.side_effect=read
    control=MagicMock()
    control.set.return_value=True
    control.lock.side_effect=lambda *a,**k:nullcontext()
    monkeypatch.setattr(agent,"connect",lambda *_:control)
    monkeypatch.setattr(agent,"Investigation",lambda *a:run)
    monkeypatch.setattr(agent.public,"create_task",lambda *a,**k:{"id":"task-test"})
    observed=[]
    def select(messages,tools,timeout):
        observed.append((messages,tools,timeout))
        if mode=="provider_failure":
            raise RuntimeError("Groq tool selection returned HTTP 429; no result was substituted")
        if mode=="incomplete_generation":
            raise agent.ProviderProtocolError("Provider did not finish a complete tool selection",{"id":"incomplete","usage":{"total_tokens":321}})
        step=len(observed)
        name=["read_work_item","follow_connections","read_source","save_verification_task"][step-1]
        args={"item_id":"repo#1"} if step<3 else ({"source_id":"s1"} if step==3 else {"title":"Reproduce the reported timeout","reason":"Verify the reported behavior against the captured issue","source_ids":["s1"]})
        if mode=="wrong_stage":
            name="save_verification_task"
        if mode=="wrong_item":
            args={"item_id":"3250"}
        if mode=="uninspected_citation" and step==4:
            args["source_ids"]=["s2"]
        message={"content":None,"tool_calls":[{"id":"call-"+str(step),"type":"function","function":{"name":name,"arguments":json.dumps(args)}}]}
        if mode=="malformed_arguments":
            message["tool_calls"][0]["function"]["arguments"]="{not json"
        if mode=="multiple_calls":
            message["tool_calls"]*=2
        usage={"prompt_tokens":800,"completion_tokens":200,"total_tokens":1000 if mode!="over_budget" else 8000}
        return message,{"id":"provider-"+str(step),"model":"test-model","usage":usage,"response_sha256":"hash"}
    monkeypatch.setattr(agent,"completion",select)
    return run,graph,observed


def test_four_call_run_gates_action_and_keeps_auditable_receipts(investigation,monkeypatch):
    run,_,observed=run_harness(investigation,monkeypatch)
    result=agent.run(run.data,run.port,run.item_id)
    assert result["status"]=="succeeded"
    assert result["budget"]["provider_calls"]==4
    assert result["budget"]["used_tokens"]==4000
    assert result["policy"]["reachable_layers"]==[["read_work_item"],["follow_connections","read_source"],["save_verification_task"]]
    assert all(0<timeout<=22 for _,_,timeout in observed)
    assert [x["request"]["params"]["name"] for x in result["trace"]]==["read_work_item","follow_connections","read_source","save_verification_task"]
    assert result["action"]["evidence_receipts"][0]["check"]=="independent stored-source reread"
    assert result["action"]["verification"]["reason_entailment"].startswith("not evaluated")
    assert all(t["function"]["name"]!="save_verification_task" for _,tools,_ in observed[:3] for t in tools)
    assert observed[0][1][0]["function"]["parameters"]["properties"]["item_id"]["enum"]==["repo#1"]
    assert "enum" not in agent.TOOLS[0]["inputSchema"]["properties"]["item_id"]
    assert agent.read_run(run.data,result["id"])["action"]==result["action"]
    # Exact query-bearing originals survive curation; later contexts keep graph facts.
    assert agent.ITEM_QUERY in result["trace"][0]["result"]["content"][0]["text"]
    final_tools=[json.loads(m["content"]) for m in observed[-1][0] if m["role"]=="tool"]
    assert final_tools[0]["archive"]["result_sha256"]==result["trace"][0]["result_sha256"]
    assert final_tools[1]["observation"]["paths"][0]["work_item"]=="repo#2"
    assert "sampled" in final_tools[1]["observation"]["limits"].lower() or "sample" in final_tools[1]["observation"]["limits"].lower()
    assert result["context_curation"][-1]["active_characters"]<result["context_curation"][-1]["original_characters"]


def test_final_schema_only_offers_inspected_sources_from_multi_source_item(investigation,monkeypatch):
    run,_,observed=run_harness(investigation,monkeypatch)
    run.item["source_ids"]=["s1","s2","s3"]
    result=agent.run(run.data,run.port,run.item_id)
    assert result["status"]=="succeeded" and len(observed)==4
    source_tool=next(t["function"] for t in observed[2][1] if t["function"]["name"]=="read_source")
    assert source_tool["parameters"]["properties"]["source_id"]["enum"]==["s1","s2","s3"]
    final_tool=observed[3][1][0]["function"]
    assert final_tool["name"]=="save_verification_task"
    citations=final_tool["parameters"]["properties"]["source_ids"]
    assert citations["items"]["enum"]==["s1"] and citations["maxItems"]==1
    assert result["action"]["source_ids"]==["s1"]
    assert "enum" not in agent.ACTION["inputSchema"]["properties"]["source_ids"]["items"]
    assert agent.ACTION["inputSchema"]["properties"]["source_ids"]["maxItems"]==5


def test_ignoring_dynamic_citation_enum_still_fails_closed(investigation,monkeypatch):
    run,_,observed=run_harness(investigation,monkeypatch,"uninspected_citation")
    run.item["source_ids"]=["s1","s2"]
    result=agent.run(run.data,run.port,run.item_id)
    assert result["status"]=="failed" and len(observed)==4 and result["action"] is None
    assert "every citation must have been inspected" in result["error"]
    assert result["trace"][-1]["request"]["params"]["arguments"]["source_ids"]==["s2"]


@pytest.mark.parametrize("mode,phase",[("provider_failure","provider"),("wrong_stage","selection_validation"),("over_budget","provider"),("incomplete_generation","provider"),("wrong_item","tool_execution"),("malformed_arguments","selection_validation"),("multiple_calls","selection_validation")])
def test_failed_runs_persist_failure_stage_without_action(investigation,monkeypatch,mode,phase):
    run,_,observed=run_harness(investigation,monkeypatch,mode)
    result=agent.run(run.data,run.port,run.item_id)
    assert result["status"]=="failed" and result["action"] is None
    assert result["failure"]["phase"]==phase
    assert len(observed)==1
    assert result["failure"]["completed_tools"]==0
    if mode in {"wrong_stage","wrong_item","malformed_arguments","multiple_calls"}:
        assert result["trace"][0]["result"]["isError"]
        if mode=="wrong_item":
            assert result["trace"][0]["request"]["params"]["arguments"]=={"item_id":"3250"}
    else:
        assert not result["trace"]
    if mode=="incomplete_generation":
        assert result["budget"]["used_tokens"]==321
    assert agent.read_run(run.data,result["id"])["failure"]==result["failure"]


def test_deadline_prevents_provider_or_tool_execution(investigation,monkeypatch):
    run,_,observed=run_harness(investigation,monkeypatch)
    clock=iter([0,100,100])
    monkeypatch.setattr(agent.time,"monotonic",lambda:next(clock))
    result=agent.run(run.data,run.port,run.item_id)
    assert result["status"]=="failed" and "deadline" in result["error"]
    assert not observed and not result["trace"]


def test_changed_graph_blocks_task_write(investigation,monkeypatch):
    run,_=investigation
    run.visited={t["name"] for t in agent.TOOLS}
    run.inspected={"s1"}
    control=MagicMock()
    control.lock.return_value=nullcontext()
    monkeypatch.setattr(agent,"connect",lambda *_:control)
    monkeypatch.setattr(agent.public,"snapshot",lambda *_:{"graph":"new-import"})
    with patch.object(agent.public,"create_task") as write:
        with pytest.raises(ValueError,match="graph changed"):
            run.call("save_verification_task",{"title":"Verify the source report","reason":"Verify it against the public issue evidence","source_ids":["s1"]})
    write.assert_not_called()


@pytest.mark.parametrize("rule,error",[
    ({"id":"bad","when":"root_read","tools":["invented_tool"]},"unknown tool"),
    ({"id":"bad","when":"invented_condition","tools":["read_source"]},"unknown predicate"),
    ({"id":"bad","when":"root_read","tools":["read_work_item"]},"own enabling tool"),
    ({"id":"bad","when":"item_scope","tools":["read_source"]},"argument binding"),
    ({"id":"bad","when":"inspected_citations","tools":["follow_connections"]},"Write-only"),
])
def test_static_policy_rejects_inoperable_bindings(rule,error):
    with pytest.raises(ValueError,match=error):
        agent.compile_policy(agent.TOOLS+[agent.ACTION],[rule])


def test_static_policy_rejects_missing_enabler_and_cross_rule_cycle():
    with pytest.raises(ValueError,match="no enabling tool"):
        agent.compile_policy(agent.TOOLS[1:]+[agent.ACTION])
    cycle=[{"id":"a","when":"root_read","tools":["follow_connections"]},
           {"id":"b","when":"connections_read","tools":["read_work_item"]}]
    with pytest.raises(ValueError,match="unreachable cycle"):
        agent.compile_policy(agent.TOOLS+[agent.ACTION],cycle)


def test_invalid_policy_fails_before_any_provider_call(investigation,monkeypatch):
    run,_,observed=run_harness(investigation,monkeypatch)
    monkeypatch.setattr(agent,"POLICY_RULES",[{"id":"bad","when":"item_scope","tools":["read_source"]}])
    result=agent.run(run.data,run.port,run.item_id)
    assert result["status"]=="failed" and result["failure"]["phase"]=="policy_validation"
    assert result["budget"]["provider_calls"]==0 and not observed


def test_policy_receipt_binds_schemas_and_predicate_tables():
    catalog=json.loads(json.dumps(agent.TOOLS+[agent.ACTION]))
    original=agent.compile_policy(catalog)
    catalog[0]["inputSchema"]["properties"]["item_id"]["maxLength"]=199
    changed=agent.compile_policy(catalog)
    assert original["sha256"]!=changed["sha256"]
    assert original["prerequisites"]==changed["prerequisites"]
