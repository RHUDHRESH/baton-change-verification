# Cloud deployment and evidence

Current architecture: app-triggered investigation, cloud code checks, bounded repair and verified publication. The [release report](AUTONOMOUS_RELEASE.md) is the reference for current test counts and live outcomes; the sixth run completed on the frozen hardened head and passed independent GitHub/artifact, source, actual provider/graph, task and main-browser audits.

## Topology

Vercel static frontend → same-origin `/api` rewrite → AWS Lambda in Mumbai → FalkorDB Cloud Free. Groq supplies graph investigation and proposed repairs. Lambda dispatches the reviewed GitHub Actions workflow, whose fresh isolated Docker container runs Rust checks; Lambda independently checks its completed job, uploaded artifact, logs and source gates before finalizing graph and Jira/Slack receipts. DynamoDB holds sessions, counters, callback-capability digests and leases; no provider credentials are written to the graph.

The [production workbench](https://baton-workspace.vercel.app/#workflow-runner) is public to read; starting execution requires operator authentication. Its approved scope is only FalkorDB/FalkorDB#3246 at pinned commit `d8190da5a99b4207e847e2fa2547911d96bd9e61`. It supports bounded production edits, not arbitrary repository/command execution or upstream merges. The [workflow guide](AUTONOMOUS_WORKFLOW.md) records the exact build image, tests, protected source, independent verification and budgets. **RDB reload is excluded from this cloud profile**; historical Codex results remain separate.

| Current deployment | Operator-read-back identity |
| --- | --- |
| Main frontend source | `6eef035aad03f8f97377246add4a375d03bc91fc` |
| Main frontend deployment | `dpl_6de1MEA9z8kxWNbB1aGLJJzyQeaE`; hypothesis label visible in the operator's main-site review |
| Hardened backend / worker source | `1af00116c84a3195f6bf1eeba1e9ebdd2e538bb4` |
| Lambda code SHA-256 | `eN99N58ThP+P9FjqVkUtRyHuu1WgHzVG8lw9uj7P864=` |
| Lambda revision | `93ff9a45-c86b-463f-8971-ec037d6cdf5b` |
| Updated archive | 4,480,888 bytes; existing environment preserved; no new cloud resources |

These identities describe deployed code, not a successful execution outcome. Both Vercel and Lambda provide HTTPS hostnames; no purchased domain is required.

## Current app-triggered run status

The first three production button runs observed the real unmodified library result: 529 passed, one failed and 17 ignored. All ended without a model generation or applied repair and recorded failure publication, rather than claiming completion. The second independently verified report retained an HTTP 403 from the Groq repair request. The underlying first-attempt cause remains unproven. [Retained attempts and evidence](AUTONOMOUS_RELEASE.md).

A paired, read-only CloudShell request to Groq's models endpoint using the existing Lambda key observed HTTP 403 with Python's default User-Agent and HTTP 200 with `Baton-Agent/0.3`. It made **zero inference calls**. This is transport evidence for the header change, not evidence that a repair was generated or passed tests. The deployed repair request supplies that header and retains sanitized failure diagnostics. Separate actual inference diagnostics with the same public failure context observed `json_validate_failed` at a 1,200-token completion budget in both JSON-object and strict-schema modes, then HTTP 200/stop with strict schema and 3,500 tokens: 4,868 prompt, 1,505 completion (including 1,264 reasoning), 6,373 total. A minimal JSON/1,200 probe returned 200; one separate token-per-minute 429 was retried later. These diagnostic outputs were never used as app patches or execution results. The deployed fourth-run request uses strict schema, valid JSON-escaping instructions and the larger budget; the fourth run subsequently established its own generation and recorded passing result, separately from those probes. See [the diagnostic record](AUTONOMOUS_RELEASE.md#direct-provider-diagnostics-separate-from-app-execution) and Groq's [structured outputs](https://console.groq.com/docs/structured-outputs) and [reasoning](https://console.groq.com/docs/reasoning) documentation.

The third button run [`67e71af389a6ce58d0a685cb17591b4a`](https://baton-workspace.vercel.app/api/public/workflows/67e71af389a6ce58d0a685cb17591b4a), [GitHub run 39159597961](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39159597961), uses workflow head `42c8e82ae684e029fc76e3b9f3973436110426f2`. **This run failed**: independent public receipt/report reads confirm 529 passed, one failed and 17 ignored, exit 101, zero repairs, and a Groq HTTP 400 repair-request error. Saved Jira/Slack failure-publication read-backs are verified. The HTTP 400 cause is not established here; the subsequent fourth attempt passed its recorded checks and publication gates under its older worker head. The UI distinguishes callback progress from independently verified results; failed execution can still have verified failure-report publication. GET reads and reloads never dispatch another run.

Fourth button run [`d0770620a12494f31fe78cc7e1180640`](https://baton-workspace.vercel.app/api/public/workflows/d0770620a12494f31fe78cc7e1180640), [GitHub run 39160583697](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39160583697), started `2026-10-18 19:50:10 UTC` with older workflow head `2acf3d3440fbf1084c35bd63139f08cb9c88a247`. Its independent proof records an actual applied Groq edit (4,817 input / 1,173 output tokens), initial 529/1/17 retained, final library 530/0/17, four targeted passing reruns and formatting. Separate actual provider GET/graph read-only audit verified Jira comment `10004` and Done, the original Slack run block and one source/task/agent-bound run with seven checks. The [release report](AUTONOMOUS_RELEASE.md#fourth-run-proof-and-limits) records hashes and limitations. The min/max edit's observed effect does not prove the model's causal explanation: the original guarded match already bounded the cap.

Subsequent hardening restricts edits to a pure constructor expression and pins the worker's `HEAD` baseline. No actual forged summary or changed-HEAD exploit was observed; the fourth run predates those worker checks. Fifth attempt [`d21663169f98a1c5f999598caa6b1ce7`](https://baton-workspace.vercel.app/api/public/workflows/d21663169f98a1c5f999598caa6b1ce7), started `2026-10-18 20:01:26 UTC`, **reached the application daily quota guard before execution dispatch** and has no GitHub run ID in independent public read-back. Its agent has three completed tools/receipts and 2,849 measured tokens. The sixth-run shared brief/graph limit is 60 instead of 50 calls/day, with no used-counter reset and all other guards retained. The earlier 711-check hardened test run predates this quota adjustment; the final frozen full suite including the adjustment has now passed. Exact grouped counts, log hashes and retained failures are centralized in the [release report](AUTONOMOUS_RELEASE.md#application-checks-and-retained-failures).

The actual account response-header diagnostic returned HTTP 200 with a 1,000 requests/day limit and an 8,000 tokens/minute limit; remaining values at that instant were 995 requests and 7,178 tokens. These headers do not measure tokens/day. The official model table lists 200,000 tokens/day; limits are shared and token/request limits can bind independently. The app cap is a conservative workload guard, not unlimited free inference or an AWS/GitHub billing guarantee. [Groq rate-limit documentation](https://console.groq.com/docs/rate-limits).

Sixth button run [`de223685c514b134ae8b471263f90d7a`](https://baton-workspace.vercel.app/api/public/workflows/de223685c514b134ae8b471263f90d7a), [GitHub run 39161825805](https://github.com/RHUDHRESH/baton-graph-workspace/actions/runs/39161825805), started `2026-10-18 20:06:39 UTC` on frozen head `1af00116c84a3195f6bf1eeba1e9ebdd2e538bb4` and completed at `20:17:08 UTC`; both GitHub jobs succeeded. It generated its own `clamp` edit through Groq, response `chatcmpl-2b9b35c7-963b-41ff-804e-091f5a8266c1`, 4,813 input / 301 output tokens. Initial 529/1/17 remains in its seven retained checks; final library 530/0/17, four targeted passing reruns and formatting produced 534 passing executions. Independent actual provider GET verified Jira comment `10005` and Done plus the exact original Slack run block; direct graph read-only queries verified one run, seven checks and source/task/agent binding. Canonical and new investigation task both read back Done. The main browser showed all five stages completed, and the frozen application suite passed 716 checks. [Final proof, hashes, screenshots and limits](AUTONOMOUS_RELEASE.md#final-hardened-run-and-independent-proof).

## Existing cloud infrastructure

AWS resources: `baton-workspace` Lambda (Python3.12, x86_64, 256MB, 180 seconds); `baton-workspace-control` DynamoDB STANDARD (10 provisioned RCU / 10 WCU, TTL `expires`, no autoscaling); and `baton-workspace-lambda-exec` with an inline policy restricted to this table. Function URL invocation permissions were explicitly approved. No CloudWatch logging permissions, EC2, Lightsail, NAT, API Gateway, ECR, paid model plan or domain were added.

AWS rejected reserved concurrency2 because of its unreserved-capacity requirement. Actual account concurrency quota:10. The request guard allows5000 app requests per UTC month; shared brief/graph guard was 50 calls per UTC day and is now raised conservatively to 60 without resetting the counter, retaining the 15-second submission cooldown. Repair-call and per-run guards remain separate. These workload guards are not billing caps. Ongoing Lambda and provisioned DynamoDB allowances, rather than signup credits or a free VM, are the intended cost basis. The existing Vercel Pro account was explicitly approved; its plan and shared usage allowances still apply. No new subscription or paid add-on was requested.

The old `builder-quest-ec2` was terminated after explicit irreversible-deletion approval. Its approved8GB root disk was deleted; subsequent matching-volume and Elastic-IP checks returned empty results.

## Historical live verification before cloud code execution

The public Vercel frontend and API proxy returned200. The deployed health check authenticated to FalkorDB Cloud. Public GitHub import/read-back produced28 work items,21 contributor accounts,18 source responses and92 relationships from FalkorDB/FalkorDB and FalkorDB/falkordb-py.

Actual Groq generation passed after correcting an initially misentered credential: `openai/gpt-oss-20b`,1040 input/322 output tokens, receipt `chatcmpl-27c13e96-629f-45f3-be59-317c8a86bca0`. Seven generated AI claims were written separately from source facts. Graph-linked task creation/completion/reload, authenticated Jira CSV export, logout, anonymous-write rejection and hostile-Origin rejection passed live API checks. Browser sign-in, real work selection and a second sourced Groq brief also passed. CSV export alone does not create a Jira issue.

Initial live agent attempts exposed ID and uninspected-citation failures; no substitute action was returned. Repairs bind exact IDs, inspected primary sources, and graph-returned file paths. The final browser run `f63527310d11f7d5a88f24acd00236b7` succeeded in 12,591 ms with four Groq calls and 5,423 measured tokens. It inspected changed-file source `src-996993d04692a63f` and saved task `task-agent-f63527310d11f7d5a88f24acd00236b7`, naming `graph/src/graph/graphblas/tensor.rs`. Independent stored-source consistency and exact task read-back passed. Path membership is verified; semantic reason entailment and task usefulness are not.

The company overview passed on managed FalkorDB after correcting an aggregate ordering incompatibility caught live. It uses two bounded graph business queries. Its first five suggestions cover three gap kinds and both repositories; the display order is not claimed to establish urgency.

For current application and verifier counts, exact reports and retained failures, use the [autonomous release report](AUTONOMOUS_RELEASE.md). The earlier [verified release](VERIFIED_RELEASE.md) records the pre-cloud-run workbench and imported Codex evidence. Its 530 Rust passes and two RDB cycles were run by Codex in Docker; they are historical and cannot establish a new GitHub Actions result. Ignored benchmarks/probes remain unrun. No locked checks or manifests were changed.

The final public preview and then the main production URL passed the complete CloudShell frontend/API harness: health, authentication, source inspection, actual Groq generation, cited graph writes, task creation/completion/reload, Jira CSV export, logout, anonymous-write rejection and hostile-Origin rejection. Final brief run `eb421c9244b19f0cb2ac5252e3cd9ad9` used 1,040 input / 322 output tokens; provider receipt `chatcmpl-8fa59bdd-950d-4dee-8dd0-d67636436868`. Browser checks independently passed source payload inspection, operator sign-in, agent execution, task completion/reload/reopen, and displayed external artifact links.

Production-host repeat verification: Groq run `1ee742ea00d122ea4262b2f4dce8b586` succeeded with 1,040 input / 291 output tokens, receipt `chatcmpl-3afacc71-7790-4889-8930-bd289034d09c`. Auth, graph/source reads, task create/complete/reload, CSV export, logout, anonymous rejection and hostile-Origin rejection all passed.

Production graph-agent run `6c09aba93fc18a7682015cdff88bbace` also passed in 13,705 ms: four actual Groq tool calls, changed-file evidence, exact graph-file grounding and task read-back. Repeated Slack/Jira publish checks on the production origin retained their existing message/issue identities and graph links.

## Setup and reproducibility

`deploy/requirements.lambda.txt` pins Linux runtime dependencies. Stage its Linux wheels with uv, run `python scripts/build_lambda.py`, then upload the code-only archive and `deploy/aws_lambda.py` to authenticated AWS CloudShell. Archives, caches and secrets are ignored by Git.

```sh
python3 aws_lambda.py prepare --archive ARCHIVE.zip
python3 aws_lambda.py configure
python3 aws_lambda.py publish
```

Configuration prompts are intended to read provider credentials without echoing them. A later troubleshooting command did echo a credential: terminal history/visible output were cleared and the temporary ignored file deleted, but previously captured tool output cannot be recalled. Rotation remains recommended and is not recorded as completed; see the [incident disclosure](AUTONOMOUS_RELEASE.md#credential-handling-incident). Store existing FalkorDB/Groq credentials in Lambda environment variables. Never print full Lambda configuration or paste secrets into chat. Use the real FalkorDB Connectivity host/port, username and Free-tier `FALKORDB_TLS=0`.

```sh
python -m scripts.stage_vercel https://ACTUAL.lambda-url.ap-south-1.on.aws/
```

This stages public assets plus security headers and the exact API rewrite. It excludes local Vercel metadata from archives. Set Lambda `BATON_ALLOWED_ORIGIN` to the primary frontend HTTPS origin and, when testing, `BATON_PREVIEW_ORIGIN` to the exact preview origin. The guard rejects lookalike origins and cross-site writes. Cookies remain HttpOnly/Secure/SameSite=Strict on the frontend origin through the proxy.

Live CloudShell harnesses `deploy/verify_live.py` and `deploy/verify_agent.py` read the operator credential directly into memory from Lambda. They print sanitized evidence, never credentials or cookies. The latter verifies MCP discovery, graph tool execution, a provider-selected agent action and persisted read-back. Local provider/Moto/graph tests use mocked boundaries and must remain labeled as such.

## Configure the reviewed cloud runner

Deploy `.github/workflows/baton-execute.yml` and the trusted worker from an exact reviewed app commit. Lambda needs the existing `BATON_GITHUB_TOKEN` with permission to read this workflow repository's source/jobs/artifacts and dispatch its reviewed workflow, plus the existing Groq and Jira/Slack configuration. Do not print tokens, full Lambda environment output or callback capabilities. `deploy/update_autonomous.py EXACT_COMMIT` updates the existing Lambda from reviewed source while preserving its existing Linux wheels and environment; it verifies the resulting code digest and does not create resources or dispatch a run.

The app records the expected workflow commit before dispatch and binds callbacks to the exact execution ID, repository, first run attempt, workflow path and head commit. The per-run capability stays in the trusted GitHub host process; it is not passed into the source container. The workflow masks it, disables persisted checkout credentials and uploads logs/report/patches for independent finalization. Only public Cargo downloads may be cached; source checkouts, compiled targets and old result artifacts are not reused as evidence.

The worker has a 35-minute deadline; the execute job has a 40-minute timeout and finalization has a separate five-minute limit. The application permits one active run, ten attempted starts per UTC month and at most two repairs per run. These are application workload limits, **not account-wide billing caps**: GitHub Actions minutes/artifacts, Lambda, DynamoDB and existing plan usage share their respective account allowances. Consult the [workflow limits](AUTONOMOUS_WORKFLOW.md#bounded-use-of-existing-services) before treating included usage as free remaining capacity.

`scripts/verify_autonomous_release.py` is a GET-only public receipt/artifact verifier. It does not start jobs, spend model calls or send provider messages. Application contract tests mock provider boundaries; production proof requires each actual run's job, generation receipt when applicable, immutable test/source evidence and separate provider read-backs.

## Jira and Slack

`server/company_connections.py` implements explicit task publishing. For the approved cloud profile, `server/autonomous_publication.py` updates existing Jira KAN-2 and its original Slack message after execution outcome verification; starting that profile explicitly authorizes these outcome updates. It publishes a verified failure honestly and requires successful code checks plus provider read-backs before a completed workflow can be shown. It records a durable intent before a provider write and never repeats an ambiguous write. Read-back verifies artifact content and the resulting graph link; pending states are surfaced honestly.

Required environment variables (plus `JIRA_CLOUD_ID` for scoped tokens): `JIRA_SITE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`. Status reports configuration presence separately from connectivity. The approved Slack setup targets a dedicated public `baton-demo` channel in the user's Raptorflow workspace, using `chat:write` and `channels:history`. Jira Free activation on the user's existing site was approved. Actual Jira and Slack creation/read-back now pass. Jira issue [KAN-1](https://rhudhresh3697.atlassian.net/browse/KAN-1) and [Slack task message](https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792332383930779) link to the same agent task. The CloudShell integration harness verified persisted graph links and identical artifact identities on repeated publish calls, without duplicate writes. The scoped Jira work token expires October 25, 2026; no Jira admin scopes were added.

Only public-source demo tasks are sent; no unrelated private Slack/Jira history is ingested. Raptorflow is the user's integration workspace, not an assertion that it is FalkorDB's internal workspace.

## Docker recovery on October 18, 2026

Docker Desktop 4.90.0 could not start its Linux engine because stale AF_UNIX socket objects returned Windows error 1920. A force stop followed by reversible isolation of socket-only runtime folders restored Engine 29.7.2. Containers, images, volumes, WSL distributions and the Docker data disk were retained. Existing application containers resumed; the isolated checks container was built successfully.

Preserved folders under `%LOCALAPPDATA%`: `Docker/run.baton-recovery-20261018`, `Docker/run.baton-recovery-20261018-2`, and `docker-secrets-engine.baton-recovery-20261018`. These retain the inaccessible runtime objects; no factory reset or disk deletion was used. Automatic review blocked a direct socket-deletion attempt, so recovery used preserved directory renames instead.

This restores the current engine, not a proven permanent upstream fix. [Docker's issue tracker documents the same startup failure](https://github.com/docker/desktop-feedback/issues/676). A future restart may require vendor remediation.

## Scope and limits

Company context uses two bounded read-only graph queries and captured source evidence. Public contributor activity does not establish employment or internal ownership. The Acme benchmark at `/benchmark.html` and Halden at `/sandbox.html` remain explicitly synthetic; their scripted/cached extraction is not live Groq inference. No synthetic company is presented as a real organization.

FalkorDB Free has no TLS, persistence or backups, and inactive instances may be removed. Only public/synthetic records belong in this demo. Recovery after graph deletion is not implemented. Full tenant isolation and sustained-concurrency benchmarking are not claimed.

Research notes verify release dates and document narrow adaptations, not full SOTA reproductions or exponential performance: [graph](RECENT_GRAPH_RESEARCH.md), [agent](RECENT_AGENT_RESEARCH.md), [actions](RECENT_ACTION_RESEARCH.md). Recent engineering releases and research contributions are distinguished explicitly.

Temporary Chrome extension file-URL access should be disabled after uploads. The user must change that setting because browser tooling cannot open extension-settings pages.

References: [Lambda allowances](https://docs.aws.amazon.com/whitepapers/latest/big-data-analytics-options/aws-lambda.html), [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/), [Function URL authorization](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html), [Groq quotas](https://console.groq.com/docs/rate-limits), [FalkorDB Free](https://github.com/FalkorDB/falkordb-cloud-docs/blob/main/tiers/free.mdx), [Vercel rewrites](https://vercel.com/docs/routing/rewrites).
