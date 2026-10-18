# M09 · HTTP API — SPEC

Paths relative to `/home/claude/baton/`. Snapshot: 12:15 IST, 18 Oct, git HEAD `85eeabd`. The repo changes every few minutes; re-check with `git log -3` and `python -m baton -h` before building.

Status:
- `server/app.py` exists (110 lines). Last change: commit `8375bfb` "API: health fails loudly without FalkorDB; deploy pins redis 8.1 + openai". It compiled when checked (`python -m py_compile server/app.py`, 18 Oct, 104-line version).
- Commit `cd65133`'s message says "verified locally: health, demo, handover". The doc writer did **not** re-run it: FastAPI and uvicorn are not in the project venv (`import fastapi` failed, 18 Oct). The Docker image was not built by the doc writer.

## What it is, in plain words
The website cannot run Python. The API is a small web server the website calls. Each route runs the same `python -m baton ...` command the checks run and sends back its JSON, so the website, the checks and the API use the same code (BUILD_PLAN.md:48). The API decides nothing; it only adds the readable text of each source to the rows (server/app.py:1, server/app.py:40-55).

## Which track focus it serves
- Track 3: "answers with clear sources": each source comes back with its type and text (server/app.py:53-54).
- Rule 10: a live deployment is preferred (00_GROUND_TRUTH.md:13). Vercel forwards `/api/*` to this API on EC2 (BUILD_PLAN.md:23, BUILD_PLAN.md:51).

## In scope
- Routes `GET /api/health`, `GET /api/demo`, `POST /api/handover`, `POST /api/ask` (server/app.py:58-110).
- Packaging: `deploy/Dockerfile`, `deploy/requirements.txt`, `docker-compose.yml`.
- Fixing the gaps below.

## Not in scope
- Any reasoning in the API; the website (M10); sign-in, users, rate limits.

## How it depends on the CLI (exactly)
| API step | CLI it runs | State at 12:15 |
|---|---|---|
| first use of a seed | `generate --seed N --out DIR` (server/app.py:29-30) | exists (baton/__main__.py:11-13) |
| beliefs for a seed | copy `fixtures/beliefs_seed<N>.json` if present (server/app.py:31-34), else `extract --world DIR --out DIR/beliefs.json` (server/app.py:35-36) | The fixture file was **deleted** in commit `84747c6` ("seed-7 Haiku runs migrated into the caches"), so every seed now goes through `extract`, **without** `--offline`. With no `--model`, `extract` replays the newest cached run for that exact world (baton/extract.py:67-91 at HEAD 85eeabd); seed 7 has one in `fixtures/extract_cache/`. Any other seed misses and calls the default model `claude-haiku-4-5` (baton/extract.py:106-107 at HEAD 85eeabd), which needs `ANTHROPIC_API_KEY` (baton/llm.py:28, baton/llm.py:55-63); compose does not pass it and deploy/requirements.txt has no `anthropic` package → exit 5 → HTTP 500 |
| `GET /api/demo` | `rehearse ... --lane W`, then `R`, then `G`, all `--confirm all` (server/app.py:74-77) | exists (baton/__main__.py:19-25). It does **not** call the `demo` command |
| `POST /api/handover` | `handover --world --beliefs --leaver --assign ... --port` (server/app.py:97) | exists (baton/__main__.py:27-32, baton/handover.py:85-91) |
| `POST /api/ask` | `ask --world --beliefs --question --port` (server/app.py:110) | exists (baton/__main__.py:34-40); feature green, 11/11 locked runs (loop/features.md:9). The API omits `--offline`; harmless today because the router is always deterministic (baton/ask.py:299, baton/ask.py:310-311) |

## What is missing or wrong (found while documenting)
1. **Seeds other than 7 fail** (no fixture, and either no `extract` or no model key/SDK in the container). Keep the web on seed 7, or commit more extraction caches.
2. `world_dir` should call `extract ... --offline` so a cache miss fails fast with exit 4 instead of trying a model (PROPOSED one-word change at server/app.py:36). Also: once M06 adds Cut data to world.json, the seed-7 cache only keeps hitting if the cache re-keying in the cut charter lands (loop/features.md, `### cut`); an uncommitted round was doing that at 12:20 IST.
3. **Possible double load on first use:** `world_dir` holds the lock only while preparing files (server/app.py:28-36). The first `rehearse` loads the graph if missing (baton/rehearse.py:113, baton/load.py:96-109 at HEAD 85eeabd). Two first requests at once could both load. PROPOSED: call `cli("load", "--world", d, "--port", PORT)` inside the lock.
4. `/api/demo` has no `after_handover`, `company`, `fixture` or `ghost_duties`; `web/mock/demo_7.json` has `company`, `fixture`, `ghost_duties`. M09 and M10 owners must agree on one shape.
5. Web mock ids (`duty:recon-monday-rerun`, `p-sam` in web/mock/handover_7.json) and hash format (`sha256:7c1e…`) do not match real ids (`d-…` duties, dotted person ids like `hana.sharma`, baton/generate.py:204 at HEAD 85eeabd, baton/generate.py:225 at HEAD 85eeabd) or real hashes (plain hex `hexdigest()`, baton/graph.py:44).
6. `BATON_OFFLINE` is set in compose (docker-compose.yml:12) but no code reads it (grep, 12:15). `OPENAI_API_KEY` is passed (docker-compose.yml:11) and read by baton/llm.py for `gpt-*` models (baton/llm.py:28); `openai>=1.40` is now in deploy/requirements.txt:5. `ANTHROPIC_API_KEY` and `BATON_MODEL` (baton/extract.py:107 at HEAD 85eeabd) are not passed, and there is no `anthropic` package, while the default model is `claude-haiku-4-5`.
7. No Gitea service; no `/api/cut` or `/api/write` route (PROPOSED in M06).
8. `web/vercel.json` (BUILD_PLAN.md:23) does not exist (web/ holds `index.html`, `styles.css`, `mock/`, `_shots/`).
9. No `/data` volume in compose; worlds regenerate after a container is recreated (harmless: generation is deterministic).
10. `depends_on` (docker-compose.yml:14) does not wait for FalkorDB to be ready; early requests get 503.
11. If a CLI prints non-JSON on success, `cli()` returns a string (server/app.py:23) and the route then fails with 500.

## Dependencies
- M02 rehearse, M03 handover, M04 ask, M05 extract: exist. M10 web: the client.
- FalkorDB `falkordb/falkordb:v4.22.1` (docker-compose.yml:3).

## Owner, time, kill
- Owner: teammate for EC2 + Vercel + GitHub (BUILD_PLAN.md:67); "teammate + me" for the 16:00 freeze and deploy (BUILD_PLAN.md:73).
- Time: 12:30–13:30 infrastructure (BUILD_PLAN.md:67); deploy at 16:00 (BUILD_PLAN.md:73).
- Kill and fallback: "site falls back to replay data" (BUILD_PLAN.md:73; also BUILD_PLAN.md:49).
