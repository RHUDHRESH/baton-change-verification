# Baton: technical build plan (Track 3 + Track 1). Written 11:20 IST, 18 Oct

**Pitch:** Every company brain knows who *knows* what. Baton knows who *owes* what, and the exact day it breaks if they leave.

**Ratio:** about 60% reused open source, about 20% new code, the rest integration. The new 20% is the part judges score: the FalkorDB reasoning.

---

## 1. What we reuse ("steal"), legally

The rules require the main FalkorDB implementation to be new work done during the event. Libraries and templates are allowed. So we reuse **libraries and MIT/Apache templates, with credit**. We **never copy another hackathon entry's code**: that is plagiarism and grounds for rejection.

| Reused | Licence | What it gives us | How |
|---|---|---|---|
| **FalkorDB v4.22.1** (Docker) | SSPL server | GRAPH.COPY forks, `algo.maxFlow`, UNIQUE constraints, range indexes | `docker-compose.yml`, pinned |
| **falkordb-py** | MIT | Python client | pip |
| **agent-memory-bench** by Liz Zhang (FalkorDB DevRel) | MIT | 1. the LLM extraction pattern: JSON-schema output, cached per prompt version, cost tracked separately (`amb/extract.py`)<br>2. provider switch, retry and price table (`amb/llm.py`)<br>3. scripted offline fake model (`amb/fake.py`)<br>4. lane fairness rules<br>5. 95% cluster-bootstrap confidence intervals (`amb/analyze.py`) | Copy and adapt into `baton/llm.py` and `baton/extract.py`, keeping the MIT notice in the file header and crediting it in the README. **We also extend her benchmark idea with a "departure" question type**, built on FalkorDB staff's own work. |
| **MCP Python SDK** (official) | MIT | Exposes Baton's tools to any agent (Claude Desktop, Cursor). This is Track 1's "tool selection through MCP". | `baton/mcp_server.py`, about 60 lines |
| **FalkorDB Browser** | SSPL (run as-is, not copied) | Judges watch the live graph and the fork | Separate container |
| **Gitea** (Docker) | MIT | A real system to write to: CODEOWNERS and on-call rota files, read back over its API | Compose service |
| **FastAPI + uvicorn + pydantic** | MIT/BSD | HTTP API | `server/app.py` (written) |
| **cytoscape.js** (cdnjs) | MIT | Graph view on the website | `web/` |
| **Vercel** (static) + **AWS EC2** (Docker) | — | Live URL. Vercel forwards `/api/*` to EC2. | `web/vercel.json`, `deploy/` |
| **pytest + Playwright** | MIT/Apache | The locked checks, plus "go and see" screenshots | Already set up |
| **Karpathy-loop harness** | ours | Locked checks, keep or revert, round log | `loop/`, running |

### What we deliberately skip
- **TurboQuant** (Google, 2026). It compresses an LLM's KV cache and vectors so models use less memory. We call hosted models and make every decision by graph traversal. Bolting it on would be decoration, and a FalkorDB engineer would see that in one question. ([Google Research](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/))
- **text-to-Cypher, QueryWeaver, vector RAG.** The model never writes Cypher; that is our safety story. QueryWeaver is also AGPL.
- **Okta, Jira Cloud, Slack live.** Fragile sign-ins, no extra proof.

## 2. What we build (new, all FalkorDB-central)

| Module | Status | What it does |
|---|---|---|
| `baton/generate.py` | ✅ round 1 kept, 9/32 | Seeded synthetic company. It plants schedules, chat, job logs, tickets and fake evidence. It never plants failures. |
| `baton/load.py`, `graph.py` | 🔨 round 2 running | World → graph with time-valid edges (vf/vt) and Source nodes. Fails loudly if FalkorDB is down. |
| `baton/rehearse.py` | 🔨 round 2 running | **The core.** The two-source gate runs as Cypher in a GRAPH.COPY fork. The leaver is removed, and every scheduled event in the next 30 days is checked for an accountable path (lanes W/R/G). Every failure carries its sources, the live hash is unchanged, and the fork is deleted. |
| `baton/handover.py` | next round | Successor accepts, then a single-query commit with an authority re-check and a UNIQUE owner constraint. Make-before-break. Replay shows 0 failures. |
| `baton/cut.py` | feature 4 | `algo.maxFlow` + residual min-cut. Proves "IMPOSSIBLE 3/4: the team can't absorb this" and names the gap. |
| `baton/ask.py` | feature 2 (checks drafted) | The company brain answers questions (owes / breaks-if-leaves / why / covers / none) from a **fixed Cypher catalogue**, with sources. The model only picks the tool. |
| `baton/extract.py` | feature 3 | The LLM reads chat, job logs and tickets and proposes beliefs (adapted from amb). Offline replay from cache, so judges need no key. |
| `baton/eval.py` | feature 5 | Sealed eval: 30 unseen companies. W/R/G are scored against the independent checker; lane A (AI alone, same model and data) and false-claim adoption are scored too. Predictions are committed first, results come with bootstrap CIs, and we report where we lose. |
| `baton/mcp_server.py` | feature 6 (stretch) | MCP tools: rehearse, owes, why, covers, handover. |

## 3. Integration

- `server/app.py` (written): `/api/demo`, `/api/handover`, `/api/ask`. It wraps the CLI, so the API and the checks exercise the same code.
- `web/` (being built): the "Same month, three ways" strips, a proof drawer (sources and Cypher), a ghost-duties panel, Handover → replay green, and Ask. It falls back to recorded replay data if the API is down.
- `docker-compose.yml` (written): FalkorDB v4.22.1 + API (+ Browser, + Gitea).
- AWS EC2 t3.small with an Elastic IP → `docker compose up -d`. Vercel rewrites `/api/*` to EC2:8000.

## 4. The harness (how we know it works)

- **Build harness:** the Karpathy loop. Each feature gets plain-language checks that you approve and that are then locked. One hypothesis per round; keep or revert by score; every round logged. "Done" means green, plus reachable from the CLI and website, plus watched running.
- **Eval harness:** generator → independent checker (pure Python, locked) → lanes. Same model and same data for the AI-only lane. Predictions are committed to git before the run.
- **Anti-cheat checks already locked:**
  - The product never reads the answer key or the checker.
  - Editing the graph in FalkorDB changes Baton's answer, which proves the graph decides.
  - Results hold on companies never seen in development.

## 5. Timeline (IST), owners, kill times

| Time | What | Who | Kill / fallback |
|---|---|---|---|
| now–13:30 | rehearsal_core green (rounds 2–4) | loop | 14:30 not green → hero = Cut + reason-broken query (both already tested) |
| 12:30–13:30 | EC2 + Vercel + GitHub repo created | teammate | — |
| 13:30–14:30 | `ask` checks locked → green | loop | not green → web shows only the Rehearsal |
| 13:30–15:00 | `extract` (amb-adapted); teammate runs it once with the GPT key → cache committed | loop + teammate | no key → dev cache from Claude, labelled as such |
| 14:30–15:30 | `cut` (maxFlow) + Gitea write with read-back | loop | Gitea fails → write to the git repo file + read-back |
| 15:00–15:45 | Eval: 30 sealed seeds, predictions committed first | me | fewer seeds; still report |
| 15:30 | **No new features** | — | — |
| 16:00 | Freeze, tag `v-freeze`, deploy to EC2 + Vercel | teammate + me | site falls back to replay data |
| 16:00–18:00 | Video (6 beats, ≤2:45) recorded from the **live URL** | teammate | 60-second hero-only cut |
| 18:30 | Placeholder submission (Track 3 + Track 1) | teammate | — |
| 20:30 | Clean clone by the non-author, from the README alone | teammate | `git checkout v-freeze` |
| 21:00 | Submit | — | — |
