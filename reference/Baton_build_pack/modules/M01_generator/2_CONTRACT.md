# M01 · Generator · CONTRACT

Every line is copied from code or a locked check. Line numbers were checked on 18 Oct at 11:40 IST. `generate.py` had md5 `99efe932…` and was last changed at 05:56. `__main__.py` citations use md5 `14b34b50…`.

**Moving line numbers in `__main__.py`.** At about 11:58 IST the `ask` round (M4, still in progress) added an `ask` subparser and dispatch to baton/__main__.py (md5 `14b34b50…`). Lines 1–33 did not move. The demo parser is now at lines 42–46 and the dispatch at lines 54–77. The citations here use that file. If the ask round is reverted, line numbers above 33 go back (demo parser 34–38, dispatch 46–60).

## 1. CLI

```
python -m baton generate --seed N --out DIR
```
| Flag | Type | Required | Source |
|---|---|---|---|
| `--seed` | int | yes | baton/__main__.py:12 |
| `--out` | path | yes | baton/__main__.py:13 |

- It creates DIR if it is missing (`mkdir(parents=True, exist_ok=True)`, baton/generate.py:470).
- stdout gets one JSON line with sorted keys (baton/__main__.py:80): `{"beliefs": int, "counts": {"duties","events","joblogs","messages","people","records","tickets": int}, "graph": "halden_<seed>", "leaver": str, "out": str, "seed": int}` (baton/generate.py:473-476).
- Seed 7, observed by the writer at 11:36 IST: `counts = {duties 11, events 74, joblogs 23, messages 17, people 9, records 22, tickets 3}`, `beliefs 6`, `leaver "hana.sharma"`.
- Exit code 0 on success. A missing flag gives the standard argparse exit code 2 (seen for `rehearse`; argparse behaves the same way for every subcommand).

## 2. `world.json`, field by field

Top level (baton/generate.py:448-455). The file is written with `sort_keys=True, indent=1` (baton/generate.py:471).

| Field | Type | Value / rule | Source |
|---|---|---|---|
| `seed` | int | the `--seed` | baton/generate.py:449 |
| `label` | str | always `"FIXTURE"` | baton/generate.py:449 |
| `company` | str | always `"Halden"` | baton/generate.py:449 |
| `now` | int, epoch ms | `1_792_713_600_000`, which is Friday 2026-10-23 00:00 UTC, the leaver's last day | baton/generate.py:16, baton/generate.py:136 |
| `day_ms` | int | `86_400_000` | baton/generate.py:13 |
| `window_days` | int | `30` | baton/generate.py:15 |
| `leaver` | str | the id of `people[0]` before sorting | baton/generate.py:206 |
| `leave_at` | int, epoch ms | `now + day_ms` (Saturday 00:00 UTC) | baton/generate.py:137 |
| `people` | list | sorted by `id` | baton/generate.py:451 |
| `duties` | list | sorted by `id` | baton/generate.py:452 |
| `records` | list | ids `rec-0001…`, numbered after sorting by their JSON text | baton/generate.py:428-429 |
| `events` | list | ids `ev-0001…`, sorted by `(at, duty, label)` | baton/generate.py:430 |
| `messages` | list | ids `msg-0001…`, sorted by `(at, channel, author, text)` | baton/generate.py:431 |
| `joblogs` | list | ids `log-0001…`, sorted by `(at, job, actor, status)` | baton/generate.py:432 |
| `tickets` | list | ids `tkt-0001…`, sorted by `(at, author, text)` | baton/generate.py:433 |

### `people[]` (baton/generate.py:204-205)
| Field | Type | Rule |
|---|---|---|
| `id` | str | the name lower-cased, with non-letters turned into `.`, for example `"hana.sharma"` (baton/generate.py:124, baton/generate.py:204) |
| `name` | str | `"First Last"` (baton/generate.py:201) |
| `team` | str | one of `Platform`, `Security`, `Billing`, `Support`, `Data` (baton/generate.py:24-30) |
| `role` | str | from `ROLES[team]` (baton/generate.py:202) |
| `left_at` | int or `null` | `null` for active people; for people who already left, `now - (4..75) days + 17 h` (baton/generate.py:203) |

There are 6–9 active people (the leaver included) and 1–3 who have already left (baton/generate.py:192).

### `duties[]` (baton/generate.py:152)
| Field | Type | Values |
|---|---|---|
| `id` | str | `d-<slug>`, `d-oncall-<slug>` or `d-job-<slug>` (baton/generate.py:225, baton/generate.py:261, baton/generate.py:300, baton/generate.py:325) |
| `name` | str | a readable name |
| `kind` | str | `cert`, `renewal`, `review`, `drill`, `compliance`, `report`, `rotation`, `oncall`, `job` (baton/generate.py:45-54, baton/generate.py:215-220, baton/generate.py:261, baton/generate.py:300) |

### `records[]`: four types (the "systems of record")
| `type` | Fields (besides `id`, `type`) | Source |
|---|---|---|
| `OWNER` | `duty`, `person`, `since` (epoch ms, 45–700 days before now) | baton/generate.py:156-157 |
| `ROUTES_TO` | `duty`, `rota` (for example `"rota-edge"`) | baton/generate.py:262-263 |
| `SHIFT` | `rota`, `person`, `from`, `to` (epoch ms; one week long) | baton/generate.py:279-280 |
| `ESCALATES_TO` | `from_person`, `to_person` | baton/generate.py:163 |

### `events[]` (baton/generate.py:160)
`{id, duty, at (epoch ms), label}`. Events are **scheduled things**, not failures: cert expiry and reminders, job runs, rota handovers, review dates.

### `messages[]` (baton/generate.py:166)
`{id, channel, author (person id), at, text}`

### `joblogs[]` (baton/generate.py:307-308, baton/generate.py:312, baton/generate.py:330)
`{id, job (duty id), actor ("scheduler" or a person id), at, status ("failed" or "succeeded")}`

### `tickets[]` (baton/generate.py:347-348, baton/generate.py:418-419)
`{id, author ("Name (Customer)"), at, text}`

## 3. `answer_key.json` and the belief schema

Top level: `{leaver, true_beliefs[], noise_beliefs[]}`. Both lists are sorted by `id` (baton/generate.py:456-458).

### Belief (baton/generate.py:317-320, baton/generate.py:353-357, baton/generate.py:369-400, baton/generate.py:436-447)
| Field | Type | Rule |
|---|---|---|
| `id` | str | `blf-01`…, shuffled across true and noise beliefs so the number gives nothing away (baton/generate.py:444-447) |
| `person` | str | a person id |
| `duty` | str | an existing duty id (ghost job), or a **new** id that exists only in the belief, for example `promise-<customer>-<slug>` or `vendor-<slug>` (baton/generate.py:354, baton/generate.py:380) |
| `duty_name` | str | a readable name |
| `kind` | str | `job`, `promise` or `vendor` |
| `claim` | str | one readable sentence |
| `events` | list of `{at, label}` | extra scheduled events that exist only through this belief (promise due dates); `[]` for jobs (baton/generate.py:319, baton/generate.py:350-352) |
| `sources` | list of str | ids of messages, joblogs, tickets or records. A noise belief may cite a ticket id that does not exist (baton/generate.py:434, baton/generate.py:439) |

**The belief file the product reads** (`--beliefs FILE`) is a JSON **list** of these objects (checks/locked/rehearsal_core/conftest.py:58-61). The product needs only `id`, plus `at` on each event. Every other field is read with `.get` (baton/rehearse.py:88-90).

## 4. Planted shapes (what the world contains)
| Shape | What it tests | Source |
|---|---|---|
| 1–3 certs or renewals owned only by the leaver inside the window, plus one outside it | W, R and G all see these | baton/generate.py:221-232 |
| A "Renewal ticket opened" event before `leave_at` | events the leaver still covers | baton/generate.py:234-235 |
| A review co-owned by the leaver and a Platform stayer | a distractor: still covered | baton/generate.py:239-244 |
| Duties owned by stayers | distractors | baton/generate.py:245-250 |
| An orphan duty owned by someone long gone (only when 2+ people have left) | already broken, not the leaver's fault | baton/generate.py:251-255 |
| An on-call rota that still lists a departed primary, who escalates to the leaver | R and G see it, W does not | baton/generate.py:266-270 |
| 1–2 "ghost" jobs with no OWNER record, kept alive by the leaver's manual reruns (joblogs and a chat line) | G only | baton/generate.py:295-320 |
| 1–2 customer promises, seen only in chat and a ticket | G only | baton/generate.py:333-357 |
| 3–4 noise beliefs: one chat line; two chat lines (one source type); a missing ticket id; sometimes one joblog row | the gate must refuse all of them | baton/generate.py:363-400 |

**Invariant:** the leaver has no outgoing `ESCALATES_TO`. Escalations start only from stayers in the pool or from people who have left (baton/generate.py:264, baton/generate.py:270, baton/generate.py:273, baton/generate.py:276). Why it matters: the R lane walks *through* people who have left, so an outgoing escalation would quietly cover the leaver's own certs (loop/rounds/rehearsal_core-1.md, "Surprises").

## 5. Rules enforced by locked checks
- Same seed gives identical bytes in both files, and a different seed gives a different world (checks/locked/rehearsal_core/test_rehearsal_core.py:28-34).
- world.json must not contain `expected_failures`, `answer_key`, `true_beliefs` or `noise_beliefs`, in any case (checks/locked/rehearsal_core/test_rehearsal_core.py:41-43).
- The leaver is in `people` with `left_at` null, and at least 4 people are active (checks/locked/rehearsal_core/test_rehearsal_core.py:45-46).
- There is an `ESCALATES_TO` to the leaver from someone with `left_at <= now` (checks/locked/rehearsal_core/test_rehearsal_core.py:48-50).
- At least one event is at or after `now + window_days*day_ms`, and `messages`, `joblogs` and `tickets` are non-empty (checks/locked/rehearsal_core/test_rehearsal_core.py:52-54).
- Every true belief passes the gate, there are at least 3 noise beliefs, and none of them passes (checks/locked/rehearsal_core/test_rehearsal_core.py:56-57).
- For every seed, the oracle sees W < R < G and R ⊆ G (checks/locked/rehearsal_core/test_rehearsal_core.py:93-96).
- Only `generate.py` may contain the string `answer_key`, and no product file may contain `oracle` (checks/locked/rehearsal_core/test_rehearsal_core.py:223-227).
