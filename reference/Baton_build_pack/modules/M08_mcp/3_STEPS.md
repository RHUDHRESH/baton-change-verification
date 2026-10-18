# M08 · STEPS

Paths relative to `/home/claude/baton/`. `PY` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`.

## The karpathy-loop rule
Checks first; a human approves; lock with `loop/bin/lock_checks.py <feature> --approved-by "..."` (loop/bin/lock_checks.py:4-6); then build. Never edit `checks/locked/**` or `loop/bin/**` (loop/program.md:17). Disputes go to `loop/disputes/<check>.md` (loop/program.md:20-22). The loop may edit only `baton`, `fixtures`, `Makefile`, `README.md` (loop/program.md:16).

Hard stop: this feature is a stretch and has no slot in the timeline; "15:30 No new features" (BUILD_PLAN.md:72). Start only when rehearsal_core is green and M04/M06 are not blocked on you.

---

### Step 0 · Install the SDK (human, 5 min)
- Goal: `mcp` importable in a Python that can also run `python -m baton`.
- PROPOSED (decide which env): a separate venv so the project venv stays clean:
  ```
  python3 -m venv /tmp/mcpvenv
  /tmp/mcpvenv/bin/pip install "mcp[cli]==2.3.0" falkordb==1.8.0
  /tmp/mcpvenv/bin/python -c "from mcp.server import MCPServer; print('ok')"
  ```
  `falkordb==1.8.0` matches deploy/requirements.txt:3; the CLI subprocess uses the same interpreter (`sys.executable`).
- Done when: the last line prints `ok`. If it fails with `ModuleNotFoundError`, try `from mcp.server.mcpserver import MCPServer` (the migration guide's path) and record which one worked in 2_CONTRACT.md.

### Step 1 · Draft the checks (agent drafts, human approves)
- Files: `checks/pending/mcp/conftest.py` (copy of checks/locked/rehearsal_core/conftest.py), `checks/pending/mcp/test_mcp.py`.
- Check names: see 4_ACCEPTANCE.md §1 (PROPOSED).
- Important: the check runner uses the project venv (loop/config.json:3). If `mcp` is not installed there, every MCP check errors, and errors count as failing (loop/bin/run_checks.py:31-32). Decide with Joyal: install `mcp` in the project venv, or keep M08 as go-and-see only (no locked checks).
- Done when: the checks run and fail because `baton/mcp_server.py` does not exist.
- Prompt:
  > Read docs/modules/M08_mcp/2_CONTRACT.md. Draft checks/pending/mcp/test_mcp.py with exactly the functions in docs/modules/M08_mcp/4_ACCEPTANCE.md §1. Test the tools by importing baton.mcp_server and calling the decorated Python functions directly (UNVERIFIED that `@mcp.tool()` in SDK v2 returns the plain function; if it does not, use `MCPServer.call_tool()`, which returns a `CallToolResult` whose `.structured_content` holds the result, and check its exact signature first), and compare their output with `python -m baton rehearse` run through conftest's `baton_json`. Add one static check that baton/mcp_server.py contains no Cypher keywords (MATCH, CREATE, MERGE, CALL). Do not write product code. Do not touch checks/locked or loop/bin.

### Step 2 · Lock (human)
- `PY loop/bin/lock_checks.py mcp --approved-by "Joyal: '<words>' (2026-10-18)"`.

### Step 3 · Write `baton/mcp_server.py` (loop round)
- Goal: tools `rehearse`, `handover` and `ask` per 2_CONTRACT.md §4; start from the sample in §5.
- Files: `baton/mcp_server.py` only. Do **not** add `mcp` imports anywhere else in `baton/`: `python -m baton` must keep running with standard library + falkordb (.claude/skills/project-context/SKILL.md:9).
- Done when: the locked mcp checks pass and the 32 rehearsal_core runs still pass.
- Prompt:
  > Create baton/mcp_server.py from the sample in docs/modules/M08_mcp/2_CONTRACT.md §5. Use the MCP Python SDK v2 API exactly as written there (`from mcp.server import MCPServer`, `@mcp.tool()`, `mcp.run()`); do NOT use `FastMCP` or `mcp.server.fastmcp` (removed in v2). Tools shell out to `python -m baton`; no Cypher in this file; no raw query tool. Return the CLI JSON unchanged; on non-zero exit return {"error", "exit_code"}. Write your prediction first.

### Step 4 · See it in the Inspector (human, 10 min)
- Commands (from py.sdk.modelcontextprotocol.io/run/, with the venv from step 0; UNTESTED here):
  ```
  cd /home/claude/baton
  FALKORDB_PORT=6399 /tmp/mcpvenv/bin/mcp dev baton/mcp_server.py
  ```
  The docs show `uv run mcp dev server.py`; with pip, the `mcp` script in the venv's `bin/` should be the same command. The Inspector may need Node.js (not verified).
- Done when: the Inspector lists `rehearse`, `handover` and `ask`; calling `rehearse` with `seed=7` returns JSON with `failures` and equal `live_hash_before`/`live_hash_after`.

### Step 5 · Per-tool `owes`/`why`/`covers`/`breaks_if_leaves` and `cut` (only if done before 15:30)
- `ask` is green (loop/features.md:9) but the CLI can only route a question (baton/ask.py:308). Separate typed MCP tools need a way to call one catalogue entry with arguments: PROPOSED `ask --tool NAME --args JSON`. That is an `ask` contract change: M04 owner drafts a check, a human locks it, then build.
- `cut` once `python -m baton cut` exists (M06).

### Step 6 · Connect a real client (human, optional)
- `uv run mcp install baton/mcp_server.py --name "Baton" -v FALKORDB_PORT=6399` (syntax from py.sdk.modelcontextprotocol.io/run/; UNTESTED).
- Done when: the client shows the Baton tools and one call returns the same JSON as the CLI. Record a 10-second screen clip for the video if it works.
