# M08 · MCP server — SPEC

Status at 12:15 IST, 18 Oct (HEAD `85eeabd`): **not started.** There is no `baton/mcp_server.py` (baton/ holds `__init__, __main__, amb_import, ask, demo, extract, generate, graph, handover, lane_a, llm, load, rehearse`). The `mcp` package is **not installed** in the project venv (`import mcp` → `ModuleNotFoundError`, checked 18 Oct) and is not in deploy/requirements.txt (deploy/requirements.txt:1-4).

## What it is, in plain words
MCP (Model Context Protocol) is a standard plug that lets an AI app (Claude Desktop, Cursor, an agent) see a list of tools and call them. M08 makes Baton's commands into MCP tools. The AI app reads each tool's name and description, picks one, and fills in the arguments. Baton runs the tool against FalkorDB and returns JSON.

The AI never writes Cypher. It only chooses a tool from a short fixed list (BUILD_PLAN.md:29, BUILD_PLAN.md:41). Every answer still comes from FalkorDB.

## Which track focus it serves
- Track 1: "graph queries and algorithms as agent tools", "tool selection through MCP" (00_GROUND_TRUTH.md:9; BUILD_PLAN.md:18).
- Track 3 indirectly: the company brain's answers become available to any agent.

## In scope
- One file, `baton/mcp_server.py`, "about 60 lines" (BUILD_PLAN.md:18), using the **official MCP Python SDK** (00_GROUND_TRUTH.md:43: FalkorDB-MCPServer is reference only).
- Tools (BUILD_PLAN.md:44 lists "rehearse, owes, why, covers, handover"):
  | Tool | Backed by | Ready today? |
  |---|---|---|
  | `rehearse` | `python -m baton rehearse` | yes (parser baton/__main__.py:19-25) |
  | `handover` | `python -m baton handover` | yes (parser baton/__main__.py:27-32) |
  | `ask` (question in plain words) | `python -m baton ask --world --beliefs --question --port [--offline]` | yes: parser baton/__main__.py:34-40; feature `ask` is green with 11/11 locked runs (loop/features.md:9) |
  | `owes`, `breaks_if_leaves`, `why`, `covers`, `who_owns` as separate MCP tools | the fixed catalogue in baton/ask.py:71-78 | **not directly**: the CLI only routes a question to a tool (baton/ask.py:308); there is no flag to call one catalogue tool with given arguments. PROPOSED (M04 owner decides): a `--tool NAME --args JSON` option on `ask` |
  | `cut` | `python -m baton cut` (M06) | **no**: checks drafted, no code |

## Not in scope
- A general "run any Cypher" tool. FalkorDB-MCPServer has `query_graph` and `query_graph_readonly` (FalkorDB-MCPServer/src/mcp/tools.ts:79-80, FalkorDB-MCPServer/src/mcp/tools.ts:137-138). Baton deliberately does not, because the model must not write Cypher (BUILD_PLAN.md:29).
- Copying FalkorDB-MCPServer code. It is TypeScript and reference only (00_GROUND_TRUTH.md:43).
- HTTP hosting of the MCP server on EC2. Run it locally over stdio.

## Inputs and outputs
- Input: tool calls from an MCP client (arguments typed by Python type hints).
- Output: the same JSON the CLI prints, returned as the tool result.

## Dependencies
- M02 `rehearse` and M03 `handover`: exist.
- M04 `ask`: built and green (loop/features.md:9). Separate per-tool MCP tools need a new `ask` option (PROPOSED).
- M06 `cut`: optional.
- FalkorDB running (any connection error → the CLI exits 3 with a "FalkorDB" message, baton/graph.py:26, baton/graph.py:30-32).
- Python ≥ 3.10 for the SDK (pypi.org/project/mcp, checked 18 Oct). The venv is Python 3.13 (.claude/skills/project-context/SKILL.md:9 path shows `python3.13`); the Docker image is 3.12 (deploy/Dockerfile:1).

## Decisions needed (owner: Joyal)
1. **Where the file lives.** BUILD_PLAN says `baton/mcp_server.py` (BUILD_PLAN.md:18). The project rule says the `baton` package uses "Standard library + falkordb only; no other deps" (.claude/skills/project-context/SKILL.md:9). PROPOSED: keep it in `baton/` (the loop may only edit `baton`, loop/program.md:16) but import `mcp` only inside `mcp_server.py`, so `python -m baton ...` never needs it.
2. **Pin.** PROPOSED: `mcp[cli]==2.3.0` (latest on PyPI on 18 Oct, released 2 Oct 2026), installed in a separate venv or added to the venv by a human.
3. **Tool arguments.** PROPOSED: tools take a `seed` and person/duty ids, not file paths; the server makes the world folder like server/app.py does (server/app.py:26-37).

## Owner, time, kill
- Owner: not named in BUILD_PLAN (feature 6, "stretch", BUILD_PLAN.md:44). Joyal assigns.
- Time: not in the timeline (BUILD_PLAN.md:62-77). "15:30 No new features" (BUILD_PLAN.md:72). So it must be done before 15:30 or dropped.
- Kill and fallback: if not working by 15:30, drop it and say in the README that Track 1 "tool selection" is shown through `ask`'s fixed catalogue (if M04 is green) instead. Do not claim MCP in the submission unless the go-and-see in 4_ACCEPTANCE.md passed.
