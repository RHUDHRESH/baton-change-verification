# Status at ZIP time (12:44 IST, 18 Oct). Code: repo_snapshot/ = main @ 980c2e2

- **Build loop:** 88/88 locked checks green, 10 rounds, 0 reverts. Integrity verified. See `LOOP_SUMMARY.md`.
- **Evidence:** `EVAL_REPORT.md` (sealed seeds 2000-2029 × sizes 1/4/8, 360 runs) and `EVAL_ADDENDUM_real_models.md` (real-model AI-alone runs + extraction gate). All 9 pre-registered predictions hit, with stated caveats.
- **Headline numbers:**
  - Workflow lane finds 14% of what breaks; Baton with the AI off finds 30%; Baton finds 100%, exact against the independent reference on all 90 runs.
  - AI alone: 0–95% depending on the run, adopted a false owner in 2 of 6 runs, and costs about 5.5k–59k tokens per question. Baton: 0 tokens per question.
- **Seen running:** API on 4 companies (#7, #101, #202, #303) with real Claude Haiku extraction caches. Endpoints: `/api/health`, demo, ask, cut, commit, handover, catalogue.
- **Docs:** `modules/` (12 × 4 docs + ground truth + index). Docs were written 11:45–12:50; later rounds moved some line numbers, so search for the quoted text if a citation is off. `modules/M10_web/samples/` = real API responses for your frontend build.
- **Your team's next steps:**
  1. Build the frontend from M10.
  2. Deploy with M11: EC2 Elastic IP + Vercel.
  3. Run the GPT extraction and AI-alone lane with your key (M05, M07).
  4. Ship with M12: video, README, submit to Track 3 + Track 1 by 21:00.
