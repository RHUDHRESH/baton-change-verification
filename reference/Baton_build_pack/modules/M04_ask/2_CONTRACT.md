# M04 · ask — contract

Legend: **FIXED** = in a locked check or in current code (cited). **PROPOSED** = not in code; the named person decides. All Cypher below is in current baton code (baton/ask.py) or is the tested var-length pattern (docs/modules/00_GROUND_TRUTH.md:24-25). Nothing new is untested.

## 1. CLI (FIXED, baton/__main__.py:40-46, 95-103)
| Item | Source |
|---|---|
| `python -m baton ask --world DIR --beliefs FILE --question TEXT [--port P] [--offline]` | __main__.py:40-46; test_ask.py:18 |
| `python -m baton ask --catalogue` prints `ask.catalogue()`, with no connection | __main__.py:97-98; ask.py:326-327; test_ask.py:78 |
| Missing `--world/--beliefs/--question` without `--catalogue` → argparse error "ask needs … (or --catalogue)", exit 2 | __main__.py:100-102 |
| `--port` default 6379 | __main__.py:45 |
| `--offline` is accepted; routing is always offline | ask.py:299, 311 |

Exit codes (FIXED): 0 answered, including `none` (__main__.py:128-129) · 2 missing flags (__main__.py:102) · 3 FalkorDB unreachable, stderr "FalkorDB is not reachable at host:port: …" (graph.py:26, 30-32; __main__.py:116-117; test_ask.py:87-92).

## 2. Output JSON (FIXED; built at ask.py:310-322, printed with `sort_keys=True` at __main__.py:128)
| Field | Type | Rule | Source |
|---|---|---|---|
| `tool` | str | `breaks_if_leaves`, `owes`, `why`, `who_owns`, `covers`, `none` | ask.py:71-78; test_ask.py:29-71; test_ask_ratchet.py:28 |
| `args` | object | `{person}` (owes, breaks) · `{duty, person}` (why) · `{duty}` (who_owns) · `{duty, day}` (covers) · `{}` or `{reason}` (none) | ask.py:176, 189, 194, 199, 177, 201 |
| `rows` | list | §3 | |
| `sources` | list of str | sorted, de-duplicated source ids; each exists in world | ask.py:322; test_ask.py:83; test_ask_ratchet.py:30 |
| `answer` | str | non-empty; uses names, not duty ids; `none` starts "That is not in the graph." | ask.py:80-81, 236, 315; test_ask.py:72, 84; test_ask_ratchet.py:51-52 |
| `cypher` | str | `CATALOGUE[tool]`; `""` for none | ask.py:310, 71-78; test_ask.py:82 |
| `question`, `graph`, `router` | str | echo; `halden_<seed>`; `"offline"` | ask.py:310-311 |
| `live_hash_before`, `live_hash_after` | str | live fingerprints; equal | ask.py:316, 322; graph.py:39-44 |

## 3. Tools (FIXED)
All tools except `breaks_if_leaves` and `none` run on a GRAPH.COPY fork with `rehearse.gate` + `rehearse.Q_HOLDS` (basis `"confirmed"`), one `ro_query` of the catalogue text, and `fork.delete()` in `finally` (ask.py:206-218). `breaks_if_leaves` calls `rehearse.on_fork(s2, "G", "all")` and `rehearse.failures` (ask.py:239-250).

| Tool | Query | Row keys | Source |
|---|---|---|---|
| `breaks_if_leaves` | `rehearse.cover_query("G")` | `{duty, duty_name, at, day, event, label, status, sources}` | ask.py:73, 239-250; rehearse.py:97-100, 142-150 |
| `owes` | `Q_OWES` | `{duty, duty_name, status, sources}`; status `record` if any OWNER edge, else the HOLDS basis | ask.py:25-31, 252-259 |
| `why` | `Q_WHY` | one row per cited Source `{duty, duty_name, person, via, basis, source, type, text}` | ask.py:33-40, 260-267 |
| `who_owns` | `Q_WHO_OWNS`: OWNER/HOLDS edges valid at `Company.now` | `{duty, duty_name, person, person_name, left_at, basis, sources}`, non-null persons only | ask.py:60-69, 268-282 |
| `covers` | `Q_COVERS`: first event of the duty on day N, else the start of day N; var-length path ≤ 4 hops valid at that time | `{duty, duty_name, at, event, label, person, person_name, via, sources}`, non-null persons only; empty = nobody | ask.py:42-58, 283-296 |
| `none` | `""` | `[]` | ask.py:77, 312-317 |

### 3.1 Router (FIXED, ask.py:88-101, 165-201)
Patterns are tried in order on `norm(question)`. `norm` lower-cases and turns every non-alphanumeric character into a space (ask.py:104-105). People are matched by full name or id, then a unique first name (ask.py:117-141). Duties are matched by exact normalised name/id, else token overlap ≥ 0.5 (ask.py:143-163). Duty names come from the live graph plus the beliefs file (ask.py:305-307).

### 3.2 PROPOSED: negative days (builder)
`norm()` removes the "-", and the covers pattern is `day (?P<day>\d+)` (ask.py:96-97, 104-105). So "on day -4" routes with `day = 4`. The doc writer ran this for every routed duty of seeds 7, 101, 202 and 303: 5 questions returned `args.day = 4` for day −4. The rows happened to match the reference in all 5, so `test_who_covers_a_duty_at_a_time_matches_the_graph` (test_ask.py:53-65) passes by luck. The first routed event is always on day −4: shifts start on the Monday before `now` (generate.py:260, 278-282). Fix: when the covers pattern matches, read `re.search(r"\bday\s+(-?\d+)\b", question, re.I)` from the raw question and pass the signed int. `Q_COVERS` only multiplies `$day` (ask.py:45, 48), so negative values work there.

## 4. Graph read (FIXED)
`Company{now, day_ms, leave_at}` (load.py:21-23) · `Person{id, name, left_at}` (load.py:25-28) · `Duty{id, name}` (load.py:30-32; MERGE'd for promoted beliefs at rehearse.py:48-49) · `Event{id, at, label}-[:NEEDS]->Duty` (load.py:42-45) · `Source{id, type, text}` (load.py:38-40) · `OWNER/ROUTES_TO/SHIFT/ESCALATES_TO {vf, vt, rec}` (load.py:47-65) · `HOLDS{vf, vt, basis, srcs, belief}`, fork only (rehearse.py:50).

## 5. API (FIXED; not run by this writer)
`POST /api/ask {seed: int = 7, question: str}` → the CLI JSON as it is (server/app.py:100-110). `world_dir()` still looks for `fixtures/beliefs_seed{seed}.json`, which no longer exists. It then runs `extract` without `--offline`, which replays the newest cached extraction for that world (server/app.py:31-36; baton/extract.py:191-198).
