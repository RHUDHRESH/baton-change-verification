# Loop summary (18 Oct 2026, about 13:35 IST)

**Outcome:** GREEN and wired. 88 of 88 locked checks pass across 6 features and 3 approved ratchets. 10 rounds, 0 reverts. Every check list was approved by the human before any code was written. `git diff --stat <last lock> -- checks/locked loop/bin` is empty.

| Feature | Checks | Rounds | Wired | Seen running |
|---|---|---|---|---|
| rehearsal_core (+ gate relevance) | 36 | 4 | CLI, /api/demo | demo on 4 companies; live hash unchanged |
| ask (+ who-owns, names) | 17 | 2 | CLI, /api/ask | owes / why / breaks / who_owns / none |
| ai_layer | 7 | 1 | CLI | offline replay, amb import |
| cut | 17 | 1 | CLI, /api/cut | IMPOSSIBLE 4/7 on #101 |
| commit_write | 5 | 1 | CLI, /api/commit | live graph + git commit + read-back |
| eval | 6 | 1 | `python -m eval.run` | sealed run committed after the predictions |

**After-action review**
- *Intended:* a working, honest Track 3 product with measured evidence by about 15:45.
- *What happened:* done by about 13:35. Going to look for ourselves caught three things the checks did not:
  - the who-owns gap;
  - the gate could be padded with an unrelated source;
  - the extraction prompt leaked the generator's due time.

  Each became an approved check or fix. The AI-alone comparison disproved our original "AI gets it wrong" story, and we pivoted to measured claims.
- *Why it went well:* locked independent references (oracle, flow reference) made every target unambiguous, and builders verified against them before committing.
- *Next time:* write exact check ids into `--predicted`, as habit H5 in method v2. Freeze the generator earlier, because cache keys depend on it.

**Method change (outer loop):** v1 → v2 adds H5. The judge is untouched.
