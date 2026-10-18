"use strict";
(() => {
  let graph = null;
  function inspect(item) {
    if (!item || item.empty()) return;
    graph.elements().unselect(); item.select();
    const data = item.data();
    $("graph-detail").replaceChildren(element("strong", data.label || data.entity_id), element("pre", JSON.stringify({ kind: data.kind, source_ids: data.source_ids, ...data.properties }, null, 2)));
  }
  async function history() {
    const seed = state.seed;
    if (state.replay) { $("history-list").textContent = "Recorded replay has no live change history."; return; }
    $("refresh-history").disabled = true;
    try {
      const response = await request(`/api/receipts?seed=${seed}`);
      if (seed !== state.seed) return;
      const target = $("history-list"); target.replaceChildren();
      if (!response.receipts.length) target.append(element("p", "No ownership changes saved for this company yet."));
      for (const receipt of response.receipts) {
        const card = element("details", undefined, "history-card");
        const summary = element("summary", `${receipt.state === "verified" ? "✓ Verified" : "Repository pending"} · ${(receipt.committed || []).length} duties · ${receipt.operation_id.slice(0, 8)}`);
        card.append(summary, element("pre", JSON.stringify(receipt, null, 2))); target.append(card);
      }
    } catch (error) { $("history-list").textContent = error.message; }
    finally { $("refresh-history").disabled = state.replay; }
  }
  $("load-graph").addEventListener("click", async () => {
    if (state.replay || state.pending) return;
    const seed = state.seed; $("load-graph").disabled = true; $("graph-summary").textContent = "Reading the departure fork…";
    try {
      const result = await request(`/api/graph?seed=${seed}`);
      if (seed !== state.seed) return;
      if (graph) graph.destroy();
      $("graph-canvas").classList.add("is-loaded");
      const colors = getComputedStyle(document.documentElement);
      graph = cytoscape({ container: $("graph-canvas"), elements: [...result.nodes, ...result.edges],
        layout: { name: "grid", cols: $("graph-canvas").clientWidth < 650 ? 3 : 6,
                  nodeDimensionsIncludeLabels: true, avoidOverlap: true, padding: 35 },
        minZoom: .15, maxZoom: 3,
        style: [
          { selector: "node", style: { label: "data(label)", "font-size": 10, color: colors.getPropertyValue("--ink"), "text-wrap": "wrap", "text-max-width": 95, "text-valign": "bottom", "text-margin-y": 7, "background-color": "#527b5e", width: 25, height: 25 } },
          { selector: 'node[kind = "Duty"]', style: { shape: "round-rectangle", "background-color": "#bba56e" } },
          { selector: 'node[kind = "Rota"]', style: { shape: "diamond", "background-color": "#8197b0" } },
          { selector: "node[?departed]", style: { "background-color": "#bc7258", "border-width": 2, "border-color": "#b1513a" } },
          { selector: "edge", style: { "curve-style": "bezier", width: 1.2, "line-color": "#a0b19e", "target-arrow-color": "#a0b19e", "target-arrow-shape": "triangle", "arrow-scale": .6 } },
          { selector: 'edge[kind = "HOLDS"]', style: { "line-style": "dashed", "line-color": "#c1944c", "target-arrow-color": "#c1944c", width: 2.5 } },
          { selector: 'edge[kind = "CAN"]', style: { opacity: .3, "line-style": "dotted" } },
          { selector: ":selected", style: { "border-color": "#466bcd", "border-width": 3, "line-color": "#466bcd", "target-arrow-color": "#466bcd" } }
        ] });
      graph.on("tap", "node, edge", (event) => inspect(event.target));
      $("graph-entity").replaceChildren(new Option("Choose a person or duty", ""));
      for (const node of result.nodes) $("graph-entity").append(new Option(`${node.data.kind}: ${node.data.label}`, node.data.id));
      $("graph-entity").disabled = false; $("graph-fit").disabled = false;
      $("graph-summary").textContent = `${result.nodes.length} entities · ${result.edges.length} connections · ${date(result.at)} UTC · ${result.live_hash_before === result.live_hash_after ? "live graph unchanged" : "graph changed during view"}`;
    } catch (error) { $("graph-summary").textContent = error.message; }
    finally { $("load-graph").disabled = state.replay; }
  });
  $("graph-entity").addEventListener("change", () => { if (graph) inspect(graph.getElementById($("graph-entity").value)); });
  $("graph-fit").addEventListener("click", () => graph?.fit(undefined, 40));
  $("refresh-history").addEventListener("click", history);
  document.addEventListener("baton:company-loaded", () => {
    if (graph) { graph.destroy(); graph = null; }
    $("graph-canvas").classList.remove("is-loaded"); $("graph-detail").replaceChildren();
    $("graph-entity").replaceChildren(new Option("Load the graph first", "")); $("graph-entity").disabled = true; $("graph-fit").disabled = true;
    $("load-graph").disabled = state.replay; $("refresh-history").disabled = state.replay;
    $("graph-summary").textContent = state.replay ? "Live graph exploration is unavailable in recorded replay." : "Select Explore live graph to load the connected company.";
    history();
  });
  document.addEventListener("baton:committed", history);
})();
