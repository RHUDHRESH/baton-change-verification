/* Merged-change verification: public reads never dispatch a runner. */
'use strict';
(function () {
  const CHANGE = 'FalkorDB/falkordb-py#212';
  const COMMIT = '207000da70ca183ab02990a98bdd97d0a3e3bb1b';
  const ACTIVE = new Set(['queued', 'running', 'verifying']);
  const TERMINAL = new Set(['completed', 'partial', 'error']);
  const POLL_LIMIT = 180, POLL_MS = 10000;
  let plan, run, creating = false, polling = false, generation = 0, configured, uncertain = false, witnessGraph, displayedPlan = null, graphResizeObserver;
  const arr = value => Array.isArray(value) ? value : [];
  const stringify = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,120}$/.test(value);

  function safeLink(value) {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value, window.location.origin);
      if (url.protocol !== 'https:' || url.username || url.password) return null;
      if (url.origin === window.location.origin && /^\/api\/public\/(release-plans|release-runs|sources)\//.test(url.pathname)) return url.href;
      if (['github.com', 'api.github.com', 'raw.githubusercontent.com'].includes(url.hostname) || /^[a-z0-9-]+\.(atlassian\.net|slack\.com)$/.test(url.hostname)) return url.href;
    } catch (_) { /* Render untrusted values as text. */ }
    return null;
  }
  function addLink(root, label, value) {
    const href = safeLink(value); if (!href) return;
    const a = el('a', label); a.href = href; a.target = '_blank'; a.rel = 'noopener'; root.append(a);
  }
  function details(label, value) {
    const node = el('details'); node.append(el('summary', label), el('pre', stringify(value))); return node;
  }
  function progress(message) { $('release-progress').textContent = message; }
  function reviewState(record) {
    if (!record) return {label: 'Awaiting verification', tone: 'pending', passed: false};
    const passed = record.evidence_status === 'verified' && record.verification_status === 'passed' && record.decision === 'passed' && ['completed', 'partial'].includes(record.status);
    if (passed) return {label: 'Verification passed', tone: 'passed', passed};
    if (record.decision === 'blocked' || record.verification_status === 'failed') return {label: 'Release decision: blocked', tone: 'blocked', passed: false};
    if (record.decision === 'passed') return {label: 'Reported pass needs verified evidence', tone: 'pending', passed: false};
    if (record.status === 'error') return {label: 'Verification needs attention', tone: 'blocked', passed: false};
    if (ACTIVE.has(record.status)) return {label: 'Verification ' + record.status, tone: 'pending', passed: false};
    return {label: 'Release decision unconfirmed', tone: 'pending', passed: false};
  }
  function controls() {
    const action = $('release-start'); if (!action) return;
    const signedIn = typeof authenticated !== 'undefined' && authenticated;
    action.disabled = !signedIn || creating || polling || uncertain || !!(run && ACTIVE.has(run.status)) || configured === false;
    action.textContent = creating ? 'Preparing verification…' : 'Investigate and verify';
    $('release-auth-note').textContent = !signedIn ? 'Sign in above to investigate, run checks and publish the result. Evidence is public.' :
      configured === false ? 'Release verification is not configured on this deployment.' :
      uncertain ? 'Submission outcome is unknown. Refresh the stored receipt before deciding whether to retry.' :
      run && ACTIVE.has(run.status) ? 'A verification is already active. Read its progress below.' :
      'Runs the pinned merged change and publishes the recorded decision to your connected Jira and Slack.';
    $('release-refresh').disabled = creating || polling;
  }
  function setStage(id, label, status) {
    const node = $('release-stage-' + id); if (!node) return;
    node.dataset.status = status; node.replaceChildren(el('span', label), el('strong', String(status).replace(/_/g, ' ')));
  }
  function renderStages() {
    const investigation = plan?.investigation?.status || (plan ? plan.plan_status : 'not started');
    setStage('investigate', '01 / INVESTIGATE', investigation);
    setStage('verify', '02 / VERIFY', run?.verification_status || 'not run');
    setStage('decide', '03 / DECIDE', run?.decision || 'unconfirmed');
    const pubs = ['jira', 'slack'].map(t => run?.publication?.[t]?.status);
    setStage('publish', '04 / PUBLISH', pubs.every(s => s === 'verified') ? 'verified' : pubs.some(Boolean) ? pubs.filter(Boolean).join(' / ') : 'not published');
  }
  function environmentRows(record) {
    const envs = record?.environments;
    return Array.isArray(envs) ? envs : envs && typeof envs === 'object' ? Object.entries(envs).map(([id, value]) => ({id, ...value})) : [];
  }
  function checkRows(env) {
    return Array.isArray(env?.checks) ? env.checks : env?.checks && typeof env.checks === 'object' ? Object.entries(env.checks).map(([id, value]) => ({id, ...value})) : [];
  }
  function renderMatrix() {
    const root = $('release-matrix'); root.replaceChildren();
    if (!plan) { root.append(el('p', 'The stored plan will name the required environments and checks. No check result is assumed.')); return; }
    const environments = arr(plan.environments), checks = arr(plan.required_checks), actual = environmentRows(run);
    if (!environments.length || !checks.length) { root.append(el('p', 'Required checks or environment coverage are missing from this plan.', 'release-warning')); return; }
    const table = el('table'), head = el('thead'), heading = el('tr'); heading.append(el('th', 'Required proof'));
    for (const env of environments) heading.append(el('th', 'redis-py ' + (env.redis_version || env.id) + (env.required === false ? ' · optional' : ' · required')));
    head.append(heading); table.append(head); const body = el('tbody');
    for (const check of checks) {
      const row = el('tr'), title = el('th'); title.append(el('strong', (check.label || check.id).replace(/^test_/, '').replace(/_/g, ' ')));
      if (check.surface) title.append(el('small', check.surface)); row.append(title);
      for (const env of environments) {
        const observed = actual.find(value => value.id === env.id || (value.redis_version && value.redis_version === env.redis_version));
        const result = checkRows(observed).find(value => value.id === check.id || value.check_id === check.id || value.name === check.id);
        const cell = el('td'), status = result?.status || (result ? 'unconfirmed' : 'not run');
        // A reported check pass is distinct from the run's verified evidence.
        const verified = run?.evidence_status === 'verified';
        const label = status === 'passed' || status === 'pass' ? verified ? 'Passed · verified' : 'Reported pass · unconfirmed' : status === 'failed' || status === 'fail' ? verified ? 'Failed · verified' : 'Reported failure · unconfirmed' : status;
        cell.append(el('span', label, 'release-check ' + (verified && ['passed', 'pass'].includes(status) ? 'passed' : ['failed', 'fail', 'error'].includes(status) ? 'blocked' : 'pending')));
        if (Number.isInteger(result?.exit_code)) cell.append(el('small', 'Exit ' + result.exit_code));
        if (result?.error) cell.append(el('small', stringify(result.error)));
        if (result?.failure_excerpt) cell.append(details('Observed failure output', result.failure_excerpt)); row.append(cell);
      }
      body.append(row);
    }
    table.append(body); root.append(table);
    root.append(el('p', run ? 'Cells reflect the stored run. Reported runner results remain unconfirmed until the evidence is verified.' : 'No app run is recorded for this plan. Required coverage does not imply passing checks.', 'release-footnote'));
  }
  function renderWitnesses() {
    const root = $('release-witnesses'); root.replaceChildren();
    if (!plan) { root.append(el('p', 'Investigate the stored source to see the paths from change to required checks.')); return; }
    const paths = arr(plan.witness_paths);
    if (!paths.length) root.append(el('p', 'No graph witness paths were returned. Missing knowledge remains a visible limitation.', 'release-warning'));
    for (const [index, path] of paths.entries()) {
      const witness = details('Witness ' + (index + 1) + (path.surface ? ' · ' + path.surface : '') + (path.label ? ' · ' + path.label : ''), path);
      addLink(witness, 'Open pinned witness source ↗', path.source_url); root.append(witness);
    }
    root.append(details('Source versions and pinned commit', {change_id: plan.change_id, source_commit: plan.source_commit, source_versions: plan.source_versions}));
    for (const check of arr(plan.required_checks)) if (check.witness_path) root.append(details('Check witness · ' + (check.label || check.id), check.witness_path));
    const graphRoot = $('release-graph');
    if (witnessGraph) { witnessGraph.destroy(); witnessGraph = undefined; }
    graphRoot.hidden = true;
    if (typeof window.cytoscape !== 'function' || !paths.length) return;
    // Draw only nodes and relationships actually supplied in witness paths.
    const nodes = new Map(), edges = [], seenEdges = new Set();
    for (const path of paths) {
      const chain = Array.isArray(path) ? path : arr(path.nodes);
      for (const value of chain) {
        const data = value?.data || value;
        const id = typeof data === 'string' ? data : data?.id;
        if (id) nodes.set(id, {data: {id, label: typeof data === 'string' ? data : data.label || data.name || id}});
      }
    }
    for (const path of paths) for (const edge of arr(path.edges)) {
      const data = edge?.data || edge;
      const from = data?.source, to = data?.target, relation = data?.relation || data?.label;
      if (!nodes.has(from) || !nodes.has(to) || typeof relation !== 'string') continue;
      const key = JSON.stringify([from, relation, to]);
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      edges.push({data: {id: 'witness-' + edges.length, source: from, target: to, label: relation}});
    }
    // An unordered node inventory does not establish any connecting relationship.
    if (!edges.length) return;
    if (!nodes.size) return;
    graphRoot.hidden = false;
    witnessGraph = window.cytoscape({container: graphRoot, elements: [...nodes.values(), ...edges], layout: {name: 'breadthfirst', directed: true, padding: 35}, style: [
      {selector: 'node', style: {'background-color': '#28533c', label: 'data(label)', color: '#263b31', 'font-size': 10, 'text-wrap': 'wrap', 'text-max-width': 135, 'text-valign': 'bottom', 'text-margin-y': 9, width: 18, height: 18}},
      {selector: 'edge', style: {'line-color': '#c3ccbf', 'target-arrow-color': '#7d9b50', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', width: 1.5, label: 'data(label)', 'font-size': 7, color: '#7a827a', 'text-background-color': '#f6f6f1', 'text-background-opacity': 1}}
    ]});
    if (typeof ResizeObserver !== 'undefined') {
      if (graphResizeObserver) graphResizeObserver.disconnect();
      graphResizeObserver = new ResizeObserver(() => { if (witnessGraph) { witnessGraph.resize(); witnessGraph.fit(undefined, 35); } });
      graphResizeObserver.observe(graphRoot);
    }
    witnessGraph.on('tap', 'node', event => { $('release-source-selection').textContent = 'Graph witness node: ' + event.target.id() + '. Expand the witness and source records below to inspect its evidence.'; });
  }
  function renderInvestigation() {
    const root = $('release-investigation'); root.replaceChildren();
    if (!plan) return;
    const investigation = plan.investigation || {};
    root.append(el('p', 'Plan ' + plan.id + ' · ' + (plan.plan_status || 'status unavailable'), 'release-footnote'));
    if (investigation.summary) root.append(el('p', investigation.summary));
    if (investigation.error) root.append(el('p', 'Investigation error: ' + stringify(investigation.error), 'release-warning'));
    if (investigation.model) root.append(el('p', 'Investigation model: ' + investigation.model, 'release-footnote'));
    root.append(details('Investigation trace · graph queries and source reads', investigation.trace || []));
    root.append(details('Model provider receipts · inference evidence', investigation.receipts || []));
    if (plan.plan_status !== 'ready') root.append(el('p', 'This plan is incomplete. Execution has not been authorized by a ready plan.', 'release-warning'));
    const limitations = arr(plan.limitations);
    if (limitations.length) { const list = el('ul', undefined, 'release-limitations'); for (const item of limitations) list.append(el('li', stringify(item))); root.append(el('h4', 'Knowledge and coverage limits'), list); }
    root.append(details('Plan receipt and content hash', plan));
  }
  function renderRun() {
    const root = $('release-decision'), evidence = $('release-evidence'), publication = $('release-publication');
    const state = reviewState(run); root.className = 'release-decision ' + state.tone;
    root.replaceChildren(el('p', 'CURRENT DECISION', 'eyebrow'), el('h2', state.label)); evidence.replaceChildren(); publication.replaceChildren();
    if (!run) {
      root.append(el('p', 'Read the stored plan, investigate its source, then verify the merged change across the required environments.'));
      evidence.append(el('p', 'No app execution receipt loaded. External preflight observations are not an app run.'));
    } else {
      root.append(el('p', 'Evidence ' + (run.evidence_status || 'unconfirmed') + ' · Checks ' + (run.verification_status || 'not run')));
      root.append(el('small', 'Run ' + run.id + (run.created_at ? ' · ' + run.created_at : '')));
      if (run.error) root.append(el('p', stringify(run.error), 'release-warning'));
      if (run.reason || run.decision_reason) root.append(el('p', stringify(run.reason || run.decision_reason)));
      if (!state.passed && run.status === 'completed') root.append(el('p', 'A completed run does not establish a passing release decision.', 'release-footnote'));
      addLink(evidence, 'Open actual cloud runner ↗', run.runner?.run_url);
      evidence.append(details('Execution receipts · checks and environment evidence', run.environments || []));
      const logs = details('Runner logs · observed command output', run.logs || run.runner?.logs || {message: 'Open the preserved raw log for each verified environment below.'});
      if (run.evidence_status === 'verified') {
        addLink(evidence, 'Open preserved verification report ↗', run.evidence?.url);
        for (const environment of environmentRows(run)) if (/^[A-Za-z0-9_.-]+$/.test(environment.id || '')) {
          const base = '/api/public/release-runs/' + encodeURIComponent(run.id) + '/logs/' + encodeURIComponent(environment.id) + '/';
          addLink(logs, 'redis-py ' + (environment.redis_version || environment.id) + ' · raw pytest log ↗', base + 'pytest.log');
          addLink(logs, 'redis-py ' + (environment.redis_version || environment.id) + ' · setup log ↗', base + 'setup.log');
        }
      } else logs.append(el('p', 'Preserved evidence is available only after independent verification.', 'release-footnote'));
      evidence.append(logs);
      if (run.latest_event) evidence.append(details('Runner progress event · unverified until final receipt', run.latest_event));
      evidence.append(details('Raw run receipt', run));
    }
    for (const target of ['jira', 'slack']) {
      const value = run?.publication?.[target], card = el('div', undefined, 'release-destination');
      card.append(el('strong', target === 'jira' ? 'Jira' : 'Slack'), el('span', value?.status || 'not published', 'release-publication-status'));
      if (value?.message) card.append(el('p', value.message));
      if (value?.error) card.append(el('p', stringify(value.error), 'release-warning'));
      if (value) addLink(card, 'Open published result ↗', value.url);
      publication.append(card);
    }
    publication.append(el('p', 'Publication reports delivery to your workspace. It does not change the verification decision.', 'release-footnote'));
  }
  function render() {
    $('release-plan-title').textContent = plan?.title || 'Verify the merged Python client change';
    $('release-source-commit').textContent = plan?.source_commit || COMMIT;
    renderStages(); renderMatrix();
    if (displayedPlan !== plan) { renderWitnesses(); renderInvestigation(); displayedPlan = plan; }
    renderRun(); controls();
  }
  function assertPlan(value) {
    if (!value || !validId(value.id) || value.change_id !== CHANGE || value.source_commit !== COMMIT) throw Error('Stored plan identity or pinned source does not match this change');
    return value;
  }
  function assertRun(value, identity) {
    if (!value || !validId(value.id) || value.id !== identity || value.plan_id !== plan?.id) throw Error('Run identity does not match the requested plan and receipt');
    return value;
  }
  async function poll(identity) {
    const token = ++generation; polling = true; controls();
    try {
      for (let attempt = 0; attempt < POLL_LIMIT; attempt++) {
        const response = await api('/api/public/release-runs/' + encodeURIComponent(identity));
        if (token !== generation) return;
        run = assertRun(response.run || response, identity); render();
        progress('Stored run ' + run.id + ' · ' + run.status + '. ' + reviewState(run).label + '.');
        if (TERMINAL.has(run.status)) return;
        await new Promise(resolve => setTimeout(resolve, POLL_MS)); if (token !== generation) return;
      }
      progress('Live reading paused at the polling limit. The run may still be active. Refresh the receipt to continue; no new run was submitted.');
    } catch (error) {
      if (token === generation) progress('Could not read execution evidence: ' + error.message + '. The last stored result remains visible; no success or failure was substituted.');
    } finally { if (token === generation) { polling = false; controls(); } }
  }
  async function hydrate() {
    if (creating || polling) return;
    const token = ++generation; progress('Reading the latest stored verification plan…');
    try {
      const response = await api('/api/public/release-plans/latest'); if (token !== generation || creating) return;
      configured = response.configured;
      const value = response.latest ?? response.plan ?? (response.id ? response : null);
      if (!value) { plan = undefined; run = undefined; uncertain = false; render(); progress('No release plan is stored yet. Sign in to investigate this merged change.'); return; }
      plan = assertPlan(value); run = undefined; uncertain = false; render();
      progress('Stored plan loaded. ' + (plan.latest_run_id ? 'Reading its execution receipt…' : 'No app run has been recorded for this plan.'));
      if (plan.latest_run_id) {
        if (!validId(plan.latest_run_id)) throw Error('Stored run identity is invalid');
        await poll(plan.latest_run_id);
      }
    } catch (error) {
      if (token === generation) progress('Stored release evidence unavailable: ' + error.message + '. No new plan or run was submitted.');
    } finally { controls(); }
  }
  async function start() {
    if (creating || polling || uncertain || (run && ACTIVE.has(run.status))) return;
    if (typeof authenticated === 'undefined' || !authenticated) { notice('Sign in before investigating, executing checks or publishing a release decision.'); return; }
    if (configured === false) { notice('Release verification is not configured on this deployment.'); return; }
    generation++; creating = true; controls(); progress('Investigating the pinned merged change. One plan request is being submitted…');
    let submitted = false;
    try {
      submitted = true;
      const response = await api('/api/public/release-plans', {change_id: CHANGE});
      plan = assertPlan(response.plan || response); run = undefined; render();
      if (plan.plan_status !== 'ready') { progress('Investigation saved an incomplete plan. Inspect missing knowledge and provider receipts; no execution was submitted.'); return; }
      if (typeof plan.plan_hash !== 'string' || !plan.plan_hash) throw Error('A ready plan did not include a content hash');
      progress('Plan ready. Submitting one verification against this exact plan hash…');
      const result = await api('/api/public/release-plans/' + encodeURIComponent(plan.id) + '/execute', {expected_plan_hash: plan.plan_hash, publish_targets: ['jira', 'slack']});
      const value = result.run || result;
      run = assertRun(value, value.id); plan.latest_run_id = run.id; render();
      await poll(run.id);
    } catch (error) {
      uncertain = submitted;
      progress('Submission was not confirmed: ' + error.message + '. This page did not repeat either POST. Refresh stored evidence before an explicit retry. A stale plan must be investigated again.');
    } finally { creating = false; controls(); }
  }
  window.BatonRelease = {reviewState, safeLink, environmentRows, render, controls, hydrate, start, poll};
  if ($('release-start')) {
    $('release-start').onclick = start; $('release-refresh').onclick = hydrate;
    render(); hydrate();
  }
})();
