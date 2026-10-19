# Goal agent implementation contract — 2026-10-19

Status: frozen interfaces for implementation; not a claim of shipped capability.

The user goal is free text. No prompt keyword routing or canned plan is allowed.
The model chooses graph investigations, generates a variable work-plan DAG and
selects the next eligible action after actual observations. Deterministic code
validates authority, source bindings, dependencies and evidence, not the goal's
semantic plan. Missing AI or graph yields a blocked run and no substitute plan.

## HTTP contract (parent owns routes)

- `POST /api/public/goals` accepts exactly `{goal:string,idempotency_key:string}`.
  Existing operator authentication and origin checks apply. It investigates and
  produces a proposed plan; it does not implicitly send messages.
- `GET /api/public/goals/latest` and `GET /api/public/goals/{id}` return a GoalRun.
- `POST /api/public/goals/{id}/act` accepts exactly
  `{expected_plan_hash:string,approved_actions:["publish_task"|"verify_release"]}`.
  The model selects the next eligible sealed step. Existing configured Jira KAN
  and Slack #baton-demo are the only external destinations.
- `POST /api/public/goals/{id}/continue` accepts `{expected_plan_hash:string}`.
  Continues bounded model investigation/replanning from actual stored graph state.
  It cannot add effect permissions. Reads/reloads never submit any of these POSTs.

GoalRun fields:
`{id,goal,status,created_at,updated_at,revision,model,provider_receipts,proposal,
events,evidence,actions,blocked_reason,approved_actions}`.
Statuses: `investigating`, `proposed`, `acting`, `needs_continuation`, `answered`,
`completed`, `blocked`, `error`. `completed` requires all proposed effect steps
to have independently verified receipts; model prose cannot establish completion.

Proposal:
`{hash,summary,success_criteria:[string],assumptions:[string],questions:[string],
steps:[{id,title,tool_name,args,why,evidence_ids:[string],depends_on:[step_id],
expected_result:string}],limitations:[string]}`.
At most six steps, no duplicate IDs/cycles/unknown tools. Hash binds goal,
proposal material, catalog version and relevant evidence fingerprint. Citation
IDs must refer to actually inspected evidence. AI claims remain proposals,
not source facts. No model-generated shell, Python, raw Cypher or URLs execute.

Events:
`{seq,type,tool_call_id?,tool_name?,args?,result?,evidence_ids?,error?,receipt_id?}`.
Only actual provider calls/tool executions appear. Evidence:
`{id,source_id,url,sha256,kind?,excerpt?,observed_by_tool_call?}`.
Actions: `{id,step_id,kind,status,url?,read_back_verified?,result?,error?}`.

## Ownership and Python interfaces

Parent owns `server/goal_contract.py`, `server/goal_actions.py`, `server/app.py`,
deployment and independent proof. Goal contract exports `CATALOG_VERSION`,
`MAX_STEPS`, `validate_proposal(proposal,goal,evidence,catalog,binding)` returning
the normalized proposal including hash, and `proposal_hash(...)`.

Graph lane owns `server/goal_graph.py` and its focused tests. Exports:

- `TOOLS`: JSON-schema MCP catalog for bounded `search_company_graph`,
  `inspect_graph_entity`, `traverse_company_graph`, `read_company_source`,
  `recall_goal_memory`. Schemas use simple bounded strings and integers.
- `call_tool(data,port,name,args,record=None)` ->
  `{observation:object,evidence:[Evidence],binding:object}`. Every operation reads
  real FalkorDB/captured public sources; no fixtures or canned reasoning fallback.
- `create_goal(data,port,record)`, `save_goal(data,port,record)`,
  `get_goal(data,port,id)`, `latest_goal(data,port)`.
- `evidence_binding(data,port,evidence)` -> stable fingerprint string, recomputed
  from actual selected source/graph facts; unrelated external nodes are excluded.
- `ready_steps(data,port,id)` -> eligible stored step IDs, derived by graph query.

Persist Goal, PlanRevision, Step, Observation/Episode and source evidence as
native graph nodes/edges (HAS_STEP, DEPENDS_ON, CITES, OBSERVED, SUPERSEDES).
The stored record can aid rendering but cannot replace actual DAG/source queries
for effect readiness/freshness. Restore from the graph after request/process end.
Public-contributor evidence never establishes employment or internal ownership.

Reasoning lane owns `server/goal_agent.py` and focused tests. Exports:

- `investigate(data,port,goal,idempotency_key)` -> persisted GoalRun.
- `continue_goal(data,port,id,expected_plan_hash,approved_actions=None,
  action_executor=None)` -> persisted GoalRun. If action_executor is supplied,
  call `action_executor(data,port,record,step)` only after model selection of a
  graph-ready step and exact current plan/evidence/permission validation.
- Reuse existing Groq Free configuration, quota/cooldown and measured receipts.
  No runtime framework install, embeddings, local model or new paid services.
  `BATON_GOAL_MODEL` can select the goal-only model without changing legacy
  workflows. Receipts retain both the requested model and the provider's actual
  returned model; a requested setting is not evidence of a successful generation.

Graph search uses bounded parameterized Cypher term matching and global candidate
ranking across the captured public graphs. Results expose the matched terms,
score and `native-terms-v1` version. This is lexical retrieval, not a full-text
index or semantic embedding search. Captured source IDs are resolved by exact
source URL matches; an entity observation alone never counts as a raw source read.
  Budget each request below Lambda180s; bounded loop, then needs_continuation.
  No manufactured finish or fabricated token usage/tool trace.

`publish_task` arguments: `{title,description,source_ids:[string]}`; model authored,
source-grounded proposed work. Provider executor saves durable intent before POST
and uses independent provider reads; ambiguous writes never repeat automatically.
`verify_release` arguments: `{change_id:"FalkorDB/falkordb-py#212"}`; current
approved immutable verification profile and its existing remaining quota.
Graph read tools are also valid plan steps. No other effect capability is allowed.

UI lane owns `web/goal-agent.js`, `web/goal-agent.css`, main `web/index.html`
integration and focused UI tests. One free-text composer and one generic agent
renderer; ten sample prompts populate that composer without branching the API.
Show model criteria/DAG, actual tool events, source evidence, plan revisions and
provider action receipts. Preserve the existing verification screen as drilldown.
Missing model -> blocked/no plan, never demo extraction or scripted response.

## Required proof

Two fresh live goals must produce materially different model-generated plans and
selected tools. Provider-off cannot plan or act. Changed actual observation must
change model-selected next action/revision; stale graph dependency/source blocks
effects. Persisted graph state must survive a fresh request. Contract mocks prove
validation only; live Groq/provider/graph receipts prove the demonstrated runs.

## Implementation validation

The complete Docker harness passed on immutable checkpoint
`b28d376f0feaad2fa33235134a351f9ff9fe70a5`: original scoring 88/88 and 1,104
pytest tests, with zero failures, errors or skips. The 140 goal-agent contract
tests are included. All 456 tracked file hashes remained unchanged. See the
[checkpoint evidence](evidence/GOAL_AGENT_B28_VALIDATION.md) for exact group
counts, command and retained log digest. This is implementation validation;
the live proof requirements above remain separate.
