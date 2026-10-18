# Cloud deployment and evidence

Updated 2026-10-18. This document distinguishes completed cloud checks from pending integration work.

## Topology

Vercel static frontend → same-origin `/api` rewrite → AWS Lambda in Mumbai → FalkorDB Cloud Free. Groq Free supplies actual GPT-OSS inference. DynamoDB holds sessions, counters and leases; no provider credentials are written to the graph.

The initial public frontend is https://baton-workspace.vercel.app. The complete company/agent frontend is the public preview https://baton-workspace-2f1no78bu-risehackathonsupport-3406.vercel.app. The stable alias retains the initial frontend; the final preview has not been promoted. Both Vercel and Lambda provide HTTPS hostnames; no purchased domain is needed.

AWS resources: `baton-workspace` Lambda (Python3.12, x86_64, 256MB, 180 seconds); `baton-workspace-control` DynamoDB STANDARD (10 provisioned RCU / 10 WCU, TTL `expires`, no autoscaling); and `baton-workspace-lambda-exec` with an inline policy restricted to this table. Function URL invocation permissions were explicitly approved. No CloudWatch logging permissions, EC2, Lightsail, NAT, API Gateway, ECR, paid model plan or domain were added.

AWS rejected reserved concurrency2 because of its unreserved-capacity requirement. Actual account concurrency quota:10. The request guard allows5000 app requests per UTC month; inference guard allows50 provider calls per UTC day, with a15-second submission cooldown. These workload guards are not billing caps. Ongoing Lambda and provisioned DynamoDB allowances, rather than signup credits or a free VM, are the intended cost basis. The existing Vercel Pro account was explicitly approved; its plan and shared usage allowances still apply. No new subscription or paid add-on was requested.

The old `builder-quest-ec2` was terminated after explicit irreversible-deletion approval. Its approved8GB root disk was deleted; subsequent matching-volume and Elastic-IP checks returned empty results.

## Actual live verification

The public Vercel frontend and API proxy returned200. The deployed health check authenticated to FalkorDB Cloud. Public GitHub import/read-back produced28 work items,21 contributor accounts,18 source responses and92 relationships from FalkorDB/FalkorDB and FalkorDB/falkordb-py.

Actual Groq generation passed after correcting an initially misentered credential: `openai/gpt-oss-20b`,1040 input/322 output tokens, receipt `chatcmpl-27c13e96-629f-45f3-be59-317c8a86bca0`. Seven generated AI claims were written separately from source facts. Graph-linked task creation/completion/reload, authenticated Jira CSV export, logout, anonymous-write rejection and hostile-Origin rejection passed live API checks. Browser sign-in, real work selection and a second sourced Groq brief also passed. CSV export alone does not create a Jira issue.

Initial live agent attempts exposed ID and uninspected-citation failures; no substitute action was returned. Repairs bind exact IDs, inspected primary sources, and graph-returned file paths. The final browser run `f63527310d11f7d5a88f24acd00236b7` succeeded in 12,591 ms with four Groq calls and 5,423 measured tokens. It inspected changed-file source `src-996993d04692a63f` and saved task `task-agent-f63527310d11f7d5a88f24acd00236b7`, naming `graph/src/graph/graphblas/tensor.rs`. Independent stored-source consistency and exact task read-back passed. Path membership is verified; semantic reason entailment and task usefulness are not.

The company overview passed on managed FalkorDB after correcting an aggregate ordering incompatibility caught live. It uses two bounded graph business queries. Its first five suggestions cover three gap kinds and both repositories; the display order is not claimed to establish urgency.

Current local verification: 139 cloud/provider/agent/company contracts and 22 foundation checks passed. The original locked-check integrity passed under WSL; native Windows reports false unapproved paths because of path separators. Legacy isolated-engine graph/red-team tests could not be rerun: `BATON_TEST_REDIS`/`BATON_TEST_MODULE` are unavailable and Docker's Linux engine is not running. Historical 172-test results are not presented as a current rerun.

The final public preview also passed the complete CloudShell frontend/API harness: health, authentication, source inspection, actual Groq generation, cited graph writes, task creation/completion/reload, Jira CSV export, logout, anonymous-write rejection and hostile-Origin rejection. Final brief run `eb421c9244b19f0cb2ac5252e3cd9ad9` used 1,040 input / 322 output tokens; provider receipt `chatcmpl-8fa59bdd-950d-4dee-8dd0-d67636436868`. Browser checks independently passed source payload inspection, operator sign-in, agent execution, task completion/reload/reopen, and displayed external artifact links.

## Setup and reproducibility

`deploy/requirements.lambda.txt` pins Linux runtime dependencies. Stage its Linux wheels with uv, run `python scripts/build_lambda.py`, then upload the code-only archive and `deploy/aws_lambda.py` to authenticated AWS CloudShell. Archives, caches and secrets are ignored by Git.

```sh
python3 aws_lambda.py prepare --archive ARCHIVE.zip
python3 aws_lambda.py configure
python3 aws_lambda.py publish
```

Configuration prompts read provider credentials without echoing them. Store existing FalkorDB/Groq credentials in Lambda environment variables. Never print full Lambda configuration or paste secrets into chat. Use the real FalkorDB Connectivity host/port, username and Free-tier `FALKORDB_TLS=0`.

```sh
python -m scripts.stage_vercel https://ACTUAL.lambda-url.ap-south-1.on.aws/
```

This stages public assets plus security headers and the exact API rewrite. It excludes local Vercel metadata from archives. Set Lambda `BATON_ALLOWED_ORIGIN` to the primary frontend HTTPS origin and, when testing, `BATON_PREVIEW_ORIGIN` to the exact preview origin. The guard rejects lookalike origins and cross-site writes. Cookies remain HttpOnly/Secure/SameSite=Strict on the frontend origin through the proxy.

Live CloudShell harnesses `deploy/verify_live.py` and `deploy/verify_agent.py` read the operator credential directly into memory from Lambda. They print sanitized evidence, never credentials or cookies. The latter verifies MCP discovery, graph tool execution, a provider-selected agent action and persisted read-back. Local provider/Moto/graph tests use mocked boundaries and must remain labeled as such.

## Jira and Slack

`server/company_connections.py` implements direct Jira issue creation and Slack posting only when explicitly invoked. It records a durable intent before a provider write and never repeats an ambiguous write. Read-back verifies artifact content and the resulting graph link; pending states are surfaced honestly.

Required environment variables (plus `JIRA_CLOUD_ID` for scoped tokens): `JIRA_SITE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`. Status reports configuration presence separately from connectivity. The approved Slack setup targets a dedicated public `baton-demo` channel in the user's Raptorflow workspace, using `chat:write` and `channels:history`. Jira Free activation on the user's existing site was approved. Actual Jira and Slack creation/read-back now pass. Jira issue [KAN-1](https://rhudhresh3697.atlassian.net/browse/KAN-1) and [Slack task message](https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792332383930779) link to the same agent task. The CloudShell integration harness verified persisted graph links and identical artifact identities on repeated publish calls, without duplicate writes. The scoped Jira work token expires October 25, 2026; no Jira admin scopes were added.

Only public-source demo tasks are sent; no unrelated private Slack/Jira history is ingested. Raptorflow is the user's integration workspace, not an assertion that it is FalkorDB's internal workspace.

## Scope and limits

Company context uses two bounded read-only graph queries and captured source evidence. Public contributor activity does not establish employment or internal ownership. The Acme benchmark at `/benchmark.html` and Halden at `/sandbox.html` remain explicitly synthetic; their scripted/cached extraction is not live Groq inference. No synthetic company is presented as a real organization.

FalkorDB Free has no TLS, persistence or backups, and inactive instances may be removed. Only public/synthetic records belong in this demo. Recovery after graph deletion is not implemented. Full tenant isolation and sustained-concurrency benchmarking are not claimed.

Research notes verify release dates and document narrow adaptations, not full SOTA reproductions or exponential performance: [graph](RECENT_GRAPH_RESEARCH.md), [agent](RECENT_AGENT_RESEARCH.md), [actions](RECENT_ACTION_RESEARCH.md). Recent engineering releases and research contributions are distinguished explicitly.

Temporary Chrome extension file-URL access should be disabled after uploads. The user must change that setting because browser tooling cannot open extension-settings pages.

References: [Lambda allowances](https://docs.aws.amazon.com/whitepapers/latest/big-data-analytics-options/aws-lambda.html), [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/), [Function URL authorization](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html), [Groq quotas](https://console.groq.com/docs/rate-limits), [FalkorDB Free](https://github.com/FalkorDB/falkordb-cloud-docs/blob/main/tiers/free.mdx), [Vercel rewrites](https://vercel.com/docs/routing/rewrites).
