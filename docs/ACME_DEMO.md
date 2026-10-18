# Acme company memory

Open [Acme in Baton](http://127.0.0.1:8000/amb.html), or choose **Acme company memory** in the sidebar.

This recreates the synthetic company task from [Liz Zhang's agent-memory-bench](https://github.com/zhang-liz/agent-memory-bench), using the MIT-licensed, already-vendored `amb/world.py` at b8ccc40. The demo fixes seed 7 and inbox length 50, the upstream short pilot length. It does not claim to be the same random seed as an unspecified recording. The upstream repository has since changed; this integration deliberately keeps the build pack's pinned generator.

The complete original inbox includes Slack, tickets, email, incidents and attached logs. Services, teams and people live in a separate persistent FalkorDB graph `baton_acme_amb_7_50_v2`. Ownership, dependencies, membership and pager changes carry source references and step validity intervals. Retractions close old edges; moving the slider reads the graph at that point without rewriting history. At step zero the entity catalogue is visible but no relationship facts have arrived.

This uses a **deterministic text parser** for the pinned generator's message templates and public entity aliases. The runtime does not consume event assertion/retraction metadata or the sealed final state. Ownership and pager facts replace prior values based on visible messages. It is not LLM extraction, a fresh model run, a memory-cost comparison, or evidence of model accuracy on arbitrary language. The UI labels this limitation. Answers execute parameterized read-only Cypher; upstream expected answers are consulted only afterward for scoring.

The five original question categories are available at their original checkpoints: lookup, multihop paging, transitive blast radius, changed facts and verbatim incident IDs. Source links open the relevant inbox text, and exact Cypher is inspectable. Additional fixed queries allow service ownership, team on-call, upstream paging, impact and incident lookup at the selected step.

API: `GET /api/amb?step=0..50`, `POST /api/amb/ask` with bounded tool/subject/step, and `GET /api/amb/questions/{qid}`. No raw query endpoint. Requests only initialize the fixed graph once; other Baton company graphs and handover receipts are unaffected.

Validation: `tests/integration/test_amb_demo.py` checks every parsed event against the upstream assertion/retraction metadata (only in tests), every generated benchmark question against live FalkorDB, all final-state edges against upstream state, step zero, source timing, repeatability, input bounds and injection resistance. These tests join the normal integration suite. The original generator and locked checks are unchanged.

Verified locally: all 134 normal checks pass (88 original, 22 foundation, 24 integration). Edge browser: 25/25 benchmark answers, generic query, step-zero reset, automatic inbox playback, raw source expansion, no page errors, and mobile width 390/390. Screenshots: `output/playwright/acme-desktop.png` and `acme-mobile.png`; browser runner: `scripts/verify_acme_browser.js`. The separately rerun 23 red-team scenarios reproduce the earlier report; they do not certify security.
