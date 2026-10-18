"""Baton HTTP API (thin wrapper over the `python -m baton` CLI contract). Every decision is made by the CLI in FalkorDB."""
import json, os, subprocess, sys, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("BATON_DATA", "/tmp/baton_data"))
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
HOST = os.environ.get("FALKORDB_HOST", "localhost")
LOCK = threading.Lock()
app = FastAPI(title="Baton API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def cli(*args):
    env = dict(os.environ, FALKORDB_HOST=HOST)
    r = subprocess.run([sys.executable, "-m", "baton", *map(str, args)], cwd=ROOT, capture_output=True, text=True,
                       timeout=300, env=env)
    if r.returncode != 0:
        raise HTTPException(503 if "falkordb" in (r.stderr + r.stdout).lower() else 500, (r.stderr or r.stdout)[-800:])
    return json.loads(r.stdout) if r.stdout.strip().startswith(("{", "[")) else r.stdout


def world_dir(seed: int) -> Path:
    d = DATA / f"seed_{seed}"
    with LOCK:
        if not (d / "world.json").exists():
            cli("generate", "--seed", seed, "--out", d)
        if not (d / "beliefs.json").exists():
            # replay the committed AI extraction for this exact company (no key needed); a live model only if configured
            args = ["extract", "--world", d, "--out", d / "beliefs.json"]
            if os.environ.get("BATON_OFFLINE", "1") == "1":
                args.append("--offline")
            cli(*args)
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


@app.get("/api/health")
def health():
    """Fails loudly when FalkorDB is down: the product does nothing without the graph."""
    from falkordb import FalkorDB
    try:
        FalkorDB(host=HOST, port=PORT).connection.ping()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"FalkorDB is not reachable at {HOST}:{PORT}: {e}")
    return {"ok": True, "falkordb": f"{HOST}:{PORT}"}


@app.get("/api/demo")
def demo(seed: int = 7):
    d = world_dir(seed)
    w = json.loads((d / "world.json").read_text())
    lanes, out = {}, None
    for lane in ("W", "R", "G"):
        out = cli("rehearse", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], "--lane", lane,
                  "--confirm", "all", "--port", PORT)
        lanes[lane] = {"failures": enrich(d, out["failures"])}
    people = {p["id"]: p for p in w["people"]}
    return {"seed": seed, "now": w["now"], "day_ms": w["day_ms"], "window_days": w["window_days"],
            "leaver": w["leaver"], "leaver_name": people[w["leaver"]]["name"], "leave_at": w["leave_at"],
            "people": w["people"], "lanes": lanes, "unpromoted": out.get("unpromoted", []),
            "live_hash_before": out["live_hash_before"], "live_hash_after": out["live_hash_after"]}


class Handover(BaseModel):
    seed: int = 7
    assign: dict


@app.post("/api/handover")
def handover(h: Handover):
    d = world_dir(h.seed)
    w = json.loads((d / "world.json").read_text())
    args = []
    for duty, person in h.assign.items():
        args += ["--assign", f"{duty}={person}"]
    out = cli("handover", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], *args, "--port", PORT)
    out["failures_after"] = enrich(d, out.get("failures_after", []))
    return out


class Ask(BaseModel):
    seed: int = 7
    question: str


@app.post("/api/ask")
def ask(a: Ask):
    d = world_dir(a.seed)
    return cli("ask", "--world", d, "--beliefs", d / "beliefs.json", "--question", a.question, "--port", PORT)


@app.get("/api/cut")
def cut(seed: int = 7):
    d = world_dir(seed)
    w = json.loads((d / "world.json").read_text())
    return cli("cut", "--world", d, "--beliefs", d / "beliefs.json", "--leaver", w["leaver"], "--port", PORT)


class Commit(BaseModel):
    seed: int = 7
    assign: dict


@app.post("/api/commit")
def commit(c: Commit):
    """Writes accepted successors to the LIVE graph, then to a git repo file, and reads both back (a real write)."""
    import subprocess as sp
    d = world_dir(c.seed)
    w = json.loads((d / "world.json").read_text())
    repo = DATA / "ops-repo"
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
