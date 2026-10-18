# Recent graph research and company-context implementation

Evidence checked 2026-10-18. Requested window: **2026-10-04 through 2026-10-18 inclusive**.

This report distinguishes a recent implementation change from an original research method. Three relevant recent sources were verified, but they do **not** establish three newly invented state-of-the-art algorithms. Bulk reads and column projection predate this window. No exponential speedup, published benchmark reproduction, or state-of-the-art accuracy is claimed.

## Source and implementation ledger

| Source | Earliest verified public date and release | What changed | Compatible adaptation here | Reproduction limits |
| --- | --- | --- | --- | --- |
| Microsoft GraphRAG [PR #2591](https://github.com/microsoft/graphrag/pull/2591), [v3.3.0](https://github.com/microsoft/graphrag/releases/tag/v3.3.0) | PR opened **2026-10-07**, merged and released **2026-10-08** | Bulk cache reads deduplicate keys, preserve namespaces, and split large SQLite requests into bounded batches. | `overview()` uses two fixed graph reads for all work and shared-file paths, deduplicates repeated contributions, and selects the graph named by the captured snapshot. | Engineering adaptation; this code does not implement GraphRAG's cache API, SQLite dispatch, cleanup concurrency, or its 500-key batches. Namespace isolation here means selecting the imported snapshot graph. |
| Cognee [PR #5745](https://github.com/topoteretes/cognee/pull/5745), [v1.6.4](https://github.com/topoteretes/cognee/releases/tag/v1.6.4) | PR opened and merged **2026-10-13**; release **2026-10-13** | Vector search avoids retrieving raw embedding columns that consumers do not use. | Contribution queries return explicit account and work maps containing only consumed properties, rather than `properties(a)` and `properties(w)`. | Engineering adaptation of payload projection to Cypher. This demo has no embedding column, pgvector, or LanceDB. Cognee's reported production failure and speed observations are not measurements of this app. |
| Tang et al., [GraphRAG-LTM, arXiv:2610.19549v1](https://arxiv.org/abs/2610.19549v1), [full text](https://arxiv.org/html/2610.19549v1) | First arXiv submission **2026-10-14 04:04:34 UTC** | Studies how query perturbations and deletion of bridge triplets disrupt evidence propagation. | Each shared-file explanation exposes which captured file sources are single-source cuts. Tests remove evidence at either endpoint and verify unsupported paths disappear. | Research-inspired local robustness diagnostic. Source deletion differs from triplet deletion; no rank attack, retriever gradient, semantic constraint, QA model, or published dataset experiment is reproduced. This does not establish a new defense or SOTA result. |

An October search hit for [Dissecting GraphRAG](https://aclanthology.org/2026.tacl-1.29/) was excluded: its primary page establishes the year but not an original release inside the requested fortnight. An updated page or search-engine date does not establish first publication.

## Actual company context

The company view uses captured public records from **FalkorDB/FalkorDB** and **FalkorDB/falkordb-py**. `server/public_workspace.py` owns capture and import. `server/company_brain.py` reads the pinned graph and snapshot, then returns:

- Public contributor accounts, their authored issues/PRs, and source-cited `AUTHORED → IN_REPOSITORY` paths. Account activity does not establish employment, team membership, or internal ownership.
- Open work with no assignees in its captured GitHub record, with an action to confirm triage responsibility. This is a captured public status, not an inferred internal assignment.
- Separate review states for an uncaptured endpoint and a captured endpoint with no review records. Missing capture does not mean a PR has no reviewers.
- A varied triage queue with a rank, a stated ranking basis, and a contributor-to-work-to-repository evidence path for each suggestion. It retains every supported gap, presents different work/kinds/repositories before repeats, and starts with captured review gaps when available. The ordering is a display policy; it does not infer business urgency or severity.
- Shared-file paths only when both work items belong to the same captured repository, contributor IDs agree with the captured items, and each file edge has its own exact GitHub PR files endpoint. The suggested action is to compare overlapping changes and ask contributors for context. Shared files do not prove a dependency.
- Single-source deletion sensitivity for each shared-file path. Capturing the same endpoint repeatedly is not independent corroboration.

Unknown graph items, unrecognized source IDs, mismatched contributors/repositories, and unsupported file endpoints are excluded. Displayed work values come from the captured snapshot. No graph failure is replaced with a fixture. The two graph queries are read-only and fixed; the view never asks a model to generate Cypher.

The import samples at most eight open issues and eight recently updated PRs per repository. Only the two most recently updated PRs per repository capture files/reviews. This is not a company-wide inventory. The company query caps returned contribution rows at 100 and shared-file paths at 50. `diagnostics` reports when either cap is reached. **A LIMIT bounds returned rows, not database scan work.** Live database profiling is still needed to assess traversal and sort costs.

## Measurements and validation

Command, from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_company_brain.py -q -s --override-ini addopts=
```

Observed result after the queue improvement: **15 passed in 0.92s**. Graph I/O is mocked; the test records are explicitly synthetic. No paid provider, Docker service, live graph query, or live GitHub import is used by these tests.

| Measure | Baseline | Adaptation | Interpretation |
| --- | ---: | ---: | --- |
| Graph round trips for 32 contribution rows plus one shared-file read | 33, a declared one-read-per-item baseline | 2 observed mocked `ro_query` calls | 93.94% fewer calls against that baseline. No network latency or production speedup was measured. |
| Serialized JSON response for 32 synthetic rows matching imported graph-property shape | 13,880 bytes, full account/work property maps | 3,217 bytes, consumed IDs only | 76.82% fewer serialized bytes. Display fields are read from the pinned local snapshot. This excludes driver protocol overhead and is not a live network measurement. |
| Two single-file-source deletion cases | One supported shared-file path before deletion | Unsupported path suppressed in both endpoint-deletion tests | Integrity behavior under missing evidence, not a QA accuracy gain or proof of robustness against arbitrary graph attacks. |

The byte test includes the graph schema's `name`, `repo`, `number`, `updated_at`, and repeated `source_ids` fields in the full-map baseline; it does not inject large embedding vectors that this app never stores. The call baseline is a transparent comparator rather than a claim about an earlier production implementation.

Additional tests cover duplicate rows, bot account types, wrong contributors, changed graph titles, wrong endpoint URLs, provenance intersection, missing reviews, row-cap reporting, and propagation of graph failure. Cypher map projections and server execution require the parent task's live FalkorDB smoke test; mocked tests do not validate database syntax or indexes.

### Live compatibility correction

The first deployed company query failed on FalkorDB Cloud **v4.22.0** with `ORDER BY cannot reference variables not projected or grouped in this scope`. It aggregated source IDs while returning the work ID inside a map, then tried to sort by `w.id`. The corrected query groups the author/work/repository scalar IDs in `WITH`, sorts by the grouped `work_id`, applies the row limit, and only then constructs the output maps. The response row shape and two-query contract are preserved. A read-only live request on 2026-10-18 succeeded after that correction, as recorded below.

### Live company queue audit and improvement

The [live company endpoint](https://kdeokfokg2d4jygx4ul3xwso5a0injxf.lambda-url.ap-south-1.on.aws/api/public/company) returned snapshot `a497740dd9c5359440cd4a7f`, captured **2026-10-18 13:08:20 UTC**: 16 public contributor accounts, 28 work items, 28 source-backed contribution paths, 18 sources, and 33 gaps. The gaps comprise 23 unassigned items, nine PRs whose review endpoint was not captured, and one captured endpoint with no review records. There are no captured shared-file paths; no overlaps or internal dependencies were invented to fill that absence.

The existing five-card preview contained five generic unassigned-work suggestions from one repository. Applying the new queue policy to that actual endpoint response locally retained all 33 gaps and produced a five-card preview covering **three gap kinds, two repositories, and five distinct work items**. Its first suggestion is to inspect the captured review status of `FalkorDB/falkordb-py#297`; its evidence remains the captured reviews endpoint, not an inference that nobody reviewed the PR. This comparison measures presentation coverage, not improved correctness or business impact. It tests the local queue helper against a real response; the updated queue still needs the parent task's deployment/UI verification.

## Requirement status

Three recent sources and three useful compatible adaptations are implemented and distinguished above. The stronger requirement of **three original, newly released SOTA techniques per agent** remains unproven for this specialist. Relabeling old engineering principles or a partial diagnostic as new SOTA research would misrepresent the result. No extra method is added solely to meet a numerical quota.
