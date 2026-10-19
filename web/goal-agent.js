/* One goal, one agent. Stored observations and provider receipts remain distinct. */
'use strict';
(() => {
  const ROOT = '/api/public/goals', ACTIVE = new Set(['investigating', 'acting']);
  const EFFECTS = {publish_task: 'Create the proposed task in Jira KAN and report it to Slack #baton-demo', verify_release: 'Run the approved merged Python client verification profile and publish its observed outcome to Jira KAN and Slack #baton-demo'};
  const PROMPTS = [
    'Explain what changed in FalkorDB Python client PR #212 and identify the evidence still needed before relying on it.',
    'Compare the public evidence for synchronous and asynchronous parameter handling in the Python client.',
    'Investigate issue #211 and propose a source-grounded verification task for review.',
    'Find public changes connected to Python client parameter validation and explain their relationships.',
    'Review the recorded evidence for redis-py compatibility and identify what remains unknown.',
    'Trace the public source behind the Python client recursive parameter helper and explain which callers depend on it.',
    'Prepare a Jira task from the public evidence about the merged Python client change, with explicit success criteria.',
    'Investigate the public Rust issue #3246 and suggest the next evidence-backed step within the available tools.',
    'Compare related public issues and pull requests in the captured FalkorDB knowledge graph; distinguish shared files from dependencies.',
    'Find what the captured public evidence says about contributors to this change, and state what it cannot establish about internal ownership.'
  ];
  let record, busy = false, reading = false, uncertain = false, generation = 0, key, keyGoal, pendingCreation = false, workGraph, workGraphObserver;
  const list = value => Array.isArray(value) ? value : [];
  const authenticatedNow = () => typeof authenticated !== 'undefined' && authenticated;
  const canContinue = () => ['needs_continuation', 'blocked'].includes(record?.status) || (record?.status === 'proposed' && Boolean(record?.proposal?.hash));
  const text = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const evidenceLabel = item => ({entity: 'Graph observation', source: 'Captured source read', model_proposal: 'Prior model proposal'}[item.kind] || 'Evidence record · kind not specified');
  const progress = value => { if ($('goal-progress')) $('goal-progress').textContent = value; };
  function requestedGoalId() {
    const hash = window.location?.hash || '';
    if (!hash.startsWith('#goal-agent?')) return undefined;
    const match = /^#goal-agent\?goal=([a-f0-9]{32})$/.exec(hash);
    if (!match) throw Error('Invalid requested goal link; expected a stored goal ID');
    return match[1];
  }
  function goalLink(id) { return /^[a-f0-9]{32}$/.test(id || '') ? '#goal-agent?goal=' + id : null; }
  function safeLink(value) {
    try {
      const origin = window.location?.origin;
      const url = new URL(value, origin);
      if (url.username || url.password) return null;
      if (origin && url.origin === origin && /^\/api\/public\/(goals|release-runs)(\/[a-zA-Z0-9_-]+)*$/.test(url.pathname) && !url.search && !url.hash) return url.href;
      if (url.protocol !== 'https:' || url.username || url.password) return null;
      if (['github.com', 'api.github.com', 'raw.githubusercontent.com'].includes(url.hostname) || /(^|\.)atlassian\.net$/.test(url.hostname) || /^[a-z0-9-]+\.slack\.com$/.test(url.hostname)) return url.href;
    } catch (_) { /* Invalid receipt URL stays visible as text in its raw record. */ }
    return null;
  }
  function detail(label, value) { const root = el('details'); root.append(el('summary', label), el('pre', text(value))); return root; }
  function bullets(root, label, values) {
    if (!list(values).length) return;
    root.append(el('h3', label)); const ul = el('ul');
    for (const value of values) ul.append(el('li', text(value)));
    root.append(ul);
  }
  function assertRecord(value, expected) {
    if (!value || typeof value.id !== 'string' || !/^[a-zA-Z0-9_-]{1,160}$/.test(value.id) || (expected && value.id !== expected)) throw Error('Stored goal identity does not match this request');
    return value;
  }
  function completionVerified(value) {
    const effects = list(value.proposal?.steps).filter(step => EFFECTS[step.tool_name]);
    return value.status === 'completed' && effects.length > 0 && effects.every(step => stepState(value, step) === 'verified');
  }
  function stepState(value, step) {
    const hash = value.proposal?.hash;
    if (typeof hash !== 'string' || !hash) return 'proposed';
    if (EFFECTS[step.tool_name]) return list(value.actions).some(action => action.step_id === step.id && action.kind === step.tool_name && action.plan_hash === hash && action.status === 'verified' && action.read_back_verified === true) ? 'verified' : 'proposed';
    return list(value.events).some(event => event.type === 'tool_result' && event.step_id === step.id && event.tool_name === step.tool_name && event.plan_hash === hash && event.status === 'succeeded') ? 'observed' : 'proposed';
  }
  function workGraphElements(value) {
    const steps = [...new Map(list(value.proposal?.steps).slice(0, 6).map(step => [step.id, step])).values()];
    const sources = new Map(list(value.evidence).map(source => [source.id, source]));
    const nodes = new Map(), edges = new Map();
    for (const step of steps) {
      const state = stepState(value, step), status = {verified: 'Verified action', observed: 'Observed read', proposed: 'Proposed'}[state];
      nodes.set('step:' + step.id, {data: {id: 'step:' + step.id, label: step.title + '\n' + status, kind: 'step', state, anchor: 'goal-step-' + step.id}});
    }
    for (const step of steps) {
      for (const dependency of list(step.depends_on)) if (nodes.has('step:' + dependency)) {
        const id = JSON.stringify(['depends', dependency, step.id]);
        edges.set(id, {data: {id, source: 'step:' + dependency, target: 'step:' + step.id, relation: 'DEPENDS_ON', label: 'prerequisite', kind: 'dependency'}});
      }
      for (const id of list(step.evidence_ids)) if (sources.has(id)) {
        const source = sources.get(id);
        nodes.set('evidence:' + id, {data: {id: 'evidence:' + id, label: id + '\n' + evidenceLabel(source), kind: 'evidence', state: 'evidence', anchor: 'goal-source-' + encodeURIComponent(id), source_id: source.source_id}});
        const edgeId = JSON.stringify(['cites', step.id, id]);
        edges.set(edgeId, {data: {id: edgeId, source: 'step:' + step.id, target: 'evidence:' + id, relation: 'CITES', label: 'cites', kind: 'citation'}});
      }
    }
    return [...nodes.values(), ...edges.values()];
  }
  function renderWorkGraph(root, value) {
    if (typeof window.cytoscape !== 'function') { root.append(el('p', 'The ordered steps below show the work graph; the visual viewer is unavailable.', 'goal-footnote')); return; }
    const container = el('div', undefined, 'goal-work-graph'); container.id = 'goal-work-graph'; container.setAttribute('role', 'img'); container.setAttribute('aria-label', 'Stored proposal dependencies and cited evidence. Prerequisite arrows point to dependent steps.');
    root.append(container, el('p', 'Arrows: prerequisite → dependent step; step → cited evidence. Proposed ≠ executed. Green: verified action; blue: observed read; outlined: proposed. Select a node to inspect its existing record below.', 'goal-footnote'));
    try {
      workGraph = window.cytoscape({container, elements: workGraphElements(value), layout: {name: 'breadthfirst', directed: true, padding: 28, spacingFactor: 1.15, animate: false}, minZoom: 0.2, maxZoom: 2, userZoomingEnabled: false, style: [
        {selector: 'node', style: {label: 'data(label)', 'font-family': 'DM Sans, sans-serif', 'font-size': 11, 'text-wrap': 'wrap', 'text-max-width': 115, color: '#263b31', 'text-valign': 'center', 'background-color': '#f6f6f1', 'border-width': 1.5, 'border-color': '#7a827a', width: 125, height: 62, shape: 'roundrectangle'}},
        {selector: 'node[state="verified"]', style: {'background-color': '#28533c', color: '#ffffff', 'border-color': '#28533c'}},
        {selector: 'node[state="observed"]', style: {'background-color': '#315b70', color: '#ffffff', 'border-color': '#315b70'}},
        {selector: 'node[kind="evidence"]', style: {'background-color': '#edf3e7', 'border-color': '#c3ccbf', shape: 'ellipse', width: 100, height: 52, 'font-size': 9}},
        {selector: 'edge', style: {width: 1.5, 'line-color': '#7a827a', 'target-arrow-color': '#7a827a', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 9, 'font-family': 'DM Sans, sans-serif', color: '#7a827a', 'text-background-color': '#f6f6f1', 'text-background-opacity': 1, 'text-background-padding': 3}},
        {selector: 'edge[kind="citation"]', style: {'line-style': 'dashed', 'line-color': '#c3ccbf', 'target-arrow-color': '#c3ccbf'}}
      ]});
      workGraph.on('tap', 'node', event => { const target = $(event.target.data('anchor')); if (target) { target.scrollIntoView?.({behavior: 'auto', block: 'nearest'}); target.tabIndex = -1; target.focus?.({preventScroll: true}); } });
      if (window.ResizeObserver) { workGraphObserver = new window.ResizeObserver(() => { workGraph?.resize(); workGraph?.fit(undefined, 28); }); workGraphObserver.observe(container); }
    } catch (_) { if (workGraph) { workGraph.destroy(); workGraph = undefined; } container.hidden = true; root.append(el('p', 'The visual graph could not load. Inspect the ordered steps and source records below.', 'goal-footnote')); }
  }
  function controls() {
    if (!$('goal-submit')) return;
    const locked = busy || reading || uncertain || ACTIVE.has(record?.status);
    $('goal-submit').disabled = !authenticatedNow() || locked;
    $('goal-refresh').disabled = busy || reading;
    $('goal-continue').disabled = !authenticatedNow() || locked || !canContinue();
    $('goal-continue').textContent = record?.status === 'blocked' ? 'Resume investigation' : 'Continue investigation';
    const selected = Object.keys(EFFECTS).filter(kind => $('goal-approve-' + kind)?.checked);
    $('goal-act').disabled = !authenticatedNow() || locked || !record?.proposal?.hash || !['proposed', 'needs_continuation'].includes(record?.status) || !selected.length;
    $('goal-auth-note').textContent = authenticatedNow() ? 'Goals, plans and receipts are public in this demo. Submitting investigates and proposes. External actions require your separate approval below.' : 'Sign in to submit a goal or approve actions. Stored evidence is public.';
  }
  function render() {
    if (workGraphObserver) { workGraphObserver.disconnect(); workGraphObserver = undefined; }
    if (workGraph) { workGraph.destroy(); workGraph = undefined; }
    const state = $('goal-state'), plan = $('goal-plan'), timeline = $('goal-timeline'), evidence = $('goal-evidence'), actions = $('goal-receipts'), approvals = $('goal-approvals');
    for (const root of [state, plan, timeline, evidence, actions, approvals]) root.replaceChildren();
    $('goal-result').hidden = !record;
    if (!record) { controls(); return; }
    state.append(el('p', 'STORED GOAL / REVISION ' + (record.revision ?? 'unknown'), 'eyebrow'), el('h2', record.goal || 'Stored goal'));
    const label = completionVerified(record) ? 'Completed · action read-backs verified' : record.status === 'completed' ? 'Completion reported · action verification unconfirmed' : String(record.status || 'unknown').replaceAll('_', ' ');
    state.append(el('strong', label, 'goal-status'), el('small', 'Goal ' + record.id + ' · ' + (record.model || 'Model not recorded') + ' · ' + (record.updated_at || record.created_at || 'Time not recorded')));
    const permalink = goalLink(record.id);
    if (permalink) { const a = el('a', 'Link to this stored goal', 'goal-permalink'); a.href = permalink; state.append(a); }
    if (record.blocked_reason) state.append(el('p', text(record.blocked_reason), 'goal-warning'));
    const proposal = record.proposal;
    if (!proposal) plan.append(el('p', 'No AI proposal is stored. A missing model or graph cannot produce a substitute plan.', 'goal-warning'));
    else {
      plan.append(el('p', 'AI PROPOSAL / REVIEW AGAINST SOURCE EVIDENCE', 'eyebrow'), el('h2', 'What the agent proposes'), el('p', proposal.summary || ''), el('code', 'Proposal hash · ' + (proposal.hash || 'missing')));
      bullets(plan, 'Success criteria', proposal.success_criteria); bullets(plan, 'Assumptions', proposal.assumptions); bullets(plan, 'Questions', proposal.questions);
      const steps = el('ol', undefined, 'goal-dag');
      for (const step of list(proposal.steps)) {
        const row = el('li', undefined, 'goal-step'); row.id = 'goal-step-' + step.id;
        row.append(el('small', step.id + ' · ' + step.tool_name), el('h3', step.title), el('p', {verified: 'Verified action · current proposal read-back', observed: 'Observed read · current proposal tool result', proposed: 'Proposed · no verified execution for this step'}[stepState(record, step)], 'goal-step-status'), el('p', step.why || ''), el('p', list(step.depends_on).length ? 'Depends on: ' + step.depends_on.join(', ') : 'No prerequisite steps', 'goal-dependency'), el('p', 'Expected result: ' + (step.expected_result || 'Not specified')));
        const citations = el('div', undefined, 'goal-citations');
        for (const id of list(step.evidence_ids)) {
          const found = list(record.evidence).find(item => item.id === id);
          const citation = el(found ? 'a' : 'span', id + (found ? '' : ' · evidence unavailable'));
          if (found) { citation.href = '#goal-source-' + encodeURIComponent(id); }
          citations.append(citation);
        }
        row.append(citations, detail('Inspect proposed arguments', step.args || {})); steps.append(row);
      }
      plan.append(el('h3', 'Proposed work graph'), el('p', 'Dependencies below come from the stored proposal. A proposed step is not an executed tool call.', 'goal-footnote'));
      renderWorkGraph(plan, record); plan.append(steps);
      bullets(plan, 'Limitations', proposal.limitations);
      for (const kind of Object.keys(EFFECTS)) if (list(proposal.steps).some(step => step.tool_name === kind)) {
        const label = el('label', undefined, 'goal-approval'), input = el('input'); input.type = 'checkbox'; input.id = 'goal-approve-' + kind; input.onchange = controls;
        label.append(input, el('span', EFFECTS[kind])); approvals.append(label);
      }
    }
    if (!list(record.events).length) timeline.append(el('p', 'No actual tool events are recorded.'));
    for (const event of list(record.events)) {
      const entry = el('div', undefined, 'goal-event');
      entry.append(el('strong', String(event.seq ?? '?') + ' · ' + (event.tool_name || event.type || 'Recorded event')));
      if (event.tool_call_id) entry.append(el('small', 'Tool call ' + event.tool_call_id));
      if (event.error) entry.append(el('p', text(event.error), 'goal-warning'));
      entry.append(detail('Actual event record', event)); timeline.append(entry);
    }
    timeline.append(detail('Inference provider receipts · ' + list(record.provider_receipts).length, list(record.provider_receipts)));
    for (const item of list(record.evidence)) {
      const entry = el('article', undefined, 'goal-source'); entry.id = 'goal-source-' + encodeURIComponent(item.id);
      entry.append(el('p', evidenceLabel(item), 'eyebrow'), el('h3', item.id), el('p', (item.kind === 'source' ? 'SOURCE ID · ' : 'ENTITY ID · ') + (item.source_id || 'not recorded')), el('code', 'Evidence SHA-256 · ' + (item.sha256 || 'not recorded')));
      const link = safeLink(item.url); if (link) { const a = el('a', item.kind === 'source' ? 'Open captured source ↗' : item.kind === 'model_proposal' ? 'Open proposal record ↗' : 'Open linked record ↗'); a.href = link; a.target = '_blank'; a.rel = 'noopener noreferrer'; entry.append(a); }
      if (item.excerpt) entry.append(el('pre', text(item.excerpt)));
      entry.append(detail('Inspect source provenance', item)); evidence.append(entry);
    }
    if (!list(record.evidence).length) evidence.append(el('p', 'No inspected source evidence is stored.'));
    for (const action of list(record.actions)) {
      const entry = el('div', undefined, 'goal-action');
      entry.append(el('h3', action.kind || 'Recorded action'), el('strong', action.status || 'Status unknown'), el('p', action.status === 'verified' && action.read_back_verified === true ? 'Independent provider read-back verified' : 'Independent provider read-back not verified'));
      const link = safeLink(action.url); if (link) { const a = el('a', 'Open action destination ↗'); a.href = link; a.target = '_blank'; a.rel = 'noopener noreferrer'; entry.append(a); }
      entry.append(detail('Actual action receipt', action)); actions.append(entry);
    }
    if (!list(record.actions).length) actions.append(el('p', 'No external action receipts are stored.'));
    controls();
  }
  async function poll(id, token) {
    for (let attempt = 0; attempt < 18 && ACTIVE.has(record?.status) && token === generation; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 10000));
      if (token !== generation) return;
      const value = assertRecord(await api(ROOT + '/' + encodeURIComponent(id)), id);
      if (token !== generation) return;
      record = value; render();
    }
    if (ACTIVE.has(record?.status)) progress('Still in progress. Automatic reads paused; refresh stored state to check again.');
  }
  async function hydrate() {
    if (busy || reading) return;
    const token = ++generation; reading = true; controls(); progress('Reading the latest stored goal…');
    try {
      const expected = pendingCreation ? undefined : requestedGoalId() || record?.id;
      const response = await api(expected ? ROOT + '/' + encodeURIComponent(expected) : ROOT + '/latest');
      if (token !== generation) return;
      if (pendingCreation && response?.goal !== keyGoal) {
        progress('The latest goal does not match the pending request; no POST was repeated. Refresh stored state again to reconcile.');
        return;
      }
      if (response === null && !expected) {
        record = undefined; uncertain = false; pendingCreation = false; render();
        progress('No goals yet. Submit an engineering goal to start an investigation. Sign in to take action.');
        return;
      }
      const value = assertRecord(response, expected);
      record = value; uncertain = false; pendingCreation = false; render(); progress('Stored state loaded. Reading does not run the agent or approve actions.');
      await poll(record.id, token);
    } catch (error) { progress('Stored goal unavailable: ' + error.message + '. No agent request was submitted.'); }
    finally { reading = false; controls(); }
  }
  async function submit() {
    if (busy || reading || uncertain || ACTIVE.has(record?.status)) return;
    if (!authenticatedNow()) { notice('Sign in before submitting a goal.'); return; }
    const goal = $('goal-input').value.trim(); if (!goal) { progress('Describe the outcome you want to investigate.'); return; }
    if (!key || keyGoal !== goal) { key = window.crypto.randomUUID(); keyGoal = goal; }
    pendingCreation = true;
    await mutate(ROOT, {goal, idempotency_key: key});
  }
  async function mutate(path, body, expected) {
    busy = true; const token = ++generation; controls(); progress('Agent request submitted once. Waiting for stored observations…');
    try {
      const value = assertRecord(await api(path, body), expected);
      record = value; key = undefined; uncertain = false; pendingCreation = false; render();
      if (path === ROOT && goalLink(record.id) && window.history?.replaceState) window.history.replaceState(null, '', goalLink(record.id));
      progress('Agent response stored. Review the proposal, source evidence and actual receipts.'); await poll(record.id, token);
    } catch (error) {
      uncertain = true; progress('Request not confirmed: ' + error.message + '. No POST was repeated. Refresh stored state before another explicit action.');
    } finally { busy = false; controls(); }
  }
  async function act() {
    if (!authenticatedNow() || busy || reading || uncertain || !record?.proposal?.hash || !['proposed', 'needs_continuation'].includes(record.status)) return;
    const kinds = Object.keys(EFFECTS).filter(kind => $('goal-approve-' + kind)?.checked && list(record.proposal.steps).some(step => step.tool_name === kind));
    if (!kinds.length) return;
    await mutate(ROOT + '/' + encodeURIComponent(record.id) + '/act', {expected_plan_hash: record.proposal.hash, approved_actions: kinds}, record.id);
  }
  async function continueGoal() {
    if (!authenticatedNow() || busy || reading || uncertain || !canContinue()) return;
    await mutate(ROOT + '/' + encodeURIComponent(record.id) + '/continue', {expected_plan_hash: record.proposal?.hash || ''}, record.id);
  }
  function examples() {
    for (const prompt of PROMPTS) { const button = el('button', prompt, 'goal-example'); button.type = 'button'; button.onclick = () => { $('goal-input').value = prompt; $('goal-input').focus(); }; $('goal-examples').append(button); }
  }
  window.BatonGoal = {hydrate, submit, act, continueGoal, controls, render, safeLink, completionVerified, examples, prompts: PROMPTS};
  if ($('goal-form')) {
    $('goal-form').onsubmit = event => { event.preventDefault(); submit(); };
    $('goal-refresh').onclick = hydrate; $('goal-act').onclick = act; $('goal-continue').onclick = continueGoal;
    if (window.addEventListener) window.addEventListener('hashchange', () => { if ((window.location.hash || '').startsWith('#goal-agent?')) hydrate(); });
    examples(); render(); hydrate();
  }
})();
