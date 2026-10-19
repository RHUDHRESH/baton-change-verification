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
  let record, busy = false, reading = false, uncertain = false, generation = 0, key, keyGoal, pendingCreation = false;
  const list = value => Array.isArray(value) ? value : [];
  const authenticatedNow = () => typeof authenticated !== 'undefined' && authenticated;
  const canContinue = () => record?.status === 'needs_continuation' || (record?.status === 'proposed' && Boolean(record?.proposal?.hash));
  const text = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const progress = value => { if ($('goal-progress')) $('goal-progress').textContent = value; };
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
    return value.status === 'completed' && effects.length > 0 && effects.every(step => list(value.actions).some(action => action.step_id === step.id && action.kind === step.tool_name && action.status === 'verified' && action.read_back_verified === true));
  }
  function controls() {
    if (!$('goal-submit')) return;
    const locked = busy || reading || uncertain || ACTIVE.has(record?.status);
    $('goal-submit').disabled = !authenticatedNow() || locked;
    $('goal-refresh').disabled = busy || reading;
    $('goal-continue').disabled = !authenticatedNow() || locked || !canContinue();
    const selected = Object.keys(EFFECTS).filter(kind => $('goal-approve-' + kind)?.checked);
    $('goal-act').disabled = !authenticatedNow() || locked || !record?.proposal?.hash || !['proposed', 'needs_continuation'].includes(record?.status) || !selected.length;
    $('goal-auth-note').textContent = authenticatedNow() ? 'Submitting investigates and proposes. External actions require your separate approval below.' : 'Sign in to submit a goal or approve actions. Stored evidence is public.';
  }
  function render() {
    const state = $('goal-state'), plan = $('goal-plan'), timeline = $('goal-timeline'), evidence = $('goal-evidence'), actions = $('goal-receipts'), approvals = $('goal-approvals');
    for (const root of [state, plan, timeline, evidence, actions, approvals]) root.replaceChildren();
    $('goal-result').hidden = !record;
    if (!record) { controls(); return; }
    state.append(el('p', 'STORED GOAL / REVISION ' + (record.revision ?? 'unknown'), 'eyebrow'), el('h2', record.goal || 'Stored goal'));
    const label = completionVerified(record) ? 'Completed · action read-backs verified' : record.status === 'completed' ? 'Completion reported · action verification unconfirmed' : String(record.status || 'unknown').replaceAll('_', ' ');
    state.append(el('strong', label, 'goal-status'), el('small', 'Goal ' + record.id + ' · ' + (record.model || 'Model not recorded') + ' · ' + (record.updated_at || record.created_at || 'Time not recorded')));
    if (record.blocked_reason) state.append(el('p', text(record.blocked_reason), 'goal-warning'));
    const proposal = record.proposal;
    if (!proposal) plan.append(el('p', 'No AI proposal is stored. A missing model or graph cannot produce a substitute plan.', 'goal-warning'));
    else {
      plan.append(el('p', 'AI PROPOSAL / REVIEW AGAINST SOURCE EVIDENCE', 'eyebrow'), el('h2', 'What the agent proposes'), el('p', proposal.summary || ''), el('code', 'Proposal hash · ' + (proposal.hash || 'missing')));
      bullets(plan, 'Success criteria', proposal.success_criteria); bullets(plan, 'Assumptions', proposal.assumptions); bullets(plan, 'Questions', proposal.questions);
      const steps = el('ol', undefined, 'goal-dag');
      for (const step of list(proposal.steps)) {
        const row = el('li', undefined, 'goal-step'); row.id = 'goal-step-' + step.id;
        row.append(el('small', step.id + ' · ' + step.tool_name), el('h3', step.title), el('p', step.why || ''), el('p', list(step.depends_on).length ? 'Depends on: ' + step.depends_on.join(', ') : 'No prerequisite steps', 'goal-dependency'), el('p', 'Expected result: ' + (step.expected_result || 'Not specified')));
        const citations = el('div', undefined, 'goal-citations');
        for (const id of list(step.evidence_ids)) {
          const found = list(record.evidence).find(item => item.id === id);
          const citation = el(found ? 'a' : 'span', id + (found ? '' : ' · evidence unavailable'));
          if (found) { citation.href = '#goal-source-' + encodeURIComponent(id); }
          citations.append(citation);
        }
        row.append(citations, detail('Inspect proposed arguments', step.args || {})); steps.append(row);
      }
      plan.append(el('h3', 'Proposed work graph'), el('p', 'Dependencies below come from the stored proposal. A proposed step is not an executed tool call.', 'goal-footnote'), steps);
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
      entry.append(el('h3', item.id), el('p', item.source_id || 'Source ID not recorded'), el('code', 'SHA-256 · ' + (item.sha256 || 'not recorded')));
      const link = safeLink(item.url); if (link) { const a = el('a', 'Open captured source ↗'); a.href = link; a.target = '_blank'; a.rel = 'noopener noreferrer'; entry.append(a); }
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
      const expected = pendingCreation ? undefined : record?.id;
      const value = assertRecord(await api(expected ? ROOT + '/' + encodeURIComponent(expected) : ROOT + '/latest'), expected);
      if (token !== generation) return;
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
    examples(); render(); hydrate();
  }
})();
