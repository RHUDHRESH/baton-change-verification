"""Baton HTTP API (thin wrapper over the `python -m baton` CLI contract). Every decision is made by the CLI in FalkorDB."""
import json, os, subprocess, sys, threading, tempfile
from typing import Annotated
from typing import Literal
from datetime import date
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import security
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("BATON_DATA", str(Path(tempfile.gettempdir()) / "baton_data")))
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
HOST = os.environ.get("FALKORDB_HOST", "localhost")
LOCK = threading.RLock()


@asynccontextmanager
async def lifespan(application):
    security.credential(DATA)
    yield


app = FastAPI(title="Baton API", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(security.RequestGuard)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get(
    "BATON_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(","))
if os.environ.get("BATON_ALLOWED_ORIGIN"):
    app.add_middleware(CORSMiddleware, allow_origins=[os.environ["BATON_ALLOWED_ORIGIN"]],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.add_middleware(security.BrowserHeaders)


@app.get("/docs", include_in_schema=False)
def api_documentation():
    # Swagger's trusted inline initializer is hash-authorized without allowing
    # arbitrary inline scripts in the product pages.
    import re, base64, hashlib
    from fastapi.openapi.docs import get_swagger_ui_html
    response = get_swagger_ui_html(openapi_url="/openapi.json", title="Baton API",
                                  swagger_favicon_url="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
                                  swagger_ui_parameters={"validatorUrl": None})
    scripts = re.findall(r"<script>(.*?)</script>", response.body.decode(), re.S)
    hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in scripts)
    response.headers["Content-Security-Policy"] = security.POLICY.replace(
        "script-src 'self'", f"script-src 'self' https://cdn.jsdelivr.net {hashes}").replace(
        "style-src 'self'", "style-src 'self' https://cdn.jsdelivr.net")
    return response


def cli(*args):
    env = dict(os.environ, FALKORDB_HOST=HOST)
    try:
        r = subprocess.run([sys.executable, "-m", "baton", *map(str, args)], cwd=ROOT, capture_output=True, text=True,
                           timeout=300, env=env)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "The graph operation exceeded its time limit")
    if r.returncode != 0:
        status = 503 if r.returncode == 3 else 409 if r.returncode == 4 else 422 if r.returncode in (1, 2) else 500
        detail = (r.stderr or r.stdout).strip()
        raise HTTPException(status, detail.splitlines()[-1][-800:] if detail else "Operation failed")
    return json.loads(r.stdout) if r.stdout.strip().startswith(("{", "[")) else r.stdout


def world_dir(seed: int) -> Path:
    if not 0 <= seed <= 2_147_483_647:
        raise HTTPException(422, "seed must be between 0 and 2147483647")
    # RT-04: public demo reads must not allocate storage or spend model credits
    # for arbitrary companies. Additional companies require local provisioning.
    if seed not in (7, 101, 202, 303):
        raise HTTPException(409, "no cached extraction for this demo company; choose 7, 101, 202 or 303")
    d = DATA / f"seed_{seed}"
    with LOCK:
        if not (d / "world.json").exists():
            cli("generate", "--seed", seed, "--out", d)
        if not (d / "beliefs.json").exists():
            # replay the committed AI extraction for this exact company (no key needed); a live model only if configured
            args = ["extract", "--world", d, "--out", d / "beliefs.json"]
            if os.environ.get("BATON_OFFLINE", "1") == "1":
                args.append("--offline")
            metadata = cli(*args)
            (d / "extraction.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return d


def enrich(d: Path, rows):
    w = json.loads((d / "world.json").read_text())
    beliefs = json.loads((d / "beliefs.json").read_text())
    text = {}
    for k, key in (("message", "messages"), ("joblog", "joblogs"), ("ticket", "tickets")):
        for x in w.get(key, []):
            text[x["id"]] = (k, x.get("text") or f'{x.get("job")} run by {x.get("actor")}: {x.get("status")}')
    for r in w["records"]:
        text[r["id"]] = ("record", " ".join(f"{a}={b}" for a, b in r.items() if a != "id"))
    names = {x["id"]: x["name"] for x in w["duties"]}
    names.update({b["duty"]: b.get("duty_name", b["duty"]) for b in beliefs})
    for r in rows:
        r["duty_name"] = names.get(r["duty"], r["duty"])
        r["sources"] = [{"id": s, "type": text.get(s, ("?", ""))[0], "text": text.get(s, ("?", ""))[1]}
                        for s in r.get("sources", [])]
    return rows


def auth_db():
    from baton.graph import connect, Unreachable
    try:
        return connect(PORT).connection
    except Unreachable as err:
        raise HTTPException(503, str(err))


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=256)


@app.post("/api/auth/login")
def operator_login(body: Login, request: Request, response: Response):
    token = security.login(request, body.token, auth_db(), DATA)
    response.set_cookie(security.COOKIE, token, max_age=security.SESSION_TTL, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "role": "operator"}


@app.get("/api/auth/status")
def operator_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": bool(security.session(request, auth_db(), DATA, required=False))}


@app.post("/api/auth/logout")
def operator_logout(request: Request, response: Response):
    token = request.cookies.get(security.COOKIE)
    if token:
        auth_db().delete("baton:session:" + security.digest(token))
    response.delete_cookie(security.COOKIE, path="/")
    return {"authenticated": False}


@app.get("/api/health")
def health():
    """Fails loudly when FalkorDB is down: the product does nothing without the graph."""
    from falkordb import FalkorDB
    try:
        FalkorDB(host=HOST, port=PORT, socket_connect_timeout=3, socket_timeout=3).connection.ping()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"FalkorDB is not reachable at {HOST}:{PORT}: {e}")
    return {"ok": True, "falkordb": f"{HOST}:{PORT}", "fixture": True, "offline": os.environ.get("BATON_OFFLINE", "1") == "1"}


@app.get("/api/demo")
def demo(seed: int = 7):
    with LOCK:
        d = world_dir(seed)
        w = json.loads((d / "world.json").read_text())
        lanes, out = {}, None
        for lane in ("W", "R", "G"):
            out = cli("rehearse", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], "--lane", lane,
                      "--confirm", "all", "--port", PORT)
            from baton.rehearse import cover_query
            lanes[lane] = {"failures": enrich(d, out["failures"]), "cypher": cover_query(lane)}
        people = {p["id"]: p for p in w["people"]}
        extraction_path = d / "extraction.json"
        extraction = json.loads(extraction_path.read_text()) if extraction_path.exists() else {"model": "cached extraction"}
        return {"seed": seed, "now": w["now"], "day_ms": w["day_ms"], "window_days": w["window_days"],
                "leaver": w["leaver"], "leaver_name": people[w["leaver"]]["name"], "leave_at": w["leave_at"],
                "people": w["people"], "duties": w["duties"], "beliefs": json.loads((d / "beliefs.json").read_text()),
                "fixture": True, "mode": "live", "extraction": {"model": extraction.get("model"), "cached": True},
                "lanes": lanes, "unpromoted": out.get("unpromoted", []),
                "live_hash_before": out["live_hash_before"], "live_hash_after": out["live_hash_after"]}


Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]


class Handover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(default=7, ge=0, le=2_147_483_647)
    assign: dict[Identifier, Identifier] = Field(max_length=100)


def validate_assignments(directory, assignments):
    world = json.loads((directory / "world.json").read_text())
    beliefs = json.loads((directory / "beliefs.json").read_text())
    duties = {d["id"] for d in world["duties"]} | {b["duty"] for b in beliefs}
    people = {p["id"] for p in world["people"]}
    if any(d not in duties or p not in people for d, p in assignments.items()):
        raise HTTPException(422, "Assignments must name known company duties and people")


@app.post("/api/handover")
def handover(h: Handover, request: Request = None):
    with LOCK:
        d = world_dir(h.seed)
        validate_assignments(d, h.assign)
        w = json.loads((d / "world.json").read_text())
        args = []
        for duty, person in h.assign.items():
            args += ["--assign", f"{duty}={person}"]
        out = cli("handover", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], *args, "--port", PORT)
        out["failures_after"] = enrich(d, out.get("failures_after", []))
        if request is not None:
            db = auth_db()
            identity = security.session(request, db, DATA, required=False)
            if identity:
                plan = {row["duty"]: row["person"] for row in out["accepted"]}
                out["preview_token"] = security.issue_preview(db, identity, h.seed, plan, out["live_hash_after"])
        return out


class Ask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(default=7, ge=0, le=2_147_483_647)
    question: str = Field(min_length=1, max_length=2000)


@app.post("/api/ask")
def ask(a: Ask):
    with LOCK:
        d = world_dir(a.seed)
        return cli("ask", "--world", d, "--beliefs", d / "beliefs.json", "--question", a.question, "--port", PORT, "--offline")


@app.get("/api/cut")
def cut(seed: int = 7):
    with LOCK:
        d = world_dir(seed)
        w = json.loads((d / "world.json").read_text())
        return cli("cut", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], "--port", PORT)


class Commit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(default=7, ge=0, le=2_147_483_647)
    assign: dict[Identifier, Identifier] = Field(max_length=100)
    preview_token: str = Field(default="", max_length=128)
    consent_confirmed: bool = False


@app.post("/api/commit")
def commit(c: Commit, request: Request):
    """Writes accepted successors to the LIVE graph, then to a git repo file, and reads both back (a real write)."""
    with LOCK:
        db = auth_db()
        identity = security.session(request, db, DATA)
        preview = security.check_preview(db, c.preview_token, identity, c.seed, c.assign)
        if c.consent_confirmed is not True:
            raise HTTPException(422, "Confirm successor agreement before saving the plan")
        import subprocess as sp
        d = world_dir(c.seed)
        validate_assignments(d, c.assign)
        w = json.loads((d / "world.json").read_text())
        repo = DATA / "ops-repo"
        from baton import graph as graph_helpers, load as loader, commit as commits
        live, _ = loader.ensure(graph_helpers.connect(PORT), w)
        if graph_helpers.fingerprint(live) != preview["fingerprint"]:
            raw = sorted(f"{duty}={person}" for duty, person in c.assign.items())
            op = security.digest(json.dumps([live.name, w["leaver"], w["leave_at"], raw]))[:24]
            saved = commits._safe_read(repo, f".baton/receipts/{op}.json") if repo.exists() else None
            if not saved or json.loads(saved).get("operation_id") != op:
                raise HTTPException(409, "Company ownership changed; preview the plan again")
        if not (repo / ".git").exists():
            repo.mkdir(parents=True, exist_ok=True)
            sp.run(["git", "init", "-q", str(repo)], check=True)
            sp.run(["git", "-C", str(repo), "-c", "user.email=baton@localhost", "-c", "user.name=Baton", "commit", "-q",
                    "--allow-empty", "-m", "init ops repo"], check=True)
        args = []
        for duty, person in c.assign.items():
            args += ["--assign", f"{duty}={person}"]
        return cli("commit", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], "--repo", repo,
                   "--port", PORT, *args)


@app.get("/api/catalogue")
def catalogue():
    return cli("ask", "--catalogue")


@app.get("/api/company")
def company_context():
    from .company import context
    with LOCK:
        return context(world_dir(7))


class FollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    work_id: Identifier
    owner: Identifier
    due: date
    notes: str = Field(default="", max_length=2000)


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["todo", "done"]


@app.get("/api/company/tasks")
def company_tasks(request: Request):
    from . import company
    security.session(request, auth_db(), DATA)
    with LOCK:
        return {"tasks": company.tasks(DATA)}


@app.post("/api/company/tasks", status_code=201)
def create_follow_up(body: FollowUp, request: Request):
    from . import company
    import time, uuid
    db = auth_db()
    security.session(request, db, DATA)
    with LOCK, db.lock("baton:company:tasks", timeout=30, blocking_timeout=10):
        world = json.loads((world_dir(7) / "world.json").read_text())
        if not body.title.strip() or body.work_id not in {w["id"] for w in company.WORK}:
            raise HTTPException(422, "Choose a company responsibility and enter a task title")
        eligible = {p["id"] for p in world["people"] if p["left_at"] is None and p["id"] != world["leaver"]}
        if body.owner not in eligible:
            raise HTTPException(422, "Choose an active teammate who is staying")
        rows = company.tasks(DATA)
        if len(rows) >= 200:
            raise HTTPException(409, "This local workspace has reached its 200-task limit")
        task = {"id": uuid.uuid4().hex, "title": body.title.strip(), "work_id": body.work_id,
                "owner": body.owner, "due": body.due.isoformat(), "notes": body.notes.strip(), "status":"todo",
                "created_at": int(time.time()*1000), "created_by":"local_operator", "completed_at":None}
        rows.append(task)
        company.save_tasks(DATA, rows)
        return task


@app.patch("/api/company/tasks/{task_id}")
def update_follow_up(task_id: str, body: TaskStatus, request: Request):
    from . import company
    import time
    db = auth_db()
    security.session(request, db, DATA)
    with LOCK, db.lock("baton:company:tasks", timeout=30, blocking_timeout=10):
        rows = company.tasks(DATA)
        task = next((r for r in rows if r["id"] == task_id), None)
        if task is None:
            raise HTTPException(404, "Task not found")
        task["status"] = body.status
        task["completed_at"] = int(time.time()*1000) if body.status == "done" else None
        company.save_tasks(DATA, rows)
        return task


@app.get("/api/graph")
def graph_view(seed: int = 7):
    from baton import explore
    with LOCK:
        directory = world_dir(seed)
        world = json.loads((directory / "world.json").read_text())
        try:
            return explore.run(directory, directory / "beliefs.json", world["leaver"], PORT)
        except Exception as err:
            from baton.graph import Unreachable
            if isinstance(err, Unreachable):
                raise HTTPException(503, str(err))
            raise


@app.get("/api/receipts")
def receipts(seed: int = 7):
    from baton.graph import graph_name
    world_dir(seed)
    with LOCK:
        directory = DATA / "ops-repo" / ".baton" / "receipts"
        records = []
        for path in directory.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("graph") == graph_name(seed):
                records.append({key: record.get(key) for key in (
                    "operation_id", "created_at", "state", "committed", "refused", "ready_to_leave", "external")})
        return {"seed": seed, "receipts": sorted(records, key=lambda item: (item["created_at"] or 0, item["operation_id"]), reverse=True)}


@app.get("/api/amb")
def acme(step: int = 50):
    from baton import amb_demo
    if not 0 <= step <= 50:
        raise HTTPException(422, "step must be between 0 and 50")
    return amb_demo.snapshot(PORT, step)


class AcmeQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(pattern="^(owner|oncall|page|impact|incident)$")
    subject: str = Field(min_length=1, max_length=100)
    step: int = Field(default=50, ge=0, le=50)


@app.post("/api/amb/ask")
def acme_ask(question: AcmeQuestion):
    from baton import amb_demo
    return amb_demo.ask(PORT, question.tool, question.subject, question.step)


@app.get("/api/amb/questions/{qid}")
def acme_question(qid: str):
    from baton import amb_demo
    try:
        return amb_demo.benchmark_question(PORT, qid)
    except ValueError as error:
        raise HTTPException(404, str(error))


from fastapi.staticfiles import StaticFiles

WEB = ROOT / "web"
if not WEB.is_dir():
    WEB = Path(sys.prefix) / "share" / "baton" / "web"
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="website")
