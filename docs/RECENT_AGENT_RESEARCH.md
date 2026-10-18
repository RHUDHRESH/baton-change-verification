# Recent reasoning-agent research and bounded implementation

Reviewed on 18 October 2026. Eligibility here uses the **first public arXiv v1 submission**, within the requested 4 October 2026 after 13:31 UTC through 18 October window. Recent publication alone does not establish state of the art, and paper results are not measurements of Baton. Three distinct techniques inform the limited practical adaptations below. A fourth, incompatible technique was reviewed separately. These are scoped adaptations, not full reproductions of the research systems.

## 1. Evidence-First Agentic Verification (Sauron) — narrow mechanical adaptation

[Primary paper and submission history](https://arxiv.org/abs/2610.17724), v1 **13 October 2026, 04:58:04 UTC**. [Method, including independent claim checking](https://arxiv.org/html/2610.17724v1).

The verifier investigates environment state and execution history, checks claimed evidence independently, and attaches evidence receipts to criterion decisions. The paper reports 0.96 versus 0.92 F1 at 23% lower cost for its GPT-5.6 Sol comparison; these are the paper's results.

Baton independently rereads each cited captured source immediately before the local task write. It checks the observed source hash, canonical payload hash, URL and capture timestamp, and denies a write if the imported graph changed. The resulting receipts distinguish source consistency from exact task-title/status/target readback. The action retains the observed graph connections for inspection. Tests inject payload changes even when the stored raw-source hash is unchanged, metadata changes and missing evidence. This checks stored provenance and local state, **not natural-language entailment, remote-source freshness or the correctness of the proposed task**. No extra verifier-model call is used.

## 2. Agent-Controlled Forgetting — limited reversible context curation

[Primary paper and submission history](https://arxiv.org/abs/2610.10590), v1 **6 October 2026, 18:13:48 UTC**. [Method and limitations](https://arxiv.org/html/2610.10590v1).

The paper exposes model-selected archival and recovery of tool observations while protecting instruction messages. Its exploratory findings vary by workload, including cases without savings or with worse assessed quality. It also describes an earlier internal implementation in February; **October 6 is the paper's initial public release, not a claim that reversible memory was invented then**.

Baton's adaptation is deliberately smaller: each observation is presented once in full. On later turns, older tool results omit reproducible query strings while keeping every returned graph fact, limitation, source ID and excerpt. Exact originals remain in the durable run trace, with the compact view carrying its trace index and SHA-256 reference. `read_run` recovers that record for inspection. System/user/assistant messages and the newest tool result stay unchanged. The policy is deterministic; it does **not** reproduce model-directed forgetting, model-accessible recovery during the four-turn loop or the paper's experiments. A local test compares active versus retained character counts, without treating that as a measured token, latency or reasoning improvement.

## 3. NOMOS — static Resolve subset and deterministic stage policy

[Primary paper and submission history](https://arxiv.org/abs/2610.11030), v1 **8 October 2026, 00:23:22 UTC**. [Algorithm 1 and static verification, section 3.3](https://arxiv.org/html/2610.11030v1).

NOMOS compiles policy into data rules, checks whether those rules can operate against tool schemas, and enforces them deterministically. Its Resolve pass checks enabling tools, argument bindings and write scope; its separate replay step screens behavioral problems. Those structural checks require no runtime model call.

Baton adapts the static subset to authored rules over a closed predicate vocabulary. Before its first Groq request, `compile_policy` rejects unknown tools/predicates, absent or self-blocked enabling tools, argument/type mismatches and write-only rules attached to reads. A fixed-point reachability check also rejects cross-rule prerequisite cycles. The valid artifact generates the same allowed-tool stages as before; only completed real reads satisfy prerequisites. Existing item/source/citation validators enforce the argument predicates. The run records the rules, reachable layers and a SHA-256 binding the rules, schemas and predicate tables. Tests inject each structural defect and verify refusal before provider execution. This does **not** reproduce natural-language extraction, majority compilation, all NOMOS predicates, its behavioral-replay experiment or semantic policy certification. Invalid authored rules are rejected rather than automatically repaired.

## Additional review: Hybrid Reasoning Agents — not implemented

[Primary paper and submission history](https://arxiv.org/abs/2610.18861), v1 **13 October 2026, 17:59:31 UTC**. [Author implementation](https://github.com/togethercomputer/HybridAgent).

HybridLink connects continuous latent computation with textual tool interaction, with dedicated supervised and reinforcement training. The authors report gains across their evaluated models and benchmarks. This requires control over model internals and training/inference infrastructure. Baton's hosted Groq chat-completion API does not expose those operations. Changing prompts, reducing context or requesting reasoning effort would not implement HybridAgent. No such claim is made, and no paper gain is transferred to this application. It is not counted among the three implemented adaptations.

## Operational changes and verification

`server/graph_agent.py` retains the existing external tool catalog and function signatures. Per-run copied schemas bind `item_id` and `source_id` to the actual selected graph item and its captured sources; the complete item ID is repeated explicitly in the prompt. At the action stage, the `source_ids` item enum contains only sources actually inspected in this investigation, and its maximum length matches that set. Merely listing an available source in the work item does not authorize a citation. The model still chooses each tool call and its arguments. Scope validation remains strict even if the provider ignores the enum.

The loop allows at most four provider calls and uses a 650-token completion ceiling per call. The deadline begins before graph initialization. Provider-reported cumulative usage is checked before executing a selected tool; token preflight is a character estimate, **not a tokenizer or a hard guarantee about provider billing/TPM**. Incomplete generations with valid usage receipts retain that usage. Failures retain their stage, attempted provider count and rejected tool requests/arguments. No response or tool selection is substituted on failure.

## Audit of the live successful run and utility boundaries

The public stored run `a78eda3a462fffff94a3b073468be1e6` completed four Groq calls in 15,012 ms using 5,159 reported tokens. Its task reason names `graph/src/graph/graphblas/tensor.rs`, which was returned by the graph traversal. That supports a concrete connection between the observed file scope and the proposed task. The run cannot establish how much the graph caused the model's choice.

The sole citation, however, was a captured reviews endpoint. Its truncated excerpt spent most of its space on a bot's profile URLs, while the grow-only behavior appeared in the work-item description. Task-write verification succeeded; that did not establish that this citation supported the reason.

The resulting changes bind utility to inspectable data without adding model calls. Source selection now offers captured records containing the selected work-item number or that PR's changed-file list; the action also requires an inspected primary citation. Reviews remain readable context and cannot alone authorize a task. Issue/review/file fields are projected before excerpt truncation so substantive text appears before profile metadata. When graph traversal returns touched files, the task title or reason must name at least one exact returned path; prefixes and suffixes of another path do not pass. A `graph_scope` receipt reports this exact-membership check. If no files were sampled, the task remains source-scoped and the receipt explicitly states that repository co-membership establishes no dependency.

These checks establish provenance category and path membership, not semantic entailment or task usefulness. A misleading reason can still mention a real path, and source text can itself be wrong or malicious. The model does not execute code from evidence. Its proposed tools remain constrained by the catalog and stage policy.

A subsequent issue-3246 demo exposed another limitation: prefix-only excerpts dropped its `### Fix (PR #3250)` section, so the task proposed clearing stale IDs during shrinking instead of checking the stated grow-only fix. Head/tail clipping alone also missed this section when long measurements followed it. Work-item descriptions now retain verbatim head, priority-section opening and tail within 1,000 characters; Markdown Fix, Resolution and Workaround headings outrank Expected behavior. Source excerpts compact string values before JSON serialization and stay within 1,400 characters, with explicit omission markers and valid JSON. The prompt directs the model to read fixes/workarounds and verify their stated desired behavior. This preserves evidence; it does not certify the model's interpretation.

The local protocol suite uses mocked provider, graph and storage boundaries and verifies successful four-call execution, staged action gating, exact graph readback, source tampering, stale imports, provider errors, malformed selections, cumulative usage overflow, incomplete generation accounting, deadline refusal, recoverable original traces, static policy defects, dynamic citation scoping, unrelated task rejection, review-only citation refusal, path-boundary checks, absent file coverage, terminal and middle-fix preservation in long issue bodies, valid bounded JSON for escaped file patches and a forbidden tool proposal after injected public instructions. The 46 tests pass locally. They do not measure live model quality, cloud latency or the papers' benchmark performance; the adversarial proposal test verifies executor refusal, not model resistance to injection.

Validation command: `.venv/Scripts/python.exe -m pytest tests/test_graph_agent.py -q --override-ini addopts=`.
