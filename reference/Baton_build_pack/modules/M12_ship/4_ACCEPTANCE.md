# M12 · Ship — ACCEPTANCE

Locked checks that must be green before the tag (exact names, checks/locked/rehearsal_core/test_rehearsal_core.py): `test_generate_is_deterministic_and_seed_sensitive` (:28), `test_world_holds_schedules_not_failures_and_has_every_planted_shape` (:39), `test_baton_G_matches_oracle_on_dev_seed` (:61), `test_baton_G_matches_oracle_on_unseen_seeds` (:69), `test_records_only_lane_R_matches_oracle` (:77), `test_workflow_lane_W_matches_oracle` (:85), `test_each_lane_sees_strictly_more_W_then_R_then_G` (:93), `test_gate_refuses_every_noise_belief_and_noise_changes_nothing` (:100), `test_unconfirmed_beliefs_are_labelled_believed_not_confirmed` (:113), `test_every_failure_cites_sources_that_exist` (:127), `test_live_graph_untouched_and_fork_dropped` (:139), `test_handover_to_active_successors_clears_every_failure` (:162), `test_handover_refuses_departed_successor_and_second_owner` (:178), `test_fails_loudly_when_falkordb_is_down` (:195), `test_wiring_demo_runs_end_to_end_offline` (:206), `test_product_never_reads_the_answer_key_or_oracle` (:220), `test_the_graph_is_the_source_of_truth_not_the_json` (:236). Any red one: its claim leaves the README and the video.

## 1. Checklist A — freeze, 16:00 (re-framed from scratchpad/book/BATON_FINAL_PLAN.md:253-262; read aloud)
1. Locked checks: count written down (3_STEPS 15:30). Red features hidden or listed as not done.
2. `docker compose up -d --build` works on fresh containers; `curl localhost:8000/api/demo?seed=7` → 200 (M11 E3).
3. `falkordb/falkordb:v4.22.1` pinned, not `latest` (docker-compose.yml:3).
4. No model output reaches a Cypher string: `grep -rn "f\"\"\"\|\.format(" baton/` and read every hit; only fixed query text with `$params` or the lane template in baton/rehearse.py:20-24 may build query text.
5. No product code reads the answer key (locked: `test_product_never_reads_the_answer_key_or_oracle`).
6. Live-graph hash equal before and after (`live_hash_before == live_hash_after` in `/api/demo`; locked: `test_live_graph_untouched_and_fork_dropped`).
7. Stopping FalkorDB makes the API return 503 (M11 F1; locked: `test_fails_loudly_when_falkordb_is_down`).
8. `deploy/requirements.txt` resolves (M11 R0).
9. `git status` clean; tag `v-freeze` pushed. "Any concern before we freeze?"

## 2. Checklist B — pre-submit, 20:30–21:00 (re-framed from scratchpad/book/BATON_FINAL_PLAN.md:265-274)
10. The non-author passed the clean clone from the README alone (3_STEPS 20:30).
11. The demo needs no API key: seed 7 uses `fixtures/beliefs_seed7.json` (server/app.py:31-34).
12. Video ≤ 2:45, opens logged out, says AI help was used.
13. Every number in README and video matches the 16:00 note.
14. None of the banned words (docs/modules/00_GROUND_TRUTH.md:51); no Slack/Okta/Jira/Gitea feature claims.
15. Data synthetic only; no secrets in the repo (`git grep -nIE "sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"` prints nothing).
16. "We knowingly do not" is near the top of the README.
17. If the eval (M7) ran: the lane table shows where we lose. If it did not run: no AI-alone claims anywhere.
18. Form: repo, live URL, video, **Track 3 and Track 1**, AI use disclosed.
19. Credits name Liz Zhang's agent-memory-bench with its MIT notice.
20. "Anyone see a reason not to submit?"

## 3. Hard questions, 30-second answers (re-framed from scratchpad/book/BATON_FINAL_PLAN.md:300-311; Slack/Okta/Gitea answers removed)
1. **"What still works without FalkorDB?"** Nothing that decides. The gate, the cover check and the hand-over are Cypher on a FalkorDB copy (baton/rehearse.py:36-75; baton/handover.py:20-25). Stop FalkorDB and the API returns 503; we show that in the video.
2. **"You planted the failures."** The generator plants schedules, chat, logs and tickets; nothing in the world file says what breaks (baton/generate.py:1-6; locked `test_world_holds_schedules_not_failures_and_has_every_planted_shape`). Failures are worked out by path queries on a copy and match an independent checker on seeds never used in development (locked `test_baton_G_matches_oracle_on_unseen_seeds`).
3. **"What breaks without the AI?"** You get lane R: records only. Duties that live only in chat and job logs are missing. The page shows R and G side by side. [quote the frozen R vs G numbers.]
4. **"What stops a made-up owner?"** A proposed duty needs at least two existing sources of two kinds, decided by a Cypher query (baton/rehearse.py:36-44); noise beliefs are refused (locked `test_gate_refuses_every_noise_belief_and_noise_changes_nothing`). A second accepted owner for a duty is blocked by a FalkorDB UNIQUE constraint (baton/handover.py:6-8, :35-37).
5. **"Why GRAPH.COPY?"** We need to remove a person and look a month ahead without touching the real graph. The copy is deleted after, and the fingerprint proves the real graph did not change (baton/graph.py:47-53; locked `test_live_graph_untouched_and_fork_dropped`). Copy time: [measure on the frozen build before claiming any number].
6. **"How is this a company brain and not an offboarding tool?"** It answers who owes what, why (with sources), and who covers what at a time; departure is the hardest question to ask it. Show the Ask section only if the locked ask checks (checks/locked/ask/test_ask.py) are green.
7. **"What is real and what is synthetic?"** Real: FalkorDB, every query, the API and site. Synthetic: the company, its chat, logs and tickets (FIXTURE). Simulated: the person's yes (`--confirm all`, server/app.py:70).
8. **"Who decides two sources are independent?"** A fixed rule: two different source kinds (message, joblog, ticket, record). We say plainly that one generator wrote both in the demo.
9. **"Which judging criteria did you optimise for?"** They are not published (docs/modules/00_GROUND_TRUTH.md:15). We built to the Track 3 focus list.
10. **"What did the AI write and what did you do?"** Read the AI-use section; name your own decisions concretely.

## 4. Anti-hallucination list
| Likely wrong | Correct | Source |
|---|---|---|
| The leaver is Priya and there are 4 failures | Seed 7's leaver is Hana Sharma in the current build; dev numbers were W 6, R 7, G 37 rows. Use only the 16:00 frozen numbers | live `/api/demo?seed=7`; web/mock/* are hand-written |
| "Three ways" = records / AI alone / Baton | The site's three rows are W, R, G (all graph lanes). "AI alone" exists only if the eval (M7) ran | web/index.html:45; server/app.py:68 |
| Mention Slack, Okta, Jira, Gitea writes | Not built; Gitea is not in compose | docs/BUILD_PLAN.md:30; docker-compose.yml:1-15 |
| Say a human confirmed each duty | Simulated in the demo (`--confirm all`) | server/app.py:70 |
| Quote win probabilities or "97–99% false-belief repetition" from the old plan | Judgement / unsourced; never say them | scratchpad/book/BATON_FINAL_PLAN.md:28, :109 |
| Say `algo.maxFlow` / "IMPOSSIBLE 3/4" | Only if the Cut shipped and is on the live URL | docs/BUILD_PLAN.md:40 |
| Say "MCP" | Only if M8 shipped | docs/BUILD_PLAN.md:44 |
| The README can link the round log | `loop/results.tsv` is git-ignored | .gitignore:2 |
| The clean clone can run the checks with no setup | They default to this sandbox's paths; set `BATON_TEST_REDIS`, `BATON_TEST_MODULE` | checks/locked/rehearsal_core/conftest.py:9-11 |
| Re-tag after a late fix | Never move `v-freeze`; README may be newer than the tag, say so | scratchpad/book/BATON_FINAL_PLAN.md:189 |
| Judges, weights or criteria | Not published | docs/modules/00_GROUND_TRUTH.md:15 |
| Credit URL is `github.com/zhang-liz/agent-memory-bench` (as in the code headers) | Verified URL is `github.com/zhang-liz/agent-memory-bench`; the FalkorDB one did not load | baton/llm.py:1; amb clone `git remote -v` |
| "AI alone" lane has results | A cached lane-A file exists (`fixtures/lane_a_seed7.raw.json`) and a locked check covers its schema (checks/locked/ai_layer/test_ai_layer.py:68); scores exist only if the eval (M7) ran | fixtures/; docs/BUILD_PLAN.md:43 |
| The deadline is 21:00 | Ours is 21:00; the event closes 23:59 IST | docs/modules/00_GROUND_TRUTH.md:7 |
