# KAN-2 reproducibility fixtures

These fixtures derive from [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB), pinned at commit [`d8190da5a99b4207e847e2fa2547911d96bd9e61`](https://github.com/FalkorDB/FalkorDB/commit/d8190da5a99b4207e847e2fa2547911d96bd9e61), authored by Avi Avni. Its parent is [`660bf0159b03de6aca093c26452c3871573d86fb`](https://github.com/FalkorDB/FalkorDB/commit/660bf0159b03de6aca093c26452c3871573d86fb).

- `before-grow-only.patch` is copied byte-for-byte from the local verification fixture `artifacts/kan2-before-grow-only.patch`. Applied to the pinned head, it restores the parent's shrink-and-prune resize/restore behavior while **retaining the head's regression tests and read-only dimension accessors**. It is a controlled counterfactual, not an exact parent checkout and **not the original orphaned-edge bug**: the parent's shrink path already prunes orphaned multi-edge IDs.
- `SSPL-1.0.txt` is an unchanged copy of the pinned upstream `LICENSE`. The upstream-derived patch material is distributed with that license; the enclosing repository's license does not replace it. Original upstream attribution remains in the upstream files and history.
- `cap-clamp.patch` is a local modification of upstream `graph/src/runtime/ops/batched_result_emitter.rs`. It expresses the existing batch ceiling as an explicit clamp; it does not change KAN-2's tensor/restore regressions. This is a separately recorded workaround for an optimized constructor result observed in the pinned toolchain, not an upstream KAN-2 change.
- `compiler-repro.rs` is original standalone reproduction code written for this investigation, copied from `artifacts/kan2/cap_clamp_repro.rs`. It prints guarded-match and explicit-clamp results for the same inputs. It asserts only the clamped results, so a zero exit code alone does not show that the guarded results agree.

The copied license retains the checked-out file's CRLF line endings. Its text matches the pinned Git license blob after newline normalization; the hash below describes the actual distributed bytes.

| File | SHA-256 |
| --- | --- |
| `before-grow-only.patch` | `314551bf6019eaf4fea6587af296fedfb8a0b4b5e7c79477272174160ef37f6e` |
| `SSPL-1.0.txt` | `df0ef9c83645474b414f82a5c6acb29dd7342a6f622f4a86b0a1c8aee1315258` |
| `cap-clamp.patch` | `68e10c01f60c06a5b5105c41ba954c6624720c187b70a4dc68edeb8365ed2000` |
| `compiler-repro.rs` | `8e0dee7e815e8de26704d4e7b11eadb88f500ec4b34ad9bc1d7ef307a668beb3` |

## Runner contract

[`scripts/verify_kan2.py`](../../../scripts/verify_kan2.py) requires an already prepared, isolated Docker container named `baton-kan2-executor`, with the exact upstream checkout at `/work` and patches staged at `/before-grow-only.patch` and `/cap-clamp.patch`. Use the pinned image manifest:

```text
ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7
```

The harness executes checks inside `/work`, applies the counterfactual patch, reverses it, and verifies restored source bytes. Do not use a shared development checkout as this runner. Pass **no credentials**, provider secrets, host credential directories, or Docker socket into the container. Public source and the build image require no application credentials.

From this repository's root in PowerShell, with a fresh container name:

```powershell
$kan2Image = 'ghcr.io/falkordb/falkordb-build@sha256:b5d954ebaf523da2171bb6306c9348a767963f32e0e1f0a3b1115a66f1e397a7'
docker pull $kan2Image
docker run --detach --name baton-kan2-executor --cap-drop=ALL --security-opt=no-new-privileges --env CARGO_BUILD_JOBS=2 --env CARGO_PROFILE_RELEASE_LTO=false --workdir /work $kan2Image sleep infinity
docker exec --workdir /work baton-kan2-executor git init
docker exec --workdir /work baton-kan2-executor git remote add origin https://github.com/FalkorDB/FalkorDB.git
docker exec --workdir /work baton-kan2-executor git fetch --depth=1 origin d8190da5a99b4207e847e2fa2547911d96bd9e61
docker exec --workdir /work baton-kan2-executor git -c core.autocrlf=false checkout --detach FETCH_HEAD
docker exec --workdir /work baton-kan2-executor git submodule update --init --recursive
docker cp docs/evidence/kan2-fixtures/before-grow-only.patch baton-kan2-executor:/before-grow-only.patch
docker cp docs/evidence/kan2-fixtures/cap-clamp.patch baton-kan2-executor:/cap-clamp.patch
python scripts/verify_kan2.py
```

Stop on any unsuccessful command. The bootstrap above uses no host mounts, inherited host environment files, or published ports. The image contains native build dependencies; public Git/Cargo fetches still require network access. The harness records tool versions and verifies tracked source bytes rather than trusting a copied Git index.

## Standalone constructor reproduction

Run in the prepared runner, independently of the upstream patches:

```powershell
docker cp docs/evidence/kan2-fixtures/compiler-repro.rs baton-kan2-executor:/tmp/kan2-cap-struct.rs
docker exec baton-kan2-executor rustc --version --verbose
foreach ($kan2Opt in 0,1,2,3) {
    docker exec baton-kan2-executor rustc --edition=2024 -Awarnings -C "opt-level=$kan2Opt" /tmp/kan2-cap-struct.rs -o /tmp/kan2-cap-struct
    docker exec baton-kan2-executor /tmp/kan2-cap-struct
}
docker exec baton-kan2-executor rustc --edition=2024 -Awarnings -C opt-level=2 --emit=asm /tmp/kan2-cap-struct.rs -o /tmp/kan2-cap-struct.s
```

The recorded observation used **rustc 1.99.0 (`b940084d7`, 2026-09-28), x86_64-unknown-linux-gnu, LLVM 23.1.1**, inside the pinned image. At optimization level 0, both constructors printed 1024 for caps 1025 and `usize::MAX`. At levels 1, 2, and 3, the guarded constructor instead printed the input cap, while the clamped constructor printed 1024. Other listed inputs agreed. These are observations from the recorded executor; they are not a claim about every installation of that compiler version, other targets, or other code shapes. Compiler reproduction success does not establish that the full KAN-2 verification batch passed.

## RDB harness audit

The pinned upstream `src/reply.rs::reply_result` returns a one-element statistics array for queries without `RETURN`; row-producing verbose replies contain headers, scalar rows, and statistics. `tests/flow/test_rdb_load.py::_test_data` reads the rows at index 1, and `test_nested_list_properties_survive_reload` uses `DEBUG RELOAD` before comparing those rows. The RDB harness must distinguish write-only seed/delete commands from snapshot reads. Each execution also needs a fresh Redis data directory so an old `kan2.rdb` cannot seed the next run implicitly.

The declared RDB checks compare node IDs/properties and parallel-edge IDs/endpoints/properties over real save/reload operations. They do **not** expose or prove internal matrix dimensions; the separate graph unit regressions cover that invariant. Audit compatibility and expected behavior are not recorded execution outcomes.

The fixture files identify the experimental inputs. Their presence does not establish that any batch, test, module build, or RDB round trip passed; those outcomes belong to separately recorded execution logs and reports.
