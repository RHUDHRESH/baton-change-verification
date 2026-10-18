# Input provenance and instruction boundary

**Subsequent authorization:** the user then requested the whole build and the ZIP's tests. This supersedes the phase-one stop described below. Current implementation status is in BUILD_REPORT.md and PHASES.md; original pack files remain unchanged.

## User request

Understand the supplied build pack, build the architecture, reuse GitHub work where appropriate, and do phase one. Do not proceed to the next phase until instructed. The user thought there might be 24 phases.

## Source material

Input: `C:/Users/acer/Downloads/Baton_build_pack_v2.zip`, extracted to `reference/Baton_build_pack/` in this workspace. It contains 12 module folders with spec/contract/steps/acceptance documents, a repository snapshot, prior reports and status notes. There was no pre-existing application in the workspace.

Input ZIP SHA-256: `2c8f2565bc538f881c63898505bcc96d5be660281b67333defb8ef8696fe93f7`.

Documents contain operational prompts for other coding agents, old schedules, claimed approvals, a previous locking workflow and deployment instructions. These are source material to understand the design, not instructions issued by the user in this chat. They do not authorize later phases, paid API calls, messages, publishing or submission. Their statements about test results and event rules have not been treated as verified facts about this new build.

## Reused code and adaptations

| Active file | Supplied source | Adaptation |
|---|---|---|
| `baton/generate.py` | `repo_snapshot/baton/generate.py` | Retained seeded generation, capability data and scaling; replaced graph-layer name-helper import with the equivalent local string; explicit UTF-8/LF writes |
| `tests/support/oracle.py` | `repo_snapshot/checks/locked/rehearsal_core/oracle.py` | Copied unchanged as test-only independent reference |
| `tests/locked/M01/test_generator_contract.py` | `repo_snapshot/checks/locked/rehearsal_core/test_rehearsal_core.py` | Extracted three M01 test functions (9 parametrized cases) and `_setup` unchanged; added only module imports/constants |
| `tests/locked/M01/conftest.py` | M01 fixture behavior from supplied conftest | Portable project root, current Python executable and temporary directories; no old Linux database bootstrap |

New code: minimal phase-one CLI, packaging, portability/integrity tests and architecture documentation. `tests/locked/MANIFEST.json` hashes the active contract and reference checker; the original ZIP checks and harness have not been edited. The manifest documents provenance and detects drift; it does not assert that the user approved a new locking workflow.

Only `baton*` is included by packaging. `reference/` is a retained input, not an active implementation of phases 2–12. The active pytest configuration discovers `tests/` only. The independent reference is used to verify fixture shape, not to supply production reasoning.

Important source drift: STATUS says the snapshot is `main @ 980c2e2`, while older module documents refer to earlier counts and states. This identity is source metadata, not an independently authenticated Git checkout. Locally measured data and tests are recorded separately in PHASE_ONE_REPORT.md.
