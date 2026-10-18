# M12 · Ship — STEPS (run sheet, IST)

Karpathy-loop rule still holds after 15:30: no new checks, no new features, never edit `checks/locked/` or `loop/bin/`. Fix only what a checklist item turns red, and log why it went red. Either person can stop the release (scratchpad/book/BATON_FINAL_PLAN.md:251).

---

## 15:30 — Stop features (docs/BUILD_PLAN.md:72)
- Goal: a known list of what is in and what is out.
- Commands:
  ```bash
  cd /home/claude/baton
  /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python -m pytest checks/locked -q -p no:cacheprovider
  ```
  (the loop's own check command, loop/config.json `check_command`)
- Done when: the pass/fail count is written down; every red feature is either hidden on the site or listed under "We knowingly do not".
- Agent prompt:
  > List which features are green (locked checks passing) and which are not. For each red one, name the page section or README claim that must be hidden or removed. Do not change code.

## 15:30–16:00 — Freeze checklist A (4_ACCEPTANCE §1), then tag
- Commands (author's laptop, repo clean):
  ```bash
  git status --short                     # must print nothing
  git tag -a v-freeze -m "Graph Hacks freeze, 16:00 IST 18 Oct"
  git push origin v-freeze
  git ls-remote --tags origin v-freeze   # must print one line
  ```
- Done when: the tag is on GitHub. Never delete or move it.

## 16:00 — Deploy the tag
- Follow M11 3_STEPS step 7. Then:
  ```bash
  curl -s "https://<project>.vercel.app/api/demo?seed=7" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['leaver_name'],d['leave_at'],[len(d['lanes'][l]['failures']) for l in 'WRG'],len(d['unpromoted']),d['live_hash_before']==d['live_hash_after'])"
  ```
- Done when: the line is pasted into a shared note. **These are the only numbers allowed in the video and README.**

## 16:00–18:00 — Video (teammate)
1. Write the six [ ] values into the beat script (M12 2_CONTRACT §2) from the 16:00 note.
2. Record each beat separately from the live URL, two takes each (scratchpad/book/BATON_FINAL_PLAN.md:190). Browser at 1280×800 or larger, page zoom 100 %, notifications off.
3. Beat 5 terminal part on the EC2 box:
   ```bash
   sudo docker compose stop falkordb
   curl -s -w "\n%{http_code}\n" "localhost:8000/api/demo?seed=7"   # shows "FalkorDB is not reachable" and 503
   sudo docker compose start falkordb
   curl -s -o /dev/null -w "%{http_code}\n" "localhost:8000/api/demo?seed=7"   # 200 again
   ```
4. Edit to ≤ 2:45; add captions; final slate: "AI coding assistants used; see README". Upload unlisted. Open the link in a logged-out window.
- Done when: video ≤ 2:45, plays logged out. By 18:00 or cut the 60 s hero-only version (beats 1, 3, 5; docs/BUILD_PLAN.md:74).

## 17:00–18:00 — README top (author)
- Paste M12 2_CONTRACT §3, §4, §5 into `README.md`; fill every [ ] from the 16:00 note; paste the queries from the frozen files (do not retype them).
- README is a mutable path for the loop (loop/config.json `mutable_paths`), but after the tag only fix text; commit on `main`. The tag stays where it is; the README on `main` may be newer than the tag — say so in one line ("Code frozen at v-freeze; README edited after").
- Done when: `grep -n "\[" README.md` shows no unfilled brackets; `grep -niE "slack|okta|jira|gitea|predicts|autopilot|production-ready|mvcc|guaranteed" README.md` shows only the "We knowingly do not" line.

## 18:30 — Placeholder submission (teammate)
- Fill the form with: repo URL, live URL, video link (or "uploading"), tracks **Track 3 and Track 1**, AI use disclosed (link to README section). If the form cannot be edited later, wait for 21:00 instead (scratchpad/book/BATON_FINAL_PLAN.md:192: "if the form allows edits").
- Done when: a confirmation screen or email exists; screenshot it.

## 18:00–19:30 — Claims check and Q&A drill (both)
- Each person reads the other's README and video script cold. Every number must match the 16:00 note; every claim must point to a file, a check or the live URL. Delete any claim that does not.
- Drill the questions in 4_ACCEPTANCE §3 out loud, 30 seconds each.
- Agent prompt:
  > Read README.md and docs/modules/M12_ship/2_CONTRACT.md §2. For every sentence that states a fact or number, give the file:line, check name or command that proves it, or write UNSOURCED. Do not edit files.

## 20:30 — Clean clone by the non-author, from the README alone
- Fresh machine or fresh directory; only the README open.
  ```bash
  git clone https://github.com/<org>/baton.git baton-clean && cd baton-clean
  git checkout v-freeze
  docker compose up -d --build
  curl -s localhost:8000/api/health; echo
  curl -s "localhost:8000/api/demo?seed=7" | head -c 300; echo
  docker compose down
  ```
- Running the locked checks on another machine needs a FalkorDB v4.22.1 module and a redis-server: set `BATON_TEST_REDIS` and `BATON_TEST_MODULE` (checks/locked/rehearsal_core/conftest.py:10-11); otherwise they point at this sandbox's scratchpad paths. Say this in the README setup if you tell judges to run the checks.
- Done when: both curls succeed using only README instructions. If anything fails: fix the README text only, or `git checkout v-freeze` again; no patching code forward (docs/BUILD_PLAN.md:76).

## 21:00 — Pre-submit checklist B (4_ACCEPTANCE §2), then submit
- Done when: the form is submitted with Track 3 and Track 1 named, and the confirmation is screenshotted. 21:00–23:59 is an untouched buffer (scratchpad/book/BATON_FINAL_PLAN.md:197).
