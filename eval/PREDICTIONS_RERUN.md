# Fresh validation protocol — 2026-10-18

Recorded before this build's evaluation output. The supplied predictions and reports already exist as prior information, so this is a replication/validation exercise, not a claim of blind preregistration.

- Run seeds 3000–3029, scales 1, 4 and 8, lanes W/R/G/A: 360 lane records.
- Expected: lane G exact on 100% of generated companies when given planted beliefs.
- Expected: model calls/tokens for W/R/G equal 0; model keys removed by the harness.
- Expected: W mean recall below 0.40 and R below 0.60 against the independent G reference.
- Use the supplied 95% bootstrap-over-seeds method without changing the checker.
- A is reported only from exact-input cached real-model runs; missing runs remain "not run". Do not generate paid model calls or treat the scripted fake as quality evidence.
- Keep real cached extraction validation separate from planted-belief engine exactness. Source-provided Claude caches are replayed, not fresh model executions.
- Publish failures and limitations alongside successes. The supplied old scores are not the results of this rerun.
