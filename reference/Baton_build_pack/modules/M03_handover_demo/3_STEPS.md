# M03 · Handover and demo · STEPS

The code exists and the checks are green (loop/results.tsv:5). The steps below are: verify, go and see, defend, and then the remaining `PROPOSED` items, which need a human decision first.

## Loop rule (applies to every step)
Checks come first. A human approves them, they are locked, and only then does building start. Never edit `checks/locked/**`, `loop/bin/**` or `.claude/settings.json` (loop/program.md:16-21). Change only `baton`, `fixtures`, `Makefile` and `README.md` (loop/config.json "mutable_paths"). One hypothesis per round, with the prediction written first (loop/program.md:23-25). "Green is not done": done also means reachable from the real entrypoint and watched running (loop/program.md:28-30).

```
S=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad
PY=$S/venv/bin/python
B=$S/venv/lib/python3.13/site-packages/redislite/bin
cd /home/claude/baton
$B/redis-server --port 6399 --daemonize yes --dir /tmp --loadmodule $S/fdb422/falkordb.so --save ''
```

## Step 1: Run the three locked checks for M03
- Goal: confirm green on your machine.
- Command (read-only; it does not write the loop's score files):
  ```
  PYTHONDONTWRITEBYTECODE=1 $PY -m pytest checks/locked/rehearsal_core -q -p no:cacheprovider -k "handover or demo"
  ```
- Done when: `4 passed` (check 12 × 2 seeds, check 13, check 15). Observed by the writer at 11:37 IST.
- Prompt:
  > Run the pytest command above and report the pass count. If a check fails, do not touch checks/; report the assertion and the stdout/stderr from the failing baton call.

## Step 2: Watch the demo run (the real entrypoint)
- Goal: see the whole story in one JSON line.
- Command: `$PY -m baton demo --seed 7 --port 6399 --offline`
- Done when: the output shows `"lanes": {"G": {"failures": 37}, "R": {"failures": 7}, "W": {"failures": 6}}`, `"after_handover": {"accepted": 6, "failures": 0, "refused": 0}`, `"unpromoted": 4`, and equal hashes (observed 11:37 IST).
- Say this when presenting: these numbers count *events*. In duties it is W 3, R 4, G 6 (loop/reports/rehearsal_core.md).
- Prompt:
  > Run `python -m baton demo --seed 7 --port 6399 --offline` with the project venv and paste the output. Explain every key using docs/modules/M03_handover_demo/2_CONTRACT.md §2. Do not edit files.

## Step 3: Show the two refusals by hand
- Goal: the "a hallucinated owner cannot get in" moment, with real output.
- Commands:
  ```
  $PY -m baton generate --seed 7 --out $S/w7
  $PY -m baton handover --world $S/w7 --beliefs fixtures/beliefs_seed7.json --leaver hana.sharma \
      --assign d-codesign-windows=ingrid.tanaka --port 6399
  $PY -m baton handover --world $S/w7 --beliefs fixtures/beliefs_seed7.json --leaver hana.sharma \
      --assign d-codesign-windows=anika.lindqvist --assign d-codesign-windows=arjun.haddad --port 6399
  ```
  (On seed 7, `ingrid.tanaka` has `left_at` set, and `anika.lindqvist` and `arjun.haddad` are active, as observed in world.json.)
- Done when: the first prints a refusal with reason `person has left or does not exist (left_at 1786554000000)`, and `d-codesign-windows` is still in `failures_after`. The second prints 1 accepted and 1 refused with `duty already has an accepted successor`. Both were observed by the writer at 11:58 IST on a scratch server. After the second command, `d-codesign-windows` is no longer in `failures_after`.
- Prompt:
  > Run the two handover commands and show only `accepted` and `refused`. Explain which line of baton/handover.py made each decision.

## Step 4: Defend it (rule 12)
| Question | Answer (with where it comes from) |
|---|---|
| Who enforces "one owner per duty": Python or the database? | The database. A FalkorDB UNIQUE constraint on `OWNER.active_key` rejects the second write. Python only turns the error into a reason (baton/handover.py:33-46, :73-76). |
| Why doesn't the constraint block the existing record owners? | Record OWNER edges have no `active_key`, and the constraint ignores edges without it (baton/handover.py:6-7; loop/rounds/rehearsal_core-3.md "Facts"). |
| What is the "authority re-check"? | Inside the same write query: the duty exists, the person exists, `left_at IS NULL`, and the person is not the leaver. Zero rows means no edge (baton/handover.py:20-25). It does **not** check a manager's approval. |
| Is the handover saved? | No. It runs on the fork, and the fork is deleted. It is a rehearsal of the handover (baton/handover.py:87; baton/rehearse.py:134-135). Writing it to the live graph is PROPOSED. |
| What does make-before-break mean here? | The successor edges are created on the fork *before* the leaver is marked as gone, and then the month is checked again (baton/rehearse.py:131-133). |
| Why is the successor edge valid from `leave_at` and not now? | Until `leave_at` the leaver still covers the duty. Every failing event is at or after `leave_at`, so the new edge covers all of them (loop/rounds/rehearsal_core-3.md "Mechanism"). |
| Does demo call an AI? | No. It reads the cached extraction `fixtures/beliefs_seed7.json`. `--offline` is the only mode today (baton/demo.py:4-5, :30). |
| Why is G 37 in demo but 38 in the checks' own run? | Demo uses the fixture beliefs. Its promise belief has 1 event and a different duty id from the generator's planted belief, which has 2 events. The demo check only needs G > R (checks/locked/rehearsal_core/test_rehearsal_core.py:214). |

## Step 5 (`PROPOSED`, needs a human decision): `make demo`
- Goal: the plan's one-command start, `docker compose up && make demo` (scratchpad book/BATON_FINAL_PLAN.md:254). Note: the plan's `OFFLINE=1`, and `BATON_OFFLINE` in docker-compose.yml:12, are read by **no** code in `baton/` or `server/`. Offline is the `--offline` flag, and demo is always offline anyway (baton/demo.py:30).
- Files touched: `Makefile` (a mutable path; it does not exist yet).
- Who decides: the team lead. There are no locked checks for it, so it is wiring, not a feature.
- Done when: `make demo` prints the same JSON as step 2 against the compose FalkorDB (`127.0.0.1:6379`, docker-compose.yml:4).
- Prompt:
  > PROPOSED, only after a human says go: add a Makefile with a `demo` target that runs `python -m baton demo --seed 7 --port 6379 --offline`. Do not add flags that do not exist in baton/__main__.py. Run it once and paste the output.

## Step 6 (`PROPOSED`, needs a human decision): persist an accepted handover
- Goal: an acceptance survives after the rehearsal (BUILD_PLAN's "single-query commit", docs/BUILD_PLAN.md:39).
- Who decides: the team. It would write to the live graph, which every current check treats as read-only (checks/locked/rehearsal_core/test_rehearsal_core.py:139-157), so it needs a new feature with new locked checks first.
- UNTESTED: whether `GRAPH.COPY` carries a constraint from the live graph to a fork. Test it with: create the index and the constraint on a scratch graph, `GRAPH.COPY` it, then `CALL db.constraints()` on the copy.
- Kill: after 15:30 IST no new features (docs/BUILD_PLAN.md:72). If this is not locked and green by then, leave it out and describe the handover as a rehearsal.
