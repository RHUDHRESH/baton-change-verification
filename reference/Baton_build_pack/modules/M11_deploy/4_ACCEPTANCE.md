# M11 · Deploy — ACCEPTANCE

## 1. Checks (no pytest checks exist for deploy; these curl checks are the contract)
Agree on this list before step 1 (human approves). Each line: command → expected output.

| Id | Where | Command | Expected |
|---|---|---|---|
| R0 | laptop | `python3 -m pip install --dry-run --ignore-installed -q -r deploy/requirements.txt && echo RESOLVES` | `RESOLVES` (fails today with `ResolutionImpossible` until step 0) |
| E1 | box | `sudo docker compose ps` | `falkordb` and `api` running |
| E2 | box | `curl -s localhost:8000/api/health` | `{"ok":true}` (server/app.py:60) |
| E3 | box | `curl -s -o /dev/null -w "%{http_code}\n" "localhost:8000/api/demo?seed=7"` | `200` |
| E4 | laptop | `curl -s -w "\n%{http_code}\n" http://<EIP>:8000/api/health` | `{"ok":true}` then `200` |
| E5 | laptop | `nc -z -w 3 <EIP> 6379; echo $?` | non-zero (port closed) |
| V1 | laptop | `curl -s -w "\n%{http_code}\n" https://<project>.vercel.app/api/health` | `{"ok":true}` then `200` — this is the UNTESTED http-IP-port rewrite |
| V2 | laptop | `curl -s "https://<project>.vercel.app/api/demo?seed=7" \| python3 -c "import json,sys;d=json.load(sys.stdin);print(d['leaver'],[len(d['lanes'][l]['failures']) for l in 'WRG'])"` | same line as from `http://<EIP>:8000` |
| V3 | laptop | `python3 tools/go_and_see.py https://<project>.vercel.app/ web/_shots` (M10) | all PASS, `replay badge visible = False` |
| F1 | box, then laptop | `sudo docker compose stop falkordb`; then `curl -s -w "\n%{http_code}\n" "http://<EIP>:8000/api/demo?seed=7"` | body contains `FalkorDB is not reachable`, code `503` (server/app.py:22; baton/graph.py:26). Then `sudo docker compose start falkordb` |

What was actually run while writing (local machine, not EC2): with the fixed requirements in a fresh venv and uvicorn on the repo, `/api/health` → 200 `{"ok":true}`; `/api/demo?seed=7` → 200 in about 1 s; `/api/handover` → 200; `/api/ask` → 500 before `ask` was added to the CLI, 200 in a re-run after; `/api/demo?seed=99` → 500 (no `extract` command); with FalkorDB stopped, `/api/demo` → 503 "FalkorDB is not reachable at localhost:6411 ..." and `/api/health` still → 200. Docker build, EC2 and Vercel steps: **not run** (no Docker daemon, no cloud access).

## 2. How to check it is up (one minute, any time)
```bash
curl -s -w " %{http_code}\n" https://<project>.vercel.app/api/health
curl -s -o /dev/null -w "demo %{http_code} in %{time_total}s\n" "https://<project>.vercel.app/api/demo?seed=7"
```
Both 200 = live. Health 200 but demo 503 = FalkorDB down (`sudo docker compose restart falkordb`). Health 502 from Vercel = API or rewrite down (check E4 directly against the EIP).

## 3. Failure modes and fallbacks
| Symptom | Likely cause | Fix | Fallback |
|---|---|---|---|
| Build stops at `pip install` with `ResolutionImpossible` | `redis==5.0.8` pin | step 0 | — |
| E4 hangs | security group lacks 8000 from 0.0.0.0/0, or wrong IP (EIP not associated) | fix SG / associate EIP | — |
| V1 returns 502 `ROUTER_EXTERNAL_TARGET_ERROR` quickly | Vercel cannot reach `http://<EIP>:8000` (wrong IP, SG, or Vercel refuses http/IP/port destinations: UNTESTED) | re-check E4; check `destination` keeps `/api` | site runs on replay data (badge); video shows `curl http://<EIP>:8000/...` on the box |
| V1 returns 404 | destination lost the `/api` prefix (copied from the docs example) | `"destination": "http://<EIP>:8000/api/:path*"` | — |
| V2 returns 502 after about 2 min | origin did not answer within 120 s (https://vercel.com/docs/errors/ROUTER_EXTERNAL_TARGET_ERROR) | pre-warm seed 7 on the box (step 3) | replay |
| Stale data after redeploy | Vercel cached `/api` | keep the `x-vercel-enable-rewrite-caching: 0` header (https://vercel.com/docs/rewrites) | — |
| Box rebooted | containers restart on their own (`restart: unless-stopped`, docker-compose.yml:5, :15); graph is reloaded on first call | run E3 once to pre-warm | — |
| Bad deploy at any time | — | Rollback section of 3_STEPS | `vercel rollback`; `git checkout v-freeze` |

## 4. Anti-hallucination list
| Likely wrong assumption | Correct fact | Source |
|---|---|---|
| `deploy/requirements.txt` installs fine | It cannot: `falkordb==1.8.0` needs `redis>=8.0.0,<9`; the file pins `redis==5.0.8` | deploy/requirements.txt:3-4; pip dry-run 18 Oct |
| The Vercel docs example can be pasted as is | The example strips `/api`; our routes need it | https://vercel.com/docs/rewrites; server/app.py:58-101 |
| Vercel accepts `http://<ip>:8000` destinations | Not stated in the docs; all examples are `https://` hostnames. UNTESTED until V1 passes | https://vercel.com/docs/rewrites |
| `/api/health` green means the product works | It never touches FalkorDB | server/app.py:58-60; measured |
| `vercel.json` already exists | It does not; `web/` has `index.html`, `styles.css`, `mock/`, `_shots/` only | `ls web/` on 18 Oct |
| Open 6379/3000 in the security group for the Browser | They are bound to 127.0.0.1; use an SSH tunnel | docker-compose.yml:4 |
| Compose runs Gitea and a separate Browser | It runs only `falkordb` and `api` | docker-compose.yml:1-15 |
| `BATON_OFFLINE` / `OPENAI_API_KEY` change behaviour | No code reads them yet | grep; server/app.py:9-11 are the only env reads in server/ |
| Use `falkordb/falkordb:latest` | Pin `v4.22.1`; `latest` will move to the Rust 6.x engine | docker-compose.yml:3; docs/modules/00_GROUND_TRUTH.md:18 |
| Hobby plan can roll back to any old deploy | Only to the previous production deployment | https://vercel.com/docs/cli/rollback |
| An Elastic IP is free while attached | AWS charges for every Elastic IP, used or idle | https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html |
| `depends_on` waits until FalkorDB is ready | It only orders start-up; first call may 503, retry | docker-compose.yml:14 |
