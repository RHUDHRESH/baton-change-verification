/* Real public company context and explicit external actions. No invented org chart. */
'use strict';
window.companyConnections = null;
async function companyWork(identity){
  if(!workspace)await load();
  const item=workspace.items.find(row=>row.id===identity);
  if(!item)throw Error('This source item is outside the imported sample.');
  select(item);document.querySelector('.detail').scrollIntoView({behavior:'smooth',block:'start'});
}
async function companyOverview(){
  const root=$('company-context');
  try{
    const company=await api('/api/public/company');root.replaceChildren();
    const projects=el('section');projects.append(el('h3','Public repositories & contributors'));
    for(const repo of company.repositories){const card=el('article',undefined,'company-card');card.append(link(repo.name,repo.url),el('p',repo.description||'Public repository'),el('small',repo.sampled_items.length+' sampled work items'));projects.append(card);}
    const people=el('details');people.append(el('summary',company.people.length+' credited contributor accounts'));
    for(const person of company.people){const row=el('p');row.append(link('@'+person.login,person.url),el('small',' · '+person.authored_items.length+' authored items · '+person.repositories.length+' repositories'));if(person.authored_items[0])row.append(button('View work',()=>companyWork(person.authored_items[0])));people.append(row);}projects.append(people);
    const gaps=el('section');gaps.append(el('h3','Source-backed investigation queue'));
    for(const gap of company.gaps.slice(0,5)){const card=el('article',undefined,'company-card');card.append(el('strong',gap.action),el('p',gap.title),el('small',gap.detail));if(gap.context_path){const context=el('details');context.append(el('summary','Why this task?'),el('p',gap.ranking_basis),el('p',gap.context_path.nodes.join(' → ')));for(const id of gap.context_path.source_ids)context.append(button('Inspect source '+id,()=>source(id)));card.append(context);}card.append(button('Investigate this work',()=>companyWork(gap.item_id)));gaps.append(card);}
    if(!company.gaps.length)gaps.append(el('p','No supported gaps in this bounded sample.'));
    for(const path of company.shared_file_paths.slice(0,2)){const card=el('article',undefined,'company-card');card.append(el('strong','Overlapping change: '+path.file),el('p',path.contributors.map(x=>'@'+x).join(' ↔ ')),el('small',path.limit),button('Inspect overlap',()=>companyWork(path.item_ids[0])));gaps.append(card);}
    root.append(projects,gaps);
    const proof=el('details');proof.append(el('summary','Why these suggestions? View graph paths and evidence'),el('pre',JSON.stringify({paths:company.paths.slice(0,6),shared_file_paths:company.shared_file_paths,queries:company.queries,diagnostics:company.diagnostics,limits:company.limits},null,2)));$('company-proof').replaceChildren(proof);
    $('company-basis').textContent=company.company.basis+'. '+company.limits[0];
  }catch(error){root.replaceChildren(el('p','Company context unavailable: '+error.message));}
  try{window.companyConnections=await api('/api/public/connections');$('connections-state').textContent=['jira','slack'].map(name=>(name==='jira'?'Your Jira KAN project':'Your Raptorflow Slack channel')+': '+(window.companyConnections[name]?.configured?'configured · '+window.companyConnections[name].destination:'not configured')).join(' · ')+'. Configuration is not a live connectivity check; published artifact links are verified separately.';if(workspace)tasks();}catch(error){$('connections-state').textContent='Connections unavailable: '+error.message;}
}
companyOverview();

function companyArtifactLink(label,url){const node=el('a',label);try{const parsed=new URL(url);if(parsed.protocol==='https:'&&!parsed.username&&!parsed.password&&(/^[a-z0-9-]+\.atlassian\.net$/.test(parsed.hostname)||/^[a-z0-9-]+\.slack\.com$/.test(parsed.hostname))){node.href=url;node.target='_blank';node.rel='noopener';}}catch{}return node;}

function executionMetric(label,value){const node=el('div',undefined,'execution-metric');node.append(el('strong',value),el('small',label));return node;}
function executionJSON(label,value){const details=el('details');details.append(el('summary',label),el('pre',JSON.stringify(value,null,2)));return details;}
let executionTaskPanels=[];
async function viewExecutionTask(taskId){
  if(!workspace)await load();
  const task=workspace?.tasks.find(row=>row.id===taskId),row=$('workspace-'+taskId);
  if(!task||!row)throw Error('The linked task is not available in this workspace response.');
  row.scrollIntoView({behavior:'smooth',block:'center'});row.tabIndex=-1;row.focus({preventScroll:true});
}
function refreshExecutionTaskLinks(){
  for(const {root,taskId} of executionTaskPanels){root.replaceChildren();if(!workspace)continue;
    const task=workspace.tasks.find(row=>row.id===taskId);
    if(task)root.append(el('small','Linked workspace task status: '+task.status+'. External artifact links do not establish provider completion status.'));
    for(const edge of workspace.edges.filter(row=>row.data.kind==='PUBLISHED_AS'&&row.data.source===taskId)){
      const artifact=workspace.nodes.find(row=>row.data.id===edge.data.target)?.data.properties;
      if(artifact)root.append(companyArtifactLink('View verified '+artifact.target+' artifact ↗',artifact.url));
    }
  }
}
function executionLink(label,url){const node=el('a',label);if(typeof url==='string'&&/^(?:https:\/\/baton-workspace\.vercel\.app)?\/evidence\/[a-zA-Z0-9_./-]+$/.test(url)&&!url.split('/').includes('..')){node.href=url;node.target='_blank';node.rel='noopener';}return node;}
async function exploreExecution(receipt){
  await companyWork(receipt.item_id);
  const match=/^task-agent-([a-f0-9]{32})$/.exec(receipt.task_id||'');
  if(match){selectedAgentId=match[1];const result=await api('/api/public/agent/'+match[1]);if(selected?.id===receipt.item_id&&selectedAgentId===match[1])showAgent(result);}
  $('agent-result').scrollIntoView({behavior:'smooth',block:'start'});
}
function renderExecution(receipt){
  const card=el('article',undefined,'execution-card'),summary=receipt.summary||{},suite=summary.graph_library||{},rdb=summary.rdb||{};
  const header=el('div',undefined,'execution-heading'),copy=el('div');
  copy.append(el('p',receipt.root_issue||'Recorded verification','eyebrow'),el('h3','Grow-only tensor resize & RDB restore verification'));
  header.append(copy,el('span',receipt.status==='passed'?'Execution checks passed':'Recorded status: '+(receipt.status||'unknown'),'execution-status'));card.append(header);
  card.append(el('p',receipt.executor||'Executor not recorded'),el('p',receipt.scope||'Execution scope not recorded.','muted'));
  const metrics=el('div',undefined,'execution-metrics');
  if(Number.isInteger(suite.passed))metrics.append(executionMetric('Graph library tests passed',String(suite.passed)));
  if(Number.isInteger(suite.failed))metrics.append(executionMetric('Graph library tests failed',String(suite.failed)));
  if(Number.isInteger(suite.ignored))metrics.append(executionMetric('Ignored tests · not run',String(suite.ignored)));
  if(Number.isInteger(rdb.round_trips))metrics.append(executionMetric('Redis save / reload cycles',String(rdb.round_trips)));
  if(metrics.children.length)card.append(metrics);
  if(Number.isInteger(rdb.nodes_preserved)&&Number.isInteger(rdb.parallel_edges_preserved))card.append(el('p','Observed result: '+rdb.nodes_preserved+' nodes and '+rdb.parallel_edges_preserved+' parallel edges preserved through '+rdb.round_trips+' Redis reload cycles. This checks the real persistence path; it does not expose matrix dimensions.','execution-impact'));
  const findings=el('div',undefined,'execution-findings');
  if(receipt.initial_failure){const first=receipt.initial_failure;findings.append(el('h4','The first run failed'),el('p','Original graph library result: '+first.passed+' passed, '+first.failed+' failed, '+first.ignored+' ignored. The failure is retained in the evidence.'));
    if(receipt.workaround)findings.append(el('p','A narrow local clamp workaround was used for the recorded passing run. '+(receipt.workaround.scope||'Workaround scope not recorded.')));
  }
  if(Number.isInteger(summary.targeted_checks)&&Number.isInteger(summary.expected_regression_failures))findings.append(el('p',summary.targeted_checks+' targeted checks passed across debug/release runs. '+summary.expected_regression_failures+' counterfactual checks failed as expected with the parent resize/restore implementation and the new regression tests retained. These establish the grow-only contract; they do not reproduce the original orphan-edge bug.'));
  card.append(findings);
  const actions=el('div',undefined,'execution-actions');
  if(receipt.task_id)actions.append(button(receipt.task_status==='done'?'View linked completed task':'View linked workspace task',()=>viewExecutionTask(receipt.task_id)));
  if(receipt.item_id)actions.append(button('Explore recorded investigation',()=>exploreExecution(receipt)));
  if(receipt.public_evidence_url)actions.append(executionLink('Read public execution evidence ↗',receipt.public_evidence_url));
  if(receipt.manifest_url)actions.append(executionLink('Open raw execution manifest ↗',receipt.manifest_url));
  actions.append(button('Download recorded receipt',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));const anchor=el('a');anchor.href=url;anchor.download='baton-execution-'+receipt.id+'.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));card.append(actions);
  const taskLinks=el('div',undefined,'execution-actions');executionTaskPanels.push({root:taskLinks,taskId:receipt.task_id});card.append(taskLinks);
  const provenance={receipt_id:receipt.id,task_id:receipt.task_id,item_id:receipt.item_id,executor:receipt.executor,source_repository:receipt.source_repository,source_commit:receipt.source_commit,image:receipt.image,report_sha256:receipt.report_sha256,imported_at:receipt.imported_at,validation:receipt.validation,audit:receipt.audit,initial_failure:receipt.initial_failure,workaround:receipt.workaround};
  const proof=executionJSON('Source, executor, initial failure & audit receipts',provenance);
  if(receipt.evidence_url)proof.append(link('Repository evidence reference ↗',receipt.evidence_url));
  if(receipt.initial_failure?.log_url)proof.append(executionLink('Read original failure log ↗',receipt.initial_failure.log_url));card.append(proof);
  const checks=el('details');checks.append(el('summary','Inspect '+(receipt.checks||[]).length+' recorded commands and results'));
  for(const check of receipt.checks||[]){const row=el('details',undefined,'execution-check');const outcome=check.matched_expectation===true?(check.exit_code!==0?'Expected regression failure observed':'Matched recorded expectation'):'Expectation not verified';row.append(el('summary',check.name+' · '+outcome+' · exit '+check.exit_code),el('pre',JSON.stringify(check,null,2)));if(check.log_url)row.append(executionLink('Read raw command log ↗',check.log_url));checks.append(row);}card.append(checks);
  return card;
}
async function executionOverview(){
  const root=$('execution-list');
  try{const response=await api('/api/public/executions');if(!Array.isArray(response.executions))throw Error('Execution response is incomplete');root.replaceChildren();executionTaskPanels=[];
    if(!response.executions.length)root.append(el('p','No execution receipt has been imported. Saved investigation tasks are available below; their status does not prove that code checks ran.','muted'));
    for(const receipt of response.executions)root.append(renderExecution(receipt));refreshExecutionTaskLinks();
    if(response.scope)root.append(el('p',response.scope,'muted'));
  }catch(error){root.replaceChildren(el('p','Execution evidence unavailable: '+error.message+'. No execution result has been substituted.','muted'));}
}
executionOverview();
