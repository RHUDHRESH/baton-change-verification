# Baton build pack: index

**Pitch:** Every company brain knows who *knows* what. Baton knows who *owes* what, and the exact day it breaks if they leave.

## How to use this pack (people and coding agents)
1. Read `00_GROUND_TRUTH.md` first. It holds the verified facts about the event rules, FalkorDB v4.22.1 quirks and licences. If any doc disagrees with it, the ground truth wins.
2. Pick a module folder. Each has four files:
   - `1_SPEC`: what and why.
   - `2_CONTRACT`: the exact interface, with file:line citations.
   - `3_STEPS`: ordered steps plus a ready-to-paste coding-agent prompt.
   - `4_ACCEPTANCE`: check names, go-and-see commands, fallbacks, and the "things an agent will assume wrongly" list.
3. Anything marked `PROPOSED` or `UNTESTED` is not a fact yet. Run the command given next to it before relying on it.
4. **Only a passing locked check or a recorded run is proof.** The docs describe; `checks/locked/` decides. Run `python3 loop/bin/run_checks.py` in the repo.
5. Never edit `checks/locked/` or `loop/bin/`. New behaviour means new checks: a human approves them, then they are locked, then the code is built.

## Modules and status
Status as of the ZIP time; see `STATUS.md` in the ZIP root for the live numbers.

| # | Module | Folder | Status |
|---|---|---|---|
| M01 | Generator (synthetic company, schedules only, sealed answer key) | `M01_generator/` | ✅ green |
| M02 | Engine: load + Rehearsal (fork, temporal paths, 2-source gate in Cypher) | `M02_engine/` | ✅ green |
| M03 | Handover + demo (UNIQUE constraint, refuse leavers) | `M03_handover_demo/` | ✅ green |
| M04 | Ask the company brain (fixed Cypher catalogue, sources, who-owns) | `M04_ask/` | ✅ green |
| M05 | AI extraction + AI-alone lane + agent-memory-bench import (Liz Zhang, MIT) | `M05_extract/` | ✅ green (caches for seeds 7, 101, 202, 303) |
| M06 | Max-flow Cut + commit & write (live graph + git file + read-back) | `M06_cut_and_write/` | ✅ green (Gitea optional, untested) |
| M07 | Eval (scale and cost curves, pre-registered predictions) | `M07_eval/` | 🔨 predictions committed; checks approved |
| M08 | MCP server | `M08_mcp/` | ⏳ stretch, untested |
| M09 | HTTP API | `M09_api/` | ✅ works locally (`/api/health`, demo, handover, ask, cut, commit, catalogue) |
| M10 | Website (team builds it) | `M10_web/` + `M10_web/samples/` (real API responses) | 📋 plan only |
| M11 | Deploy (EC2 + Vercel) | `M11_deploy/` | 📋 plan; waiting on the Elastic IP |
| M12 | Ship (freeze, video, README, submit) | `M12_ship/` | 📋 plan |

## Honest limits to repeat everywhere
- The company is synthetic (FIXTURE). The planted structure comes from our generator. Liz Zhang's agent-memory-bench company is the externally written check.
- On a 9-person company, a model reading everything finds about as much as Baton: 36 of 38 events on seed 7. Baton's measured advantages are size, cost per question, proofs, safe writes and the max-flow verdict, not "the AI gets it wrong".
- The AI extraction caches were made by Claude Haiku through the harness, not through the API, and they are labelled that way. A GPT run by the team replaces or adds to them.
