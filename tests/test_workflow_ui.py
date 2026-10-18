"""Execute the actual vanilla-JS workflow UI against adversarial fake API data."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
HARNESS = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
  constructor(tag,text){this.tag=tag;this.children=[];this.own=text||'';this.hidden=false;}
  set textContent(value){this.own=String(value);this.children=[];}
  get textContent(){return this.own+this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
  set innerHTML(value){throw Error('Unsafe HTML rendering attempted');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.own='';this.children=[...children];}
}
const nodes=new Map(),calls=[],delays=[];let saves=0;
const context={URL,Set,console,window:{location:{origin:'https://baton-workspace.vercel.app'}},
  authenticated:input.authenticated!==false,selected:{id:input.selected||'FalkorDB/FalkorDB#3246'},
  $:id=>nodes.get(id),el:(tag,text,cls)=>{const x=new Element(tag,text);x.className=cls;return x;},
  notice:message=>{context.lastNotice=message;},load:async()=>{saves++;},
  localStorage:{getItem:()=>input.saved||null,setItem:()=>{}},
  setTimeout:(resolve,delay)=>{delays.push(delay);resolve();}};
let sequence=[...(input.records||[])],index=0;
context.api=async(path,body)=>{calls.push({path,body});if(input.failAt===calls.length-1)throw Error('mock network unavailable');
  const value=sequence[Math.min(index++,sequence.length-1)];return JSON.parse(JSON.stringify(value));};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
for(const id of ['workflow-result','workflow-refresh','workflow-progress','workflow-profile-note','workflow-start-profile','workflow-start-selected'])nodes.set(id,new Element('div'));
function tree(node){return {tag:node.tag,text:node.own,href:node.href||null,children:node.children.map(x=>typeof x==='string'?x:tree(x))};}
(async()=>{
 const ui=context.window.BatonWorkflow;
 if(input.mode==='review')return console.log(JSON.stringify(ui.reviewState(input.record)));
 if(input.mode==='link')return console.log(JSON.stringify({url:ui.safeLink(input.url)}));
 if(input.mode==='render')ui.render(input.record);
 if(input.mode==='controls')ui.controls();
 if(input.mode==='hydrate')await ui.hydrate();
 if(input.mode==='hydrate-start'){await ui.hydrate();await ui.start();}
 if(input.mode==='poll')await ui.poll(input.identity||'workflow-test');
 if(input.mode==='start')await ui.start();
 if(input.mode==='hydrate-start-race'){
   let release;context.api=(path,body)=>{calls.push({path,body});if(calls.length===1)return new Promise(resolve=>{release=resolve;});return Promise.resolve(input.records[calls.length===2?1:2]);};
   const hydration=ui.hydrate();await Promise.resolve();await ui.start();release(input.records[0]);await hydration;
 }
 if(input.mode==='race'){
   let release;context.api=path=>{calls.push({path});if(calls.length===1)return new Promise(resolve=>{release=resolve;});return Promise.resolve(input.records[1]);};
   const old=ui.poll('workflow-old');await Promise.resolve();const fresh=ui.poll('workflow-new');await fresh;release(input.records[0]);await old;
 }
 console.log(JSON.stringify({root:tree(nodes.get('workflow-result')),text:nodes.get('workflow-result').textContent,
   progress:nodes.get('workflow-progress').textContent,refreshHidden:nodes.get('workflow-refresh').hidden,profileDisabled:nodes.get('workflow-start-profile').disabled,
   selectedDisabled:nodes.get('workflow-start-selected').disabled,note:nodes.get('workflow-profile-note').textContent,
   calls,delays,loads:saves,notice:context.lastNotice||null}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
"""


def js(**payload):
    assert NODE, "Node.js is required to execute the actual browser workflow code"
    result = subprocess.run([NODE, "-e", HARNESS, str(ROOT / "web/workflows.js")],
        input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=15)
    return json.loads(result.stdout)


@pytest.fixture
def completed():
    return {"id": "workflow-test", "item_id": "FalkorDB/FalkorDB#3246", "status": "completed",
        "runner": {"provider": "GitHub Actions", "verified": True, "run_id": 123, "run_url": "https://github.com/example/repo/actions/runs/123"},
        "checks": {"verified": True, "passed": 530, "failed": 0, "ignored": 17, "total": 547,
                   "results": [{"name": "graph_library", "exit_code": 0, "test_summaries": [{"passed": 530, "failed": 0}]}]},
        "publish_targets": ["jira", "slack"],
        "publication": {"jira": {"status": "verified", "read_back_verified": True},
                        "slack": {"status": "verified", "read_back_verified": True}}}


def test_actual_ui_requires_test_and_provider_readback_evidence(completed):
    assert js(mode="review", record=completed)["completed"] is True


@pytest.mark.parametrize("mutation", ["exit-zero-only", "zero-tests", "skipped-only", "failed-test", "unverified", "historical-codex", "runner-unverified", "runner-proof-missing", "wrong-run", "missing-run", "publication-created", "readback-false", "readback-missing", "partial", "failed", "unknown"])
def test_false_or_partial_success_never_becomes_completed(completed, mutation):
    if mutation == "exit-zero-only": completed["checks"] = {"results": [{"exit_code": 0}]}
    elif mutation == "zero-tests": completed["checks"].update(passed=0, failed=0)
    elif mutation == "skipped-only": completed["checks"].update(passed=0, failed=0, ignored=530)
    elif mutation == "failed-test": completed["checks"]["failed"] = 1
    elif mutation == "unverified": completed["checks"]["verified"] = False
    elif mutation == "historical-codex": completed["runner"]["provider"] = "Codex isolated Docker runner"
    elif mutation == "runner-unverified": completed["runner"]["verified"] = False
    elif mutation == "runner-proof-missing": completed["runner"].pop("verified")
    elif mutation == "wrong-run": completed["runner"]["run_id"] = 456
    elif mutation == "missing-run": completed["runner"].pop("run_url")
    elif mutation == "publication-created": completed["publication"]["slack"]["status"] = "created"
    elif mutation == "readback-false": completed["publication"]["jira"]["read_back_verified"] = False
    elif mutation == "readback-missing": completed["publication"]["jira"].pop("read_back_verified")
    else: completed["status"] = mutation
    assert js(mode="review", record=completed)["completed"] is False


def test_partial_publication_errors_and_test_logs_remain_visible_as_text(completed):
    completed.update(status="partial", error="Slack publication needs reconciliation")
    completed["publication"]["slack"] = {"status": "failed", "error": "Provider read-back failed"}
    completed["checks"]["results"][0]["log"] = '<script>window.pwned=true</script>'
    completed["repairs"] = [{"attempt": 1, "diff": '<img src=x onerror=alert(1)>', "provider_response_id": "repair-receipt"}]
    result = js(mode="render", record=completed)
    assert "publication needs attention" in result["text"]
    assert "Provider read-back failed" in result["text"]
    assert '<script>window.pwned=true</script>' in result["text"]
    assert '<img src=x onerror=alert(1)>' in result["text"]
    assert "repair-receipt" in result["text"]
    assert "not complete" in result["text"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://github.com.evil.test/run", "https://user:secret@github.com/a/b", "https://evil.test/log", "http://github.com/a/b"])
def test_runner_and_log_links_reject_unsafe_destinations(url):
    assert js(mode="link", url=url)["url"] is None


def test_unsupported_selected_work_has_no_cloud_profile():
    result = js(mode="controls", selected="FalkorDB/falkordb-py#308")
    assert result["selectedDisabled"] is True
    assert "no approved execution profile" in result["note"]
    assert result["profileDisabled"] is False  # Standalone button explicitly selects #3246.


def test_anonymous_operator_cannot_submit_workflow(completed):
    result = js(mode="start", authenticated=False, records=[completed])
    assert result["calls"] == []
    assert "Sign in" in result["notice"]


def test_start_makes_exactly_one_post_then_reads_the_same_receipt(completed):
    result = js(mode="start", records=[{"id": "workflow-test", "status": "queued"}, completed])
    posts = [call for call in result["calls"] if "body" in call]
    assert len(posts) == 1
    assert posts[0]["body"] == {"item_id": "FalkorDB/FalkorDB#3246", "allow_repair": True, "publish_targets": ["jira", "slack"]}
    assert result["calls"][1]["path"] == "/api/public/workflows/workflow-test"
    assert result["loads"] == 1


def test_unknown_submission_outcome_is_never_automatically_reposted():
    result = js(mode="start", failAt=0)
    assert len(result["calls"]) == 1
    assert "did not repeat the POST" in result["progress"]


def test_poll_limit_pauses_without_fabricating_failure_or_reposting(completed):
    completed["status"] = "running"
    result = js(mode="poll", records=[completed])
    assert len(result["calls"]) == 90
    assert all("body" not in call for call in result["calls"])
    assert result["delays"] == [5000] * 90
    assert "may still be active" in result["progress"]
    assert "No new run was submitted".lower() in result["progress"].lower()


def test_poll_network_failure_does_not_claim_runner_failure(completed):
    result = js(mode="poll", records=[completed], failAt=0)
    assert "No success or failure has been substituted" in result["progress"]
    assert len(result["calls"]) == 1
    assert result["refreshHidden"] is False


def test_stale_poll_response_cannot_overwrite_newer_workflow(completed):
    older = copy.deepcopy(completed); older["id"] = "workflow-old"
    newer = copy.deepcopy(completed); newer["id"] = "workflow-new"
    result = js(mode="race", records=[older, newer])
    assert "Workflow workflow-new" in result["text"]
    assert "Workflow workflow-old" not in result["text"]


def test_changed_workflow_identity_is_rejected(completed):
    completed["id"] = "workflow-unrequested"
    result = js(mode="poll", records=[completed])
    assert "identity does not match" in result["progress"]
    assert "Checks and requested publication verified" not in result["text"]


def test_transitional_internal_shapes_do_not_crash_or_display_completed(completed):
    completed.update(status="succeeded", checks=[{"exit_code": 0}], evidence={"url": "https://github.com/example/repo"},
                     repairs={}, stages={}, publish_targets={"jira": True})
    result = js(mode="render", record=completed)
    assert "Code verification is not confirmed" in result["text"]
    assert "Checks and requested publication verified" not in result["text"]


def test_fresh_browser_reads_public_latest_without_posting(completed):
    result = js(mode="hydrate", records=[{"latest": completed, "configured": True}])
    assert result["calls"] == [{"path": "/api/public/workflows"}]
    assert "Checks and requested publication verified" in result["text"]


def test_saved_browser_receipt_resumes_exact_id_with_get_only(completed):
    result = js(mode="hydrate", saved="workflow-test", records=[completed])
    assert result["calls"] == [{"path": "/api/public/workflows/workflow-test"}]
    assert "Checks and requested publication verified" in result["text"]


def test_unconfigured_deployment_disables_cloud_submission():
    result = js(mode="hydrate", records=[{"latest": None, "configured": False}])
    assert result["profileDisabled"] is True
    assert result["selectedDisabled"] is True
    assert "not configured" in result["note"]
    assert all("body" not in call for call in result["calls"])


def test_unconfigured_receipt_cannot_be_followed_by_programmatic_post():
    result = js(mode="hydrate-start", records=[{"latest": None, "configured": False}])
    assert result["calls"] == [{"path": "/api/public/workflows"}]
    assert "not configured" in result["notice"]


def test_actual_graph_investigation_and_runner_limits_are_reviewable(completed):
    completed["limits"] = {"scope": "Pinned public source; RDB reload not part of this cloud profile"}
    completed["investigation"] = {"trace": [{"tool": "inspect_primary_source", "source_ids": ["source-real"]}]}
    result = js(mode="render", record=completed)
    assert "RDB reload not part" in result["text"]
    assert "source-real" in result["text"]
    assert "inspect_primary_source" in result["text"]


def test_slow_latest_receipt_cannot_overwrite_operator_new_run(completed):
    older = copy.deepcopy(completed); older["id"] = "workflow-old"
    newer = copy.deepcopy(completed); newer["id"] = "workflow-new"
    result = js(mode="hydrate-start-race", records=[{"latest": older, "configured": True}, {"id": "workflow-new", "status": "queued"}, newer])
    assert "Workflow workflow-new" in result["text"]
    assert "Workflow workflow-old" not in result["text"]
    assert len([call for call in result["calls"] if "body" in call]) == 1


@pytest.mark.parametrize("passed,failed,ignored", [(534, 0, 17), (12, 2, 3)])
def test_counts_describe_executions_including_reruns_not_unique_tests(completed, passed, failed, ignored):
    completed["checks"].update(passed=passed, failed=failed, ignored=ignored)
    result = js(mode="render", record=completed)
    assert f"{passed} passing test executions (includes targeted reruns)" in result["text"]
    assert f"{failed} failed" in result["text"]
    assert f"{ignored} ignored / not run" in result["text"]
    assert f"{passed} tests passed" not in result["text"]
