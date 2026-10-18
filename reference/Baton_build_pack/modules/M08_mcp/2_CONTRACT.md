# M08 · CONTRACT

Paths relative to `/home/claude/baton/`. `ref/` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/falkor/repos/`.

Legend: **EXISTS** (cited), **PROPOSED** (not in code; Joyal decides), **UNTESTED** (never run by us).

## 1. MCP Python SDK facts (checked 18 Oct 2026 by WebFetch; the package was NOT installed or run by us)

| Fact | Source |
|---|---|
| Package `mcp`, latest **2.3.0**, released 2 Oct 2026; 2.0.0 released 28 Jul 2026 | pypi.org/project/mcp |
| Requires Python ≥ 3.10 | pypi.org/project/mcp |
| Install: `pip install "mcp[cli]"` or `uv add "mcp[cli]"`; the `cli` extra adds the `mcp` command (`mcp dev`, `mcp run`, `mcp install`) | pypi.org/project/mcp; github.com/modelcontextprotocol/python-sdk README |
| Server class is `MCPServer`: `from mcp.server import MCPServer` | PyPI page, GitHub README, py.sdk.modelcontextprotocol.io/run/ |
| Migration guide gives the import as `from mcp.server.mcpserver import MCPServer, Context` | py.sdk.modelcontextprotocol.io/migration/ |
| **v1 `FastMCP` is gone**: "Importing `mcp.server.fastmcp`, or anything below it, raises `ModuleNotFoundError`." | py.sdk.modelcontextprotocol.io/migration/ |
| `@mcp.tool()` decorator is unchanged from v1; type hints define the input schema | migration guide; GitHub README ("`a: int, b: int` *is* the schema") |
| A returned dict, list, scalar or model is wrapped into `content` and `structured_content` | migration guide |
| Run: `if __name__ == "__main__": mcp.run()`; "With no argument, the transport is `stdio`." `run()` blocks | py.sdk.modelcontextprotocol.io/run/ |
| `transport="stdio"` takes no keyword arguments; host/port go to `run()`, never the constructor (passing `port` to `MCPServer(...)` raises `TypeError`) | migration guide; run page |
| Sync (`def`) tool handlers run on a worker thread in v2 | migration guide |
| Default server name is `mcp-server`; pass the name positionally | migration guide |
| `MCP_*` environment variables and `.env` files are no longer read by the SDK | migration guide |
| To show the model a tool failure: raise `ToolError` or return `CallToolResult(is_error=True)`. The import path of `ToolError` was **not** found in the pages read → UNVERIFIED | migration guide |
| `MCPServer.call_tool()` returns a `CallToolResult` (read `.content`, `.structured_content`); exact arguments not checked → UNTESTED | migration guide |
| CLI: `uv run mcp dev server.py` (Inspector), `uv run mcp run server.py`, `uv run mcp install server.py --name "Bookshop"`, `uv run mcp install server.py -v API_KEY=abc123 -f .env` | py.sdk.modelcontextprotocol.io/run/ |

Not verified: the Claude Desktop config file format; whether `mcp dev` needs Node.js for the Inspector. Use `mcp install` instead of hand-editing config.

## 2. Reference only: FalkorDB-MCPServer (EXISTS, do not copy)
- TypeScript, MIT, author Katie Mulliken (ref/FalkorDB-MCPServer/package.json).
- Tools: `query_graph`, `query_graph_readonly`, `list_graphs`, `delete_graph`, `get_graph_schema`, `get_node_schema`, `get_relationship_schema` (ref/FalkorDB-MCPServer/src/mcp/tools.ts:79-80, :137-138, :182-183, :210-211, :256-257, :313-314, :362-363).
- It has a read-only mode flag that runs `GRAPH.RO_QUERY` (ref/FalkorDB-MCPServer/src/mcp/tools.ts:46).
- Lesson for Baton: it exposes raw Cypher. Baton exposes only fixed tools.

## 3. Baton CLI the tools call (EXISTS)
| Command | Flags | Source |
|---|---|---|
| `rehearse` | `--world` (req), `--beliefs` (req), `--leaver` (req), `--lane W|R|G` (default G), `--confirm all|none` (default none), `--port` (default 6379) | baton/__main__.py:19-25 |
| `handover` | `--world`, `--beliefs`, `--leaver` (all req), `--assign DUTY=PERSON` (repeatable), `--port` | baton/__main__.py:27-32 |
| `generate` | `--seed` (req), `--out` (req) | baton/__main__.py:11-13 |
| `ask` | `--catalogue` (print `{tool: cypher}` and exit), `--world`, `--beliefs`, `--question` (all three needed unless `--catalogue`), `--port`, `--offline` | baton/__main__.py:34-40 |
| `demo` | `--seed` (default 7), `--port`, `--offline`, `--beliefs` | `demo` sub-parser in baton/__main__.py |
| `extract` | `--world`, `--out` (both required), `--model`, `--offline`, `--cache-dir`; cache miss with `--offline` → exit 4; missing model key → exit 5 | `extract` sub-parser in baton/__main__.py; baton/extract.py:176-182 at HEAD 85eeabd |

Outputs:
- `rehearse` → `{lane, leaver, graph, failures:[{duty, at, day, event, label, status, sources}], unpromoted:[{belief, reason}], live_hash_before, live_hash_after}` (baton/rehearse.py:146-147, baton/rehearse.py:154-156, baton/rehearse.py:94).
- `ask` → `{question, tool, args, cypher, graph, router, rows, sources, answer, live_hash_before, live_hash_after}`; `tool` is one of `owes`, `breaks_if_leaves`, `why`, `covers`, `who_owns`, `none` (baton/ask.py:310-323, baton/ask.py:71-78). The `run` function accepts `offline` but the router is always the deterministic one (`"router": "offline"`, baton/ask.py:299, baton/ask.py:310-311).
- `handover` → `{leaver, graph, accepted:[{duty, person}], refused:[{duty, person, reason}], failures_after:[...], live_hash_before, live_hash_after}` (baton/handover.py:79-81, baton/handover.py:89-91).
- Errors: FalkorDB unreachable → exit 3, message on stderr (baton/graph.py:26, baton/graph.py:30-32); unknown leaver → `SystemExit` message, exit 1 (baton/rehearse.py:115-116); usage error → exit 2.
- `handover` changes only a fork that is deleted; nothing in the live graph changes (baton/handover.py:87, baton/rehearse.py:134-135). The tool description must say "rehearses a handover".

## 4. Baton MCP tools (PROPOSED — owner: Joyal)
Server name `"baton"`. Transport stdio. File `baton/mcp_server.py`.

| Tool | Arguments (type) | Returns |
|---|---|---|
| `rehearse` | `seed: int = 7`, `leaver: str = ""` (empty = the world's leaver), `lane: str = "G"` | the `rehearse` JSON |
| `handover` | `seed: int = 7`, `assign: dict[str, str]` (duty id → person id), `leaver: str = ""` | the `handover` JSON |
| `cut` | `seed: int = 7`, `leaver: str = ""` | the `cut` JSON (only after M06 exists) |
| `ask` | `question: str`, `seed: int = 7` | the `ask` JSON (exists today) |
| `owes`, `breaks_if_leaves`, `why`, `covers`, `who_owns` | typed arguments (`person`, `duty`, `day`) | needs a new `ask` option to call one catalogue entry directly (PROPOSED; M04 owner decides). Tool names from baton/ask.py:71-78, checks/locked/ask/test_ask.py:29, :38, :48, :62, :71 and checks/locked/ask/test_ask_ratchet.py:28 |

On CLI failure, return `{"error": <last 800 chars of stderr>, "exit_code": <int>}` (same trimming as server/app.py:22). PROPOSED; switch to `ToolError` once its import path is verified.

World folder: `$BATON_DATA/seed_<N>` like server/app.py:26-37 (generate if missing). Beliefs: `fixtures/beliefs_seed7.json` was deleted in commit `84747c6`; beliefs now come from `extract --offline` replaying the cache (keyed on the world's bytes, baton/extract.py:9-11 at HEAD 85eeabd; miss → exit 4). Only seed 7 has a cached run (`fixtures/extract_cache/`). The sample below still checks the old fixture path first; harmless, delete it if you like.

FalkorDB port: env `FALKORDB_PORT` (default 6379) and host `FALKORDB_HOST` (default localhost), the names server/app.py:10-11 and baton/graph.py:21 already use. These are read by our code, not by the SDK.

## 5. Code sample (UNTESTED: written from the docs above; never run; `mcp` not installed here)
```python
"""Baton MCP server: fixed tools over the Baton CLI. The model picks a tool; it never writes Cypher."""
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp.server import MCPServer

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("BATON_DATA", "/tmp/baton_data"))
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
mcp = MCPServer("baton")


def _cli(*args):
    r = subprocess.run([sys.executable, "-m", "baton", *map(str, args)], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout)[-800:], "exit_code": r.returncode}
    return json.loads(r.stdout)


def _world(seed):
    d = DATA / f"seed_{seed}"
    if not (d / "world.json").exists():
        out = _cli("generate", "--seed", seed, "--out", d)
        if "error" in out:
            return None, out
    beliefs = ROOT / "fixtures" / f"beliefs_seed{seed}.json"      # old fixture path (deleted in 84747c6)
    if not beliefs.exists():                                        # replay the extraction cache
        beliefs = d / "beliefs.json"
        if not beliefs.exists():
            out = _cli("extract", "--world", d, "--out", beliefs, "--offline")
            if "error" in out:
                return None, out
    leaver = json.loads((d / "world.json").read_text())["leaver"]
    return (d, beliefs, leaver), None


@mcp.tool()
def rehearse(seed: int = 7, leaver: str = "", lane: str = "G") -> dict:
    """Rehearse a departure on a copy of the company graph: list every scheduled duty in the next
    30 days that nobody could act on if this person left, with sources. Never changes the live graph."""
    w, err = _world(seed)
    if err:
        return err
    d, beliefs, default_leaver = w
    return _cli("rehearse", "--world", d, "--beliefs", beliefs, "--leaver", leaver or default_leaver,
                "--lane", lane, "--confirm", "all", "--port", PORT)


@mcp.tool()
def handover(assign: dict[str, str], seed: int = 7, leaver: str = "") -> dict:
    """Rehearse a handover: successors accept duties (duty id -> person id) on a copy of the graph,
    then the rehearsal runs again. Returns accepted, refused (with reasons) and what still fails."""
    w, err = _world(seed)
    if err:
        return err
    d, beliefs, default_leaver = w
    args = []
    for duty, person in assign.items():
        args += ["--assign", f"{duty}={person}"]
    return _cli("handover", "--world", d, "--beliefs", beliefs, "--leaver", leaver or default_leaver,
                *args, "--port", PORT)


@mcp.tool()
def ask(question: str, seed: int = 7) -> dict:
    """Ask the company graph a plain question (what someone owes, what breaks if they leave, why a duty
    is theirs, who covers a duty on a day). Returns the tool chosen, rows, sources and the exact Cypher run."""
    w, err = _world(seed)
    if err:
        return err
    d, beliefs, _ = w
    return _cli("ask", "--world", d, "--beliefs", beliefs, "--question", question, "--port", PORT, "--offline")


if __name__ == "__main__":
    mcp.run()
```
Unverified points in this sample: that `dict` return annotations produce valid structured output in 2.3.0; that `dict[str, str]` is accepted as an argument type; that `subprocess.run` inside a sync handler is fine on the v2 worker thread (it should be; it is not async code).
