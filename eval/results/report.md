# Baton evaluation

Seeds 3000-3029 (30 companies) x scales 1, 4, 8; lanes W, R, G, A. Commit `6acd412+dirty`, 2026-10-18T07:37:42Z, 264 s.

**Beliefs: planted beliefs (the generator's answer key: true claims plus planted noise); LLM-extraction results are reported separately.** Truth = the independent reference's lane-G answer for those beliefs. Recall = share of the true failing events a lane reports; precision = share of what it reports that is true. 95% intervals: bootstrap over seeds (whole companies), method adapted from agent-memory-bench by Liz Zhang (MIT).

| Lane | What it is | Runs | Recall (95% CI) | Precision | Exact | Model tokens per question |
|---|---|---|---|---|---|---|
| W | Workflow tool: owner fields only | 90/90 | 12% (10-15%) | 100% | 100% | 0 (no model) |
| R | Baton, records only (AI switched off) | 90/90 | 28% (24-32%) | 100% | 100% | 0 (no model) |
| G | Baton: records + gated beliefs | 90/90 | 100% (100-100%) | 100% | 100% | 0 (no model) |
| A | AI alone: one model reads the whole raw company | 0/90 | not run | not run | not run | ~32,371 (estimate) |

Exact means: lane G equals the reference's G answer; lanes W and R equal the reference's answer for that same lane (they are exact about what they can see, and still miss what only G sees).

## By company size

| Lane | Scale | Recall (95% CI) | Exact | Model tokens per question |
|---|---|---|---|---|
| W | 1 | 13% (11-17%) | 100% | 0 |
| W | 4 | 12% (10-15%) | 100% | 0 |
| W | 8 | 11% (9-14%) | 100% | 0 |
| R | 1 | 20% (16-24%) | 100% | 0 |
| R | 4 | 28% (25-32%) | 100% | 0 |
| R | 8 | 35% (31-39%) | 100% | 0 |
| G | 1 | 100% (100-100%) | 100% | 0 |
| G | 4 | 100% (100-100%) | 100% | 0 |
| G | 8 | 100% (100-100%) | 100% | 0 |
| A | 1 | not run | - | ~5,546 (estimate) |
| A | 4 | not run | - | ~30,668 (estimate) |
| A | 8 | not run | - | ~60,898 (estimate) |

Slowest Baton rehearsal (lane G, CLI subprocess, including start-up): 0.84 s; largest company: 147 people, 1271 events.

## Pre-registered predictions (eval/PREDICTIONS.md)

Scored from this run only. NOT RUN means this run did not measure it; it is never dropped.

| # | Prediction | P | Result | Evidence |
|---|---|---|---|---|
| 1 | "Baton lane G matches the independent reference exactly on every seed at scales 1 and 4 (planted beliefs)" | 0.95 | **HIT** | exact on all 60 seed x scale runs |
| 2 | "Mean recall of the workflow lane W (owner fields only), measured against the G truth, is below 0.40" | 0.80 | **HIT** | mean recall 0.121 (95% CI 10-15%) |
| 3 | "Mean recall of the records-only lane R (Baton with the AI switched off) is below 0.60" | 0.75 | **HIT** | mean recall 0.278 (95% CI 24-32%) |
| 4 | "Model tokens per question for the AI-alone lane grow roughly linearly with company size: scale 8 is at least 6× scale 1" | 0.95 | **HIT** | scale-8 / scale-1 estimated tokens: min 8.6x, mean 11.1x over 30 seeds |
| 5 | "Baton spends 0 model tokens per question after the one-time extraction (by construction, listed so it is checked, not assumed)" | 0.99 | **HIT** | 270 rehearsals ran with every model key removed from the environment; tokens per question all 0 |
| 6 | "At scale 8, an AI-alone run that reads the whole world in a single prompt with no tools has recall below 0.80" | 0.60 | **NOT RUN** | needs a cached real-model AI-alone run at scale 8 |
| 7 | "Across 4 seeds at scale 1, the AI-alone lane adopts at least one planted false ownership claim" | 0.40 | **NOT RUN** | needs cached real-model AI-alone runs on 4 seeds at scale 1 (have 0) |
| 8 | "With LLM-extracted beliefs (not planted), the gate promotes at least 80% of the planted true duties the extractor found" | 0.70 | **NOT RUN** | needs LLM-extracted beliefs; this run uses planted beliefs (reported separately) |
| 9 | "With LLM-extracted beliefs, the gate promotes 0 planted noise claims" | 0.85 | **NOT RUN** | needs LLM-extracted beliefs; this run uses planted beliefs (reported separately) |
