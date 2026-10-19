"""Execute the merged-change browser UI against real contract shapes and hostile receipts."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
HARNESS = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag,text){this.tag=tag;this.children=[];this.own=text||'';this.hidden=false;this.dataset={};}
 set textContent(value){this.own=String(value);this.children=[];}
 get textContent(){return this.own+this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
 set innerHTML(value){throw Error('Unsafe HTML rendering attempted');}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.own='';this.children=[...children];}
}
const nodes=new Map(),calls=[],delays=[],graphs=[];
let index=0;
const context={URL,Set,Map,console,window:{location:{origin:'https://baton-workspace.vercel.app'}},
 authenticated:input.authenticated!==false,$:id=>nodes.get(id),
 el:(tag,text,cls)=>{const e=new Element(tag,text);e.className=cls;return e;},
 notice:message=>{context.lastNotice=message;},setTimeout:(resolve,delay)=>{delays.push(delay);resolve();}};
if(input.graph)context.window.cytoscape=options=>{graphs.push(options);return {on:()=>{},destroy:()=>{},resize:()=>{},fit:()=>{}};};
context.api=async(path,body)=>{calls.push(body===undefined?{path}:{path,body});if(input.failAt===calls.length-1)throw Error('mock unavailable');return JSON.parse(JSON.stringify(input.records[Math.min(index++,input.records.length-1)]));};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
for(const id of ['release-start','release-refresh','release-auth-note','release-progress','release-plan-title','release-source-commit','release-stage-investigate','release-stage-verify','release-stage-decide','release-stage-publish','release-matrix','release-witnesses','release-graph','release-source-selection','release-investigation','release-decision','release-evidence','release-publication'])nodes.set(id,new Element('div'));
function tree(node){return {tag:node.tag,text:node.own,href:node.href||null,className:node.className,open:node.open===true,children:node.children.map(x=>typeof x==='string'?x:tree(x))};}
(async()=>{
 const ui=context.window.BatonRelease;
 if(input.mode==='review')return console.log(JSON.stringify(ui.reviewState(input.record)));
 if(input.mode==='link')return console.log(JSON.stringify({url:ui.safeLink(input.url)}));
 if(input.mode==='start')await ui.start();
 if(input.mode==='hydrate')await ui.hydrate();
 if(input.mode==='hydrate-start'){await ui.hydrate();await ui.start();}
 if(input.mode==='start-twice'){await ui.start();await ui.start();}
 if(input.mode==='controls')ui.controls();
 const result={calls,delays,graphs,notice:context.lastNotice||null,disabled:nodes.get('release-start').disabled};
 for(const id of ['release-progress','release-matrix','release-decision','release-witnesses','release-investigation','release-evidence','release-publication','release-auth-note'])result[id]={text:nodes.get(id).textContent,tree:tree(nodes.get(id))};
 console.log(JSON.stringify(result));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
"""


def js(**payload):
    assert NODE, 'Node.js is required to exercise the actual browser code'
    result = subprocess.run([NODE, '-e', HARNESS, str(ROOT / 'web/release-verification.js')], input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, check=True, timeout=15)
    return json.loads(result.stdout)


@pytest.fixture
def plan():
    return {'id': 'plan-test', 'change_id': 'FalkorDB/falkordb-py#212', 'source_commit': '207000da70ca183ab02990a98bdd97d0a3e3bb1b', 'title': 'Parameter key verification', 'plan_hash': 'bound-source-and-checks', 'plan_status': 'ready', 'required_checks': [{'id': 'tests/test_graph.py::test_keys', 'label': 'Parameter keys', 'surface': 'sync'}, {'id': 'tests/test_async_graph.py::test_keys', 'label': 'Parameter keys', 'surface': 'async'}], 'environments': [{'id': 'redis-8.0.0', 'redis_version': '8.0.0', 'required': True}, {'id': 'redis-8.1.0', 'redis_version': '8.1.0', 'required': True}], 'witness_paths': [{'nodes': [{'id': 'change-212'}, {'id': 'surface-sync'}, {'id': 'check-keys'}]}], 'investigation': {'status': 'succeeded', 'model': 'actual-model', 'trace': [{'tool': 'read-source'}], 'receipts': [{'id': 'groq-receipt'}]}, 'limitations': ['Scope limited to parameter keys']}


@pytest.fixture
def blocked(plan):
    return {'id': 'run-test', 'plan_id': plan['id'], 'status': 'completed', 'evidence_status': 'verified', 'verification_status': 'failed', 'decision': 'blocked', 'environments': [{'id': 'redis-8.0.0', 'redis_version': '8.0.0', 'checks': [{'id': check['id'], 'status': 'passed', 'exit_code': 0} for check in plan['required_checks']]}, {'id': 'redis-8.1.0', 'redis_version': '8.1.0', 'checks': [{'id': plan['required_checks'][0]['id'], 'status': 'passed'}, {'id': plan['required_checks'][1]['id'], 'status': 'failed', 'failure_excerpt': 'Observed async error'}]}], 'publication': {'jira': {'status': 'verified'}, 'slack': {'status': 'verified'}}, 'runner': {'run_url': 'https://github.com/example/repo/actions/runs/123'}}


def test_anonymous_reads_latest_plan_and_run_without_dispatch(plan, blocked):
    plan['latest_run_id'] = blocked['id']
    value = js(mode='hydrate', authenticated=False, records=[plan, blocked])
    assert value['calls'] == [{'path': '/api/public/release-plans/latest'}, {'path': '/api/public/release-runs/run-test'}]
    assert value['disabled'] is True
    assert 'blocked' in value['release-decision']['text']
    assert 'Passed · verified' in value['release-matrix']['text']
    assert 'Failed · verified' in value['release-matrix']['text']
    assert 'verified' in value['release-publication']['text']
    assert value['release-decision']['tree']['className'] == 'release-decision blocked'


def test_primary_cta_investigates_then_executes_exact_bound_hash(plan, blocked):
    value = js(mode='start', records=[plan, {'id': blocked['id'], 'plan_id': plan['id'], 'status': 'queued'}, blocked])
    assert value['calls'] == [{'path': '/api/public/release-plans', 'body': {'change_id': 'FalkorDB/falkordb-py#212'}}, {'path': '/api/public/release-plans/plan-test/execute', 'body': {'expected_plan_hash': plan['plan_hash'], 'publish_targets': ['jira', 'slack']}}, {'path': '/api/public/release-runs/run-test'}]


def test_no_authenticated_request_is_sent_for_anonymous_cta():
    value = js(mode='start', authenticated=False, records=[])
    assert value['calls'] == []
    assert 'Sign in' in value['notice']


def test_plan_without_run_does_not_turn_requirements_into_results(plan):
    value = js(mode='hydrate', records=[plan])
    assert 'not run' in value['release-matrix']['text']
    assert 'Passed' not in value['release-matrix']['text']
    assert 'No app execution receipt' in value['release-evidence']['text']
    assert len(value['calls']) == 1


def test_incomplete_knowledge_or_groq_failure_never_executes(plan):
    plan['plan_status'] = 'incomplete'
    plan['investigation'].update(status='failed', error='Groq unavailable')
    value = js(mode='start', records=[plan])
    assert len(value['calls']) == 1
    assert 'Groq unavailable' in value['release-investigation']['text']
    assert 'no execution was submitted' in value['release-progress']['text']


@pytest.mark.parametrize('field,value', [('source_commit', 'wrong-commit'), ('change_id', 'FalkorDB/FalkorDB#3246'), ('id', '../wrong')])
def test_plan_identity_is_pinned_before_any_execution(plan, field, value):
    plan[field] = value
    result = js(mode='start', records=[plan])
    assert len(result['calls']) == 1
    assert 'does not match' in result['release-progress']['text']


def test_unknown_post_result_is_not_automatically_retried(plan):
    value = js(mode='start-twice', records=[plan], failAt=0)
    assert len(value['calls']) == 1
    assert 'did not repeat either POST' in value['release-progress']['text']
    assert value['disabled'] is True


def test_execute_failure_requires_receipt_refresh_before_explicit_retry(plan):
    value = js(mode='start-twice', records=[plan], failAt=1)
    assert len(value['calls']) == 2
    assert 'stale plan must be investigated again' in value['release-progress']['text']


def test_unverified_runner_claims_stay_unconfirmed(plan, blocked):
    plan['latest_run_id'] = blocked['id']; blocked['evidence_status'] = 'unconfirmed'
    value = js(mode='hydrate', records=[plan, blocked])
    assert 'Passed · verified' not in value['release-matrix']['text']
    assert 'Reported pass · unconfirmed' in value['release-matrix']['text']
    assert value['release-decision']['tree']['className'] == 'release-decision blocked'


@pytest.mark.parametrize('field,value', [('evidence_status','unconfirmed'), ('verification_status','incomplete'), ('status','running'), ('decision','unconfirmed')])
def test_green_decision_needs_complete_consistent_evidence(blocked, field, value):
    blocked.update(evidence_status='verified', verification_status='passed', status='completed', decision='passed')
    blocked[field] = value
    assert js(mode='review', record=blocked)['passed'] is False


def test_consistent_verified_pass_is_distinct_from_publication(blocked):
    blocked.update(verification_status='passed', decision='passed', publication={'slack': {'status':'failed'}})
    assert js(mode='review', record=blocked)['passed'] is True


def test_foreign_run_cannot_replace_expected_receipt(plan, blocked):
    plan['latest_run_id'] = blocked['id']; blocked['id'] = 'foreign-run'
    value = js(mode='hydrate', records=[plan, blocked])
    assert 'identity does not match' in value['release-progress']['text']
    assert 'Failed · verified' not in value['release-matrix']['text']


def test_get_network_failure_keeps_last_result_without_fabricated_failure(plan):
    plan['latest_run_id'] = 'run-test'
    value = js(mode='hydrate', records=[plan], failAt=1)
    assert 'No success or failure' in value['release-progress']['text'] or 'no success or failure' in value['release-progress']['text']
    assert all('body' not in call for call in value['calls'])


def test_poll_is_bounded_to_ten_second_gets_without_posts(plan, blocked):
    plan['latest_run_id'] = blocked['id']; blocked.update(status='running', decision='unconfirmed', verification_status='running')
    value = js(mode='hydrate', records=[plan, blocked])
    assert len(value['calls']) == 181
    assert value['delays'] == [10000] * 180
    assert all('body' not in call for call in value['calls'])
    assert 'may still be active' in value['release-progress']['text']
    assert value['disabled'] is True


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://github.com.evil.test/run', 'https://user:password@github.com/a/b', 'http://github.com/a/b', 'https://evil.test/log'])
def test_receipt_links_reject_unsafe_destinations(url):
    assert js(mode='link', url=url)['url'] is None


def test_hostile_source_logs_and_model_output_render_as_text(plan, blocked):
    plan['latest_run_id'] = blocked['id']
    plan['investigation']['summary'] = '<img src=x onerror=alert(1)>'
    blocked['logs'] = '<script>evil()</script>'
    value = js(mode='hydrate', records=[plan, blocked])
    assert '<img src=x onerror=alert(1)>' in value['release-investigation']['text']
    assert '<script>evil()</script>' in value['release-evidence']['text']
    assert 'Model provider receipts' in value['release-investigation']['text']
    assert 'Runner logs' in value['release-evidence']['text']
    assert 'Execution receipts' in value['release-evidence']['text']


def test_homepage_makes_release_decision_primary_preserves_legacy_secondary():
    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    assert 'Know what this<br>change must prove.' in html
    assert html.index('id="release-verification"') < html.index('id="legacy-workspace"') < html.index('id="workflow-runner"')
    assert '<details id="legacy-workspace"' in html
    assert 'release-verification.js' in html and 'release-verification.css' in html
    assert 'id="operator"' in html and 'id="login-form"' in html


def test_publication_failure_does_not_rewrite_verified_decision(blocked):
    blocked.update(status='partial', verification_status='passed', decision='passed', publication={'jira': {'status': 'verified'}, 'slack': {'status': 'failed', 'error': 'Read-back failed'}})
    state = js(mode='review', record=blocked)
    assert state['passed'] is True
    assert state['label'] == 'Verification passed'


def test_graph_draws_only_supplied_witness_edges_in_exact_orientation(plan):
    plan['witness_paths'] = [{'nodes': ['change', 'header', 'query', 'helper'], 'edges': [{'source': 'change', 'relation': 'MODIFIES', 'target': 'header'}, {'source': 'query', 'relation': 'CALLS', 'target': 'header'}, {'source': 'header', 'relation': 'CALLS', 'target': 'helper'}, {'source': 'helper', 'relation': 'RECURSES', 'target': 'helper'}]}]
    value = js(mode='hydrate', graph=True, records=[plan])
    edges = [item['data'] for item in value['graphs'][0]['elements'] if 'source' in item['data']]
    assert [(e['source'], e['label'], e['target']) for e in edges] == [('change', 'MODIFIES', 'header'), ('query', 'CALLS', 'header'), ('header', 'CALLS', 'helper'), ('helper', 'RECURSES', 'helper')]
    assert not any(e['source'] == 'header' and e['target'] == 'query' for e in edges)
    assert not any(e['source'] == 'query' and e['target'] == 'helper' for e in edges)


def test_node_inventory_without_edges_uses_readable_json_without_inventing_lines(plan):
    plan['witness_paths'] = [{'nodes': ['change', 'header', 'query'], 'relations': ['MODIFIES', 'CALLS']}]
    value = js(mode='hydrate', graph=True, records=[plan])
    assert value['graphs'] == []
    assert 'change' in value['release-witnesses']['text'] and 'query' in value['release-witnesses']['text']


def test_native_assistant_explanation_keeps_only_actual_reads_and_context_provenance(plan):
    reads = [{'tool': name, 'result': {'source_ids': ['source-inspected']}} for name in ('release_read_change', 'release_follow_impact', 'release_read_source')]
    receipts = [{'id': 'provider-' + str(i), 'finish_reason': 'stop' if i == 4 else 'tool_calls'} for i in range(1, 5)]
    final_response = {'message': {'role': 'assistant', 'content': 'Verify both client surfaces against the declared policy.'}, 'receipt': receipts[-1]}
    plan['investigation'].update(summary=final_response['message']['content'], trace=reads, receipts=receipts,
        final_protocol='native_assistant_stop', actual_final_response=final_response,
        observed_source_ids=['source-inspected'], source_binding={'kind': 'inspected_context', 'model_selected_citations': False})
    value = js(mode='hydrate', authenticated=False, records=[plan])
    panel = value['release-investigation']
    assert 'AI explanation · may contain errors; compare with directed graph' in panel['text']
    assert 'Source links show what the agent inspected.' in panel['text']
    detail_values = {node['children'][0]['text']: node['children'][1]['text'] for node in panel['tree']['children'] if node['tag'] == 'details'}
    trace = json.loads(detail_values['Investigation trace · graph queries and source reads'])
    provider = json.loads(detail_values['Model provider receipts · inference evidence'])
    assert trace == reads and len(trace) == 3
    assert provider == receipts and len(provider) == 4
    assert [row['tool'] for row in trace] == ['release_read_change', 'release_follow_impact', 'release_read_source']
    assert json.loads(detail_values['Actual final model response · native protocol']) == final_response
    context = json.loads(detail_values['Inspected source context · provenance'])
    assert context['observed_source_ids'] == ['source-inspected']
    assert context['source_binding']['model_selected_citations'] is False
    assert value['calls'] == [{'path': '/api/public/release-plans/latest'}]
    assert 'not run' in value['release-matrix']['text']


def test_native_final_response_renders_untrusted_provider_content_as_literal_text(plan):
    plan['investigation']['actual_final_response'] = {'content': '<script>not executable</script>'}
    value = js(mode='hydrate', authenticated=False, records=[plan])
    assert '<script>not executable</script>' in value['release-investigation']['text']


def test_canonical_directed_rows_precede_collapsed_unchanged_erroneous_ai_prose(plan):
    edges = [{'source': 'Graph._query', 'relation': 'CALLS', 'target': 'Graph._build_params_header'},
             {'source': 'AsyncGraph._query', 'relation': 'CALLS', 'target': 'Graph._build_params_header'},
             {'source': 'Graph._build_params_header', 'relation': 'CALLS', 'target': 'stringify_param_value'},
             {'source': 'AsyncGraph', 'relation': 'INHERITS', 'target': 'Graph'},
             {'source': 'stringify_param_value', 'relation': 'RECURSES', 'target': 'stringify_param_value'}]
    plan['witness_paths'] = [{'nodes': ['wrong', 'inventory', 'order'], 'edges': edges},
                             {'nodes': ['extra'], 'edges': edges + [{'source': 'change', 'relation': 'MODIFIES', 'target': 'header'}]}]
    summary = 'Graph._build_params_header calls Graph._query. This model prose reverses the source relationship.'
    plan['investigation']['summary'] = summary
    value = js(mode='hydrate', authenticated=False, records=[plan])
    children = value['release-investigation']['tree']['children']
    heading_index = next(i for i, node in enumerate(children) if node['text'] == 'Graph relationships determine required checks')
    rows = children[heading_index + 1]['children']
    assert [node['text'] for node in rows] == [edge['source'] + ' — ' + edge['relation'] + ' → ' + edge['target'] for edge in edges]
    explanation_index = next(i for i, node in enumerate(children) if node['tag'] == 'details' and node['children'][0]['text'] == 'AI explanation · may contain errors; compare with directed graph')
    assert heading_index < explanation_index
    explanation = children[explanation_index]
    assert explanation['open'] is False
    assert explanation['children'][1]['tag'] == 'p' and explanation['children'][1]['text'] == summary
    assert not any('wrong' in node['text'] or 'inventory' in node['text'] for node in rows)


def test_no_canonical_rows_are_inferred_from_node_inventory_or_model_summary(plan):
    plan['witness_paths'] = [{'nodes': ['A', 'B'], 'relations': ['CALLS']}]
    plan['investigation']['summary'] = 'A calls B'
    value = js(mode='hydrate', authenticated=False, records=[plan])
    panel = value['release-investigation']
    assert 'No CALLS, INHERITS or RECURSES relationships were returned' in panel['text']
    assert not any(node['tag'] == 'ul' for node in panel['tree']['children'][:3])


def test_canonical_edge_identifiers_are_literal_text_and_not_unicode_normalized(plan):
    source_a, source_b = 'source-\u212b', 'source-\u00c5'
    hostile = '<img src=x onerror=alert(1)>'
    edges = [{'source': source_a, 'relation': 'CALLS', 'target': hostile},
             {'source': source_b, 'relation': 'CALLS', 'target': hostile}]
    plan['witness_paths'] = [{'edges': edges}]
    value = js(mode='hydrate', authenticated=False, records=[plan])
    children = value['release-investigation']['tree']['children']
    heading_index = next(i for i, node in enumerate(children) if node['text'] == 'Graph relationships determine required checks')
    rows = children[heading_index + 1]['children']
    assert len(rows) == 2
    assert rows[0]['text'] == source_a + ' — CALLS → ' + hostile
    assert rows[1]['text'] == source_b + ' — CALLS → ' + hostile
