# Addendum: real-model runs (predictions 6–9). Scored 18 Oct 2026, about 13:30 IST

These runs used **Claude Haiku as a subagent inside Claude Code** (the build harness), not through the API, so there is no token accounting. Small samples; read these as signals, not as a benchmark.

## AI alone (lane A): one model reads the whole raw company, no code, no graph
The model got the same `world.json` the other lanes load, minus the answer key, which was moved out of the folder before each run. It read the file in pages with no tools that filter or compute. It answered which scheduled events will have nobody able to act after the leaver goes, and who owns each duty. Scoring is done by `eval/lane_a_score.py` against the independent reference. Raw answers are in `eval/results/lane_a_runs/`.

| Company (sealed seed) | Size | Recall | Precision | False ownership claim adopted |
|---|---|---|---|---|
| 2000 | ×1 | **0%** | n/a (0 answered correctly) | yes: listed Emeka Lund as owner of billing-reconcile from one "I think" chat line (it noted "unconfirmed") |
| 2001 | ×1 | 21% | 100% | no |
| 2002 | ×1 | 93% | 100% | no |
| 2003 | ×1 | 95% | 100% | no |
| 2000 | ×8 | **6%** | 100% | no |
| 2001 | ×8 | 83% | 100% | yes: Rafael Kowalski for a warehouse-snapshot job |
| (dev) 7 | ×1 | 95% (36/38) | 97% | no |

Baton on the same companies matched the independent reference exactly: 100% recall and 100% precision. Its answers are the same every run, and every red item cites its sources.

**What this shows:** the AI-alone lane is **unreliable rather than uniformly bad**. On two of five sealed scale-1 companies it does about as well as Baton. On the others it misses almost everything. In one case it read "can do the job" records as ownership and concluded nothing would break. A reader can't tell which kind of run they got. And every question costs a full re-read (see `report.md`: about 5,500 tokens at ×1, about 59,000 at ×8, estimated).

## Gate on real extractions (Claude Haiku extractions committed in `fixtures/extract_cache/`)
`eval/extraction.py` covers 4 companies (7, 101, 202, 303). **These are development seeds, not the sealed set.**
- 11 of 11 planted hidden duties were found by the model, and all 11 were promoted by the gate.
- 12 weak claims (one source, hedged, or same-kind sources) were all refused. False promotions: **0**.

## Predictions 6–9 (text unchanged from `eval/PREDICTIONS.md`)
| # | Prediction | P | Result |
|---|---|---|---|
| 6 | At scale 8, an AI-alone run that reads the whole world in a single prompt with no tools has recall below 0.80 | 0.60 | **HIT, weakly.** Mean recall 0.45 over n=2 (6% and 83%). Not a single prompt: the model paged through the file with the Read tool, no code. |
| 7 | Across 4 seeds at scale 1, the AI-alone lane adopts at least one planted false ownership claim | 0.40 | **HIT.** 1 of 4 (seed 2000), with the model's own "unconfirmed" note. |
| 8 | With LLM-extracted beliefs, the gate promotes at least 80% of the planted true duties the extractor found | 0.70 | **HIT.** 11/11, development seeds. |
| 9 | With LLM-extracted beliefs, the gate promotes 0 planted noise claims | 0.85 | **HIT.** 0 promoted. |

**All 9 predictions hit.** Being right 9 times out of 9 at these confidence levels suggests we were under-confident, or that the predictions were too easy. Treat the small-n items (6–9) as provisional until the team's GPT run repeats them.
