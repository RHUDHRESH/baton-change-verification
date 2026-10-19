# Goal agent checkpoint: full harness validation

On 2026-10-19 at 02:48:59 UTC, the complete Docker harness passed against an
isolated, clean checkout of commit
`b28d376f0feaad2fa33235134a351f9ff9fe70a5` (tree
`fddf0aef1197602737a230938652529c393e7546`). The mutable development checkout was
not mounted into the checks container.

```text
docker compose --profile checks run --rm --build checks
```

The command runs the unchanged original scoring suite and every pytest group in
`scripts/check_all.py`. All ten commands exited zero.

| Suite | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Original scoring | 88 / 88 | 0 / 0 / 0 |
| Foundation | 22 | 0 / 0 / 0 |
| Transport integration | 39 | 0 / 0 / 0 |
| Red team | 23 | 0 / 0 / 0 |
| Cloud contracts | 170 | 0 / 0 / 0 |
| Execution contracts | 123 | 0 / 0 / 0 |
| Autonomous contracts | 245 | 0 / 0 / 0 |
| Autonomous release contracts | 29 | 0 / 0 / 0 |
| Merged change release contracts | 313 | 0 / 0 / 0 |
| Goal agent contracts | 140 | 0 / 0 / 0 |
| **Pytest total** | **1,104** | **0 / 0 / 0** |

All 456 tracked file hashes matched the pre-run snapshot afterward, and the
checkout remained clean. The retained 8,034-byte log has SHA-256
`0fc9be61bcc6af1ec8ebaed3ab202a64ecdf9b817c9e5822f310b6424e3f1287`.

Local proof records are `artifacts/release-b28d376-results.json`,
`artifacts/release-b28d376-code-hashes.json`,
`artifacts/check-run-release-b28d376.json`,
`artifacts/check-all-release-b28d376.log`, and the nine JUnit reports in
`artifacts/release-b28d376-xml/`. Historical checkpoint records were preserved.

This validates implementation contracts, real isolated graph operations, UI
rendering, and the existing integration/security suites. Mocked model and
provider responses establish validation behavior only. This harness is not
evidence that a production goal called Groq, generated a materially different
plan, executed an effect, or received an independent provider read-back. Those
claims require separately captured live goal IDs and actual receipts, as defined
in [the goal agent contract](../GOAL_AGENT_CONTRACT.md#required-proof).

## Independent public deployment observation

At 02:51:19.869 UTC on the same day, a fresh anonymous browser observed the
[main app](https://baton-workspace.vercel.app/). The HTML, goal JavaScript and
CSS, shared public JavaScript, and release JavaScript and CSS all returned
HTTP 200 and matched the exact Git blob bytes at this checkpoint. The browser
blocked non-read requests; none were attempted. No page errors, failed requests
or horizontal overflow were observed at 1440 × 1000 and 390 × 844 viewports.
All anonymous action controls were disabled.

That observation pinned goal `1da09ee89ba82246d3e3552cfa031f81`, revision 0,
in `needs_continuation`: no proposal, nine stored events, three model-provider
receipts, no source evidence and no action receipts. The UI displayed those
counts without synthesizing a plan or a successful outcome. This describes
that response; it does not assert that the global latest pointer stayed fixed
while the operator continued working.

Exact asset digests and observed UI facts are retained in
`artifacts/prod-goal-b28-readonly-proof.json`. Desktop, stored-goal and mobile
screenshots are in `output/playwright/prod-goal-b28-*.png`. This read-only proof
does not establish the live planning/action requirements above.
