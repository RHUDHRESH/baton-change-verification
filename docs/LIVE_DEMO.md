# Live company-work demo

Open https://baton-workspace.vercel.app and select FalkorDB issue
[#3246](https://github.com/FalkorDB/FalkorDB/issues/3246).
The source reports latent stale multi-edge IDs when a tensor shrinks and names
PR #3250's grow-only fix. Public contributor accounts do not establish employment.

The operator starts **Investigate & create verification task**. Groq chooses
arguments for four tools: read the graph work item, traverse connected work and
contributors, inspect a primary captured source, and save a task. The graph returns
PR #3250 and its recorded author; repository co-membership alone is not a dependency.
No changed-file coverage was sampled for the root issue, so its task is source-scoped.

The operator reviews the proposed task, then explicitly chooses **Create Jira issue**
and **Post to Slack** on that task. Each adapter separately reads back its created
artifact, checks its contents, and writes the artifact relationship into FalkorDB.
These are the user's KAN project and Raptorflow `#baton-demo` channel, not FalkorDB's
internal workspaces. Creating verification work does not resolve the upstream bug.

During the demo, review caught an initial incorrect shrink/prune proposal. It was
not published externally. The bounded evidence projection had omitted the issue's
fix section. Commit `3f47f3f` preserves fix/resolution/workaround/expected sections
alongside source openings and endings, retains valid JSON, and labels omissions.
The actual issue payload and 142 affected contract checks passed after this repair.
The original proposal remains an unpublished record, rather than being erased.

## Completed production run

- Agent run: `c108922c16a39ceaa82623d5748c4df0`, succeeded in 15,141 ms.
- Tools: `read_work_item` → `follow_connections` → `read_source` → `save_verification_task`.
- Primary captured source: `src-c21f9fc95e68bcb0`.
- Workspace task: `task-agent-c108922c16a39ceaa82623d5748c4df0`.
- Reviewed title: Verify Tensor::resize is grow-only and RDB load never shrinks dimensions.
- Created [Jira KAN-2](https://rhudhresh3697.atlassian.net/browse/KAN-2).
- Posted [the task to Slack](https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199).

The app's Jira and Slack buttons performed these actual writes on the main URL.
Each artifact passed separate provider read-back and appeared in a subsequent public
FalkorDB query through `LocalTask-[:PUBLISHED_AS]->ExternalArtifact`. Both artifacts
retain the same source hash; their task identities match the agent-created task.
The task remains To Do: its proposed code verification has not been executed by
Baton, and no upstream issue or pull request was modified.

Final Groq response receipt: `chatcmpl-1509ac29-1bc4-4bd6-8e44-9a67a9b946c7`.
All four provider receipts and full tool arguments/results are persisted in the
[agent run](https://baton-workspace.vercel.app/api/public/agent/c108922c16a39ceaa82623d5748c4df0).
