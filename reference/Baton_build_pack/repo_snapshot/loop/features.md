# features.md - baton

One feature at a time. A feature is small enough that its success can be verified by code, and big enough
to be worth a user noticing. Never "build the whole app".

| # | Feature | Status | Checks (locked) | Rounds | Method |
|---|---------|--------|-----------------|--------|--------|
| 1 | rehearsal-core | accepted | 32/32 | 3 | 1 |
| 2 | ask | green (wired: CLI + /api/ask) | 11/11 | 1 | 1 |
| 3 | ai_layer | green (CLI; caches replay offline) | 7/7 | 1 | 1 |
| 4 | ask ratchet | green | +6 | 1 | 1 |
| 5 | cut | green (CLI) | 17/17 | 1 | 1 |
| 6 | commit_write | green (CLI + /api/commit) | 5/5 | 1 | 1 |
| 7 | gate ratchet | green | +4 | 1 | 1 |
| 8 | eval | green; sealed run committed | 5/5 | 1 | 1 |

Status: `todo` -> `chartered` -> `checks-approved` -> `building` -> `green` -> `audited` -> `accepted` (or `blocked` / `killed`).

---

## Feature charter template (copy one per feature)

### <feature name>
- **Goal, plain words (no jargon, a smart 14-year-old could repeat it):**
- **Who cares / what changes for them:**
- **Entrypoints that must exist when done** (route / page / command a real user goes through):
- **Shared rules or formats this touches** (so old code gets updated too):
- **Not included, and why** (scope cut agreed up front; a written non-goal list stops late surprises):
- **Riskiest assumption (the monkey):**
- **Premortem - "it shipped and it's broken: why?"** (top 3-5 reasons -> each becomes a check or a watch-item):
- **Kill criteria:** stop after <N> rounds or <K> rounds without a new passing check; or if <measurable> by <when>.
- **Taste gate needed?** (yes if the point is delight / "wow", not just correctness): <yes/no, what a stranger should see in 60 seconds>


### rehearsal-core
- **Goal, plain words:** Before someone leaves, Baton copies the company graph, removes them, walks every already-scheduled obligation over the next 30 days, and lists each one that would have nobody able to act. Successors can then accept duties and the list goes to zero. The real graph is never touched.
- **Who cares:** the manager of the person leaving; the judges (Track 3: who owns what, keeping knowledge current, answers with sources).
- **Entrypoints:** `python -m baton generate|load|rehearse|handover|demo` (JSON on stdout).
- **Shared rules:** world.json schema (records / events / messages / joblogs / tickets), belief schema, graph name `halden_<seed>`.
- **Not included (and why):** LLM extraction quality (separate feature + eval), maxFlow cut, Gitea write, Slack, UI, the AI-only lane (eval feature). Keeps the first loop on the monkey.
- **Riskiest assumption (monkey):** FalkorDB path queries with per-edge time validity reproduce an independent oracle on unseen companies.
- **Premortem:** generator plants failures (circular) -> world must hold schedules only; engine computes in Python not FalkorDB -> graph-is-truth check; engine reads answer key -> isolation check; fork left behind or live graph mutated -> hash/list check; noise beliefs slip through -> gate check.
- **Kill criteria:** 12 rounds or 3 rounds without a new passing check; if not green by 14:30 IST, fall back to the tested Cut + broken-reason hero.
- **Taste gate:** yes, later (the three-column timeline in the video).

### ask
- **Goal, plain words:** Ask the company brain a question in normal words and get an answer from the graph with its sources: what someone owes, what breaks if they leave, why a duty is theirs, who covers something on a given day. If the graph can't answer, it says so. The model may only pick a question type and its arguments from a fixed list; it never writes Cypher.
- **Who cares:** Track 3 judges ("answers with clear sources", "who owns what"); managers.
- **Entrypoints:** `python -m baton ask --world DIR --beliefs FILE --question Q --port P [--offline]`, `python -m baton ask --catalogue`; API `/api/ask` (server/app.py).
- **Not included:** live-model routing quality (an offline deterministic router is checked; the model router reuses the same catalogue), answer prose quality.
- **Monkey:** mapping free-text names ("Hana Sharma", duty names) to graph ids without the answer key.
- **Kill criteria:** 8 rounds / 3 without progress; if not green by 14:30, the website shows only the Rehearsal.

### ai_layer
- **Goal:** the model reads chat, job logs and tickets and proposes beliefs with cited sources; results are cached by world hash + model + prompt version so judges replay with no key; an "AI alone" lane (same model, same raw data, no graph) is cached the same way; Liz Zhang's agent-memory-bench company (MIT, vendored in third_party/amb) is imported as an externally-written second company with its truth sealed.
- **Entrypoints:** `extract`, `lane-a`, `amb-import` CLI commands; `server/app.py` already calls `extract` for seeds without a cache.
- **Not included:** model quality (eval measures it); the ask model router (later).
- **Monkey:** a cache format that replays byte-for-byte and never silently serves a stale cache for a changed world.
- **Kill:** 8 rounds; if not green by 15:00, ship with the seed-7 cache only.

### cut
- **Goal:** prove whether the people who stay can absorb everything the leaver held: FalkorDB `algo.maxFlow` on a fork over duty → capable stayer → capacity, with a min-cut certificate naming what nobody can take, and an N-1 sweep.
- **Entrypoints:** `python -m baton cut --world DIR --beliefs FILE --leaver ID --port P`.
- **Shared formats touched:** world.json gains CAN records and people[].capacity; extraction/lane-A caches must therefore be keyed on the inputs each step actually reads, so existing caches stay valid.
- **Monkey:** algo.maxFlow returns no min-cut; compute it from a residual BFS and prove capacity(cut) == flow.
- **Kill:** 6 rounds; if not green by 14:30, the Cut stays as the tested spike shown in the README only.

### commit_write
- **Goal:** Baton gets the work done. Accepted successors are written to the LIVE graph (one successor per duty enforced by a UNIQUE constraint; people who left refused by a guarded write), then to a real external system (a file in a git repository, committed), and both are read back into a receipt. Nothing reaches the external system if the graph write fails or is refused.
- **Entrypoints:** `python -m baton commit --world DIR --beliefs FILE --leaver ID --assign DUTY=PERSON ... --repo DIR --port P`; later `/api/commit`.
- **Not included:** Gitea (optional adapter behind the same interface, later), Slack.
- **Monkey:** ordering — graph first, file second, read-back third — with no partial external write on refusal.
- **Kill:** 6 rounds; if not green by 15:00, the demo shows handover on the fork only and says so.

### eval
- **Goal:** measured, pre-registered evidence. Baton stays exact as the company grows; W and R miss what G finds; model tokens per question: the AI-alone lane must re-read the whole company each time, while Baton spends none after one extraction. Bootstrap 95% CIs (method adapted from agent-memory-bench by Liz Zhang, MIT). Predictions in eval/PREDICTIONS.md were committed before any result.
- **Entrypoints:** `python -m baton generate --scale N`, `python -m eval.run --seeds A-B --scales 1,4 --lanes W,R,G --port P --out DIR` -> results.json + report.md. Lane A results are read from cached real-model runs where they exist and reported as "not run" otherwise.
- **Not included:** running live models (needs the team's key).
- **Kill:** 6 rounds; by 15:45 publish whatever is measured.
