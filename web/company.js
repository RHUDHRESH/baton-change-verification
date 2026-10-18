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
    const projects=el('section');projects.append(el('h3','Projects & contribution context'));
    for(const repo of company.repositories){const card=el('article',undefined,'company-card');card.append(link(repo.name,repo.url),el('p',repo.description||'Public repository'),el('small',repo.sampled_items.length+' sampled work items'));projects.append(card);}
    const people=el('details');people.append(el('summary',company.people.length+' credited contributor accounts'));
    for(const person of company.people){const row=el('p');row.append(link('@'+person.login,person.url),el('small',' · '+person.authored_items.length+' authored items · '+person.repositories.length+' repositories'));if(person.authored_items[0])row.append(button('View work',()=>companyWork(person.authored_items[0])));people.append(row);}projects.append(people);
    const gaps=el('section');gaps.append(el('h3','A practical queue for today'));
    for(const gap of company.gaps.slice(0,5)){const card=el('article',undefined,'company-card');card.append(el('strong',gap.action),el('p',gap.title),el('small',gap.detail));if(gap.context_path){const context=el('details');context.append(el('summary','Why this task?'),el('p',gap.ranking_basis),el('p',gap.context_path.nodes.join(' → ')));for(const id of gap.context_path.source_ids)context.append(button('Inspect source '+id,()=>source(id)));card.append(context);}card.append(button('Investigate this work',()=>companyWork(gap.item_id)));gaps.append(card);}
    if(!company.gaps.length)gaps.append(el('p','No supported gaps in this bounded sample.'));
    for(const path of company.shared_file_paths.slice(0,2)){const card=el('article',undefined,'company-card');card.append(el('strong','Overlapping change: '+path.file),el('p',path.contributors.map(x=>'@'+x).join(' ↔ ')),el('small',path.limit),button('Inspect overlap',()=>companyWork(path.item_ids[0])));gaps.append(card);}
    root.append(projects,gaps);
    const proof=el('details');proof.append(el('summary','Why these suggestions? View graph paths and evidence'),el('pre',JSON.stringify({paths:company.paths.slice(0,6),shared_file_paths:company.shared_file_paths,queries:company.queries,diagnostics:company.diagnostics,limits:company.limits},null,2)));$('company-proof').replaceChildren(proof);
    $('company-basis').textContent=company.company.basis+'. '+company.limits[0];
  }catch(error){root.replaceChildren(el('p','Company context unavailable: '+error.message));}
  try{window.companyConnections=await api('/api/public/connections');$('connections-state').textContent=['jira','slack'].map(name=>name.toUpperCase()+': '+(window.companyConnections[name].configured?'configured · action verification required':'not connected')).join(' · ');if(workspace)tasks();}catch(error){$('connections-state').textContent='Connections unavailable: '+error.message;}
}
companyOverview();

function companyArtifactLink(label,url){const node=el('a',label);try{const parsed=new URL(url);if(parsed.protocol==='https:'&&!parsed.username&&!parsed.password&&(/^[a-z0-9-]+\.atlassian\.net$/.test(parsed.hostname)||/^[a-z0-9-]+\.slack\.com$/.test(parsed.hostname))){node.href=url;node.target='_blank';node.rel='noopener';}}catch{}return node;}
