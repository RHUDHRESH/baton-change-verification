# Change verification demo — 4 minutes 30 seconds

**Current status:** the local implementation and contract tests are validated. A read-only browser check loaded a real plan from the local FalkorDB graph: four required checks, four witnesses and ten captured primary-source versions. It used `investigate=False`; it proves neither live Groq inference nor a deployed app execution. Production run and publication proof will be added after deployment. No production run ID, result or provider link is asserted here.

Open [Baton](https://baton-workspace.vercel.app/). Use actual stored evidence throughout. Start a run before presenting only when an operator has authorized its execution and Jira/Slack effects; the walkthrough does not promise a run will finish in 4½ minutes. If no run exists, show that state. Do not substitute local feasibility results or the earlier Rust workflow.

## 0:00–0:35 — The user problem

Show **Know what this change must prove.**

> A Python client user needs to pass real property names into a graph query. Names such as `@type` and hyphenated identifiers can break when serialized as bare Cypher identifiers. Issue #211 describes that problem. PR #212 already merged the upstream change. Our job here is to establish what that change must prove, run the required checks, and keep an honest decision with the work.

Open [issue #211](https://github.com/FalkorDB/falkordb-py/issues/211) or [PR #212](https://github.com/FalkorDB/falkordb-py/pull/212). Explain that the app uses public engineering evidence. Connected Jira and Slack belong to the operator’s workspace; they are not FalkorDB’s internal systems.

## 0:35–1:10 — Pin the source

Point to commit `207000da70ca183ab02990a98bdd97d0a3e3bb1b`, then open **Why these checks? → Source versions and pinned commit**.

> We bind the plan to the merged source, captured source hashes, required checks and environment policy. A changing branch name or a model summary is not the execution contract. Source versions and witness spans let someone inspect the exact basis for each obligation. Missing coverage stays incomplete; a relevant source or graph change requires a new plan.

## 1:10–2:00 — Why the graph requires async checks

Expand a sync witness and an async witness. Follow the actual directed edges and source spans.

> The changed header builder is in `Graph`. Both query paths call it, and `AsyncGraph` inherits from `Graph`. The header builder also calls the recursive map-value serializer. That connects this change to synchronous and inherited asynchronous behavior, including nested values. The graph selects the four reviewed regression obligations; the model can inspect and explain that evidence, while deterministic policy seals the executable plan.

Primary code: [`Graph._build_params_header`](https://github.com/FalkorDB/falkordb-py/blob/207000da70ca183ab02990a98bdd97d0a3e3bb1b/falkordb/graph.py#L247), [`AsyncGraph` and its query path](https://github.com/FalkorDB/falkordb-py/blob/207000da70ca183ab02990a98bdd97d0a3e3bb1b/falkordb/asyncio/graph.py#L24), and [`stringify_param_value`](https://github.com/FalkorDB/falkordb-py/blob/207000da70ca183ab02990a98bdd97d0a3e3bb1b/falkordb/helpers.py#L21).

## 2:00–2:40 — Show the plan and the unknowns

Show **Investigate → Verify → Decide → Publish**, the required environment matrix, investigation trace and provider receipts.

> The Python `redis` client package is tested at 8.0.0 and 8.1.0; the FalkorDB server image stays pinned. Both client versions are required by this reviewed verification policy. A requirement is not a passing result. Anonymous visitors read stored evidence; the authenticated action investigates, submits the exact plan hash, and requests Jira/Slack publication. A failed Groq investigation blocks dispatch. An absent execution remains “not run”; a missing receipt remains unconfirmed.

If no production run exists, keep those unknown cells visible and explain the remaining steps without clicking the action.

## 2:40–3:35 — Read the actual matrix and decision

If a stored run exists, show its runner link, per-environment results and **Read the run, not just the verdict**. Open a raw pytest log separately from the execution receipt.

> Each cell comes from this run’s preserved evidence. The app checks the GitHub execution identity, immutable source, commands, JUnit cases and log bindings. Verified evidence can contain failing tests. If either required environment fails, the decision is blocked; a passing row cannot override it. A callback or completed runner is not enough to claim a passing release.

For a real failed matrix, point to the failed obligation and its observed output. For an incomplete run, show the missing evidence. Do not narrate an anticipated failure as an observed production result. These checks establish behavior within the declared matrix, not a proven root cause.

## 3:35–4:15 — Keep the outcome with the work

Open **Jira & Slack delivery**. Use only returned artifact links and their actual statuses.

> Publication has its own receipts. A blocked verification can produce an open Jira investigation task and a Slack report containing the source, plan, runner and evidence references. Provider read-back confirms delivery. It does not turn failed checks green, mark remediation done, or prove an upstream fix. Unknown write outcomes stay visible and are not automatically reposted.

If production publication has not occurred, show “not published” and describe this as the implemented flow, not completed delivery.

## 4:15–4:30 — Close on the precise contribution

> We verified an existing merged change; we did not author a new fix or merge upstream. A full test suite across the same environments could also catch a failure. The contribution is the source-backed explanation of required coverage, a sealed reproducible plan, and an auditable decision carried into the operator’s work tools.
