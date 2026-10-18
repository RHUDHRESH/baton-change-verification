# Brief for module-doc writers (shared by all four writers)

You write the build documents for Baton modules. These docs will be handed to coding agents (GPT, Claude) and to two students who must build, explain and defend the work tonight. A hallucinated API, flag, schema field, Cypher feature or number in these docs will cost us the hackathon. **Accuracy beats completeness.**

## Read first (all paths absolute)
- /home/claude/baton/docs/modules/00_GROUND_TRUTH.md (the law)
- /home/claude/baton/docs/BUILD_PLAN.md (module list, owners, times)
- /home/claude/baton/.claude/skills/project-context/SKILL.md (CLI contract and semantics)
- /home/claude/baton/checks/locked/rehearsal_core/{test_rehearsal_core.py,oracle.py,conftest.py} (the locked contract)
- /home/claude/baton/checks/pending/ask/test_ask.py (drafted contract for M4)
- /home/claude/baton/baton/*.py (what exists now: generate, graph, load, rehearse; more may appear while you work, so re-list before you cite)
- /home/claude/baton/server/app.py, /home/claude/baton/docker-compose.yml, /home/claude/baton/deploy/* (API and deploy, written, untested)
- /home/claude/baton/web/ (website in progress)
- /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/verify/{spike.py,native_spike.py,forecast_spike.py,hero_check.py,acl_check.py} (tested FalkorDB patterns)
- /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/book/BATON_FINAL_PLAN.md (story, video beats, README top, checklists, Q&A; NOTE it was written for a Track 1 framing with Slack/Gitea details that changed — the BUILD_PLAN and GROUND_TRUTH win on conflicts)
- /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/falkor/repos/ (cloned FalkorDB repos incl. docs/, falkordb-py/, agent-memory-bench/, FalkorDB-MCPServer/) — use these to VERIFY any FalkorDB/library syntax you write.

## For each module write exactly these 4 files in /home/claude/baton/docs/modules/<MXX_slug>/
1. `1_SPEC.md` — what and why in plain words (a 14-year-old could repeat it); which Track 3 / Track 1 focus point it serves; in scope / not in scope; inputs, outputs; dependencies on other modules; owner; time budget; kill time and fallback (from BUILD_PLAN).
2. `2_CONTRACT.md` — the exact interface: CLI flags, JSON shapes (field by field, types), graph labels / relationship types / properties, API routes, file paths, exit codes, error messages. Every item must be copied from an existing file (cite `path:line`) or be explicitly marked `PROPOSED (not yet in code)`. Cypher: only patterns that appear in the tested spike files or in current baton code (cite them) — anything else is marked `UNTESTED` with the exact command to test it.
3. `3_STEPS.md` — ordered build steps a coding agent can follow without guessing: each step = goal, files touched, exact commands, "done when" (an observable result), and a ready-to-paste prompt for a coding agent. Include the karpathy-loop rule: checks first, human approves, lock, then build; never edit checks/locked or loop/bin.
4. `4_ACCEPTANCE.md` — how we know it is done: the locked or drafted check names (exact test function names), the go-and-see commands and the expected visible output, failure modes and their fallbacks, and an "anti-hallucination list": things a coding agent is likely to assume wrongly for this module (e.g. falkordblite has no maxFlow; no datetime(); answer key must never be read), each with the correct fact and its source.

## Hard rules
- Never invent: library functions, CLI flags, environment variables, endpoints, field names, numbers, dates, judge preferences, rival claims. If you need something that doesn't exist yet, mark it `PROPOSED` and say who decides.
- Every factual line about existing code ends with a citation like `(baton/rehearse.py:42)` or `(checks/locked/rehearsal_core/test_rehearsal_core.py:120)`. Open the file and check the line before citing.
- Plain English, short sentences, no marketing words. Use the words list in GROUND_TRUTH §E.
- Do not edit any file outside your own module folders. Do not run git. You may run read-only commands and the project's python (`/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`) to check syntax claims.
- At the end, self-audit: grep your docs for every backticked identifier and confirm it exists in the cited file or is marked PROPOSED/UNTESTED. Report how many citations you checked and how many you fixed.
