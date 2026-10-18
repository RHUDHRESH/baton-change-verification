# Recent research behind company actions

Reviewed 18 October 2026. The strict rolling two-week cutoff used here is
4 October 2026 13:31 UTC. The three included papers each have a first arXiv
version after that cutoff and before the review date; this is primary-source
first-version evidence, not a claim to have ruled out every earlier private
disclosure. These are recent research techniques relevant to the implementation.
Their papers do not establish that this application is state of the art or that
it produces exponential improvements. No benchmark result below is a Baton result.

| Technique | Primary first-release evidence | Applied adaptation | Scope of evidence |
| --- | --- | --- | --- |
| Evidence-Grounded Behavior Graph (EBG), *What Did the Agent Actually Do?* | [arXiv v1](https://arxiv.org/abs/2610.06406v1), submission history: **5 October 2026, 14:25:16 UTC** | A verified external artifact is linked to its local task and captured GitHub work item by `PUBLISHED_AS` and `EVIDENCED_BY`; the receipt preserves source and material-action hashes. | The authors report better decision identification/evidence localization in most settings across eight models. This adapter implements a small evidence-linked action view, not their full graph construction or AgentMonBench. |
| Retrieval-admissibility verification, *The Right Memory in the Wrong Context* | [arXiv v1](https://arxiv.org/abs/2610.07309v1), submission history: **5 October 2026, 19:47:43 UTC** | A stored task may publish only evidence from its exact captured snapshot and graph, with captured source IDs and an approved public repository URL. Missing provenance blocks dispatch. The receipt records this bounded admissibility result. Replaying against changed source/task/destination context is rejected. | The paper separates admissible, inadmissible and unresolved memory use, required-evidence recall, exposure and disclosure. Baton uses a deterministic public-source gate; it does not implement the authors' retriever, private multi-principal policies or benchmark evaluation. |
| Retry-permission versus recovery evaluation, *RetryBench* | [arXiv v1](https://arxiv.org/abs/2610.15884v1), submission history: **11 October 2026, 20:00:44 UTC** | Receipts expose `write_retry_allowed=false` separately from `readback_retry_allowed`. Timeout tests assert that an unknown write never causes another POST; known identities permit only read-back. The UI can report unresolved recovery without falsely reporting completion. | The paper's contribution is a contract probe and controlled interface results, not invention of idempotency. It studies four purposive tasks and a single recovery decision. Baton uses failure/replay tests inspired by that distinction, not the study's model protocol. |

The earlier candidate *Runtime Authorization of Self-Generated Subgoals*
([v1](https://arxiv.org/abs/2610.04975v1), 4 October 2026 05:43:47 UTC) was
excluded from the three because it precedes the strict rolling cutoff. The
implementation's final task/configuration recheck is ordinary defensive
engineering and is not counted as a fourth recent technique. Durable receipts,
locks, hashes and provider read-back are established techniques, not newly
invented SOTA methods.

## Adapter contract

`server.company_connections.status()` returns `jira` and `slack` entries with
sanitized configuration presence, a destination when valid, and `verified=false`.
It performs no authentication probe and reveals neither email addresses nor
tokens. A configured entry does not establish a connected account.

`publish_task(data, port, task_id, target)` accepts only `jira` or `slack` and an
existing public-workspace task. The API caller must already enforce the user's
authenticated session and an explicit publication action. A model-generated
description cannot choose a destination or grant authority. Environment config
selects the provider destination, and an intent receipt must be persisted before
any POST. Credentials remain in server/Lambda environment variables and are
never written to the graph, receipt or response.

The existing control-store lock serializes each task/target action. In AWS this
uses `BATON_CONTROL_DYNAMODB_TABLE` and `DynamoControl`; local deployments can
use the existing private control Redis. Receipts use the workspace's durable
record backend and contain only public task/evidence and sanitized artifact
metadata. Graph linkage stores the artifact URL, hashes and verification time.
This is a public demonstration workspace; do not use these routes to ingest
company history or confidential work.

| Receipt state | Meaning | Repeated explicit call |
| --- | --- | --- |
| `pending` | Intent is durable; external outcome is unknown, including timeouts and malformed acknowledgements. | Returns the receipt; no automatic replacement write. Inspect the configured destination manually. |
| `remote_created` | A validated provider identity was received and persisted. | Reads that artifact only. |
| `verification_pending` | Identity is known but a separate read-back failed, differed or was unavailable. | Repeats read-back only. |
| `verified` | Separate provider read-back matches the submitted artifact and public evidence. | Returns the receipt; can repair pending graph linkage. Verification time remains visible. |
| `error` | The task/configuration changed before dispatch; no provider write was attempted. | Remains terminal unless an operator reconciles the existing intent. |
| `rejected` | A recognized provider response explicitly refused the write, such as invalid authentication, missing scope, inaccessible channel or an HTTP request rejection. | Returns actionable diagnostic guidance; never reposts this action automatically. Reconcile the receipt after fixing configuration. |

A crash after provider creation but before identity persistence leaves a pending
receipt. The adapter intentionally cannot infer non-execution from missing data
and cannot promise exactly-once delivery. No automatic retry deletes receipts
or changes the action identity. A graph failure preserves provider verification
and returns `graph_linked=false` with an honest message.

Provider failures include a sanitized `diagnostic` with a stable `code`,
`stage` (`publish` or `verification`) and actionable `message`. Recognized Slack
permission/authentication/channel errors and HTTP 400/401/403/404/405/413/422/429
responses produce `rejected` only during publication. HTTP 5xx, timeouts,
malformed acknowledgements, unknown Slack errors and Slack
`internal_error`/`fatal_error` remain `pending`; an error response can occur
after part of an operation succeeds. Neither state grants write-retry permission.
An HTTP 429 may include a validated integer `retry_after_seconds`, solely as
guidance. No error body, arbitrary provider code, URL, reason or header text is
copied into the diagnostic. A recognized error during read-back leaves the known
artifact in `verification_pending`; after permissions are corrected, the next
explicit call checks that artifact and clears the stale diagnostic on success.

## Configuration and provider permissions

Jira requires `JIRA_SITE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and
`JIRA_PROJECT_KEY`. `JIRA_ISSUE_TYPE` optionally overrides `Task`. Only an exact
HTTPS `*.atlassian.net` site is accepted; userinfo, ports, nested paths and
redirects are refused. Requests use Jira Cloud REST v3 issue creation and then a
separate issue GET.

For a scoped API token, also set optional `JIRA_CLOUD_ID` to the site's canonical
lowercase UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`). This selects only the
fixed API gateway `https://api.atlassian.com/ex/jira/{cloudId}`; the same approved
REST v3 paths are appended. The cloud ID must belong to `JIRA_SITE_URL`, which
continues to supply human links and the displayed destination. API requests use
HTTP Basic authentication with `JIRA_EMAIL:JIRA_API_TOKEN` in both modes. Choose
the Jira classic scopes `read:jira-work` and `write:jira-work` for this issue
create/read-back flow. When `JIRA_CLOUD_ID` is unset or empty, existing unscoped
tokens continue to use the configured site API. A cloud ID change invalidates
an existing action's material contract rather than reusing its receipt across
tenants. Invalid cloud IDs fail closed without being echoed. See [Atlassian's
scoped-token instructions](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/).

The account needs Browse Projects and Create Issues for the
selected project, access to the configured issue type, and any mandatory project
fields must be compatible with this minimal Task payload. API tokens do not
create a Jira site or project. See the [official issue REST
reference](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).

Slack requires `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` for one configured
channel/group; the bot must be installed and invited to that channel. Its
[chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/)
permission is `chat:write`. Independent read-back requires `channels:history`
for a public channel or `groups:history` for a private channel, using
[conversations.history](https://docs.slack.dev/reference/methods/conversations.history/)
with both timestamps fixed to the newly returned message timestamp,
`inclusive=true`, and `limit=1`. No pagination, other message queries, private
history ingestion or DM discovery occurs. A verified message also needs a valid
[chat.getPermalink](https://docs.slack.dev/reference/methods/chat.getPermalink/)
result bound to that channel and timestamp; that method requires no extra scope.
Slack read-back rate limits may delay verification, so posting permission alone
can yield `verification_pending`.

Every request has a 20-second socket timeout, a 512,000-byte response cap and no
redirect or retry. Provider exception bodies and credentials are suppressed.
Slack markup/mentions and link/media unfurls are disabled for submitted task
text. Jira read-back checks the expected project, issue key, title and complete
evidence description; Slack checks the exact timestamp and message text.

## Validation and present limits

`tests/test_company_connections.py` uses mocked providers and a copied in-memory
workspace-record store. It checks provider create/read-back sequences, receipt
replay, concurrent clicks, uncertain writes, changed evidence/destinations,
pre-dispatch task changes, graph repair, allowed origins, no redirects, response
limits, secret-safe errors and Slack mention escaping. It never sends a company
message. The in-memory fixture avoids weakening the production Linux-only safe
file-write policy when tests run on Windows.

Scoped-token tests additionally check both HTTP methods against the fixed
gateway, Basic authentication, unchanged human links, rejection of URL/path/query
injection and noncanonical UUIDs, and replay rejection when the cloud ID changes.
Failure tests distinguish explicit rejection from partial/unknown execution,
check actionable permission guidance and validated rate-limit metadata, reject
raw provider-secret echoes, and verify that fixing read-back permission never
causes a second POST.

This test suite creates no live provider artifacts. Live verification requires
server credentials and an existing Jira site/project or Slack app/channel.
This adapter creates tasks/messages outbound from public GitHub
evidence; it does not yet ingest real private company activity, infer employee
relationships or synchronize subsequent provider edits.
