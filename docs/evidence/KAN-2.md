# KAN-2: grow-only tensor and restore verification

**Local verification complete; evidence publication and provider updates pending.** All 20 recorded checks met their stated expectations, including two real RDB reloads. The post-run evidence audit was verified at **2026-10-18 15:26:47 UTC**. This report does not mark Jira or workspace work Done, close the upstream issue, claim an upstream fix or merge, or establish that the deployed Baton service runs this upstream source revision.

Work tracked by [Jira KAN-2](https://rhudhresh3697.atlassian.net/browse/KAN-2), [the original Slack task message](https://raptorflow.slack.com/archives/C0CA7B1BYTT/p1792334785098199), and workspace task `task-agent-c108922c16a39ceaa82623d5748c4df0`. The public source is [FalkorDB issue #3246](https://github.com/FalkorDB/FalkorDB/issues/3246), which identifies the grow-only change in [PR #3250](https://github.com/FalkorDB/FalkorDB/pull/3250).

## Execution and source

**Codex executed the code checks in an isolated Docker container. Groq and AWS Lambda did not execute them.** Groq previously created the verification task through Baton's graph tools; Lambda hosts the app and provider adapters.

| Input | Recorded value |
| --- | --- |
| Upstream head | [`d8190da5a99b4207e847e2fa2547911d96bd9e61`](https://github.com/FalkorDB/FalkorDB/commit/d8190da5a99b4207e847e2fa2547911d96bd9e61) |
| Parent behavior | [`660bf0159b03de6aca093c26452c3871573d86fb`](https://github.com/FalkorDB/FalkorDB/commit/660bf0159b03de6aca093c26452c3871573d86fb) |
| Image manifest | `ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7` |
| Runner / checkout | `baton-kan2-executor` / `/work` |
| Rust / Cargo | `rustc 1.99.0 (b940084d7 2026-09-28)` / `cargo 1.99.0 (5f94df478 2026-08-27)` |
| Build environment | `CARGO_BUILD_JOBS=2`, `CARGO_PROFILE_RELEASE_LTO=false` |
| Source checks | 957 tracked blobs matched the pinned head before execution and after both patches were removed |

No credentials, provider secrets, host credential directories, or Docker socket were passed into this runner. The image and source were public inputs. Reproduction commands, patch hashes, attribution, and upstream SSPL license are in [the fixture README](kan2-fixtures/README.md).

## Recorded results

| Check | Actual recorded result |
| --- | --- |
| Initial unpatched graph library | **529 passed, 1 failed, 17 ignored**, exit 101; failure was `cap_at_or_above_batch_size_is_ignored` |
| Constructor workaround applied; graph library rerun | **530 passed, 0 failed, 17 ignored**, exit 0 |
| Head tensor resize and graph restore, debug and release | Four exact checks; **1 passed, 0 failed, 0 ignored each** |
| Controlled parent resize/restore behavior | Four exact checks; **0 passed, 1 failed, 0 ignored each**, exit 101; expected invariant violations detailed below |
| Parent-behavior patch reversed; head checks repeated | All four debug/release checks again recorded **1 passed, 0 failed, 0 ignored each** |
| `cargo fmt --all --check` | Exit 0 |
| Both patches removed; tracked source verified | **957 blobs, zero mismatches** |
| Module build | `cargo build --locked`, exit 0 |
| Real RDB save/reload | **Two reloads passed**; exact node and parallel-edge records preserved |

The 17 ignored graph-library cases are upstream opt-in measurement benchmarks/probes, including timing-only planner and matrix-cost checks. They were not executed and are not counted as passed. The full suite above is the debug-profile graph library; the release checks are the two named regression cases, not a full release suite.

The controlled baseline restores the parent's shrink-and-prune implementation while retaining the head's regression tests and dimension accessors. **That parent already pruned `me` entries; it is not the original orphaned-edge implementation.** The negative checks demonstrate the grow-only contract:

- Debug resize fails because the expected “never shrinks” panic does not occur.
- Release resize reports an actual `(4, 4)` tensor instead of the expected `(8, 8)`.
- Debug and release restore each report `node_cap 16384 below the saved size` of 40960.

These are executed test failures, not compile failures or empty filtered runs. Their purpose is to show that the retained regressions distinguish parent behavior from the grow-only head.

## Separate constructor workaround and limits

The initial full-suite failure was retained rather than discarded. A guarded-match constructor produced an unexpected batch ceiling in the recorded optimized toolchain. The local [cap-clamp patch](kan2-fixtures/cap-clamp.patch) expresses the same intended ceiling with `unwrap_or(...).clamp(...)`; it changes only `graph/src/runtime/ops/batched_result_emitter.rs`, leaving the tensor/restore source and regression tests untouched.

The [standalone reproduction](kan2-fixtures/compiler-repro.rs) observed the discrepancy at optimization levels 1–3, but not level 0, using the pinned image's x86_64 Rust 1.99.0 / LLVM 23.1.1 toolchain. This is a bounded observation, not a universal compiler diagnosis. The successful full suite therefore means **pinned upstream source plus this disclosed local workaround**, not an unmodified-head pass. No patch was submitted upstream by this work.

The actual patched source hash was observed during the RDB module-build stage and matched the pinned source plus the reviewed patch; [the proof](kan2-logs/patched-source-proof.json) records that observation. This file-hash measurement was not taken during the earlier unit tests. The later audit checked logs, commands, known negative-check failure reasons, actual runner image/environment, patch artifacts, and restored source bytes; it does not imply all those audit checks ran before the original execution.

## Real RDB preservation

The isolated module created 90,001 nodes, added two parallel `R` relationships from node 0 to node 1, and deleted the other 89,999 nodes. After `SAVE` and each of two `DEBUG RELOAD` operations, the [recorded snapshot](kan2-logs/rdb_roundtrip.json) remained exactly:

```text
Node rows [id, i]:             [[0, 0], [1, 1]]
Edge rows [src, dst, id, tag]:  [[0, 1, 0, "first"], [0, 1, 1, "second"]]
Edge count:                   2
```

These checks demonstrate preservation of these node IDs/properties and parallel-edge IDs/endpoints/properties through two real reloads. They do not expose internal matrix dimensions; the graph unit regressions test that invariant. The isolated Redis server was stopped after the run, and the [server log](kan2-logs/rdb-server.log) is retained. No latency, throughput, or memory speedup is established by these correctness checks.

## Reviewable evidence

The review package includes [the exact execution manifest](execution.json) and [raw logs](kan2-logs/), including the [retained initial failure](kan2-logs/initial_graph_library.log), [successful graph library run](kan2-logs/head_graph_library.log), and [constructor reproduction](kan2-logs/cap_clamp_repro.log). The manifest records command arguments, exit codes, counts, and log hashes; [SHA256SUMS](kan2-logs/SHA256SUMS) covers all 19 exported nonempty log/evidence files. All nonempty audited check outputs are included; the five empty patch/format logs are represented by their recorded zero-byte lengths and SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` rather than empty files.

The [unit harness](../../scripts/verify_kan2.py) and [RDB harness](../../scripts/verify_kan2_rdb.py) define the checks; their cleanup and failure-reporting paths also have [mock failure tests](../../tests/test_kan2_runner.py). Those mocks verify reporting behavior and are separate from the actual Rust/Docker execution evidence above.

The package still needs an immutable committed evidence URL before provider publication. Jira, Slack, and workspace status changes require their own successful provider writes and read-back; no such completion action is claimed in this document.
