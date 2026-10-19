# Controlled native graph-dependence proof

**16 passed; zero failures, errors or skips; 17 deselected (3.13 seconds).**
This run tested commit `789c44694ee55c276a6a41db4628b39126de1606`, tree
`a01acdb42c37ed9a1ba1923c30175c84ed5fa696`, from a clean, read-only checkout.
The plan was **TEST-authored** by `tests/test_goal_graph.py::goal()`. Captured
public-source fixtures were isolated test inputs. There were **zero model or
provider calls and zero production graph mutations**. Successful semantic
interpretation, useful live planning and provider execution remain separate
acceptance requirements; this proof establishes none of those.

The native engine ran on a random localhost port: Redis server **8.10.2**,
FalkorDB graph module **42201 (4.22.1)**, vectorset module **1**, Python **3.13.5**.
Docker image ID:
`sha256:f9552c2b82e01d6ffb3018d02e05615bd3ab928a61074bd94aee0d0204cd8192`.

## Observed mutations and restoration

The supplemental probe began with `publish DEPENDS_ON inspect`, two native
`CITES` links to actual inspected test-source evidence, and ready steps
`["inspect"]`. [Recorded query results](goal-graph-dependence-789-probe.json)
retain the before, ablated and restored rows. `$plan` selected only this
temporary plan revision.

```cypher
MATCH (:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep)
OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:GoalStep)
RETURN s.step_id,collect(d.step_id) ORDER BY s.step_id

MATCH (:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep)
OPTIONAL MATCH (s)-[:CITES]->(e:GoalEvidence)
RETURN s.step_id,collect(e.id) ORDER BY s.step_id
```

| Controlled change | Actual result |
| --- | --- |
| `MATCH (:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep)-[r:DEPENDS_ON]->() DELETE r` | Native read showed no dependency; readiness rejected with `Native plan dependency or step binding changed`. |
| Restore `publish DEPENDS_ON inspect` using `MERGE` | Ready steps returned `["inspect"]`. |
| `MATCH (:PlanRevision {id:$plan})-[:HAS_STEP]->(s:GoalStep)-[r:CITES]->() DELETE r` | Native read showed no citations; readiness rejected with `Native plan citation binding changed`. |
| Restore both steps' `CITES` links using the original evidence ID | Ready steps returned `["inspect"]`. |
| `CREATE (:Unrelated {id:'isolated-unrelated-fact',value:'irrelevant'})` in the isolated source graph | Selected-evidence fingerprint unchanged; ready steps remained `["inspect"]`. |
| Append a test-only comment to selected cached source content | Readiness rejected with `Relevant inspected evidence changed`. |
| Restore the original captured source bytes | Dependency/citation rows matched their initial values; ready steps returned `["inspect"]`. |

Fixture teardown deleted the temporary graphs and stopped the isolated engine.
The unrelated-node case does not establish unrelated-edge behavior for goal
plans. The separate release-plan edge test covers that distinct implementation.

## Test selection and retained hashes

Fifteen existing cases covered native DAG persistence, five selected-binding
mutations, relevant versus unrelated entity changes, reused step IDs across
revisions, three episode/action mutations, three invalid DAGs and forged
source-kind rejection. The sixteenth was the supplemental mutation/restoration
probe above. Completion receipts in these cases were test-authored, not
independently verified live provider receipts.

The exact historical command was:

```powershell
docker run --rm -v "${PWD}/artifacts/public-source-git:/workspace:ro" -v "${PWD}/artifacts/goals_graph_dependence_789_probe.py:/probe/test_goal_ablation.py:ro" -v "${PWD}/artifacts/goals-graph-dependence-789:/evidence" graphhacks-checks:latest python -m pytest tests/test_goal_graph.py /probe/test_goal_ablation.py -k 'native_goal_dag_survives or selected_native_freshness or selected_entity_binding or revision_reused_step or native_observation_removal or native_storage_rejects or source_kind_cannot or isolated_native_dependency' --junitxml=/evidence/junit.xml -q -p no:cacheprovider --tb=short
```

At execution, that checkout was pinned to `789c446`; it has since advanced.
To rerun the fifteen tracked cases, use a fresh detached checkout of the exact
commit, build `deploy/Dockerfile.checks`, and use the same pytest selection
without the supplemental `/probe` path. The supplemental script and full JUnit
record are retained as local audit artifacts, with hashes below; their presence
is not required by the application's normal checks.

| Artifact | SHA-256 |
| --- | --- |
| Full local proof JSON, `artifacts/goals-graph-dependence-789-proof.json` | `9c6fc129c771c93b7aa9b6f2f7a53bec5e7cda6d75a82d30e3300e4a9fb33221` |
| Supplemental probe source (5,713 bytes) | `009472cae4581d424f0b161735a2da7b1874869f86a3fb0ac348f79ad2068843` |
| JUnit XML (2,369 bytes) | `c4ba080f20f3b0eaa9cf4c78d501f0a492a5633af373125eb393f3c7a2f2c86e` |
| Probe JSON (3,099 bytes; published here byte-identically) | `ad7075f351b5eb93391eb2b3f12d450005c465f07b27a7355dd69466880bea1b` |
| Pinned `fixtures/release_py211/public_sources.json` (294,939 bytes) | `03d2dc5912da732f44d6b1dc5f30d04fbdd869eeb866290d0112ee1e89a2227c` |

These results support native graph integrity and selected-fact freshness guards.
They do not establish that an AI chose a correct goal, plan or next action.
