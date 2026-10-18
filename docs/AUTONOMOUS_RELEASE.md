# App-triggered cloud workflow release review

**Final hardened app-triggered workflow: completed and independently verified. Application checks: 716 passed, zero failures/errors/skips.** Sixth run `de223685c514b134ae8b471263f90d7a` investigated the graph, generated its own Groq edit, retained the initial library failure, reran unchanged checks, verified evidence and updated the existing Jira/Slack artifacts. Main-browser review showed all five workflow stages completed. Earlier failures remain documented below.

Baton turns a public issue into a graph-backed investigation, an isolated code-check run, a bounded model repair when an actual check fails, and evidence attached to the operator's existing Jira/Slack work. The useful chain is **public source → graph investigation → verification task → cloud run/checks → external artifact**. A saved task, model response, accepted dispatch, callback, or historical passing receipt cannot substitute for new execution proof.

## Final hardened run and independent proof

| Evidence | Verified result |
| --- | --- |
| App run | [de223685c514b134ae8b471263f90d7a](https://baton-workspace.vercel.app/api/public/workflows/de223685c514b134ae8b471263f90d7a), `completed`; recorded completion `2026-10-18 20:17:08 UTC` |
| Actual GitHub execution | [39161825805](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39161825805); `execute` and `finalization` succeeded; workflow head `1af00116c84a3195f6bf1eeba1e9ebdd2e538bb4` |
| Before / after | Initial **529 passed, 1 failed, 17 ignored** retained; after the generated edit, final library **530 passed, 0 failed, 17 ignored**; four exact debug/release targeted passes and formatting exit 0 |
| Count meaning | **534 passing test executions**, including targeted reruns; not 534 distinct tests. Seven retained check records and six final checks |
| Actual Groq generation | `openai/gpt-oss-20b`, response `chatcmpl-2b9b35c7-963b-41ff-804e-091f5a8266c1`; **4,813 input / 301 output tokens**; one applied edit generated for this run |
| Applied patch SHA-256 | `53037d17511e978a10bdcaa8ab618da110dfacc1cec7364702f66af7f87823b3` |
| Raw model-output SHA-256 | `7145c98f456f60fb06fc51ae6a4241a37b5981194148add5ae07f92e5a156e04` |
| GitHub artifact | ID `12149033898`; SHA-256 `ee18bdd49827d9ab5ead7132ea6b0024e7fec1c14ff6a453e426fc11f8357e78` |
| Public report | [Verified run evidence](https://baton-workspace.vercel.app/api/public/workflows/de223685c514b134ae8b471263f90d7a/evidence); SHA-256 `abe7ae924787842344b37e2995461500f88542ef5a685ea5b5a146ce3fdd6ce6` |
| Raw logs / protected source | All seven public raw logs verified; the applied production source and immutable test region independently reconstructed; runner inventory records 957 tracked blobs |
| Actual provider GET audit | [Jira KAN-2](https://rhudhresh3697.atlassian.net/browse/KAN-2): exact new comment `10005` and Done. [Original Slack message](https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199): exact new run block, message `1792334785.098199` in `C0CA7B1BYTT` |
| Actual graph read-only audit | `baton_public_falkordb_a497740dd9c5359440cd4a7f`: one bound run, seven checks/links and exact task/source/agent binding |
| Task read-back | `task-agent-c108922c16a39ceaa82623d5748c4df0` and new investigation task `task-agent-15f9a93aad9c81b792a4a8238019e9c1` both Done |
| Main browser | Operator observed completed investigation, execution, repair, verification and publication stages, passing counts, hypothesis label and provider links; screenshots `artifacts/baton-autonomous-main-verified.png` and `artifacts/baton-autonomous-results-verified.png` |

The generated edit is `record_cap.unwrap_or(BATCH_SIZE).clamp(1, BATCH_SIZE)` within the permitted constructor expression. It was generated through this app run, not copied from a diagnostic probe or the historical Codex workaround. **Passing checks establish observed before/after behavior, not a proven root cause.** The original guarded match already bounded the cap under ordinary Rust semantics; no unsupported model explanation is endorsed. This is not a new upstream tensor fix, merge, full release suite, RDB test or performance result.

The tracked, reviewable audit outputs are [release proof](evidence/autonomous-de223685-release-proof.json) and [direct Cloud/provider proof](evidence/autonomous-de223685-cloud-proof.json). These are actual read-only audit outputs, not cryptographic attestations from the providers. The new JSON files are repository evidence; they are not yet served as static files by the frontend. The public app receipt, report and raw-log endpoints above already serve the actual execution evidence. The first independently reread GitHub job/artifact data, public report, raw logs, stored generation/patch receipts and returned workspace graph. The second used actual provider GET requests and `GRAPH.RO_QUERY` to check the exact external artifacts and database binding. Neither audit dispatched a job or sent provider updates. The Groq API was not independently queried for historical generation content; the generation receipt and exact raw edit were matched to the app record and artifact.

## Scope and execution boundary

| Boundary | Approved scope |
| --- | --- |
| Public issue | [FalkorDB/FalkorDB#3246](https://github.com/FalkorDB/FalkorDB/issues/3246), with related public [PR #3250](https://github.com/FalkorDB/FalkorDB/pull/3250) |
| Upstream source | [Commit d8190da5a99b4207e847e2fa2547911d96bd9e61](https://github.com/FalkorDB/FalkorDB/commit/d8190da5a99b4207e847e2fa2547911d96bd9e61) |
| Build image | `ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7` |
| Executor | GitHub Actions, running a fresh isolated Docker source container; Lambda coordinates and Groq generates proposed edits |
| Editable expression | Only the pure integer/Option `let pack_ceiling` expression in `graph/src/runtime/ops/batched_result_emitter.rs`; arbitrary identifiers, strings, macros, I/O and extra statements are rejected; tests and other tracked files are protected |
| Repair limit | At most two observed-failure-driven Groq edits; no stored workaround patch is substituted |
| Destinations | Existing operator Jira `KAN-2` and original Raptorflow Slack message; these are not presented as FalkorDB internal systems |
| Explicit limits | One reviewed repository/profile; no arbitrary commands, upstream merge, complete release-mode suite, RDB reload, or new speedup/ROI claim |

The constructor file is the separately observed library failure, not a claim that it is the original tensor bug. The cloud profile must execute its own checks. A successful final library run requires 530 passed, zero failed and 17 ignored; four exact debug/release tensor/restore checks and formatting must also pass. The aggregate 534 passing **test executions** includes targeted reruns, rather than 534 distinct tests. The 17 ignored upstream benchmarks/probes remain unrun. The older [Codex Docker evidence](evidence/KAN-2.md), including its two RDB cycles, has a different executor and is not proof for any new cloud run.

The [workflow design and reproduction guide](AUTONOMOUS_WORKFLOW.md) describes the commands, protected source checks, isolated container, provenance gates, budgets and shared GitHub Actions allowance. The workbench polls every ten seconds for up to 240 reads, then pauses honestly with a manual GET refresh. Reload and polling never dispatch a new run automatically. Live callback progress and log tails are explicitly unverified until independent job, artifact, log and repair-receipt checks pass.

## Hardening identified after the fourth run started

Review found two possible false-pass paths: arbitrary generated production Rust could print a forged test summary and exit zero, and a mutable `HEAD` could undermine a source comparison that treats it as the baseline. **No exploitation of either path has been observed in the actual runs.** Unchanged test bytes alone are not sufficient to exclude these paths.

The new server guard restricts edits to the single `let pack_ceiling` integer/Option expression and rejects arbitrary identifiers, strings, macros, I/O and extra statements. Worker hardening pins the baseline to the approved commit and checks that `HEAD` has not changed. Model explanations remain unverified hypotheses; passing checks demonstrate observed before/after behavior, not the model's claimed root cause.

The fourth run uses the older `2acf3d3440fbf1084c35bd63139f08cb9c88a247` worker head. Its verified outcome cannot establish that the newer worker hardening was exercised. The sixth run supplied the required fresh successful execution after the code freeze, with the frozen 716-check application suite and independent live proof above.

## Observed production attempts

| Attempt | Recorded outcome |
| --- | --- |
| First app run `70ef58fe339ab6e347867b9a5870702a` | Verified **failure**, not a completed fix |
| Actual first GitHub run | [39157767073](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39157767073) |
| Original first-run graph library | **529 passed, 1 failed, 17 ignored; exit 101** |
| Applied first-run repairs | **0**; no new task completion was established |
| Automatic failure publication | Saved provider read-back receipts verified Jira comment `10001` and the original Slack-message failure update |
| First-run proof | Local generated `artifacts/autonomous-first-failure-proof.json`; [public workflow receipt](https://baton-workspace.vercel.app/api/public/workflows/70ef58fe339ab6e347867b9a5870702a) and [verified report](https://baton-workspace.vercel.app/api/public/workflows/70ef58fe339ab6e347867b9a5870702a/evidence) |
| Second app run `4b0dc321cde70303f194ef3c5297c8bc` | Independently read back as **failed**, with runner and check evidence verified: **529 passed, 1 failed, 17 ignored; exit 101** |
| Actual second GitHub run | [39158788905](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39158788905) |
| Second-run review | [Public receipt](https://baton-workspace.vercel.app/api/public/workflows/4b0dc321cde70303f194ef3c5297c8bc); [verified failed report](https://baton-workspace.vercel.app/api/public/workflows/4b0dc321cde70303f194ef3c5297c8bc/evidence). Zero repairs; Jira and Slack saved read-backs both verified |
| Third app run `67e71af389a6ce58d0a685cb17591b4a` | Independently read back as **failed**: runner/check evidence verified, **529 passed, 1 failed, 17 ignored; exit 101**; zero repairs |
| Actual third GitHub run | [39159597961](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39159597961), workflow head `42c8e82ae684e029fc76e3b9f3973436110426f2` |
| Third-run review | [Public receipt](https://baton-workspace.vercel.app/api/public/workflows/67e71af389a6ce58d0a685cb17591b4a); [verified failed report](https://baton-workspace.vercel.app/api/public/workflows/67e71af389a6ce58d0a685cb17591b4a/evidence). Saved Jira and Slack read-backs both verified |
| Fourth app run `d0770620a12494f31fe78cc7e1180640` | **Completed and independently verified**, with its own actual Groq edit; started `2026-10-18 19:50:10 UTC` |
| Actual fourth GitHub run | [39160583697](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39160583697), workflow head `2acf3d3440fbf1084c35bd63139f08cb9c88a247` |
| Fourth-run review | [Public receipt](https://baton-workspace.vercel.app/api/public/workflows/d0770620a12494f31fe78cc7e1180640); [verified report](https://baton-workspace.vercel.app/api/public/workflows/d0770620a12494f31fe78cc7e1180640/evidence) |
| Fifth app run `d21663169f98a1c5f999598caa6b1ce7` | **Failed before dispatch at the application quota guard**. Started `2026-10-18 20:01:26 UTC` against hardened source `6eef035aad03f8f97377246add4a375d03bc91fc`; no GitHub run ID or verified code checks |
| Sixth app run `de223685c514b134ae8b471263f90d7a` | **Completed and independently verified on the hardened head**. Started `2026-10-18 20:06:39 UTC`, with no counter reset |
| Actual sixth GitHub run | [39161825805](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39161825805), workflow head `1af00116c84a3195f6bf1eeba1e9ebdd2e538bb4` |
| Sixth-run review | [Completed public receipt](https://baton-workspace.vercel.app/api/public/workflows/de223685c514b134ae8b471263f90d7a); final hardened job/artifact, source, actual provider/graph and task audits passed |

### Fourth-run proof and limits

`artifacts/autonomous-fourth-release-proof.json` records the independent GitHub artifact, public report, raw-log and model-edit verification. `artifacts/autonomous-fourth-cloud-proof.json` records separate actual provider GET and `GRAPH.RO_QUERY` checks; neither verifier sent messages or updated state.

| Verified fourth-run evidence | Observed value |
| --- | --- |
| Execution / final checks | Seven retained check records including the initial failed library; six final checks: library 530/0/17, four exact targeted passes and formatting exit 0 |
| Test total | 534 passing test executions including the targeted reruns; no claim of 534 unique tests |
| Real Groq generation | `openai/gpt-oss-20b`, response `chatcmpl-418a82d1-763e-4efe-b477-094e19795e9d`, 4,817 input / 1,173 output tokens; one applied model edit |
| Applied patch SHA-256 | `0f4aa5aed402545d9d10c024abc1630cf64499470a72e386ee8a84e6fa24444d` |
| Artifact / report SHA-256 | Artifact `12149171193`: `c583f647e0fa3bb3779463cd6f86ece343ee969dc1665fba8a2cc373f81b2e6c`; report `1968daca2df8225bcaa2c3f37e463568db76bffdae93b55d2d2e070f12b226de` |
| Logs and source | Seven public raw logs verified; applied source and protected test-region bytes reconstructed. The runner artifact records 957 tracked blobs |
| Actual Jira read-back | Exact run comment `10004` on KAN-2 and Done state independently read |
| Actual Slack read-back | Exact new run block in original message `1792334785.098199`, channel `C0CA7B1BYTT`, independently read |
| Actual graph read-back | `baton_public_falkordb_a497740dd9c5359440cd4a7f`: one bound run, seven check nodes/links, and verified task/source/agent binding |
| Workspace tasks | Canonical task and the fourth investigation task `task-agent-7bc44458349f8ce8f63002dc59308453` read back as Done |

The edit replaces the guarded `record_cap` match with `Some(cap) => cap.min(BATCH_SIZE).max(1)` and `None => BATCH_SIZE`. Both versions already bound the cap under ordinary Rust semantics. The model's explanation that the original allowed a cap above `BATCH_SIZE` is unsupported by the original source. **Passing checks establish the observed before/after behavior, not a proven root cause.** This is not an upstream merge or a new fix of the original tensor issue. No RDB reload, full release suite or performance gain is claimed for this run.

### Fifth-attempt quota guard and next attempt

Independent [agent read-back](https://baton-workspace.vercel.app/api/public/agent/2f181ea1e86f70d9f55321e9f02e868d) records `Daily free-quota guard reached`, phase `preflight`, after three completed tools and three measured provider receipts using 2,849 tokens. The shared app brief/graph counter had reached its conservative 50-call daily limit. This was a legitimate guard failure: no source-verified task action was accepted and no GitHub execution was dispatched. It is not a code-check failure or a successful retry of the fourth run.

The sixth-run deployment raises that shared application limit to 60 daily calls while retaining the used counter and all other guards. **No app counter is reset.** The sixth fresh button attempt established its own successful receipts; the failed fifth record is retained. The earlier 711-check run predates this quota adjustment; the current completed 716-check run below includes it.

A separate actual CloudShell response-header probe returned HTTP 200 with request limit 1,000, token limit 8,000, remaining requests 995 and remaining tokens 7,178, saved in `artifacts/groq-free-quota-headers.json`. Groq documents those request headers as **requests per day** and token headers as **tokens per minute**, not tokens per day. Its published Free table also lists 200,000 tokens/day for GPT-OSS 20B; that daily token value was not measured by these headers. Limits are shared across the organization and any threshold can bind. [Official Groq rate limits and header meanings](https://console.groq.com/docs/rate-limits).

The app's 60-call guard is deliberately below the observed request allowance, not a promise of unlimited free inference, remaining token capacity, or AWS/GitHub billing protection. Diagnostic calls are not app-run repair results, and no quota or successful-generation receipt is fabricated.

The first attempt ended with a repair-callback error. Its underlying cause remains **unproven**. The second deployment reduced `max_completion_tokens` to 1200 and retained sanitized diagnostics; its actual verified report now records: `App callback returned HTTP 409: Groq repair returned HTTP 403; no substitute patch was supplied`. There is no generation receipt or patch for that attempt. This establishes an HTTP 403 response at the repair request, not why the provider rejected it.

The repair HTTP request lacked the `User-Agent` used by the working graph-agent request. A paired, read-only CloudShell models-endpoint probe observed HTTP 403 with Python's default User-Agent and HTTP 200 with `Baton-Agent/0.3`, using the same existing Lambda key and making zero inference calls. The deployed repair request then added that header. The third run reached a different error: `App callback returned HTTP 409: Groq repair returned HTTP 400; no substitute patch was supplied`. It still produced no generation receipt or patch. This is transport/request diagnostic evidence, not successful repair proof or a diagnosis of the HTTP 400 response. The corrected provider integration subsequently produced the fourth run's independently verified generation and execution described above; the earlier failed records remain unchanged. The first attempt's cause remains unproven; subsequent diagnostic probes are recorded separately below.

### Direct provider diagnostics, separate from app execution

The operator replayed the same public failure context in CloudShell to investigate the request failure. These were real diagnostic provider calls, not tests run by the app or patches supplied to a cloud run:

| Diagnostic request | Observed provider result |
| --- | --- |
| Minimal JSON prompt, 1,200 completion-token budget | HTTP 200 |
| Public failure context, `json_object`, 1,200 budget | HTTP 400, `json_validate_failed` |
| Public failure context, strict JSON schema, 1,200 budget | HTTP 400, `json_validate_failed` |
| Public failure context, strict JSON schema, 3,500 budget | HTTP 200, `finish_reason=stop`; 4,868 prompt + 1,505 completion = 6,373 total tokens; the completion included 1,264 reasoning tokens |
| Separate probe exceeding the shared token-per-minute allowance | HTTP 429; retried later |

The successful probe's output was **not used as an app model patch, execution result, or replacement receipt**. The app integration now requests strict JSON-schema output, instructs valid JSON string escaping and allows 3,500 completion tokens. These observations motivate that request configuration for this context; they do not prove a universal token threshold or a completed repair. The fourth button run subsequently generated its own measured receipt, applied its own validated edit and passed its recorded checks; it did not use the diagnostic output. The sixth run subsequently supplied the separate fresh hardened proof above.

Groq documents [structured-output modes and schema requirements](https://console.groq.com/docs/structured-outputs), [reasoning configuration](https://console.groq.com/docs/reasoning), and the [completion-token request parameter](https://console.groq.com/docs/api-reference). Those describe the API contract; the observed errors and token counts above are operator-run diagnostic evidence, not guarantees inferred from documentation.

Failure publication is useful evidence for all three attempts: [Jira KAN-2](https://rhudhresh3697.atlassian.net/browse/KAN-2) and the [original Slack message](https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199) received the failed outcome rather than an invented success. The independent HTTP failure verifier checked the app's saved provider receipts; it did not itself query or write those providers. Existing historical Done states must not be read as completion of a new run.

## Application checks and retained failures

The final frozen hardened eight-group Docker run, including the shared 60-call quota adjustment, recorded **716 passing checks**, zero failures/errors/skips and all eight commands exiting zero. This includes strict-schema/budget tests, constrained-edit adversarial checks, the pinned-HEAD regression and five additional shared-quota tests. The reports below were independently parsed from actual saved results; application test success does not establish the live cloud run outcome. These are layered application and verifier checks, not unique product scenarios, live provider operations, or Rust test counts.

| Layer | Passing checks | Report |
| --- | ---: | --- |
| Original locked judge | 88 | `loop/last_score.json`: integrity `ok`, 88/88, zero skips counted as failures; 66.1 seconds |
| Foundation | 22 | `artifacts/foundation-tests.xml` |
| HTTP/MCP/security integration | 39 | `artifacts/transport-tests.xml` |
| Red-team regressions | 23 | `artifacts/redteam-tests.xml` |
| Cloud, graph, model and provider contracts | 147 | `artifacts/cloud-contract-tests.xml` |
| Prior execution and release contracts | 123 | `artifacts/execution-contract-tests.xml` |
| **Judge, foundation, integration, security, cloud and prior execution groups** | **442** | Fresh checks-image full run |
| Autonomous worker, repair, routes, provenance, publisher and actual JavaScript UI | **245** | `artifacts/autonomous-contract-tests.xml` |
| Independent public receipt / direct-cloud verifier contracts | **29** | `artifacts/autonomous-release-contract-tests.xml` |
| **Final frozen eight-group total** | **716** | **442 + 245 + 29**, including 687 application checks and 29 verifier checks |

The final autonomous group contains publisher 31, repair 34, routes 66, worker 29, workflow provenance/completion 43 and UI 42; the verifier group contains public-release 22 and direct-cloud-verifier 7. Most provider boundaries are mocked and fault-injected. The 716 recorded checks are layered coverage, not 716 unique user scenarios, live provider calls or upstream Rust tests. They are separate from the independently verified live sixth-run result above. The previous 711-, 690- and 686-check runs, earlier 229-case group and other partial reports remain historical snapshots.

The saved final full-run log is `artifacts/check-all-autonomous-cap60.log`, 4,062 bytes, independently matched to SHA-256 `77837ee858c9b21296bcfd86378dc2345736b258b8cff90cf9958f5bc30b9e83`. `artifacts/check-run.json` contains eight zero exit codes; the locked score records integrity `ok` and 88 passes. The other seven JUnit reports contain 628 passing cases and no failures, errors or skips.

The first fresh `check_all` invocation retained **one stale UI assertion failure**: implementation polling had been extended to 240 reads while the collected test still expected 90. `artifacts/check-all-autonomous-repro.log` retains its actual 203-pass/1-fail outcome. The test now verifies 240 GET-only reads with ten-second delays, honest pause/no fabricated failure, and no repeated POST; the corrected final Docker group passed. No assertion was skipped or marked expected-failure. Earlier exploratory combined-suite host/event-loop isolation failures are retained in `artifacts/autonomous-release-regressions.xml`; the corrected isolated integration, red-team, cloud and autonomous reruns passed, with no production host checks weakened.

The original judge and harness were not edited. A read-only Linux Docker invocation of `loop/bin/verify_locked.py` confirmed that locked checks, loop tools and FIXED rules match the manifest. Native Windows path-separator inventory false alarms are not the scored environment and were not suppressed by changing the judge.

## Verified deployment and reproduction

| Deployment | Operator-reported management-plane identity |
| --- | --- |
| Main workbench | [baton-workspace.vercel.app](https://baton-workspace.vercel.app/#workflow-runner) |
| Current frontend source | `6eef035aad03f8f97377246add4a375d03bc91fc` |
| Current frontend deployment | `dpl_6de1MEA9z8kxWNbB1aGLJJzyQeaE`; main alias ready, hypothesis label observed by the operator |
| Hardened backend / worker source | `1af00116c84a3195f6bf1eeba1e9ebdd2e538bb4` |
| Lambda code SHA-256 | `eN99N58ThP+P9FjqVkUtRyHuu1WgHzVG8lw9uj7P864=` |
| Lambda revision | `93ff9a45-c86b-463f-8971-ec037d6cdf5b` |
| Updated archive | 4,480,888 bytes; environment preserved; no new cloud resources |

The deployment table records the frozen hardened source used by the successful sixth run. The fourth run's older source and the fifth attempt's legitimate quota failure remain separate history. The shared 60-call adjustment retained its used counter and passed the frozen suite; final sixth-run job/artifact, source, provider, graph, task and main-browser proof are complete.

Reproduce application checks and the independent release audit:

```text
docker compose --profile checks build checks
docker compose --profile checks run --rm checks
python scripts/verify_autonomous_release.py --run-id de223685c514b134ae8b471263f90d7a --output artifacts/autonomous-hardened-release-proof.json
```

The release verifier uses the existing local Git credential manager for private GitHub GET requests and never prints the credential. The separate CloudShell audit used [verify_autonomous_cloud.py](../deploy/verify_autonomous_cloud.py) with `--run-id`, an approved dependency archive and its exact SHA-256, and `--output artifacts/autonomous-hardened-cloud-proof.json`. It reads the existing Lambda configuration in memory and issues provider GET / graph read-only queries. Its archive/hash arguments depend on the actual reviewed archive; a different archive must not be substituted. GitHub artifacts have a one-day retention policy, while the verified app report/log endpoints preserve the copied evidence.

### Main-origin audits and browser proof

At `2026-10-18 20:11:13 UTC`, GET-only verification of the main URL returned HTTP 200 for the HTML, `workflows.js`, `public.js`, `company.js` and `public.css`; all five matched their staged/local bytes. HTML and the two workflow/public scripts also matched commit `6eef035` byte-for-byte. `company.js` and `public.css` were staged with CRLF while Git stores LF: they match the commit after line-ending normalization, not as exact Git bytes. The deployed `workflows.js` SHA-256 is `519fc51c805faaaf5e26c56571268d7fa84c212450734d19233dd32c3ccb23fe`, with the hypothesis label and 240-by-ten-second polling present.

The same-origin API returned `no-store`, latest run `de223685c514b134ae8b471263f90d7a`, GitHub `39161825805`, head `1af00116c84a3195f6bf1eeba1e9ebdd2e538bb4`, active `graph_library_initial`, and `checks.verified=false`. Evaluating the actual deployed script's review-state function against that receipt returned `completed=false`, with check/publication verification false. That was an interim API/script audit, not terminal proof; its sanitized output is `artifacts/autonomous-sixth-ui-readonly-audit.json`.

At `2026-10-18 20:19:40 UTC`, a subsequent independent GET returned `completed`, all five stages completed, checks 534/0/17 verified and both destinations verified. The actual deployed script returned `completed=true`, `checksVerified=true` and `publicationVerified=true`; this matches the separate completed main-browser review. The sanitized script/API audit is `artifacts/autonomous-hardened-ui-readonly-audit.json`.

The operator separately read the actual shared inference counter as 54 after the prior 50 and four new graph-agent calls. This preserves the used count across the cap change; no counter was reset. Read-only asset/receipt auditing itself made no login, dispatch, provider-write or model calls.

## Credential handling incident

A troubleshooting command inadvertently echoed a credential into captured tool output. Terminal history and visible output were cleared, and the temporary ignored credential file was deleted. **Previously captured tool output cannot be recalled**; no credential value is reproduced here. These cleanup steps do not revoke the credential. Rotation is recommended and is **not recorded as completed**. This incident must not be described as erased or resolved by rotation.
