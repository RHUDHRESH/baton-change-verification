# M03 · Handover and demo · ACCEPTANCE

## Locked checks (exact names, checks/locked/rehearsal_core/test_rehearsal_core.py)
| Check | Line | Status |
|---|---|---|
| `test_handover_to_active_successors_clears_every_failure[7]` | :162 | passing since round 3 (loop/results.tsv:5) |
| `test_handover_to_active_successors_clears_every_failure[101]` | :162 | passing since round 3 |
| `test_handover_refuses_departed_successor_and_second_owner` | :178 | passing since round 3 |
| `test_wiring_demo_runs_end_to_end_offline` | :206 | passing since round 3; needs `fixtures/beliefs_seed7.json` (loop/rounds/rehearsal_core-3.md "Result") |

## Go and see
| Command | Expected visible output | Seen |
|---|---|---|
| `python -m baton demo --seed 7 --port P --offline` | `W 6, R 7, G 37`; `after_handover {accepted 6, failures 0, refused 0}`; `unpromoted 4`; equal hashes | 11:37 IST (writer); loop/reports/rehearsal_core.md |
| `handover … --assign d-codesign-windows=ingrid.tanaka` (seed 7) | refused, `person has left or does not exist (left_at 1786554000000)`; the duty is still in `failures_after` | 11:58 IST (writer) |
| `handover … --assign d-codesign-windows=anika.lindqvist --assign d-codesign-windows=arjun.haddad` | 1 accepted; arjun refused with `duty already has an accepted successor` | 11:58 IST (writer) |
| `demo --seed 8 …` | stderr `baton demo: no cached extraction for seed 8 …`, exit 4 | 11:37 IST (writer) |
| stop FalkorDB, then `demo` | `FalkorDB is not reachable at …`, exit 3 | rehearse path seen; loop/reports/rehearsal_core.md reports it for the CLI |
| `uvicorn server.app:app`, then `POST /api/handover {"seed":7,"assign":{…}}` | accepted plus remaining failures | loop/reports/rehearsal_core.md "Go and see"; not re-run by this writer |

## Failure modes and fallbacks
| Failure | Symptom | Fallback |
|---|---|---|
| Fixture missing or ids drifted after a generator change | exit 4, or G ≤ R, or `after_handover.failures > 0` | restore `fixtures/beliefs_seed7.json`; never change the generator after the freeze (M01 3_STEPS.md, step 3) |
| Constraint not OPERATIONAL within 5 s | `RuntimeError: FalkorDB unique constraint on OWNER.active_key is …` | rerun. Round 3 saw OPERATIONAL on the first poll (loop/rounds/rehearsal_core-3.md "Facts") |
| A FalkorDB error other than a constraint violation during accept | traceback, non-zero exit (baton/handover.py:74-75) | read the message; fix the cause, do not swallow it |
| An old `halden_7` left on the server (for example after a manual edit) | demo numbers differ from the table above | delete `halden_7` and rerun (demo loads it again if it is missing) |
| API down during the video | the web falls back to recorded data (docs/BUILD_PLAN.md:49) | note: `web/mock/*.json` is hand-written, not recorded CLI output (see below) |

## Anti-hallucination list
| Wrong assumption | Correct fact | Source |
|---|---|---|
| "The handover is committed to the company graph" | Acceptances are written on the fork, and the fork is deleted. The live graph is unchanged (equal hashes) | baton/handover.py:87; baton/rehearse.py:134-135 |
| The authority re-check verifies a manager's approval | It checks that the duty and person exist, `left_at IS NULL`, and the person is not the leaver. That is all | baton/handover.py:20-25 |
| Python decides "one owner per duty" | A FalkorDB UNIQUE constraint on `OWNER.active_key` does; Python maps the error to a reason | baton/handover.py:33-46, :73-76 |
| The leaver's OWNER edge is closed (`vt` set) | Never. Departure = `left_at` set on the fork | baton/rehearse.py:56 |
| A person with a future `left_at` can accept | No. `Q_ACCEPT` requires `left_at IS NULL` | baton/handover.py:22 |
| `handover` takes `--lane` or `--confirm` | It does not; it always runs G with `confirm=all` | baton/__main__.py:27-32; baton/handover.py:87 |
| A refused assignment makes the command fail | Exit 0; refusals are listed in `refused` | observed; baton/handover.py:61-82 |
| `demo --offline` switches off an online mode | There is no online mode yet; demo always reads the cache | baton/demo.py:30 |
| `python -m baton extract` exists (the demo's error message says to run it) | It does not exist yet (no subparser) | baton/__main__.py:7-46; baton/demo.py:23 |
| `OFFLINE=1` / `BATON_OFFLINE=1` control the demo | No code reads either variable | grep of baton/ and server/ (11:58 IST); docker-compose.yml:12 |
| `/api/demo` runs `baton demo` and includes the handover | It runs `rehearse` W/R/G only, with `--confirm all` | server/app.py:63-76 |
| The API can show the second-owner refusal | `assign` is a dict (one person per duty), so it cannot | server/app.py:79-81, :89-90 |
| Demo G = the checks' G | Demo uses the fixture beliefs (G 37 on seed 7); with the planted beliefs G is 38. The check only needs G > R | loop/rounds/rehearsal_core-3.md "Facts"; checks/locked/rehearsal_core/test_rehearsal_core.py:214 |
| Demo counts failing duties | It counts failing events (seed 7: G 37 events, 6 duties) | baton/demo.py:43; loop/reports/rehearsal_core.md |
| `web/mock/handover_7.json` shows real output | It is hand-written: ids like `p-sam`, `duty:…`, ISO dates, and hashes prefixed `sha256:`. Real ids are `first.last` / `d-…`, real times are epoch ms, real hashes are bare hex | web/mock/handover_7.json; baton/graph.py:44; baton/generate.py:204 |
| Fixtures exist for every seed | Only `fixtures/beliefs_seed7.json` | `ls fixtures` (11:37 IST) |
| Gitea write, read-back receipt or Slack are part of handover | Not in M03 code | docs/BUILD_PLAN.md:20 (planned); baton/handover.py (absent) |
| GRAPH.COPY copies the UNIQUE constraint | UNTESTED. The code creates the constraint on each fork | baton/handover.py:35-37 |
