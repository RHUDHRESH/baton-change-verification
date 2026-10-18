# M08 · ACCEPTANCE

Paths relative to `/home/claude/baton/`. `PY` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`.

## 1. Checks
**No locked or drafted checks exist for M08** (locked: rehearsal_core, ask, ai_layer, cut; pending: commit_write, eval — checks/locked/MANIFEST.json `files`, `ls checks/pending`, 12:15). Names below are PROPOSED; a human approves and locks them, or decides M08 is go-and-see only (3_STEPS.md step 1).

`checks/pending/mcp/test_mcp.py` (PROPOSED):
| Check function | What it asserts |
|---|---|
| `test_mcp_server_lists_only_the_fixed_tools` | the server exposes exactly `rehearse`, `handover`, `ask` (plus `cut` and per-catalogue tools only if built) and no raw-query tool |
| `test_mcp_ask_equals_cli_ask` | for "What breaks if <leaver name> leaves?" the `ask` tool returns the same `tool`, `rows` duty set and `cypher` as `python -m baton ask ... --offline` |
| `test_mcp_rehearse_equals_cli_rehearse` | the `rehearse` tool for seed 7 returns the same `failures` (duty, at) pairs as `python -m baton rehearse ... --lane G --confirm all` |
| `test_mcp_handover_equals_cli_handover` | same comparison for `handover` with one assignment |
| `test_mcp_server_contains_no_cypher` | the text of `baton/mcp_server.py` has no `MATCH`, `CREATE`, `MERGE`, `CALL ` |
| `test_mcp_reports_falkordb_down_as_tool_error` | with a dead port, the tool returns an error whose text contains "FalkorDB" and no `failures` key |
| `test_cli_still_runs_without_mcp_installed` | `python -m baton generate --seed 11 --out <tmp>` works in an interpreter without `mcp` (the CLI never imports it) |

## 2. Go and see
1. Import works (step 0): `/tmp/mcpvenv/bin/python -c "from mcp.server import MCPServer; print('ok')"` → `ok`.
2. Inspector (step 4): `FALKORDB_PORT=6399 /tmp/mcpvenv/bin/mcp dev baton/mcp_server.py` → a browser page lists `rehearse`, `handover`, `ask`. Call `rehearse` with `seed: 7` → JSON with `failures` (each with `duty`, `at`, `day`, `event`, `label`, `status`, `sources`, as in baton/rehearse.py:146-147) and `live_hash_before == live_hash_after`.
3. Compare by hand with the CLI:
   ```
   PY -m baton rehearse --world $BATON_DATA/seed_7 --beliefs $BATON_DATA/seed_7/beliefs.json --leaver <leaver> --lane G --confirm all --port 6399
   ```
   Same failure list.
4. Stop FalkorDB, call `rehearse` again → an error mentioning "FalkorDB" (the CLI prints "FalkorDB is not reachable at ...", baton/graph.py:26, and exits 3, baton/graph.py:30-32).

## 3. Failure modes and fallbacks
| Failure | Fallback |
|---|---|
| `ModuleNotFoundError: mcp.server.fastmcp` | You followed a v1 tutorial. Use `from mcp.server import MCPServer` (SDK v2) |
| `ModuleNotFoundError: mcp` inside the checks | `mcp` is not in the project venv (checked 18 Oct). Install it there (human) or make M08 go-and-see only |
| `TypeError: ... unexpected keyword argument 'port'` | Transport options go to `run()`, not to `MCPServer(...)` (py.sdk.modelcontextprotocol.io/run/) |
| Inspector will not start | It may need Node.js (unverified). Show the checks passing instead |
| `seed` other than 7 fails | Only seed 7 has a cached extraction (`fixtures/extract_cache/`); any other seed needs a real extraction run with a model key |
| Not working by 15:30 | Drop M08 (BUILD_PLAN.md:72). Do not mention MCP in the submission or video |

## 4. Anti-hallucination list
| Likely wrong assumption | Correct fact | Source |
|---|---|---|
| `from mcp.server.fastmcp import FastMCP` | Removed in v2; raises `ModuleNotFoundError`. Use `MCPServer` | py.sdk.modelcontextprotocol.io/migration/ |
| `MCPServer("baton", port=8000)` | Host/port go to `run()`; constructor raises `TypeError` | migration guide; run page |
| `mcp.run()` defaults to HTTP | Default transport is stdio | py.sdk.modelcontextprotocol.io/run/ |
| The SDK reads `MCP_*` env vars or `.env` | No longer in v2 | migration guide |
| `mcp` is already installed | Not in the venv, not in deploy/requirements.txt | `import mcp` failed 18 Oct; deploy/requirements.txt:1-4 |
| We can reuse FalkorDB-MCPServer code | Reference only; it is TypeScript and exposes raw Cypher | 00_GROUND_TRUTH.md:43; ref FalkorDB-MCPServer/src/mcp/tools.ts:79-80 |
| Add a "run Cypher" tool for flexibility | The model never writes Cypher; fixed tools only | BUILD_PLAN.md:29, BUILD_PLAN.md:41 |
| `handover` tool commits ownership | It rehearses on a fork that is deleted; live graph unchanged | baton/handover.py:87, baton/rehearse.py:134-135 |
| The read-only ACL user can run the tools | Tools call `rehearse`, which does `GRAPH.COPY` and writes on a fork. The tested read-only user allows only `GRAPH.RO_QUERY`, `GRAPH.EXPLAIN`, `GRAPH.LIST`, `INFO`, `PING` | verify/acl_check.py:5 (`verify/` = scratchpad verify folder), baton/graph.py:52, baton/rehearse.py:129 |
| `owes`, `why`, `covers` can be called directly through the CLI | `ask` routes a question; no flag picks a catalogue tool with arguments | baton/__main__.py:34-40, baton/ask.py:308 |
| `ask --offline` changes how answers are made | The router is always deterministic; output says `"router": "offline"` | baton/ask.py:299, baton/ask.py:310-311 |
| `ToolError` is at `mcp.server.mcpserver.exceptions` (or similar) | Import path not verified | — |
