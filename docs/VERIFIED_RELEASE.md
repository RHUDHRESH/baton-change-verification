# Verified release: public issue to evidenced follow-through

**Application verification: 437 passing checks across the recorded run and corrected reruns. The promoted production URL passed asset, evidence, execution, graph, task, stored-agent and fresh Groq response verification.** The fresh request was made once by the parent operator; the independent release verifier used GET requests only. This is not a claim that the first full test invocation was entirely green.

Baton helps an operator turn a public FalkorDB issue into a source-backed verification task, review its reasoning, publish approved work to the operator's Jira/Slack, and retain separate execution evidence. The graph connects **source → investigation → local task → execution receipt/checks → external artifact** so a reviewer can inspect how the work and its proof relate. Recorded contributor activity does not establish employment or internal ownership; Jira KAN and Raptorflow Slack are the operator's connected workspaces.

## Application test results

The following counts were parsed from the saved reports on 2026-10-18. All selected final reports have zero failures, errors, or skipped tests.

| Coverage | Passing | Recorded result |
| --- | ---: | --- |
| Original locked checks | 88 | `loop/last_score.json`: integrity `ok`, 88/88, zero skips counted as failures, exit 0; 76.8 seconds |
| Foundation | 22 | `artifacts/foundation-tests.xml` |
| Whole HTTP/MCP/security integration suite, final rerun | 39 | `artifacts/transport-final-tests.xml` |
| Red-team regressions | 23 | `artifacts/redteam-tests.xml` |
| Cloud, graph-agent, company-context and provider contracts | 142 | `artifacts/cloud-contract-tests.xml` |
| Execution import, runner, completion and live-verification contracts, final rerun | 123 | `artifacts/execution-final-contract-tests.xml` |
| **Current verified coverage** | **437** | **88 + 22 + 39 + 23 + 142 + 123** |

The reports above and `artifacts/check-run.json` are generated local run artifacts, outside the committed evidence package. The [test runner](../scripts/check_all.py) records its constituent commands. Provider contract tests include mocked traffic and fault injection; these counts do not represent 437 live model calls or provider operations.

The original full run had **one integration failure**: a homepage assertion still expected `PUBLIC COMPANY WORKSPACE` after the page became a public engineering workboard. The actual company, citation, route and sandbox assertions had passed. The [integration test](../tests/integration/test_company.py) retained all those checks and replaced the obsolete label assertion with the current purpose headline, the execution section, and the explicit distinction between recorded Codex execution and automatically launching a Rust build. Its focused rerun passed, then the **entire 39-test integration suite passed**. No check was skipped or marked expected-failure. The initial `transport-tests.xml` and `check-run.json` retain the first failure rather than rewriting that history.

## Original judge integrity

The original [locked manifest, version 9](../checks/locked/MANIFEST.json), [scoring runner](../loop/bin/run_checks.py), and [integrity verifier](../loop/bin/verify_locked.py) were unchanged. The full run's score reports `integrity: ok`; a subsequent read-only verifier run in the Linux Docker checks image confirmed that locked checks, harness tools, and the FIXED rules match the manifest. Independent byte verification also matched **22 locked files and nine harness files**. The working-tree diff for `checks/locked`, `loop/bin`, and `program.md` was empty.

The verification environment was the Docker checks image. A native Windows invocation of the original verifier produces inventory false alarms from backslash-relative paths; it is not the scored environment, and the judge was not changed to suppress that portability issue.

## Separate upstream Rust verification

These results are separate from the 437 application checks. **Codex ran them in an isolated Docker runner; Groq and Lambda did not execute the Rust checks.** The complete [KAN-2 report](evidence/KAN-2.md), [audited manifest](evidence/execution.json), [raw logs and hashes](evidence/kan2-logs/), and [reproduction fixtures](evidence/kan2-fixtures/README.md) retain the inputs and outcomes.

- Pinned FalkorDB source: `d8190da5a99b4207e847e2fa2547911d96bd9e61`.
- Initial unpatched graph library: **529 passed, one failed, 17 ignored**. The constructor failure remains in the evidence.
- With the separately disclosed local clamp workaround: **530 passed, zero failed, 17 ignored**. The 17 upstream opt-in benchmark/probe cases were not run and are not counted as passed.
- **Eight targeted positive checks** passed across debug/release head and restored-head runs. **Four controlled parent-behavior checks failed as expected**, each executing one test and reproducing the relevant invariant violation.
- **Two actual RDB reloads** preserved nodes `[[0, 0], [1, 1]]` and parallel-edge rows `[[0, 1, 0, "first"], [0, 1, 1, "second"]]`, with edge count two.
- All **957 tracked source blobs** matched the pinned source after both patches were removed.

The controlled baseline retains the head's tests/accessors and restores the parent's shrink-and-prune behavior. The parent already pruned `me`; this is not a reproduction of the original orphaned-edge implementation. The clamp workaround was isolated to the test workspace and is not an upstream merge. Real RDB checks demonstrate persistence of the recorded graph contents, not direct observation of internal matrix dimensions. No SOTA result, guaranteed ROI, or new throughput, latency, memory, or exponential speedup is established here.

## Release deployment and live read-back

Read-only HTTPS verification of the **main production URL**, not a preview, passed at **2026-10-18 16:03:53 UTC**. The local verifier used eight concurrent GET workers and no login, writes, model calls or provider operations. Its sanitized output is `artifacts/public-release-verification.json`; its reproducible script is `artifacts/verify_public_release.py`.

| Release proof | Status / value |
| --- | --- |
| Promoted frontend source commit | `1c137fb8c01180a8e32ab87ceca91e34a85d41f2` |
| Production frontend / deployment | [baton-workspace.vercel.app](https://baton-workspace.vercel.app), `dpl_4k16J6uqwY5Yvus7NA8HsBDvAoYS`; deployment identifiers supplied by the parent operator, asset bytes independently verified |
| Production static assets | Main HTML, `public.js`, `company.js`, and `public.css` matched staged bytes exactly |
| Public evidence bytes | Manifest SHA-256 `19fd8fbf48e238480400d31e215d13d2b22bf681edbb417137f7a8ab0477bb85`; all 19 published raw log/evidence files matched local `SHA256SUMS` |
| Lambda artifact / revision | Parent management-plane read-back: code SHA `wIxxBE92pIdzcFm+80zObK8nha6XiIKaPIp9caw9/iA=`, revision `aa4914b0-9b2d-4194-b4ef-f00f47a89ce1`; successful production API reads independently verified |
| Public execution API | [GET executions](https://baton-workspace.vercel.app/api/public/executions): one receipt, 20 check records, canonical full public receipt/check digests verified, task status `done` |
| Actual source graph / snapshot | `baton_public_falkordb_a497740dd9c5359440cd4a7f` / `a497740dd9c5359440cd4a7f` |
| Graph relationships | Exact receipt/check IDs; `HAS_EXECUTION=1`, `VALIDATES=1`, `HAS_CHECK=20`; matching LocalTask node and task record both `done` |
| Stored investigation | [Agent c108922…](https://baton-workspace.vercel.app/api/public/agent/c108922c16a39ceaa82623d5748c4df0): `succeeded`, four tool calls, four stored model receipts, cited source metadata and captured payload hash matched |
| Main browser review | Parent observed the execution card's 530/0/17 counts, two reloads, task Done and Jira/Slack links; local screenshot `artifacts/baton-main-execution.jpg` captured at 16:00:41 UTC |
| Fresh Groq inference for this release | Run `8fc1217e06fd8666373389a8433865cd`, `succeeded`, model `openai/gpt-oss-20b`, `cached=false`; 1,254 input / 269 output tokens; response `chatcmpl-319c3f44-18b0-4aa6-9299-8a092d2cc204` matched the parent's actual request and public API read-back |

The fresh response's input SHA-256 is `084f50388f343cb6afe0203645c7875cd321baf5513bef5ac95e81a288aa1748`; output SHA-256 is `3fbdffac92ba5b450876da3cfd94fef813e8b09b0133f01740da86dad575a941`. The verifier recomputed the latter from the returned raw output and checked the parsed output, source citation, provider receipt and token counts. The public graph independently contained the matching `InferenceRun`, six `AIClaim` nodes, and six `PRODUCED` links. The parent's separate direct Cloud FalkorDB read also verified six `CITES` relationships to `src-c21f9fc95e68bcb0`; source nodes and those links are intentionally excluded from the public graph view, so the HTTP verifier does not claim to have observed them there.

The verified task is `task-agent-c108922c16a39ceaa82623d5748c4df0`, linked to public issue #3246. The earlier Jira Done, original Slack-message update, and workspace Done actions have their own [provider completion receipt](evidence/completion.json). Read-only release verification did not resend or alter those artifacts. Creating or completing workspace work does not resolve the upstream issue, and the imported public snapshot does not claim to be a complete or continuously synchronized company inventory.
