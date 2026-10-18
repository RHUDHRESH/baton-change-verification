# program.md - baton

This is the operating manual for the loop, written in plain English like Karpathy's `program.md`.
Every builder reads it at the start of every round. It has two halves with different owners:

- **FIXED RULES** belong to the human. Their hash is locked in `checks/locked/MANIFEST.json`;
  if they change, the loop refuses to score.
- **HOW TO WORK** belongs to the loop. The auto-loop rewrites it between features, using evidence from
  `loop/results.tsv`. It can improve *how the builder works*. It can never touch the judge.

<!-- FIXED:BEGIN -->
## FIXED RULES

1. **The score is the number of locked checks passing.** Get it with `python3 loop/bin/run_checks.py`.
   Nothing else counts: not your own opinion, not "it looks right", not a demo that you wrote yourself.
2. **You may change only:** `baton`, `fixtures`, `eval`, `Makefile`, `README.md`
   Everything else is read-only: `checks/locked/**`, `loop/bin/**`, `.claude/settings.json`, and this
   FIXED section. The judge must stay outside the thing being judged, otherwise the easiest way to
   "improve" the score is to move the goalposts.
3. **Never edit, delete, skip, xfail, weaken or route around a locked check.** If you believe a check is
   wrong, write `loop/disputes/<check>.md` (what it asserts, why that is wrong, evidence) and keep working on
   everything else. A human decides disputes. You do not.
4. **One round = one hypothesis = one commit.** Before touching code, write the prediction into the round
   file: "I expect <named checks> to flip to passing because <mechanism>". A result with no prior prediction
   teaches nothing (every outcome looks like success).
5. **Keep a round only if** more checks pass AND no previously-passing check now fails. Equal score with
   less code is also a keep. Anything else is reverted, no matter how clever the change was.
6. **Green is not done.** Done = all locked checks pass AND the feature is reachable from the real entrypoint
   (UI route, CLI command, API endpoint) AND you have run the real app and watched the feature work
   (go and see; record facts separately from interpretations).
7. **Stop conditions are written down in advance:** stop after 12 rounds on a feature, or after
   3 consecutive rounds with no new passing check. Then write `loop/reports/<feature>-blocked.md`
   (what you tried, what the failing checks have in common, your best theory of the cause, what you'd try
   next). A clean, honest stop is a good outcome. Extending the budget to "just try a few more" is not allowed.
8. **Tag every revert** with a short cause tag (wiring-gap, regression, spec-misread, edge-case, persistence,
   shared-code-drift, invariant, integration, perf, flaky-env, scope-creep, check-dispute, other). The
   auto-loop learns only from what is logged.
9. **Do not pause to ask whether to continue** while within budget. Do stop and ask for: an irreversible
   action, a check dispute you cannot work around, or anything outside the mutable paths.
10. **No secrets in logs or commits. No destructive commands outside the mutable paths.**
<!-- FIXED:END -->

<!-- METHOD:BEGIN version=2 -->
## HOW TO WORK  (method v1 - seeded; the auto-loop revises this between features)

### Each round
1. Read the failing checks (`loop/last_score.json`), the feature entry in `loop/features.md`, the project-context
   skill, and the last few rows of `loop/results.tsv` for this feature. Do not repeat a hypothesis that
   already failed; read *why* it failed.
2. Pick the failing check(s) closest to flipping. Form ONE hypothesis. Write the prediction.
3. Make the smallest change that tests it. Prefer deleting or simplifying over adding.
4. Commit. Run the score. Let `decide.py` judge. Revert (and clean new files) if it says revert.
5. Log the round with `log_round.py` including the tag and what you learned about the *mechanism*, not just
   whether it worked.

### Habits (each one earned by evidence; format matters, a script reads it)
- H1 (tag: wiring-gap, since v1, evidence: seed): Connect the feature to the app in the same round that makes its
  checks pass: the route, form, menu entry or call site a real user or caller goes through. Passing checks on code
  nothing calls is not a feature.
- H2 (tag: shared-code-drift, since v1, evidence: seed): Before changing a shared rule or format, search for every
  place the app already does that job and make each follow the new rule in the same round. Old code that still reads
  the old format is a bug waiting for a user.
- H3 (tag: invariant, since v1, evidence: seed): When a feature splits, shares or allocates something, state the
  invariant in one line first (e.g. "shares sum to the total") and test it on awkward inputs (3-way split of 100).
- H4 (tag: persistence, since v1, evidence: seed): If the feature stores state, restart the process and confirm the
  state is still there. A passing in-memory test says nothing about a database that nothing writes to.
<!-- METHOD:END -->
