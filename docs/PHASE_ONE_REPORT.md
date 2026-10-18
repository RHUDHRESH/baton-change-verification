# Phase one verification

Historical phase-one report. The user later authorized the full build; see BUILD_REPORT.md for the current 124-test result and completed modules.

Verified 2026-10-18 on Windows with Python 3.12.14. Scope: M01 generator and architecture/reuse documentation. **No authorization to start phase two.**

## Result

**24 tests passed:** 9 supplied M01 contract cases and 15 additional portability, data integrity and scope checks. The isolated supplied-contract run also passed 9/9. No original assertion was weakened. The original ZIP files remain untouched: all 158 file entries were compared byte-for-byte against the archive, with zero changes.

The active generator's objects match the supplied snapshot for seed 7 at scales 1, 4 and 8. An additional check covers unique IDs, valid object references and the leaver's escalation invariant across seeds 0–59. The supplied cases verify repeat generation, seed sensitivity, fixture shapes, true/noise evidence eligibility, and strictly increasing W/R/G fixture coverage using the independent test reference. These are fixture tests, not a run of the future graph engine.

## Changes delivered

- Reused the supplied deterministic generator and preserved its capability/scaling behavior.
- Removed its import of the later graph layer, so phase one runs with the standard library alone.
- Added a minimal CLI, explicit UTF-8/LF output, installable package and pinned development requirements.
- Preserved the supplied pack under `reference/`, extracted its 9 M01 cases into an integrity-manifested suite, and added portability/scope checks.
- Documented architecture, phase gates, input provenance and the GitHub reuse register.

## Observed seed 7

| Field | Observed |
|---|---|
| Leaver | `hana.sharma` |
| People / duties | 9 / 11 |
| Events | 74 |
| Messages / job logs / tickets | 17 / 23 / 3 |
| Records | 44: 10 OWNER, 1 ROUTES_TO, 7 SHIFT, 4 ESCALATES_TO, 22 CAN |
| True + noise beliefs in separate grading file | 6 |
| Graph name returned in summary | `halden_7` (name only; no connection) |

The pack's old 22-record count omits the snapshot's 22 CAN records. The retained seed-7 world SHA-256 is `c11219d2c5b629689ee31df2f88b3bd70fd73b997fee41bbe4fcb461cca8b2b0`; grading-file SHA-256 is `792aa8a2de43263c9c99a8b1db594047e89dec0c90d6609a7601e3c4de965b95`.

## Packaging and commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/locked/M01 -q
.\.venv\Scripts\python.exe -m baton generate --seed 7 --out artifacts/seed7
uv build --wheel --out-dir artifacts/dist
```

Built `artifacts/dist/baton_departure-0.1.0-py3-none-any.whl`. Inspected the wheel: its only application files are `baton/__init__.py`, `baton/__main__.py` and `baton/generate.py`; the rest is package metadata. Installed it into a separate environment with no project dependencies, then ran the `baton` entry point from `artifacts/`, outside the source directory. Its generated files match the source-run files byte-for-byte.

Local outputs: `artifacts/seed7/world.json`, the separate grading file, the wheel and `artifacts/phase-one-verification.json`. These generated artifacts are gitignored and can be recreated using the commands above. The README and this report retain the useful measurements.

## Remaining boundary

The active CLI offers only `generate`; future commands are rejected. No FalkorDB instance, API, frontend, MCP server, extraction provider, external write or deployment has been started. The ZIP's previous 88/88 and evaluation claims are not reproduced or claimed by this build. Runtime licensing of the supplied generator remains unspecified; its source provenance is disclosed rather than assigning a new license to it.

The next potential phase is M02 (graph import and rehearsal), only after the user instructs us to continue.
