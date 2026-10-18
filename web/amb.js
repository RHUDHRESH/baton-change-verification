"use strict";
const $ = id => document.getElementById(id);
function el(tag, text) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; }
let data, graph, timer, generation = 0;
async function api(url, body) {
  const r = await fetch(url, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
  const result = await r.json(); if (!r.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Request failed (${r.status})`); return result;
}
function showResult(target, result) {
  target.replaceChildren(el("strong", result.answers.length ? result.answers.join(", ") : "No matching facts at this step."));
  target.append(el("p", `Inbox step ${result.step} · ${result.sources.length} source receipts`));
  for (const id of result.sources) { const a = el("a", `${id} ↗ `); a.href = `#${id}`; a.onclick = () => { const row = $(id); if (row) row.open = true; }; target.append(a); }
  const details = el("details"); details.append(el("summary", "Exact Cypher"), el("pre", result.cypher)); target.append(details);
}
function subjects() {
  const selected = $("subject").value, kind = $("tool").value === "oncall" ? "Team" : "Service";
  $("subject").replaceChildren(...data.nodes.filter(n => n.data.kind === kind).map(n => new Option(n.data.label, n.data.id)));
  if ([...$("subject").options].some(o => o.value === selected)) $("subject").value = selected;
}
async function load(step) {
  const current = ++generation;
  $("status").textContent = "Reading company memory…";
  try {
    const result = await api(`/api/amb?step=${step}`); if (current !== generation) return;
    data = result; $("step").value = step; $("step-label").textContent = `Inbox step ${step} of 50`;
    $("counts").textContent = `${data.nodes.length} entities · ${data.edges.length} current connections`;
    if (graph) graph.destroy();
    graph = cytoscape({container:$("amb-graph"), elements:[...data.nodes,...data.edges], layout:{name:"cose", animate:false, nodeRepulsion:120000, idealEdgeLength:100, padding:30},
      style:[{selector:"node",style:{label:"data(label)","font-size":10,"text-valign":"bottom","text-margin-y":6,"background-color":"#527b5e",color:getComputedStyle(document.documentElement).getPropertyValue("--ink"),width:23,height:23}},
        {selector:'node[kind = "Service"]',style:{shape:"round-rectangle","background-color":"#8197b0"}}, {selector:'node[kind = "Team"]',style:{shape:"diamond","background-color":"#bba56e"}},
        {selector:"edge",style:{"curve-style":"bezier",width:1.3,"target-arrow-shape":"triangle","line-color":"#a0b19e","target-arrow-color":"#a0b19e"}},
        {selector:":selected",style:{"border-width":3,"border-color":"#466bcd","line-color":"#466bcd"}}]});
    function inspect(item) { $("detail").replaceChildren(el("strong",item.data("label")),el("pre",JSON.stringify(item.data(),null,2))); const id=item.data("source_id"); if(id){const a=el("a",`Read ${id} ↗`);a.href=`#${id}`;a.onclick=()=>{$(id).open=true;};$("detail").append(a);} }
    graph.on("tap","node, edge",e=>inspect(e.target));
    $("entity").replaceChildren(new Option("Choose an entity", ""), ...data.nodes.map(n=>new Option(`${n.data.kind}: ${n.data.label}`,n.data.id)));
    $("entity").onchange=()=>{const item=graph.getElementById($("entity").value);if(item.length)inspect(item);};
    $("inbox-list").replaceChildren();
    for (const item of [...data.inbox].reverse()) { const d=el("details");d.id=item.id;d.append(el("summary",`${item.step.toString().padStart(2,"0")} · ${item.kind.replaceAll("_"," ")} · ${item.time.slice(0,16).replace("T"," ")} UTC`),el("pre",item.text));$("inbox-list").append(d); }
    if(!data.inbox.length)$("inbox-list").append(el("p","No inbox items read yet. Move the slider to begin."));
    $("question-list").replaceChildren();$("score").textContent="";$("answer").replaceChildren();$("detail").textContent="Select a node or connection to see its source.";
    for (const q of data.questions) {const d=el("details");d.append(el("summary",`${q.id} · ${q.category} · step ${q.step} — ${q.text}`));const b=el("button","Run this question →");b.className="button plain";const out=el("div");b.onclick=async()=>{b.disabled=true;try{const r=await api(`/api/amb/questions/${q.id}`);showResult(out,r);out.prepend(el("p",r.correct?"✓ Matches benchmark answer":"Answer differs from benchmark"));}catch(e){out.textContent=e.message;}finally{b.disabled=false;}};d.append(b,out);$("question-list").append(d);}
    subjects();$("status").textContent="Live FalkorDB · parsed facts";
  } catch(e){$("status").textContent=e.message;stop();}
}
function stop(){clearInterval(timer);timer=null;$("play").textContent="Play inbox →";}
$("step").addEventListener("change",()=>{stop();load(Number($("step").value));});
$("play").onclick=()=>{if(timer){stop();return;}let next=Number($("step").value);if(next===50)next=0;load(next);$("play").textContent="Pause replay";timer=setInterval(()=>{if(next>=50){stop();return;}load(++next);},1800);};
$("tool").onchange=()=>{if(data)subjects();};
$("query-form").onsubmit=async e=>{e.preventDefault();if(!data)return;const step=data.step;try{const r=await api("/api/amb/ask",{tool:$("tool").value,subject:$("subject").value,step});if(data.step===step)showResult($("answer"),r);}catch(error){$("answer").textContent=error.message;}};
$("check-all").onclick=async()=>{if(!data)return;stop();const questions=data.questions,step=data.step;$("check-all").disabled=true;let correct=0;try{for(const q of questions){const r=await api(`/api/amb/questions/${q.id}`);correct+=Number(r.correct);}if(data.step===step)$("score").textContent=`${correct} / ${questions.length} benchmark answers match · parsed facts, live graph queries`;}catch(e){$("score").textContent=e.message;}finally{$("check-all").disabled=false;}};
load(50);
