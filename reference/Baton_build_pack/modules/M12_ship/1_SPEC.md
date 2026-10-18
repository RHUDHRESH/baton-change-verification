# M12 · Ship — SPEC

## What it is, in plain words
The last six hours. We stop adding features, freeze the code under a git tag, put it live, record a short video from the live site, write the top of the README, send a placeholder submission early, have the person who did **not** write the code set it up from the README alone, and then submit. Every number we say must come from the frozen build.

## Why
- Submissions close 18 Oct 2026, 23:59 IST; our own deadline is 21:00 IST (docs/modules/00_GROUND_TRUTH.md:7).
- Rule 10 needs a public repo, a README with setup, the graph data model and "the Cypher queries or graph algorithms the product depends on", a demo video, a live deployment if we can, and the tracks named (docs/modules/00_GROUND_TRUTH.md:13).
- Rules 11–13: AI coding help must be disclosed, and we must be able to explain the graph model, queries, architecture and decisions (docs/modules/00_GROUND_TRUTH.md:14).
- We enter Track 3 and Track 1 and must name both when we submit (docs/modules/00_GROUND_TRUTH.md:10).

## Framing (Track 3 first)
Pitch, word for word: **"Every company brain knows who knows what. Baton knows who owes what, and the exact day it breaks if they leave."** (docs/BUILD_PLAN.md:3)
- Track 3 focus points we can show (docs/modules/00_GROUND_TRUTH.md:8): one graph from records, chat, job logs and tickets; who owns what; tracing each answer back to its source; answers with clear sources.
- Track 1 focus points we can show (docs/modules/00_GROUND_TRUTH.md:9): multi-hop graph queries (paths up to 4 hops with time-valid edges, baton/rehearse.py:20-24, :58-70); explainable results (every failure carries sources, baton/rehearse.py:75). Tool selection through MCP only if M8 ships; `algo.maxFlow` only if the Cut ships.
- Dropped from the old plan (scratchpad/book/BATON_FINAL_PLAN.md was written for Track 1 only): Slack, Okta, Jira, Gitea writes, the "AI alone" lane unless the eval ran, precedent learning, all win-probability numbers.

## In scope
Freeze checklist, tag `v-freeze`, deploy (M11 step 7), video (≤ 2:45, 6 beats, recorded from the live URL), README top section, AI-use disclosure, credit for agent-memory-bench, placeholder submission at 18:30, clean-clone test at 20:30, submit at 21:00.

## Not in scope
New features after 15:30 (docs/BUILD_PLAN.md:72). Moving the tag. Claims about judging criteria or judges (not published, docs/modules/00_GROUND_TRUTH.md:15). Claims about other entries (docs/modules/00_GROUND_TRUTH.md:51).

## Inputs / outputs
- Inputs: the repo at `v-freeze`; the live URL from M11; the measured numbers from `GET /api/demo?seed=7` and any eval output (M7).
- Outputs: tag `v-freeze`; video file + unlisted link; README top; `AI-USE` text (in README or its own file); the submitted form.

## Dependencies
M11 live URL (or replay-mode site), M10 page, whatever of M2–M8 is green at 15:30.

## Owner, time, kill (docs/BUILD_PLAN.md:72-77)
| Time (IST) | What | Who | Kill / fallback |
|---|---|---|---|
| 15:30 | No new features | — | — |
| 16:00 | Freeze, tag `v-freeze`, deploy to EC2 + Vercel | teammate + author | site falls back to replay data |
| 16:00–18:00 | Video (6 beats, ≤ 2:45) from the live URL | teammate | 60-second hero-only cut |
| 18:30 | Placeholder submission (Track 3 + Track 1) | teammate | — |
| 20:30 | Clean clone by the non-author, from the README alone | teammate | `git checkout v-freeze` |
| 21:00 | Submit | both | — |
