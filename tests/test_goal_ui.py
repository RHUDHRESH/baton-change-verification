"""Exercise the actual dependency-free goal UI; mocked responses prove rendering only."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const nodes=new Map(),calls=[],delays=[];
class Element {
 constructor(tag,text){this.tag=tag;this.children=[];this.own=text||'';this.hidden=false;this.value='';this.checked=false;}
 set id(value){this.identity=value;nodes.set(value,this);}get id(){return this.identity;}
 set textContent(value){this.own=String(value);this.children=[];}get textContent(){return this.own+this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
 set innerHTML(value){throw Error('Unsafe HTML rendering');}
 append(...children){this.children.push(...children);}replaceChildren(...children){this.own='';this.children=[...children];}focus(){this.focused=true;}
}
let index=0;
const context={URL,Set,Map,console,window:{location:{origin:'https://baton-workspace.vercel.app'},crypto:{randomUUID:()=> 'test-idempotency-key'}},authenticated:input.authenticated!==false,
 $:id=>nodes.get(id),el:(tag,text,cls)=>{const e=new Element(tag,text);e.className=cls;return e;},notice:message=>context.noticeText=message,
 setTimeout:(resolve,delay)=>{delays.push(delay);resolve();},api:async(path,body)=>{calls.push(body===undefined?{path}:{path,body});if(input.failAt===calls.length-1)throw Error('mock unavailable');return JSON.parse(JSON.stringify(input.records[Math.min(index++,input.records.length-1)]));}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
for(const id of ['goal-input','goal-submit','goal-refresh','goal-continue','goal-act','goal-auth-note','goal-progress','goal-result','goal-state','goal-plan','goal-timeline','goal-evidence','goal-receipts','goal-approvals','goal-examples'])nodes.set(id,new Element('div'));
nodes.get('goal-input').value=input.goal||'Investigate this actual public change';
const ui=context.window.BatonGoal;
function tree(e){return {tag:e.tag,text:e.own,href:e.href||null,id:e.id||null,children:e.children.map(x=>typeof x==='string'?x:tree(x))};}
(async()=>{
 if(input.mode==='link')return console.log(JSON.stringify({url:ui.safeLink(input.url)}));
 if(input.mode==='completion')return console.log(JSON.stringify({verified:ui.completionVerified(input.record)}));
 if(['hydrate','act','continue','hydrate-submit'].includes(input.mode))await ui.hydrate();
 if(['submit','submit-twice','hydrate-submit'].includes(input.mode))await ui.submit();
 if(input.mode==='submit-twice')await ui.submit();
 if(input.mode==='act'){for(const kind of input.approve||[]){const e=nodes.get('goal-approve-'+kind);if(e)e.checked=true;}await ui.act();}
 if(input.mode==='continue')await ui.continueGoal();
 if(input.mode==='examples'){ui.examples();for(const button of nodes.get('goal-examples').children){button.onclick();} }
 const result={calls,delays,notice:context.noticeText,disabled:nodes.get('goal-submit').disabled,continueDisabled:nodes.get('goal-continue').disabled,input:nodes.get('goal-input').value};
 for(const id of ['goal-state','goal-plan','goal-timeline','goal-evidence','goal-receipts','goal-progress','goal-approvals','goal-examples'])result[id]={text:nodes.get(id).textContent,tree:tree(nodes.get(id))};
 console.log(JSON.stringify(result));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
"""


def js(**payload):
    assert NODE, 'Node.js is required to exercise the actual UI'
    result = subprocess.run([NODE, '-e', HARNESS, str(ROOT / 'web/goal-agent.js')], input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, timeout=15, check=True)
    return json.loads(result.stdout)


@pytest.fixture
def goal():
    return {'id': 'goal-real-shape', 'goal': 'Compare inspected public parameter handling', 'status': 'proposed', 'revision': 2, 'model': 'recorded-model', 'proposal': {'hash': 'sealed-source-plan-hash', 'summary': 'An AI proposal needing review', 'success_criteria': ['Identify a recorded caller'], 'assumptions': ['Captured corpus only'], 'questions': ['Is additional evidence needed?'], 'limitations': ['No internal ownership evidence'], 'steps': [{'id': 'inspect', 'title': 'Read the source', 'tool_name': 'read_company_source', 'args': {'source_id': 'source/A'}, 'why': 'Inspect actual context', 'evidence_ids': ['ev/A'], 'depends_on': [], 'expected_result': 'Observed source'}, {'id': 'task', 'title': 'Propose source-grounded follow-up', 'tool_name': 'publish_task', 'args': {'title': 'A proposed task', 'description': 'Evidence-based review', 'source_ids': ['source/A']}, 'why': 'Keep reviewed work', 'evidence_ids': ['ev/A'], 'depends_on': ['inspect'], 'expected_result': 'Independent provider receipt'}]}, 'events': [{'seq': 1, 'type': 'tool_result', 'tool_name': 'read_company_source', 'tool_call_id': 'native-call', 'result': {'path': 'falkordb/graph.py'}}], 'provider_receipts': [{'id': 'provider-1'}, {'id': 'provider-2'}], 'evidence': [{'id': 'ev/A', 'source_id': 'source/A', 'url': 'https://github.com/FalkorDB/falkordb-py/blob/main/falkordb/graph.py', 'sha256': 'a' * 64, 'excerpt': 'actual captured excerpt'}], 'actions': [], 'approved_actions': []}


def test_anonymous_hydrates_actual_goal_using_only_get(goal):
    result = js(mode='hydrate', authenticated=False, records=[goal])
    assert result['calls'] == [{'path': '/api/public/goals/latest'}]
    assert result['disabled'] is True
    assert goal['goal'] in result['goal-state']['text']
    assert 'No external action receipts' in result['goal-receipts']['text']


def test_missing_provider_has_null_proposal_and_no_synthetic_result(goal):
    goal.update(status='blocked', proposal=None, events=[], provider_receipts=[], evidence=[], blocked_reason='Groq is unavailable')
    result = js(mode='hydrate', records=[goal])
    assert 'Groq is unavailable' in result['goal-state']['text']
    assert 'No AI proposal is stored' in result['goal-plan']['text']
    assert 'No actual tool events' in result['goal-timeline']['text']
    assert 'Read the source' not in result['goal-plan']['text']
    assert result['goal-approvals']['tree']['children'] == []


def test_one_free_text_submit_has_only_contract_body_and_never_acts(goal):
    result = js(mode='submit', goal='  A new unconstrained engineering goal  ', records=[goal])
    assert result['calls'] == [{'path': '/api/public/goals', 'body': {'goal': 'A new unconstrained engineering goal', 'idempotency_key': 'test-idempotency-key'}}]
    assert 'Approve' not in str(result['calls'])


def test_anonymous_submit_does_not_post():
    result = js(mode='submit', authenticated=False, records=[])
    assert result['calls'] == []
    assert 'Sign in' in result['notice']


def test_unknown_post_never_retries_automatically(goal):
    result = js(mode='submit-twice', records=[goal], failAt=0)
    assert len(result['calls']) == 1
    assert 'No POST was repeated' in result['goal-progress']['text']
    assert result['disabled'] is True


def test_examples_only_populate_same_composer_without_api_routes():
    result = js(mode='examples', records=[])
    assert len(result['goal-examples']['tree']['children']) == 10
    assert result['calls'] == []
    assert 'internal ownership' in result['input']


def test_variable_dependency_dag_comes_from_proposal_not_events(goal):
    goal['proposal']['steps'].append({'id': 'alternative', 'title': 'An arbitrary third branch', 'tool_name': 'traverse_company_graph', 'args': {}, 'why': 'Model choice', 'evidence_ids': ['not-observed'], 'depends_on': ['inspect', 'task'], 'expected_result': 'More context'})
    result = js(mode='hydrate', records=[goal])
    assert 'Depends on: inspect, task' in result['goal-plan']['text']
    assert 'not-observed · evidence unavailable' in result['goal-plan']['text']
    assert 'An arbitrary third branch' in result['goal-plan']['text']
    assert 'An arbitrary third branch' not in result['goal-timeline']['text']
    assert 'Inference provider receipts · 2' in result['goal-timeline']['text']


def test_approve_only_selected_proposed_capability_and_bound_hash(goal):
    result = js(mode='act', approve=['publish_task', 'verify_release'], records=[goal, goal])
    assert result['calls'][1] == {'path': '/api/public/goals/goal-real-shape/act', 'body': {'expected_plan_hash': 'sealed-source-plan-hash', 'approved_actions': ['publish_task']}}


def test_no_action_without_explicit_checkbox(goal):
    assert len(js(mode='act', approve=[], records=[goal])['calls']) == 1


def test_continue_has_no_extra_effect_permissions(goal):
    result = js(mode='continue', records=[goal, goal])
    assert result['calls'][1] == {'path': '/api/public/goals/goal-real-shape/continue', 'body': {'expected_plan_hash': 'sealed-source-plan-hash'}}


def test_budget_limited_investigation_can_continue_before_proposal(goal):
    goal.update(status='needs_continuation', proposal=None)
    loaded = js(mode='hydrate', records=[goal])
    assert loaded['continueDisabled'] is False
    result = js(mode='continue', records=[goal, goal])
    assert result['calls'][1] == {'path': '/api/public/goals/goal-real-shape/continue', 'body': {'expected_plan_hash': ''}}
    assert 'No AI proposal is stored' in result['goal-plan']['text']


def test_verification_approval_names_actual_publication_destinations(goal):
    goal['proposal']['steps'][1]['tool_name'] = 'verify_release'
    result = js(mode='hydrate', records=[goal])
    assert 'publish its observed outcome to Jira KAN and Slack #baton-demo' in result['goal-approvals']['text']


def test_structured_source_excerpt_is_readable_json(goal):
    goal['evidence'][0]['excerpt'] = {'path': 'falkordb/graph.py', 'lines': [10, 11]}
    result = js(mode='hydrate', records=[goal])
    assert '"path": "falkordb/graph.py"' in result['goal-evidence']['text']
    assert '[object Object]' not in result['goal-evidence']['text']


@pytest.mark.parametrize('url', ['/api/public/goals/a-real-goal', '/api/public/release-runs/run-1', 'https://baton-workspace.vercel.app/api/public/release-runs/run-1'])
def test_same_origin_actual_goal_or_run_receipt_links_allowed(url):
    expected = 'https://baton-workspace.vercel.app' + url if url.startswith('/') else url
    assert js(mode='link', url=url)['url'] == expected


@pytest.mark.parametrize('url', ['/api/auth/status', '/api/public/tasks', 'https://evil.example/api/public/goals/a', '/api/public/goals/a?redirect=https://evil.example', '/api/public/goals/a%2Fb'])
def test_other_same_origin_paths_and_external_receipt_paths_rejected(url):
    assert js(mode='link', url=url)['url'] is None


def test_foreign_goal_cannot_replace_action_response(goal):
    foreign = copy.deepcopy(goal); foreign['id'] = 'foreign-goal'
    result = js(mode='continue', records=[goal, foreign])
    assert 'identity does not match' in result['goal-progress']['text']
    assert 'goal-real-shape' in result['goal-state']['text']


def test_text_is_rendered_safely_and_source_id_is_preserved(goal):
    goal['proposal']['summary'] = '<img src=x onerror=alert(1)>'
    result = js(mode='hydrate', records=[goal])
    assert '<img src=x onerror=alert(1)>' in result['goal-plan']['text']
    assert 'source/A' in result['goal-evidence']['text']
    assert 'actual captured excerpt' in result['goal-evidence']['text']


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://github.com.evil.example/a', 'https://u:p@github.com/x', 'http://github.com/a', 'https://evil.example/a'])
def test_hostile_receipt_links_not_clickable(url):
    assert js(mode='link', url=url)['url'] is None


def test_completion_prose_without_independent_receipt_never_verifies(goal):
    goal['status'] = 'completed'
    result = js(mode='hydrate', records=[goal])
    assert 'Completion reported · action verification unconfirmed' in result['goal-state']['text']
    goal['actions'] = [{'id': 'independent-receipt-id', 'step_id': 'task', 'kind': 'publish_task', 'status': 'verified', 'read_back_verified': True}]
    assert js(mode='completion', record=goal)['verified'] is True


@pytest.mark.parametrize('patch', [{'step_id': 'other-step'}, {'status': 'partial'}, {'read_back_verified': False}, {'kind': 'verify_release'}])
def test_completion_requires_every_effect_bound_to_verified_receipt(goal, patch):
    goal['status'] = 'completed'
    action = {'id': 'task', 'step_id': 'task', 'kind': 'publish_task', 'status': 'verified', 'read_back_verified': True}
    action.update(patch); goal['actions'] = [action]
    assert js(mode='completion', record=goal)['verified'] is False


def test_active_goal_uses_bounded_ten_second_gets_only(goal):
    goal['status'] = 'investigating'
    result = js(mode='hydrate', records=[goal])
    assert len(result['calls']) == 19
    assert result['delays'] == [10000] * 18
    assert all('body' not in call for call in result['calls'])
    assert 'Automatic reads paused' in result['goal-progress']['text']


def test_homepage_integrates_goal_first_and_preserves_release_drilldown():
    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    assert html.index('id="goal-agent"') < html.index('id="verification-drilldown"') < html.index('id="release-verification"') < html.index('id="legacy-workspace"')
    for asset in ['/goal-agent.js', '/goal-agent.css', '/release-verification.js', '/release-verification.css']:
        assert asset in html
    assert 'id="login"' in html and 'id="operator"' in html
    assert 'No React' not in html
