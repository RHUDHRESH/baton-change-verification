# Graph-derived change verification

This profile verifies the already merged [FalkorDB-py PR #212](https://github.com/FalkorDB/falkordb-py/pull/212), associated with [issue #211](https://github.com/FalkorDB/falkordb-py/issues/211). It does not author a new fix or merge upstream. The existing Rust workflow is separate.

## Why the graph changes the work

Pinned Python source establishes that the asynchronous graph client inherits parameter-header construction from the synchronous Graph class. That construction invokes the recursive value serializer. Scoped AST extraction records those calls, inheritance and source spans in FalkorDB. Reviewed associations connect the supported sync and async API contracts to four existing regression tests; those associations are labelled as reviewed bindings, not measured coverage.

Fixed parameterized graph traversals derive the required test IDs and witnesses. The execution registry translates returned IDs into approved commands. Missing inheritance or other required coverage produces an incomplete plan. A relevant change invalidates its sealed binding; unrelated graph additions do not. Graph tests exercise both conditions using an isolated engine.

The source corpus includes public issue/PR discussion, README/API documentation, pinned implementation and tests. Earlier escaping suggestions remain proposals; the merged implementation and negative assertions reject literal-backtick and empty keys. Public contributor activity does not establish employment or internal responsibility. Jira KAN and Raptorflow Slack are the operator's workspaces, not FalkorDB's internal systems.

## Execution boundary

- Source: `FalkorDB/falkordb-py@207000da70ca183ab02990a98bdd97d0a3e3bb1b`.
- Required environments: Redis client 8.0.0 and 8.1.0, with the same pinned Python and FalkorDB server images. Exact dependencies use reviewed wheel hashes.
- Required cases: `test_param_non_identifier_keys` and `test_param_invalid_keys_rejected` in each of `tests/test_graph.py` and `tests/test_async_graph.py`.
- Tests remain unchanged. No source repair, arbitrary commands or browser-selected repository is accepted.
- Each environment receives a disposable database. The sync fixture runs `FLUSHDB`; cloud/shared databases are never used for these tests.
- Test containers receive no cloud credential, callback capability, host mount or Docker socket.

The independent verifier checks the actual GitHub run/workflow identity, completed execute job, artifact digest, source archive/blobs, environment manifests, exact test identities, collection, raw logs, JUnit outcomes and dependency locks. A callback or zero exit status alone cannot establish success. Failed checks are retained as verified failing evidence; missing or substituted evidence is unconfirmed.

## App and publication

An authenticated main-URL action creates a plan, requires actual successful Groq investigation, seals the relevant graph/source/policy binding, then dispatches the approved workflow. Groq selects typed MCP tools and returns an explicitly labelled explanation; it cannot remove deterministic obligations.

Execution and publication are separately finalized. A verified failing matrix remains blocked even if one environment passes or both provider publications succeed. Run-specific Jira/Slack content contains plan/run identities, per-environment results and an immutable evidence reference. Control-store intents precede writes; separate provider reads verify the resulting artifacts. Ambiguous writes are never automatically repeated. A remediation task is not transitioned to Done by publication.

## Reproduction and evidence limits

Run `docker compose --profile checks run --rm checks` for the existing locked judge and separately reported application suites, including the release gate. These tests validate contracts and isolated graph behavior; mocked provider boundaries do not establish live integration success.

The upstream profile also has a local Docker smoke path in `scripts/release_gate_worker.py --help`. Local smoke artifacts are research/test evidence. Only a new app-dispatched workflow plus independent readback establishes a production run. Hosted runner queue/image-pull time is not covered by the local timing measurement.

This is one audited change family and one declared compatibility matrix, not general dependency discovery or comprehensive release certification. A full conventional suite can catch the same async failure. The retrospective comparison demonstrates explainable scope selection and enforcement, not a universal performance advantage.
