# M11 · Deploy — SPEC

## What it is, in plain words
We rent one small Linux server on AWS (EC2 `t3.small`, Ubuntu 24.04) and give it a fixed public address (an Elastic IP). On it, Docker runs two containers: FalkorDB and our API (docker-compose.yml:1-15). The web page is a plain static site on Vercel. When the page asks for `/api/...`, Vercel forwards the request to our server on port 8000 (docs/BUILD_PLAN.md:51). Judges open one `https://...vercel.app` link and everything they see comes from FalkorDB on our server. If the server is down, the page shows recorded data with a "Replay data" badge (docs/BUILD_PLAN.md:73; web/index.html:18).

## Why
- Rule 10: "live deployment preferred (otherwise full local setup + video)" (docs/modules/00_GROUND_TRUTH.md:13).
- The video is recorded from the live URL (docs/BUILD_PLAN.md:74).
- Rule 2/3: FalkorDB must be central (docs/modules/00_GROUND_TRUTH.md:11). The live site proves it: stop FalkorDB and the API returns 503 (server/app.py:22).

## Which focus it serves
Track 3 and Track 1 both, indirectly: it is how judges reach the product. It is not itself a judged feature.

## In scope
- One EC2 instance, one Elastic IP, one security group.
- `docker compose up -d --build` of the repo at tag `v-freeze`.
- `web/vercel.json` with one rewrite `/api/:path*` → `http://<EIP>:8000/api/:path*`, and caching of that path turned off.
- Health checks, a pre-warm call, rollback.

## Not in scope
- HTTPS on the EC2 box, a domain name, a load balancer, auto-scaling, persistent volumes, backups.
- Gitea (listed in docs/BUILD_PLAN.md:20 and :50 but not in docker-compose.yml). Dropped.
- Locking the API to Vercel-only traffic (Vercel documents an origin-secret header pattern, https://vercel.com/docs/rewrites, "Restricting your origin to Vercel traffic"; it needs an API change). PROPOSED for later, not tonight.

## Inputs and outputs
- Inputs: the public GitHub repo at tag `v-freeze`; `deploy/Dockerfile`, `deploy/requirements.txt`, `docker-compose.yml`; `web/`.
- Outputs: `http://<EIP>:8000/api/*` (API) and `https://<project>.vercel.app` (site).

## Dependencies
- M10 web must contain `web/vercel.json` (does not exist yet) and `web/app.js` (does not exist yet).
- The API wraps the CLI (server/app.py:17-23), so whatever is green in `baton/` at `v-freeze` is what is live.
- **Blocker found while writing:** `deploy/requirements.txt:4` pins `redis==5.0.8`, but `falkordb==1.8.0` (deploy/requirements.txt:3) requires `redis>=8.0.0,<9`. `pip install --dry-run -r deploy/requirements.txt` fails with `ResolutionImpossible`, so `docker compose build` will fail. With `redis==8.1.0` the same dry-run succeeds, and the API ran locally with it. Fix in 3_STEPS step 0. Owner of `deploy/`: the human team lead approves.

## Owner, time, kill
- Owner: the teammate (EC2 + Vercel + GitHub repo, 12:30–13:30, docs/BUILD_PLAN.md:67); deploy at the 16:00 freeze with the author (docs/BUILD_PLAN.md:73).
- Time budget: 60 min first setup; 15 min redeploy at freeze.
- Kill / fallback: if the live API is not reachable through Vercel by 16:30, ship the static site in replay mode and show the API in the video by `curl` on the EC2 box; rule 10 then needs "full local setup + video" (docs/modules/00_GROUND_TRUTH.md:13), which the README's `docker compose up` covers.
