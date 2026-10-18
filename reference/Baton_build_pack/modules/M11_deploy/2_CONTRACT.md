# M11 · Deploy — CONTRACT

Every line is copied from a file (`path:line`), from a cited web page, or marked `PROPOSED` / `UNTESTED`.

## 1. Containers (docker-compose.yml)
| Service | Image / build | Ports on the host | Env | Source |
|---|---|---|---|---|
| `falkordb` | `falkordb/falkordb:v4.22.1` (pinned) | `127.0.0.1:6379:6379`, `127.0.0.1:3000:3000` (local only) | none | docker-compose.yml:2-5 |
| `api` | built from `deploy/Dockerfile`, context `.` | `8000:8000` (all interfaces) | `FALKORDB_HOST=falkordb`, `FALKORDB_PORT=6379`, `OPENAI_API_KEY=${OPENAI_API_KEY:-}`, `BATON_OFFLINE=${BATON_OFFLINE:-1}` | docker-compose.yml:6-15 |

- Both services: `restart: unless-stopped` (docker-compose.yml:5, :15). `api` `depends_on: [falkordb]` (docker-compose.yml:14); this orders start-up only, it does not wait for FalkorDB to be ready.
- No volumes. Graphs and `/data` are lost when containers are removed. That is fine: the CLI loads the graph again when it is missing (baton/rehearse.py:109-113) and seed 7's world is regenerated (server/app.py:29-30).
- `OPENAI_API_KEY` and `BATON_OFFLINE` are passed in but no code reads them yet (grep of `baton/`, `server/` finds only server/app.py:9-11 env reads: `BATON_DATA`, `FALKORDB_PORT`, `FALKORDB_HOST`).
- Port 3000 is the FalkorDB Browser. FalkorDB's docs show it on `falkordb/falkordb:latest` (scratchpad/falkor/repos/docs/getting-started/index.mdx:404-405). That it is bundled in the `v4.22.1` tag is UNVERIFIED; test with the SSH tunnel in 3_STEPS step 6.

## 2. API image (deploy/Dockerfile)
- Base `python:3.12-slim` (deploy/Dockerfile:1); installs `deploy/requirements.txt` (deploy/Dockerfile:3-4); copies `baton`, `server`, `fixtures` (deploy/Dockerfile:5-7); `BATON_DATA=/data` (deploy/Dockerfile:8); runs `uvicorn server.app:app --host 0.0.0.0 --port 8000` (deploy/Dockerfile:10).
- Requirements (deploy/requirements.txt:1-4): `fastapi==0.115.0`, `uvicorn==0.30.6`, `falkordb==1.8.0`, `redis==5.0.8`.
- **Broken pin:** `falkordb` 1.8.0 declares `redis<9,>=8.0.0` (read from the installed package metadata). `redis==5.0.8` cannot be installed with it; pip reports `ResolutionImpossible` (dry-run done 18 Oct). `redis==8.1.0` resolves (dry-run done) and is the version in the project venv. Fix = step 0 of 3_STEPS.
- `docker build` itself is **UNTESTED** (no Docker daemon in the writing sandbox). Test: `docker compose build api` on the EC2 box or a laptop.

## 3. API routes the deploy must expose
`GET /api/health`, `GET /api/demo?seed=N`, `POST /api/handover`, `POST /api/ask` (server/app.py:58, :63, :84, :101). Full shapes: docs/modules/M10_web/2_CONTRACT.md.
- `/api/health` returns `{"ok": true}` without touching FalkorDB (server/app.py:58-60). It proves the API process is up, not that FalkorDB is.
- The real "is it up" check is `GET /api/demo?seed=7` → HTTP 200 with a `lanes` object. When FalkorDB is down it returns HTTP 503 with a body containing "FalkorDB is not reachable" (server/app.py:22; baton/graph.py:26). Measured locally both ways.

## 4. AWS
| Item | Value | Source / status |
|---|---|---|
| Instance type | `t3.small` | docs/BUILD_PLAN.md:51 |
| OS | Ubuntu Server 24.04 LTS | task brief. Docker supports "Ubuntu Noble 24.04 (LTS)" (https://docs.docker.com/engine/install/ubuntu/) |
| Public address | one Elastic IP, associated with the instance | docs/BUILD_PLAN.md:51. CLI: `aws ec2 allocate-address`, `aws ec2 associate-address --instance-id <i-...> --allocation-id <eipalloc-...>` (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html). That page says there is a charge for every Elastic IP, used or idle |
| Disk | 20 GiB gp3 | PROPOSED (room for two images and build cache); teammate decides |

### Security group (inbound)
| Port | Protocol | From | Why |
|---|---|---|---|
| 22 | TCP | your own IP only ("My IP" in the console) | SSH |
| 8000 | TCP | `0.0.0.0/0` | Vercel's proxy must reach the API. We did not find a published, fixed list of Vercel egress IPs, so the port is open to all. UNVERIFIED whether a narrower rule is possible |
| 6379 | — | **do not open** | FalkorDB is bound to 127.0.0.1 (docker-compose.yml:4) |
| 3000 | — | **do not open** | Browser is bound to 127.0.0.1 (docker-compose.yml:4); use an SSH tunnel |

Outbound: leave the default (all). The box needs it for `apt`, Docker Hub and PyPI.

Risk accepted for tonight: the API is open to anyone. Data is synthetic (docs/modules/00_GROUND_TRUTH.md:12). Each new `seed` creates a folder under `/data` (server/app.py:26-30); today any seed without a cached beliefs file fails before much is written (server/app.py:31-36).

## 5. Vercel
`web/vercel.json` — PROPOSED (not yet in repo; docs/BUILD_PLAN.md:23 names this path):
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [
    { "source": "/api/:path*", "destination": "http://<EIP>:8000/api/:path*" }
  ],
  "headers": [
    { "source": "/api/:path*", "headers": [ { "key": "x-vercel-enable-rewrite-caching", "value": "0" } ] }
  ]
}
```
What Vercel's docs say (fetched 18 Oct):
- Rewrites to external origins are supported; example `"source": "/api/:path*", "destination": "https://api.example.com/:path*"` (https://vercel.com/docs/rewrites, "Rewrites to external origins").
- **Keep `/api` in the destination.** The docs example drops the prefix. Our FastAPI routes include `/api` (server/app.py:58, :63, :84, :101), so `.../:path*` without `/api` would 404.
- Setting `x-vercel-enable-rewrite-caching` to `0` stops Vercel caching upstream responses (https://vercel.com/docs/rewrites, "Disabling caching for rewrites to external origins"). Projects created on or after 6 Apr 2026 honour upstream cache headers by default (same page). FastAPI sends none, but `0` makes it explicit.
- Vercel waits at most 120 s for the external origin to start responding, then returns 502 `ROUTER_EXTERNAL_TARGET_ERROR` (https://vercel.com/docs/errors/ROUTER_EXTERNAL_TARGET_ERROR; https://vercel.com/changelog/cdn-origin-timeout-increased-to-two-minutes). `/api/demo?seed=7` took about 1 s locally once the world existed.
- **UNTESTED:** every example in the docs uses an `https://` hostname. Whether a plain `http://` raw IP with port `:8000` is accepted is not stated. Test command after deploy: `curl -s -w "\n%{http_code}\n" https://<project>.vercel.app/api/health` must print `{"ok":true}` and `200`. If it fails, see 4_ACCEPTANCE failure modes.
- CLI: install `npm i -g vercel`; `vercel login` (https://vercel.com/docs/cli). Deploy `vercel --prod`; `--yes` skips set-up questions; the first deployment of a new project is always production (https://vercel.com/docs/cli/deploy). Rollback: `vercel rollback [deployment-id or url]`; on Hobby only to the previous production deployment (https://vercel.com/docs/cli/rollback).
- Fast static deploys skip the build step only for up to 10 HTML/Markdown files (https://vercel.com/docs/cli/deploy, "Fast static deployments"). `web/` has CSS/JS/JSON too, so it uses the normal flow; no build command is needed.

## 6. Names used in the commands
| Placeholder | Meaning |
|---|---|
| `<EIP>` | the Elastic IP, e.g. `203.0.113.10` |
| `<key.pem>` | the EC2 key pair file |
| `<org>/baton` | the public GitHub repo (still `REPLACE_ME` in web/index.html:123) |
| `<project>` | Vercel project name |
