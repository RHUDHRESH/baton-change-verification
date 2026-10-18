# Pre-registered predictions (written 18 Oct 2026, 12:32 IST, before any eval run)

Written by Claude (the build harness) for team VoltMind and committed to git before any result exists. `checks/locked/eval` verifies from git history that this file came first. Probabilities are our judgement, not data. Each prediction is scored when the eval runs, and misses are published next to hits.

**Already observed before this file, so not predictions:** on seed 7 (scale 1), an AI-alone run (Claude Haiku via the harness, reading the raw world) found 36 of the 38 failing events the reference finds. Baton with Haiku-extracted beliefs found 37 of 38.

| # | Prediction | P |
|---|---|---|
| 1 | Baton lane G matches the independent reference exactly on every seed at scales 1 and 4 (planted beliefs) | 0.95 |
| 2 | Mean recall of the workflow lane W (owner fields only), measured against the G truth, is below 0.40 | 0.80 |
| 3 | Mean recall of the records-only lane R (Baton with the AI switched off) is below 0.60 | 0.75 |
| 4 | Model tokens per question for the AI-alone lane grow roughly linearly with company size: scale 8 is at least 6× scale 1 | 0.95 |
| 5 | Baton spends 0 model tokens per question after the one-time extraction (by construction, listed so it is checked, not assumed) | 0.99 |
| 6 | At scale 8, an AI-alone run that reads the whole world in a single prompt with no tools has recall below 0.80 | 0.60 |
| 7 | Across 4 seeds at scale 1, the AI-alone lane adopts at least one planted false ownership claim | 0.40 |
| 8 | With LLM-extracted beliefs (not planted), the gate promotes at least 80% of the planted true duties the extractor found | 0.70 |
| 9 | With LLM-extracted beliefs, the gate promotes 0 planted noise claims | 0.85 |

How each is scored: `eval/run.py` writes `eval/results/` and `report.md`. Predictions 6–9 need real model runs. Any run not done by the freeze is reported as "not run", never dropped.
