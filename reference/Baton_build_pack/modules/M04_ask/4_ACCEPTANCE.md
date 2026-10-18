# M04 · ask — acceptance

## Locked checks — 17/17 passing when the writer ran `pytest checks/locked/ask`
checks/locked/ask/test_ask.py:
| Test function | Runs | What it proves |
|---|---|---|
| `test_what_breaks_if_someone_leaves_matches_the_rehearsal` | 7, 202 | tool, `args.person` = leaver, duty set = reference lane G (test_ask.py:25-31) |
| `test_what_does_someone_owe_lists_records_and_confirmed_duties` | 7, 202 | duty set = every OWNER record ∪ promoted beliefs (test_ask.py:34-41) |
| `test_why_is_a_ghost_duty_theirs_cites_exactly_its_evidence` | 7, 202 | sources = exactly the belief's sources (test_ask.py:44-50) |
| `test_who_covers_a_duty_at_a_time_matches_the_graph` | 7 | rows non-empty ⇔ covered at the event (test_ask.py:53-65) |
| `test_unanswerable_question_says_so_without_sources` | 7 | `none`, no rows or sources, "not in the graph" (test_ask.py:68-72) |
| `test_cypher_comes_from_the_fixed_catalogue_and_sources_exist` | 7, 202 | `cypher == catalogue[tool]`; sources exist (test_ask.py:75-84) |
| `test_ask_fails_loudly_when_falkordb_is_down` | – | non-zero exit, "falkordb" in the output (test_ask.py:87-92) |

checks/locked/ask/test_ask_ratchet.py:
| Test function | Runs | What it proves |
|---|---|---|
| `test_who_owns_a_recorded_duty_names_its_record_owners` | 7, 202 | `who_owns`, persons = record owners, sources exist (test_ask_ratchet.py:18-30) |
| `test_who_owns_a_duty_known_only_from_chat_names_the_gated_holder` | 7, 202 | persons = {belief person}, sources = the belief's sources (test_ask_ratchet.py:33-40) |
| `test_answers_use_human_names_not_raw_ids` | 7, 202 | rows have `duty_name`; answers contain no duty ids (test_ask_ratchet.py:43-52) |

All rehearsal_core and ai_layer checks must stay green (loop/config.json `check_command` runs `checks/locked`).

## Go and see
Start FalkorDB as in the project-context skill (port 6399), then:
```
PY=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python
W=/tmp/ask7; $PY -m baton generate --seed 7 --out $W
$PY -m baton extract --world $W --out $W/beliefs.json --offline
$PY -m baton ask --catalogue | $PY -c "import json,sys; print(sorted(json.load(sys.stdin)))"
$PY -m baton ask --world $W --beliefs $W/beliefs.json --question "What breaks if Hana Sharma leaves?" --port 6399 --offline
$PY -m baton ask --world $W --beliefs $W/beliefs.json --question "Who owns Warehouse snapshot to cold storage?" --port 6399 --offline
$PY -m baton ask --world $W --beliefs $W/beliefs.json --question "Who covers Edge and CDN on-call on day -4?" --port 6399 --offline | $PY -c "import json,sys; print(json.load(sys.stdin)['args'])"
$PY -m baton ask --world $W --beliefs $W/beliefs.json --question "What is the CEO's favourite colour?" --port 6399 --offline
$PY -m baton ask --world $W --beliefs $W/beliefs.json --question "What does Hana Sharma owe?" --port 1 --offline; echo "exit=$?"
```
If the `extract --offline` line exits 4, something the extractor reads has changed since the seed-7 cache was made (M05 4_ACCEPTANCE, first failure mode). For this go-and-see only, use the key beliefs instead: `$PY -c "import json; k=json.load(open('$W/answer_key.json')); json.dump(k['true_beliefs']+k['noise_beliefs'], open('$W/beliefs.json','w'))"`. This is what the locked checks do (test_ask.py:11-14).

Expected:
- The catalogue prints `['breaks_if_leaves', 'covers', 'none', 'owes', 'who_owns', 'why']`.
- The breaks answer names duties in words (no `d-…` ids), `args.person` = `hana.sharma` (the seed-7 leaver), and the two live hashes are equal.
- `who_owns` names Hana Sharma with "confirmed from chat", backed by the seed-7 extract cache's ghost-job belief (ask.py:277-281).
- The covers args print `{'duty': 'd-oncall-edge', 'day': -4}` after the fix. **Today they print `'day': 4`** (2_CONTRACT §3.2).
- The colour question gives `none`, `sources: []`, and "That is not in the graph. …".
- The dead port gives "FalkorDB is not reachable at localhost:1 …" and `exit=3`.

## Failure modes and fallbacks
| Failure | Fallback |
|---|---|
| The negative-day fix regresses something | Revert (loop/program.md:26-27); list "negative day numbers are read as positive" as a known limit in the README |
| Ask unusable on the live site | "website shows only the Rehearsal" (loop/features.md:47; docs/BUILD_PLAN.md:68) |

## Anti-hallucination list
| # | Wrong assumption | Correct fact | Source |
|---|---|---|---|
| A-1 | "Use the website's tool names (`what_breaks_if_leaves`, `who_owes`, `why_owner`, `who_covers_on_day`, `path_between`, `list_unconfirmed`)." | The code uses `breaks_if_leaves`, `owes`, `why`, `who_owns`, `covers`, `none`. | ask.py:71-78; web/index.html:108-115 |
| A-2 | "Copy Cypher from web/mock/ask_7.json." | It uses `Obligation`, `OWNER_FIELD`, `DOES`, `DETACH DELETE`, none of which exist. A departure is `SET p.left_at` on a fork. | web/mock/ask_7.json; rehearse.py:56; load.py:5-12 |
| A-3 | "`day -4` works." | `norm()` drops "-" and the pattern is `\d+`, so −4 becomes 4. The 5 doc-time cases matched only by luck. | ask.py:96-97, 104-105 |
| A-4 | "Day N = start of day N." | It is the first event of the duty on day N; the start of the day is only the fallback. Coverage at the start of the day differs for 1–2 events per seed (doc-time scratch run). | ask.py:44-48 |
| A-5 | "Write beliefs or HOLDS edges to the live graph." | Fork only; deleted afterwards; the live fingerprint stays unchanged. | ask.py:206-218; test_rehearsal_core.py:139-157 |
| A-6 | "`owes` filters OWNER by time." | Untimed. Every OWNER record counts (`who_owns` does filter by `Company.now`). | ask.py:25-31, 60-63; test_ask.py:39-40 |
| A-7 | "Sources are objects." | The CLI returns id strings. | test_ask.py:50, 83; ask.py:322 |
| A-8 | "Use `EXISTS{}` / `COUNT{}` / `shortestPath`." | Not in v4.22. Use the OPTIONAL MATCH var-length pattern. | docs/modules/00_GROUND_TRUTH.md:24-27 |
| A-9 | "Let a model write Cypher when no tool fits." | Never: `none`. | docs/BUILD_PLAN.md:29; ask.py:3-5 |
| A-10 | "A model already routes without `--offline`." | No. `router` is always "offline". | ask.py:299, 311; loop/features.md:45 |
| A-11 | "Mention the reference checker in a comment." | "oracle" in any baton/*.py fails a locked check; "answer_key" is allowed only in generate.py. | test_rehearsal_core.py:223-227 |
| A-12 | "Read names from world.json." | Person and Duty names come from the live graph; promise names come from the beliefs file. | ask.py:304-307; test_rehearsal_core.py:236-246 |
| A-13 | "ask's breaks rows say 'believed'." | ask uses `on_fork(..., "all")`, so belief rows say "confirmed". The rehearse CLI default is "none". | ask.py:241; __main__.py:24 |
| A-14 | "Say Baton 'predicts' failures." | Banned wording. | docs/modules/00_GROUND_TRUTH.md:51 |
