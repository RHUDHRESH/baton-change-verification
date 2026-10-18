# rehearsal_core: GREEN & wired (3 of 12 rounds, 32/32 checks)

**Integrity:** `git diff --stat <lock commit 1700334> -- checks/locked loop/bin` is empty. Checks were approved by Rhudhresh before any code, locked, and never edited.

**What was built (plain words):** a seeded fake company (schedules only, never failures); a loader into FalkorDB with time-valid edges; a Rehearsal that copies the graph, gates AI beliefs in Cypher (≥2 sources of ≥2 kinds), removes the leaver, and checks every scheduled event for 30 days in three lanes; a handover where a database UNIQUE constraint allows one successor per duty and a guarded write refuses anyone who has left; and `demo`, which runs it all.

| Round | Hypothesis | Result |
|---|---|---|
| 1 | skeleton + generator | keep, +9 (9/9 predicted) |
| 2 | load + rehearse engine | keep, +19 (19/19 predicted) |
| 3 | handover + demo | keep, +4 (4/4 predicted) |

No reverts. Prediction accuracy 32/32.

**Go and see (facts):**
- `python -m baton demo --seed 7 --offline` → W 6, R 7, G 37 failing events; 4 beliefs refused with reasons; after handover 0; live hash identical before/after.
- FalkorDB stopped → "FalkorDB is not reachable at localhost:6311" and exit code 3.
- The API (`uvicorn server.app:app`) answers `/api/health`, `/api/demo?seed=7` (failures enriched with source text) and `/api/handover` (accepted + remaining failures) against a real FalkorDB.

**Interpretations:**
- G=37 counts *events*. The daily warehouse job alone is 29 of them. The story and the UI should count **duties** (W 3, R 4, G 6 distinct duties on seed 7) and show events on the timeline.

**After-action review:**
- *Intended:* 32/32 by 13:30.
- *Happened:* 32/32 at about 12:05.
- *Why:* the locked independent checker made the target unambiguous, and the builders verified against it before committing.
- *Next time:* tell builders up front that `fixtures/` may not exist.

**Next features:** ask (approved, lock now), extract plus lane A, cut plus write, eval.
