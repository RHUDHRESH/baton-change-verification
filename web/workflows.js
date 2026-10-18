/* App-triggered cloud workflow. No imported historical receipt is a live run. */
'use strict';
(function () {
  const PROFILE_ITEM = 'FalkorDB/FalkorDB#3246';
  const TERMINAL = new Set(['completed', 'partial', 'failed']);
  const TARGETS = ['jira', 'slack'];
  const POLL_ATTEMPTS = 240, POLL_INTERVAL_MS = 10000;
  let current, polling = false, creating = false, generation = 0, configured;

  function safeLink(value) {
    if (typeof value !== 'string') return null;
    try {
      const parsed = new URL(value, window.location.origin);
      if (parsed.username || parsed.password || parsed.protocol !== 'https:') return null;
      if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/public/workflows/')) return parsed.href;
      if (['github.com', 'api.github.com'].includes(parsed.hostname) || /^[a-z0-9-]+\.(atlassian\.net|slack\.com)$/.test(parsed.hostname)) return parsed.href;
    } catch (_) { /* Untrusted runner output is displayed as text only. */ }
    return null;
  }

  function reviewState(record) {
    const checks = record.checks || {};
    const counted = Number.isSafeInteger(checks.passed) && checks.passed > 0 &&
      Number.isSafeInteger(checks.failed) && checks.failed === 0;
    const runner = record.runner || {};
    const runId = String(runner.run_id || runner.job_id || '');
    const runURL = runner.run_url || runner.url;
    const runMatch = typeof runURL === 'string' && /^https:\/\/github\.com\/[^/]+\/[^/]+\/actions\/runs\/(\d+)(?:[/?#]|$)/.exec(runURL);
    const runnerVerified = /^github actions$/i.test(runner.provider || '') && runner.verified === true && /^[1-9]\d*$/.test(runId) &&
      runMatch && runMatch[1] === runId;
    const checksVerified = checks.verified === true && counted && runnerVerified;
    const requested = Array.isArray(record.publish_targets) ? record.publish_targets : TARGETS;
    const targetsValid = requested.length > 0 && requested.every(target => TARGETS.includes(target));
    const publicationVerified = targetsValid && requested.every(target => {
      const value = record.publication?.[target];
      return value?.status === 'verified' && value.read_back_verified === true;
    });
    const completed = record.status === 'completed' && checksVerified && publicationVerified;
    let title = 'Workflow ' + (record.status || 'status unavailable');
    if (completed) title = 'Checks and requested publication verified';
    else if (record.status === 'completed') title = 'Reported completion needs supporting evidence';
    else if (record.status === 'partial') title = checksVerified ? 'Checks verified; publication needs attention' : 'Workflow partially complete; inspect the results';
    else if (record.status === 'failed') title = 'Workflow stopped; inspect the recorded failure';
    return {completed, checksVerified, publicationVerified, title,
      terminal: TERMINAL.has(record.status), tone: completed ? 'verified' : TERMINAL.has(record.status) ? 'attention' : 'running'};
  }

  function details(label, value) {
    const node = el('details');
    node.append(el('summary', label), el('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2)));
    return node;
  }

  function addLink(root, label, value) {
    const url = safeLink(value);
    if (!url) return;
    const node = el('a', label); node.href = url; node.target = '_blank'; node.rel = 'noopener'; root.append(node);
  }

  function render(record) {
    const root = $('workflow-result');
    if (!root) return;
    const state = reviewState(record), runner = record.runner || {};
    const heading = el('div', undefined, 'workflow-run-heading');
    heading.append(el('h3', state.title), el('span', state.completed ? 'verified' : record.status === 'completed' ? 'completion unverified' : record.status || 'unknown', 'workflow-badge ' + state.tone));
    root.replaceChildren(heading, el('p', 'Workflow ' + record.id + ' · ' + (record.item_id || PROFILE_ITEM), 'muted'));
    root.append(el('p', runner.provider ? 'Executor: ' + runner.provider + (runner.run_id ? ' · run ' + runner.run_id : '') :
      'Executor not yet confirmed. No code-check result is claimed.', 'workflow-attribution'));
    addLink(root, 'Open actual cloud runner ↗', runner.run_url || runner.url);
    if (runner.source_commit) root.append(el('p', 'Source commit: ' + runner.source_commit, 'muted'));
    if (record.limits?.scope) root.append(el('p', 'Execution scope: ' + record.limits.scope, 'muted'));
    if (record.investigation) root.append(details('Graph investigation, tool calls and source citations', record.investigation));
    const stages = el('ol', undefined, 'workflow-stages');
    for (const stage of Array.isArray(record.stages) ? record.stages : []) {
      const row = el('li'); row.append(el('strong', (stage.label || stage.id || 'Stage') + ' · ' + (stage.status || 'pending')));
      if (stage.detail) row.append(el('p', stage.detail)); stages.append(row);
    }
    if (stages.children.length) root.append(stages);
    if (record.error) root.append(el('p', record.error, 'workflow-error'));
    if (record.latest_event && !state.terminal) {
      const event = record.latest_event, data = event.data || {};
      const check = typeof data.check === 'string' ? data.check : data.check?.name;
      root.append(el('h4', 'Live runner progress · unverified'),
        el('p', (event.stage || 'Runner event') + (check ? ' · ' + check : '') + (event.at ? ' · ' + event.at : '')),
        el('p', 'Progress comes from the runner callback. It does not establish passing checks; final job, artifact and log verification is still required.', 'muted'));
      if (Number.isInteger(data.check?.exit_code)) root.append(el('p', 'Observed check exit: ' + data.check.exit_code + ' · unverified'));
      if (typeof data.log_tail === 'string') root.append(details('Live log tail · unverified', data.log_tail));
    }
    const checks = record.checks || {};
    if (Object.keys(checks).length) {
      root.append(el('h4', 'Code-check evidence'), el('p', [
        Number.isSafeInteger(checks.passed) ? checks.passed + ' passing test executions (includes targeted reruns)' : 'Passed count unavailable',
        Number.isSafeInteger(checks.failed) ? checks.failed + ' failed' : 'Failure count unavailable',
        Number.isSafeInteger(checks.ignored) ? checks.ignored + ' ignored / not run' : 'Ignored count unavailable'
      ].join(' · ')));
      if (!state.checksVerified) root.append(el('p', 'Code verification is not confirmed. Exit zero alone, an empty test run, or a saved task is not passing code evidence.', 'workflow-error'));
      for (const check of Array.isArray(checks.results) ? checks.results : []) {
        const row = details((check.name || 'Check') + ' · exit ' + (check.exit_code ?? 'unknown'), check);
        addLink(row, 'Open check log ↗', check.log_url); root.append(row);
      }
    }
    const repairs = Array.isArray(record.repairs) ? record.repairs : [];
    if (repairs.length) root.append(el('p', 'Model explanations are unverified hypotheses. Passing checks establish observed before/after behavior, not a proven root cause.', 'muted'));
    for (const repair of repairs) root.append(details('Groq repair attempt ' + (repair.attempt ?? 'recorded') + ' · proposed diff and receipt', repair));
    for (const entry of Array.isArray(record.evidence) ? record.evidence : []) {
      const row = el('div', undefined, 'workflow-evidence');
      if (entry.sha256) row.append(el('code', 'SHA-256 ' + entry.sha256));
      addLink(row, 'Open run evidence ↗', entry.url); root.append(row);
    }
    const publication = el('div', undefined, 'workflow-publication');
    publication.append(el('h4', 'Jira and Slack read-backs'));
    for (const target of Array.isArray(record.publish_targets) ? record.publish_targets.filter(target => TARGETS.includes(target)) : TARGETS) {
      const value = record.publication?.[target] || {}, row = el('div');
      row.append(el('strong', (target === 'jira' ? 'Jira' : 'Slack') + ' · ' + (value.status || 'pending')));
      if (value.error) row.append(el('p', value.error, 'workflow-error'));
      addLink(row, 'Open ' + target + ' artifact ↗', value.url); publication.append(row);
    }
    root.append(publication);
    if (record.status === 'partial') root.append(el('p', 'The workflow is not complete. Review each destination receipt before retrying publication; this page will not post again automatically.', 'workflow-error'));
    root.append(details('Inspect complete workflow receipt', record));
    $('workflow-refresh').hidden = false;
  }

  function controls() {
    const busy = creating || polling || (current && !TERMINAL.has(current.status));
    const signedIn = typeof authenticated !== 'undefined' && authenticated;
    const chosen = typeof selected !== 'undefined' && selected;
    const profile = $('workflow-start-profile'), selectedButton = $('workflow-start-selected');
    if (profile) profile.disabled = !signedIn || configured === false || !!busy;
    if (selectedButton) selectedButton.disabled = !signedIn || configured === false || !!busy || chosen?.id !== PROFILE_ITEM;
    const refresh = $('workflow-refresh'); if (refresh) refresh.disabled = polling;
    const support = $('workflow-profile-note');
    if (support) support.textContent = configured === false ? 'Cloud execution is not configured on this deployment. No runner result is substituted.' : chosen && chosen.id !== PROFILE_ITEM ?
      'Cloud checks currently support FalkorDB/FalkorDB#3246 only. This selected item has no approved execution profile.' :
      'Approved profile: FalkorDB/FalkorDB#3246 on its pinned source. Other repositories and arbitrary commands are not supported.';
  }

  async function poll(identity) {
    const token = ++generation; polling = true; $('workflow-refresh').hidden = false; controls();
    try {
      for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
        if (token !== generation) return;
        const record = await api('/api/public/workflows/' + encodeURIComponent(identity));
        if (token !== generation) return;
        if (record.id !== identity || record.item_id !== PROFILE_ITEM) throw Error('Workflow response identity does not match the requested run.');
        current = record; render(record);
        if (TERMINAL.has(record.status)) {
          $('workflow-progress').textContent = reviewState(record).title;
          if (typeof load === 'function') await load();
          return;
        }
        $('workflow-progress').textContent = 'Cloud workflow continues · update ' + (attempt + 1) + '. Checks and publication are verified separately.';
        await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      $('workflow-progress').textContent = 'Automatic polling paused. The cloud run may still be active. Refresh this receipt to continue; no new run was submitted.';
    } catch (error) {
      $('workflow-progress').textContent = 'Could not read the workflow: ' + error.message + '. No success or failure has been substituted. Refresh the receipt to retry the read.';
    } finally { if (token === generation) { polling = false; controls(); } }
  }

  async function start() {
    if (creating || polling || (current && !TERMINAL.has(current.status))) return;
    if (configured === false) { notice('Cloud execution is not configured on this deployment.'); return; }
    if (typeof authenticated === 'undefined' || !authenticated) { notice('Sign in before starting cloud checks or publishing work.'); return; }
    generation++; creating = true; $('workflow-runner')?.scrollIntoView?.({behavior: 'smooth', block: 'start'}); controls(); $('workflow-progress').textContent = 'Submitting one cloud workflow for the approved issue…';
    try {
      const record = await api('/api/public/workflows', {item_id: PROFILE_ITEM, allow_repair: true, publish_targets: TARGETS});
      if (!record || !/^[A-Za-z0-9_-]{1,100}$/.test(record.id || '')) throw Error('The server did not return a valid workflow identity.');
      current = {...record, item_id: PROFILE_ITEM};
      try { localStorage.setItem('baton.lastWorkflow', record.id); } catch (_) { /* Receipt remains visible without local storage. */ }
      render(current); await poll(record.id);
    } catch (error) {
      $('workflow-progress').textContent = 'Workflow submission was not confirmed: ' + error.message + '. This page did not repeat the POST. Inspect the runner before starting another run.';
    } finally { creating = false; controls(); }
  }

  async function hydrate() {
    const token = generation;
    try {
      let identity;
      try { identity = localStorage.getItem('baton.lastWorkflow'); } catch (_) { /* Optional browser hint. */ }
      if (/^[A-Za-z0-9_-]{1,100}$/.test(identity || '')) {
        current = {id: identity, status: 'unknown'}; await poll(identity); return;
      }
      const response = await api('/api/public/workflows');
      if (token !== generation || creating) return;
      configured = response.configured;
      const record = response.latest;
      if (record) {
        if (!/^[A-Za-z0-9_-]{1,100}$/.test(record.id || '') || record.item_id !== PROFILE_ITEM) throw Error('Latest workflow profile could not be confirmed.');
        current = record; render(record);
        if (TERMINAL.has(record.status)) $('workflow-progress').textContent = reviewState(record).title;
        else await poll(record.id);
      }
      controls();
    } catch (error) {
      if (token !== generation || creating) return;
      $('workflow-progress').textContent = 'Latest cloud workflow could not be read: ' + error.message + '. No new run was submitted.';
    }
  }

  window.BatonWorkflow = {reviewState, safeLink, render, controls, start, poll, hydrate};
  if ($('workflow-start-profile')) {
    $('workflow-start-profile').onclick = start;
    $('workflow-start-selected').onclick = start;
    $('workflow-refresh').onclick = () => { if (current?.id && !polling) poll(current.id); };
    controls();
    hydrate();
  }
})();
