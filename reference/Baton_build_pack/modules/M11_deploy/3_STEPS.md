# M11 · Deploy — STEPS (copy-paste for the teammate)

Karpathy-loop rule: checks first, a human approves, lock, then build. For deploy the "checks" are the curl commands in 4_ACCEPTANCE §1; agree on them before step 1. Never edit `checks/locked/` or `loop/bin/`. Do not put any key or password in the repo.

Replace `<EIP>`, `<key.pem>`, `<org>`, `<project>` everywhere.

---

## Step 0 — Fix the requirements pin (on a laptop, before anything else)
- Goal: `docker compose build` can install the Python packages.
- Files: `deploy/requirements.txt` line 4.
- Change `redis==5.0.8` → `redis==8.1.0`. Reason: `falkordb==1.8.0` requires `redis>=8.0.0,<9`; the old pin makes pip fail with `ResolutionImpossible` (M11 2_CONTRACT §2).
- Commands (any machine with Python 3.12+):
  ```bash
  cd baton
  sed -i 's/^redis==5.0.8$/redis==8.1.0/' deploy/requirements.txt
  python3 -m pip install --dry-run --ignore-installed -q -r deploy/requirements.txt && echo RESOLVES
  ```
- Done when: it prints `RESOLVES`. Commit and push (human approves: `deploy/` is outside the loop's mutable paths, loop/config.json).
- Agent prompt:
  > In deploy/requirements.txt change only `redis==5.0.8` to `redis==8.1.0`. Run `pip install --dry-run --ignore-installed -r deploy/requirements.txt` and paste the last lines. Touch nothing else.

## Step 1 — Launch the EC2 instance (AWS console, about 10 min)
1. EC2 → Launch instance. Name `baton`. AMI: **Ubuntu Server 24.04 LTS**. Type: **t3.small**. Key pair: create or pick one; download `<key.pem>`.
2. Network settings → Create security group `baton-sg`:
   - SSH, TCP 22, source **My IP**.
   - Custom TCP, port **8000**, source **0.0.0.0/0** (Anywhere-IPv4).
   - Nothing else. Never open 6379 or 3000.
3. Storage: 20 GiB gp3 (PROPOSED size).
4. Launch.
5. EC2 → Network & Security → **Elastic IPs** → **Allocate Elastic IP address** → Allocate. Select it → **Actions → Associate Elastic IP address** → Resource type **Instance** → pick `baton` → **Associate** (steps from https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html). Write the address down as `<EIP>`.
- Done when: `ssh -i <key.pem> ubuntu@<EIP> 'lsb_release -ds'` prints an Ubuntu 24.04 line. (Run `chmod 400 <key.pem>` first if ssh refuses the key.)

## Step 2 — Install Docker on the box (commands from https://docs.docker.com/engine/install/ubuntu/)
```bash
ssh -i <key.pem> ubuntu@<EIP>
# on the box:
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run hello-world
```
- Done when: `hello-world` prints its greeting and `sudo docker compose version` prints a version. (We use `sudo docker ...` throughout so no group change or re-login is needed.)

## Step 3 — Start Baton on the box
```bash
# on the box:
git clone https://github.com/<org>/baton.git
cd baton
git checkout v-freeze            # before 16:00 use main; after the freeze always the tag
sudo docker compose up -d --build
sudo docker compose ps
curl -s localhost:8000/api/health; echo
curl -s -o /dev/null -w "demo %{http_code}\n" "localhost:8000/api/demo?seed=7"
```
- Done when: `ps` shows `falkordb` and `api` running; health prints `{"ok":true}`; demo prints `demo 200`. The demo call also pre-warms seed 7 (generates the world and loads the graph).
- If the build fails at `pip install`: step 0 was not pushed.
- If demo prints 503: FalkorDB is not up yet. `sudo docker compose logs falkordb | tail -20`, wait, retry.

## Step 4 — Check from outside
```bash
# on your laptop:
curl -s -w "\n%{http_code}\n" http://<EIP>:8000/api/health
curl -s "http://<EIP>:8000/api/demo?seed=7" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['leaver'],[len(d['lanes'][l]['failures']) for l in 'WRG'],d['live_hash_before']==d['live_hash_after'])"
```
- Done when: `{"ok":true}` / `200`, then a line like `hana.sharma [6, 7, 37] True` (the numbers are whatever the frozen build gives; write them down for the video).
- If it hangs: the security group is missing port 8000 from 0.0.0.0/0.

## Step 5 — Vercel static site with the `/api` rewrite
1. In the repo, create `web/vercel.json` (PROPOSED content from M11 2_CONTRACT §5) with your real `<EIP>`:
   ```bash
   cd baton/web
   cat > vercel.json <<'EOF'
   {
     "$schema": "https://openapi.vercel.sh/vercel.json",
     "rewrites": [
       { "source": "/api/:path*", "destination": "http://<EIP>:8000/api/:path*" }
     ],
     "headers": [
       { "source": "/api/:path*", "headers": [ { "key": "x-vercel-enable-rewrite-caching", "value": "0" } ] }
     ]
   }
   EOF
   EIP=203.0.113.10                     # <- your Elastic IP
   sed -i "s/<EIP>/$EIP/" vercel.json
   grep destination vercel.json
   python3 -m json.tool vercel.json > /dev/null && echo JSON_OK
   ```
   The heredoc is quoted on purpose (so `$schema` is not expanded); `sed` then puts in the address. Commit and push.
2. Deploy from `web/`:
   ```bash
   npm i -g vercel
   vercel login
   cd baton/web
   vercel --yes          # first deploy of a new project is production
   vercel --prod         # every later deploy
   ```
   `stdout` of `vercel` is the deployment URL (https://vercel.com/docs/cli/deploy). The stable production URL is shown in the dashboard as `https://<project>.vercel.app`.
- Done when: 4_ACCEPTANCE §1 checks V1–V3 pass.
- Agent prompt:
  > Create web/vercel.json exactly as in docs/modules/M11_deploy/2_CONTRACT.md §5 with the Elastic IP the human gives you. Keep `/api` in the destination path. Validate with `python3 -m json.tool`. Do not add any other keys.

## Step 6 — FalkorDB Browser for judges' screenshots (optional)
```bash
# on your laptop:
ssh -i <key.pem> -L 3000:127.0.0.1:3000 ubuntu@<EIP>
# then open http://localhost:3000 in your browser
```
- Done when: you see graph `halden_7`. If nothing listens on 3000, the v4.22.1 image has no Browser (UNVERIFIED, M11 2_CONTRACT §1); skip it. Fallback `sudo docker compose exec falkordb redis-cli GRAPH.LIST` is also UNTESTED (that `redis-cli` is inside the image is not checked).

## Step 7 — Freeze deploy (16:00, docs/BUILD_PLAN.md:73)
```bash
# on the box:
cd ~/baton && git fetch --tags && git checkout v-freeze
sudo docker compose up -d --build
curl -s -o /dev/null -w "demo %{http_code}\n" "localhost:8000/api/demo?seed=7"
# on the laptop:
cd baton && git checkout v-freeze && cd web && vercel --prod
curl -s -o /dev/null -w "vercel demo %{http_code}\n" "https://<project>.vercel.app/api/demo?seed=7"
```
- Done when: both print 200. Record the leaver and W/R/G counts in the README (M12).

## Rollback
- API to the frozen tag (or an earlier tag):
  ```bash
  cd ~/baton && git checkout v-freeze && sudo docker compose up -d --build
  ```
- API off entirely (site goes to replay data): `sudo docker compose stop api`.
- Site: `vercel rollback` (back to the previous production deployment; Hobby plan cannot go further back, https://vercel.com/docs/cli/rollback). Undo a rollback: `vercel promote <deployment-url>`.
- Never move or re-create the `v-freeze` tag ("Never edit the tag in place", scratchpad/book/BATON_FINAL_PLAN.md:189).
