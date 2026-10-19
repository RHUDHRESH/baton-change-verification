# Change verification release record

Status: **interim record; final release validation pending** (2026-10-19 UTC).
The first actual app execution, `c93a2d6a99390dabc3eb3816834726a4`, produced
independently verified failing evidence. It is retained as historical evidence;
it does not certify the subsequent projection/UI changes or a finished release.

## Product boundary

The current bounded profile is graph-driven verification with an AI
investigation assistant. The sealed verification plan and its execution can run
algorithmically; the model assists evidence inspection and explanation. Under
a definition requiring AI to be essential to the core workflow, this is not
an AI-native product. A general goal planner and ten goal-driven AI-native
features are targets, not shipped capabilities. This record does not claim a
complete company brain.

## First actual app execution

The operator used the main app to investigate and submit the reviewed change.
The app performed four actual Groq requests using `openai/gpt-oss-20b`, with
6,902 measured total tokens: three native tool selections executed real MCP
`tools/call` requests (`release_read_change`, `release_follow_impact`, and
`release_read_source`), followed by a native assistant response with
`finish_reason=stop`. The final response was ordinary model text, not a
fabricated tool call. Source attribution was runtime-observed context, not
model-selected citation verification. Deterministic graph obligations controlled
the sealed matrix.

The application dispatched GitHub Actions automatically. This execution was
not a manually dispatched workflow or an imported local smoke result.

| Binding | Observed value |
| --- | --- |
| Plan | `358043b754c6e408b3ac9c1e7cfebfb9` |
| Plan hash | `98ab5e66fb38ac2145d35a40d1f659595ef6ede3dfcd8bdb203f7c5bf7bc1542` |
| App run | `c93a2d6a99390dabc3eb3816834726a4` |
| GitHub run | `39189033882` |
| Workflow source | `f30801c28298036dbe6a59b51970edfb2541c025` |
| Workflow | `.github/workflows/baton-verify.yml`, `workflow_dispatch`, attempt 1 |
| Artifact | `12159128028`, `baton-verify-c93a2d6a99390dabc3eb3816834726a4` |
| Source commit | `207000da70ca183ab02990a98bdd97d0a3e3bb1b` |
| Jira artifact | `KAN-3` |
| Slack message timestamp | `1792376150.947499` |

At the independent readback, both GitHub jobs (`execute`, `finalization`) had
completed successfully. The application state was `completed`, with evidence
`verified`, verification `failed`, and release decision **`blocked`**. Successful
orchestration and publication did not turn failing tests into a passing release.

| Python redis client dependency | Passed | Failed | Errors | Skipped | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8.0.0 | 4 | 0 | 0 | 0 | 4 |
| 8.1.0 | 2 | 2 | 0 | 0 | 4 |
| Total | 6 | 2 | 0 | 0 | 8 |

Both failures were the required asynchronous cases and reported
`Redis.__init__() got an unexpected keyword argument 'himport_registry'`.
Both synchronous cases passed in each environment. Source before/after hashes
were unchanged. The four exact pytest node IDs were the two
`test_param_non_identifier_keys` and `test_param_invalid_keys_rejected` cases
in each of `tests/test_graph.py` and `tests/test_async_graph.py`.

The matrix versions above identify the **Python redis client**, not a database
server release. Python was 3.13.5, pinned by image digest
`python@sha256:a7cb177dc60dfa77b223192cd0d9e6ce1aac7cf9a569023d68e7c91b6371a718`.
The separate disposable test server image was
`falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a`.
Each environment used its own disposable database; the upstream fixture's
`FLUSHDB` did not target the managed cloud workspace database. Dependencies
were hash-locked; source containers received no cloud credentials, callback
capability, host mounts, or Docker socket.

## Independent evidence and hashes

The read-only [independent proof](evidence/release-c93-independent-proof.json)
was produced by `scripts/verify_release_gate.py`. It authenticated the actual
GitHub run/jobs/artifact and independently verified the downloaded ZIP. The
public report and all nine other public raw files matched that artifact byte
for byte. The verifier checked source/archive bindings, commands, measured
dependencies, exact JUnit identities, positive collection, zero skips, outcomes,
and graph-certificate hashes. Its result was **`verified_failure`**.

| Material | SHA-256 |
| --- | --- |
| Independent proof JSON | `65f6fc60dc61c2b78102622b8eb26ef398b34fb721e6b725f45102415118b3f8` |
| Direct cloud audit JSON | `dc9836df378b8ec4fd9573273b66976e138dbfd9a272150a4e09ae92e45306a0` |
| Jira open-status audit JSON | `3ebd62bc8b79c8c64fa7f0f6937ef3d2443f5a60f413e0e4d78112c32779cc57` |
| GitHub artifact ZIP | `fb54712d10f1631a401f5b6c5cedef20a401f57caad0a57113898c6840f0a833` |
| Execution report | `e558500436f3fd646286681b03204c027aebec3e2fb1d53362cb700e4884acec` |
| Upstream source ZIP | `cb2057288440cfc977da4bcfbf3770a3a577511f6ef5d3b5b79cf4006ea1a499` |
| Normalized eight results | `9367c50f15e9ea00568c288c461cb8bdec4812d646fbcd0151f72481bccf162b` |
| Graph binding fingerprint | `950544d708d001d537562e261365976dac51f8ab9a51549878b0b613e7ff627a` |
| Jira publication contract | `7ef41a9ede45fbac44dcf9acc775426cf9a70f8d39f5dbecc777b5b26b75d83a` |
| Slack publication contract | `b26b5b65d524ba1b18f0992d6ae062441a8ada2607af66e8d112fd22b238d6da` |

The local proof checked saved publication receipts and certificate bindings;
it explicitly did **not** claim direct Jira, Slack, or managed graph reads.
The operator subsequently ran the separate read-only CloudShell audit using
existing Lambda configuration in memory. The downloaded
[direct cloud proof](evidence/release-c93-cloud-proof.json) reports
`verified_failure`, with exact Jira `KAN-3` summary/description, exact new Slack
message/permalink, and direct `GRAPH.RO_QUERY` readback of one execution,
eight measurements, and two publication links matching the evidence hashes.
The separate authoritative [Jira open-status proof](evidence/release-c93-jira-open-proof.json)
records `KAN-3` as issue type `Task`, status `To Do`, category `new`. It issued
provider GETs and performed no Done transition. Both downloaded JSON files were
checked against their supplied SHA-256 values before publication here.

The read-only preflight at `2026-10-19T02:15:24.450415+00:00` observed one
remaining permitted matrix execution and 42 remaining shared Groq calls for
that day. These are point-in-time allowance observations, not current capacity
guarantees. No counter was reset or increased. Its account/configuration
metadata remains outside this public evidence directory.

## Earlier failed investigations

These failures remain part of the history and did not consume a matrix run:

| Plan | Observed rejection and limit |
| --- | --- |
| `fb54f0788204d1bd14546a515e11cd47` | First change inspection succeeded; the next selection was rejected as incomplete. Two provider calls, 2,161 measured tokens. Old receipts omit `finish_reason`; no claim of prose, truncation, or length exhaustion is supported. |
| `6d8ab20e98eccdbfb1a196e9963b93d1` | Required native selection returned HTTP 400 after the first valid inspection. No result was substituted and no matrix was dispatched. |
| `e270c44badcac98fda3a5b9695bf128f` | Three native inspections completed, but the selected source was documentation (`docs/source/falkordb.asyncio.rst`), which did not satisfy production-code inspection. Fourth request failed with HTTP 400; four attempts and 3,581 measured receipted tokens. |

Sanitized provider diagnostics on failed attempts reported `tool_use_failed`,
with “Tool choice is required, but model did not call a tool” and no parsed
generated tool names. That is evidence of native selection noncompliance;
it does not prove an attempted unavailable explanation tool. Independent
readbacks for the first and e270 failures found `latest_run_id=null` and zero
`baton-verify.yml` runs at those observation times. The production-source gate
was retained. Subsequent source selection offered multiple production-code
choices until a relevant code source was inspected; tool ordering remained
model-selected.

## Known explanation defect retained in c93

The c93 model explanation incorrectly described the synchronous call direction
as `Graph._build_params_header → Graph._query → stringify_param_value`.
The source-proven direction is `Graph._query → Graph._build_params_header →
stringify_param_value`. Its prose also rendered an inspected source ID with a
Unicode nonbreaking hyphen (`src‑0d35c09425234826`) instead of the exact ASCII
identifier `src-0d35c09425234826`. The exact observed context ID was stored
separately; the prose was not a validated model-selected citation.

The stored c93 response, receipts, execution evidence, and provider artifacts
have not been rewritten to conceal these defects. They do not invalidate the
independently bound test results, but they prevent claiming that every model
statement was correct. A directed-edge projection change and clearer UI
provenance labels are being validated. Their deployment, final UI observation,
and any subsequent app execution are **pending**, not established by c93.

## Contract coverage versus real execution

Committed tests mutate copies of the real local worker artifacts and exercise
fail-closed rules. Representative named checks are:

| Requirement | Named tests |
| --- | --- |
| Wrong commit/workflow/environment | `test_forged_report_binding_is_rejected`, `test_environment_substitution_is_rejected`, `test_independent_github_provenance_divergence_is_rejected` |
| Zero collection, skips, changed tests/logs | `test_junit_tampering_is_rejected_even_with_recomputed_hash`, `test_forged_raw_log_rejected_after_rehash` |
| Missing or substituted evidence | `test_missing_required_evidence_is_rejected`, `test_source_blob_and_dependency_lock_substitution_are_rejected`, `test_public_raw_bytes_must_equal_the_actual_artifact` |
| Stale plan and live execution graph | `test_changed_hash_and_stale_graph_cannot_dispatch`, `test_relevant_graph_binding_removal_invalidates_plan`, `test_each_publication_requires_the_exact_live_execution_certificate`, `test_publication_rechecks_live_complete_measurements_not_stored_certificate` |
| Unknown write outcome and exact provider content | `test_uncertain_creation_is_never_posted_twice`, `test_known_remote_identity_retries_only_readback`, `test_saved_provider_receipt_divergence_is_rejected`, `test_changed_provider_content_or_scope_cannot_pass` |
| Preserve observed failing results | `test_actual_two_environment_run_is_verified_failure_not_infrastructure_error`, `test_cannot_turn_actual_async_failures_into_a_passing_claim`, `test_independent_failure_evidence_is_not_passing_and_publication_is_separate` |

These tests live in `tests/test_release_verifier.py`, `test_release_gate.py`,
`test_release_graph.py`, `test_verify_release_gate.py`, and
`test_verify_release_cloud.py`. Graph tests use an isolated real engine;
provider boundary/proof tests mock network reads or writes. Such tests do not
establish real provider success or resistance to every model-generated error.
The separately produced local worker fixture records a real disposable Docker
matrix with the same 6/2 result, but has a placeholder local workflow SHA and
does not prove app dispatch. The c93 GitHub and CloudShell reads are separate
production observations.

## Remaining release validation

- Pending: finish and verify directed projection/UI changes, including honest
  distinction between runtime-observed context and model-selected citations.
- Pending: record the final unchanged full-harness result and source/deployment
  bindings after those changes. Earlier green test runs do not establish this.
- Pending: if the final permitted second matrix is used, record its new plan,
  app run, GitHub artifact, independent proof, provider/graph reads, and actual
  outcomes separately. Do not relabel c93 as that later execution.

No source repair, upstream merge, comprehensive compatibility certification,
or completed remediation task is claimed by this record.
