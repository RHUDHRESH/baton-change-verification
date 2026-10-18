"use strict";
const $ = (id) => document.getElementById(id);
const savedSeed = Number(localStorage.getItem("baton-seed"));
const state = { data: null, seed: [7, 101, 202, 303].includes(savedSeed) ? savedSeed : 7, replay: false, catalogue: {}, preview: null, pending: false };
state.operator = false;
const laneNames = { W: "Checklist", R: "Connected records", G: "Baton" };
function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function date(at, options = {}) { return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC", ...options }).format(at); }
function note(text) { $("notice").textContent = text; $("notice").hidden = !text; }
async function request(path, payload) {
  const response = await fetch(path, { method: payload === undefined ? "GET" : "POST", headers: payload === undefined ? {} : { "Content-Type": "application/json" }, body: payload === undefined ? undefined : JSON.stringify(payload), signal: AbortSignal.timeout(60000) });
  const result = await response.json();
  if (!response.ok) { const error = new Error(typeof result.detail === "string" ? result.detail : `The request failed (${response.status}).`); error.status = response.status; throw error; }
  return result;
}
function groups() {
  const map = new Map();
  for (const row of state.data.lanes.G.failures) {
    if (!map.has(row.duty)) map.set(row.duty, []);
    map.get(row.duty).push(row);
  }
  return [...map.entries()];
}
function mode() {
  $("connection").textContent = state.replay ? "Recorded replay" : "Live graph connected";
  $("connection").className = `status${state.replay ? " replay" : ""}`;
  for (const id of ["capacity", "replay", "write", "question"]) $(id).disabled = state.replay;
  $("ask-form").querySelector("button").disabled = state.replay;
}
function timeline() {
  const data = state.data;
  const axis = $("calendar-axis"); axis.replaceChildren(element("span", "DAY OF THE MONTH"));
  for (let day = 0; day < data.window_days; day++) axis.append(element("span", new Date(data.now + day * data.day_ms).getUTCDate()));
  $("strips").replaceChildren();
  for (const lane of ["W", "R", "G"]) {
    const rows = data.lanes[lane].failures;
    $("count-" + lane).textContent = rows.length;
    const line = element("div", undefined, "lane-row");
    const label = element("div", undefined, "lane-label"); label.append(element("span", lane, "lane-badge"), element("span", laneNames[lane])); line.append(label);
    for (let day = 0; day < data.window_days; day++) {
      const events = rows.filter((r) => r.day === day);
      const cell = element("button", events.length || "", `day${events.length ? " has-events" : ""}`);
      cell.type = "button"; cell.dataset.count = events.length;
      cell.setAttribute("aria-label", `${laneNames[lane]}, ${date(data.now + day * data.day_ms)}: ${events.length} events lose coverage`);
      cell.title = cell.getAttribute("aria-label"); cell.disabled = !events.length;
      cell.addEventListener("click", () => proof(`${date(data.now + day * data.day_ms)} · ${laneNames[lane]}`, events, lane));
      line.append(cell);
    }
    $("strips").append(line);
  }
  $("window-label").textContent = `${date(data.now)} – ${date(data.now + (data.window_days - 1) * data.day_ms, { year: "numeric" })} · all dates UTC`;
  const unchanged = data.live_hash_before && data.live_hash_before === data.live_hash_after;
  $("integrity").textContent = unchanged ? `${state.replay ? "Recorded: " : ""}✓ Live graph unchanged` : "Graph integrity unavailable";
}
function dutyList() {
  $("duty-list").replaceChildren(); $("assignments").replaceChildren();
  const entries = groups(); $("duty-count").textContent = `${entries.length} duties`;
  const people = state.data.people.filter((person) => person.id !== state.data.leaver && person.left_at === null);
  for (const [id, rows] of entries) {
    const first = rows[0]; const informal = rows.some((row) => row.status !== "record");
    const row = element("div", undefined, "duty-row"); row.append(element("span", informal ? "↗" : "◷", "duty-symbol"));
    const info = element("div", undefined, "duty-info"); info.append(element("strong", first.duty_name || id));
    const details = element("small"); details.append(element("span", informal ? "Informal duty" : "Recorded", `tag${informal ? " informal" : ""}`), document.createTextNode(`${rows.length} event${rows.length === 1 ? "" : "s"} · first gap ${date(first.at)}`)); info.append(details);
    const button = element("button", "View proof ↗", "evidence-link"); button.type = "button"; button.setAttribute("aria-label", `View proof for ${first.duty_name || id}`); button.addEventListener("click", () => proof(first.duty_name || id, rows, "G"));
    row.append(info, button); $("duty-list").append(row);
    const assignment = element("div", undefined, "assignment"); const label = element("label", first.duty_name || id); const controlId = `successor-${entries.findIndex(([duty]) => duty === id)}`; label.htmlFor = controlId; label.append(element("small", `${rows.length} scheduled events`));
    const select = element("select"); select.id = controlId; select.dataset.duty = id; select.append(new Option("Choose successor", ""));
    for (const person of people) select.append(new Option(person.name, person.id));
    select.disabled = state.replay;
    select.addEventListener("change", () => { state.preview = null; $("write").hidden = true; $("receipt").hidden = true; $("hand-status").textContent = "Plan changed. Replay to check it."; });
    assignment.append(label, select); $("assignments").append(assignment);
  }
  if (!entries.length) { $("duty-list").append(element("p", "No newly uncovered duties in this rehearsal.", "empty")); $("assignments").append(element("p", "No successors needed for these scheduled events.", "empty")); }
  const refused = state.data.unpromoted || []; $("refused-count").textContent = refused.length; $("refused").replaceChildren();
  for (const belief of refused) $("refused").append(element("p", `${belief.belief}: ${belief.reason}`, "refused-item"));
}
function proof(title, rows, lane) {
  $("proof-title").textContent = title; const body = $("proof-body"); body.replaceChildren();
  body.append(element("p", `${rows.length} scheduled event${rows.length === 1 ? "" : "s"} lose coverage after ${state.data.leaver_name} leaves. ${state.replay ? "This is recorded replay data." : "This rehearsal ran on an isolated FalkorDB copy."}`));
  for (const row of rows) {
    const item = element("div", undefined, "proof-event"); item.append(element("strong", row.label), element("p", `${date(row.at, { hour: "2-digit", minute: "2-digit" })} UTC · ${row.status === "record" ? "Recorded responsibility" : "Evidence-gated belief (fixture confirmation)"}`)); body.append(item);
  }
  body.append(element("h3", "The supporting evidence"));
  const unique = new Map(rows.flatMap((row) => row.sources || []).map((source) => [source.id || source, source]));
  for (const [id, source] of unique) { const card = element("div", undefined, "source"); card.append(element("small", `${source.type || "source"} / ${id}`), element("p", source.text || id)); body.append(card); }
  if (!unique.size) body.append(element("p", "No source text was captured for this record."));
  const query = state.data.lanes[lane].cypher;
  if (query) { body.append(element("h3", "Coverage query used"), element("pre", query)); }
  body.append(element("h3", "Live graph fingerprint"), element("pre", `Before: ${state.data.live_hash_before || "unavailable"}\nAfter:  ${state.data.live_hash_after || "unavailable"}`));
  $("proof").showModal();
}
function render() {
  const data = state.data;
  $("leaver-name").textContent = data.leaver_name;
  const person = data.people.find((p) => p.id === data.leaver);
  $("initials").textContent = data.leaver_name.split(" ").map((word) => word[0]).slice(0, 2).join("");
  $("leaver-role").textContent = `${person?.role || "Team member"} · ${person?.team || "Halden"}`;
  $("departure-date").textContent = date(data.leave_at - data.day_ms, { year: "numeric" });
  $("company-number").textContent = `Company #${data.seed}`;
  $("question").placeholder = `What does ${data.leaver_name} owe?`;
  $("chips").replaceChildren();
  for (const [label, question] of [["Who owes what?", `What does ${data.leaver_name} owe?`], ["What loses coverage?", `What breaks if ${data.leaver_name} leaves?`]]) {
    const chip = element("button", label); chip.type = "button"; chip.disabled = state.replay; chip.addEventListener("click", () => { $("question").value = question; $("ask-form").requestSubmit(); }); $("chips").append(chip);
  }
  state.preview = null; $("write").hidden = true; $("consent-label").hidden = true; $("consent").checked = false; $("receipt").hidden = true; $("hand-status").textContent = ""; $("capacity-result").replaceChildren(); $("answer").replaceChildren();
  mode(); timeline(); dutyList();
  document.dispatchEvent(new Event("baton:company-loaded"));
}
async function load() {
  if (state.pending) return;
  state.pending = true; $("main").classList.add("busy"); $("main").setAttribute("aria-busy", "true"); $("refresh").disabled = true; $("seed").disabled = true; $("connection").className = "status loading"; $("connection").textContent = "Running rehearsal"; note("");
  try {
    state.data = await request(`/api/demo?seed=${state.seed}`); state.replay = false; render();
    note(`FIXTURE · ${state.data.extraction?.model || "Supplied model"} extraction replayed from cache. Coverage is computed live in FalkorDB; no model is called per question.`);
    await catalogue();
  } catch (error) {
    try {
      const response = await fetch("/samples/api_demo_seed7.json"); if (!response.ok) throw error;
      state.data = await response.json(); state.replay = true; state.seed = state.data.seed; $("seed").value = String(state.seed); render();
      note(`Recorded replay · Live rehearsal unavailable: ${error.message} Showing supplied Company #7 data. Live actions are disabled. Re-run to reconnect.`);
    } catch { note(`Unable to load a company: ${error.message}`); $("connection").textContent = "Unavailable"; $("connection").className = "status replay"; }
  } finally { state.pending = false; $("main").classList.remove("busy"); $("main").setAttribute("aria-busy", "false"); $("refresh").disabled = false; $("seed").disabled = false; }
}
async function catalogue() {
  try {
    state.catalogue = await request("/api/catalogue"); $("catalogue").replaceChildren();
    for (const [name, query] of Object.entries(state.catalogue)) { const details = element("details"); details.append(element("summary", name), element("pre", query)); $("catalogue").append(details); }
  } catch { $("catalogue").textContent = "The query catalogue is currently unavailable."; }
}
function assignments() { return Object.fromEntries([...$("assignments").querySelectorAll("select")].filter((select) => select.value).map((select) => [select.dataset.duty, select.value])); }
function receipt(text, rows = []) {
  const target = $("receipt"); target.replaceChildren(element("strong", text));
  if (rows.length) { const list = element("ul"); for (const row of rows) list.append(element("li", row)); target.append(list); }
  target.hidden = false;
}
$("handover-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (state.replay || state.pending) return;
  const assign = assignments(); if (!Object.keys(assign).length) { $("hand-status").textContent = "Choose at least one successor to rehearse."; return; }
  $("replay").disabled = true; $("write").hidden = true; $("write").textContent = "Write accepted plan"; $("hand-status").textContent = "Replaying the month on a graph copy…";
  try {
    const result = await request("/api/handover", { seed: state.seed, assign });
    state.preview = { result, assign };
    $("hand-status").textContent = `${result.failures_after.length} uncovered events remain. Live ownership unchanged.`;
    receipt(`${result.accepted.length} eligible successors in preview`, [...result.accepted.map((row) => `${row.duty} → ${row.person}`), ...result.refused.map((row) => `Refused ${row.duty}: ${row.reason}`)]);
    $("write").hidden = !result.accepted.length;
    $("consent-label").hidden = !result.accepted.length; $("consent").checked = false;
  } catch (error) { $("hand-status").textContent = error.message; }
  finally { $("replay").disabled = false; }
});
$("write").addEventListener("click", async () => {
  if (!state.preview || state.replay || state.pending) return;
  if (!state.operator || !state.preview.result.preview_token) { $("operator-dialog").showModal(); $("operator-token").focus(); return; }
  if (!$("consent").checked) { $("hand-status").textContent = "Confirm that the selected successors agreed before saving."; return; }
  $("write").disabled = true; $("replay").disabled = true; $("hand-status").textContent = "Writing accepted ownership and verifying the repository…";
  try {
    const accepted = Object.fromEntries(state.preview.result.accepted.map((row) => [row.duty, row.person]));
    const result = await request("/api/commit", { seed: state.seed, assign: accepted,
      preview_token: state.preview.result.preview_token, consent_confirmed: $("consent").checked });
    document.dispatchEvent(new Event("baton:committed"));
    const external = result.external;
    receipt(`${result.committed.length} duties written · ${external?.verified ? "repository read-back verified" : "external write pending"}`, [`Still uncovered: ${result.still_uncovered.length} duties`, ...(external ? [`File: ${external.file}`, `Commit: ${external.commit}`] : []), ...result.refused.map((row) => `Refused ${row.duty}: ${row.reason}`)]);
    $("hand-status").textContent = result.ready_to_leave ? "All scheduled duties have coverage in this replay." : "Ownership saved. Some duties still need coverage.";
    if (external?.verified) { $("write").hidden = true; state.preview = null; }
    else { $("write").hidden = false; $("write").textContent = "Retry repository write"; $("hand-status").textContent = "Graph ownership saved. Repository write needs a retry."; }
  } catch (error) { $("hand-status").textContent = error.message; if (error.status === 401) { state.operator = false; $("operator").textContent = "Operator sign in"; $("operator-dialog").showModal(); } }
  finally { $("write").disabled = false; $("replay").disabled = false; }
});
$("reset").addEventListener("click", () => { for (const select of $("assignments").querySelectorAll("select")) select.value = ""; state.preview = null; $("write").hidden = true; $("receipt").hidden = true; $("hand-status").textContent = "Plan cleared. Saved ownership is unaffected."; });

$("operator").addEventListener("click", async () => {
  if (!state.operator) { $("operator-dialog").showModal(); $("operator-token").focus(); return; }
  try { await request("/api/auth/logout", {}); state.operator = false; $("operator").textContent = "Operator sign in"; state.preview = null; $("write").hidden = true; $("consent-label").hidden = true; }
  catch (error) { note(error.message); }
});
$("close-operator").addEventListener("click", () => { $("operator-token").value = ""; $("operator-dialog").close(); });
$("operator-dialog").addEventListener("close", () => { $("operator-token").value = ""; });
$("operator-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try { await request("/api/auth/login", {token: $("operator-token").value}); state.operator = true;
    $("operator").textContent = "Operator · sign out"; $("operator-dialog").close(); $("operator-message").textContent = "";
    if (state.preview) $("handover-form").requestSubmit();
  } catch (error) { $("operator-message").textContent = error.message; }
  finally { $("operator-token").value = ""; button.disabled = false; }
});
request("/api/auth/status").then(result => { state.operator = result.authenticated; $("operator").textContent = state.operator ? "Operator · sign out" : "Operator sign in"; }).catch(() => {});
$("capacity").addEventListener("click", async () => {
  if (state.replay || state.pending) return;
  const planSeed = state.seed;
  $("capacity").disabled = true; $("capacity-result").textContent = "Checking skills and capacity…";
  try {
    const result = await request(`/api/cut?seed=${planSeed}`); if (planSeed !== state.seed) return; const body = $("capacity-result"); body.replaceChildren(element("strong", `${result.flow} / ${result.demand}`), element("p", result.verdict === "POSSIBLE" ? "The team has enough eligible capacity." : "The team cannot absorb every duty with current skills and capacity."));
    if (result.unplaceable.length) body.append(element("p", `Unfilled in this flow: ${result.unplaceable.join(", ")}`));
    const details = element("details"); details.append(element("summary", "View the capacity certificate"), element("pre", JSON.stringify({ min_cut: result.min_cut, certificate: result.certificate, n_minus_1: result.n_minus_1 }, null, 2))); body.append(details);
    if (result.assignments?.length) {
      const use = element("button", result.verdict === "POSSIBLE" ? "Use suggested successors →" : "Use partial plan →", "button lime"); use.type = "button";
      use.addEventListener("click", () => {
        if (state.replay || state.pending || planSeed !== state.seed) return;
        const suggested = new Map(result.assignments.map((row) => [row.duty, row.person]));
        for (const select of $("assignments").querySelectorAll("select")) select.value = suggested.get(select.dataset.duty) || "";
        state.preview = null; $("write").hidden = true; $("receipt").hidden = true;
        $("hand-status").textContent = "Graph-derived successors selected. Replay to verify coverage.";
        $("handover-section").scrollIntoView({ behavior: "smooth", block: "start" });
      }); body.append(use);
    }
  } catch (error) { $("capacity-result").textContent = error.message; }
  finally { $("capacity").disabled = false; }
});
$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (state.replay || state.pending) return;
  const submit = $("ask-form").querySelector("button"); submit.disabled = true; $("answer").textContent = "Following the graph…";
  try {
    const result = await request("/api/ask", { seed: state.seed, question: $("question").value.trim() });
    const target = $("answer"); target.replaceChildren(element("p", result.answer)); target.append(element("small", `${result.tool} · ${result.rows.length} rows · ${result.sources.length} cited sources · 0 model calls`));
    if (result.sources.length) { const sources = element("details"); sources.append(element("summary", "Source IDs"), element("pre", result.sources.join("\n"))); target.append(sources); }
    const query = element("details"); query.append(element("summary", "Exact query used"), element("pre", result.cypher)); target.append(query);
  } catch (error) { $("answer").textContent = error.message; }
  finally { submit.disabled = false; }
});
$("seed").value = String(state.seed);
$("seed").addEventListener("change", () => { state.seed = Number($("seed").value); localStorage.setItem("baton-seed", String(state.seed)); load(); });
$("refresh").addEventListener("click", load);
$("close-proof").addEventListener("click", () => $("proof").close());
$("proof").addEventListener("click", (event) => { if (event.target === $("proof")) { const box = $("proof").getBoundingClientRect(); if (event.clientX < box.left) $("proof").close(); } });
let theme = localStorage.getItem("baton-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
document.documentElement.dataset.theme = theme;
$("theme").addEventListener("click", () => { theme = theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = theme; localStorage.setItem("baton-theme", theme); });
load();
