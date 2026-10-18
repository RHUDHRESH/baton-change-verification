# M04 · ask — build steps (remaining work)

`PY=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`. Run from `/home/claude/baton`.

## Loop rule (Karpathy loop): checks first, human approves, lock, then build
- Never edit `checks/locked/**` or `loop/bin/**` (loop/program.md:16-19). Disputes go in `loop/disputes/<check>.md` (loop/program.md:20-22).
- The loop may change only `baton`, `fixtures`, `eval`, `Makefile`, `README.md` (loop/config.json `mutable_paths`).
- One hypothesis per round, prediction first, keep only on more passes with no regressions (loop/program.md:23-27).
- Score with `python3 loop/bin/run_checks.py` (loop/program.md:14). It covers all of `checks/locked`.
- New behaviour needs a new check first: draft it in `checks/pending/ask/`, a human approves, then `python3 loop/bin/lock_checks.py ask --approved-by "..." --amend` (loop/bin/lock_checks.py:5).

## Done already (do not redo)
- 17/17 locked ask runs green, including `who_owns` and the human-name ratchet.

## Step 1 — check first: negative day (human approves)
- Goal: a check that fails today. Suggested plain-language item: "Asking who covers the first on-call duty on its first day (a negative day number) routes to that negative day."
- Suggested test (for `checks/pending/ask/test_ask_negative_day.py`, after human approval):
  ```
  def test_covers_keeps_a_negative_day(worlds, port):
      d, w, k, beliefs, bp = _setup(worlds, 7)
      duty = sorted(r["duty"] for r in w["records"] if r["type"] == "ROUTES_TO")[0]
      at = min(e["at"] for e in w["events"] if e["duty"] == duty)
      day = (at - w["now"]) // w["day_ms"]
      assert day < 0
      name = next(x["name"] for x in w["duties"] if x["id"] == duty)
      out = _ask(port, d, bp, f"Who covers {name} on day {day}?")
      assert out["args"]["day"] == day
  ```
  It reuses `_setup`/`_ask` as written in test_ask.py:11-18. The pending folder needs its own copy of those helpers, because it has no conftest until it is locked.
- Done when: the check is locked and fails.

## Step 2 — fix it
- Prediction: "`test_covers_keeps_a_negative_day` flips; nothing regresses."
- Prompt:
  > In baton/ask.py the covers route loses the minus sign: norm() (ask.py ~104) turns "-" into a space and the covers pattern uses `day (?P<day>\d+)` (ask.py ~96-97). Keep the router deterministic. When the covers pattern matches, take the day from the RAW question with `re.search(r"\bday\s+(-?\d+)\b", question, re.I)` and pass that signed int as args["day"]. route() needs the raw question for this; it receives it already as its first argument before norm(). Do not change Q_COVERS. Never write "oracle" or "answer_key" in baton/. Run python3 loop/bin/run_checks.py.

## Step 3 — go and see (habit H1, loop/program.md:57-59)
- Run the 4_ACCEPTANCE commands, then through the API (M09 docs): `curl -s -X POST localhost:8000/api/ask -H 'content-type: application/json' -d '{"seed":7,"question":"Who owns Warehouse snapshot to cold storage?"}'`. That duty is a seed-7 ghost job (seed-7 extract cache).
- Update loop/features.md:9 to the real count (17/17, or 18/18 after Step 1).
