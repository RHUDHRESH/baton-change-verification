# Prompt and cache design adapted from agent-memory-bench by Liz Zhang (MIT),
# Copyright (c) 2026 Liz Zhang — MIT License (see third_party/amb/LICENSE)
# https://github.com/zhang-liz/agent-memory-bench (amb/extract.py: extraction cached on disk per dataset, model and
# prompt version, so every condition replays identical facts).
"""`python -m baton extract`: a model reads the company's chat, job logs and tickets and proposes beliefs.

A belief is {id, person, duty, duty_name, kind, claim, events, sources}: "this person does or owes this, and here is
where it says so". The model only proposes; the rehearsal's gate decides what is promoted.

Every run is cached under --cache-dir as <input_sha16>-<model>-<key>.json, key = sha256(input bytes + model +
PROMPT_VERSION)[:16], holding {model, prompt_version, input_sha, created, beliefs, usage}. The input bytes are exactly
what the extractor reads (`extract_input`: the clock, people id/name/team/role/left_at, duties, every record except
CAN capability records, messages, job logs, tickets) as canonical JSON, so any change to what the model sees misses
the cache, while data the model never sees (capability, capacity) cannot invalidate it. --offline only replays: with
--model it replays that model's run for this exact input; without --model the newest run for it, whatever the
model. A miss exits 4 and writes nothing. The output file is json.dumps(beliefs, indent=1, sort_keys=True), so replays are
byte-identical to the first run.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import llm

PROMPT_VERSION = "v2"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "fixtures" / "extract_cache"
KEYS = ("id", "person", "duty", "duty_name", "kind", "claim", "events", "sources")

SCHEMA = {
    "type": "object",
    "properties": {"beliefs": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"}, "person": {"type": "string"}, "duty": {"type": "string"},
            "duty_name": {"type": "string"}, "kind": {"type": "string"}, "claim": {"type": "string"},
            "events": {"type": "array", "items": {
                "type": "object", "properties": {"at": {"type": "integer"}, "label": {"type": "string"}},
                "required": ["at", "label"], "additionalProperties": False}},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": list(KEYS), "additionalProperties": False}}},
    "required": ["beliefs"], "additionalProperties": False,
}


# ---- cache (shared with lane_a) ----------------------------------------------------------------------------------
class CacheMiss(Exception):
    """Offline and nothing cached for this exact world; the CLI turns this into exit code 4."""


def read_world(world_dir):
    return json.loads((Path(world_dir) / "world.json").read_text())


def extract_input(w):
    """The part of a world the extractor reads (prompt and fake model alike). Capability data is not part of it."""
    return {"now": w["now"], "day_ms": w["day_ms"],
            "people": [{k: p.get(k) for k in ("id", "name", "team", "role", "left_at")} for p in w["people"]],
            "duties": w["duties"], "records": [r for r in w["records"] if r.get("type") != "CAN"],
            "messages": w.get("messages", []), "joblogs": w.get("joblogs", []), "tickets": w.get("tickets", [])}


def input_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _safe(model):
    return re.sub(r"[^A-Za-z0-9._-]", "_", model)


def cache_file(cache_dir, ibytes, model, version, extra=b""):
    isha = hashlib.sha256(ibytes).hexdigest()
    key = hashlib.sha256(ibytes + model.encode() + version.encode() + extra).hexdigest()[:16]
    return Path(cache_dir) / f"{isha[:16]}-{_safe(model)}-{key}.json"


def lookup(cache_dir, ibytes, model, version, extra=b"", match=lambda e: True, exact_only=False):
    """Return (path, entry) for this exact input, or (None, None).

    With a model: the entry under the current key; unless exact_only, else the newest entry of that model for this
    input (an older prompt version). Without a model: the newest entry for this input, any model. Every candidate
    must carry the full input sha, so a 16-character prefix collision can never serve another world's answer."""
    wsha = hashlib.sha256(ibytes).hexdigest()
    if model:
        p = cache_file(cache_dir, ibytes, model, version, extra)
        if p.is_file():
            e = json.loads(p.read_text())
            if e.get("input_sha") == wsha and match(e):
                return p, e
        if exact_only:
            return None, None
    pattern = f"{wsha[:16]}-{_safe(model)}-*.json" if model else f"{wsha[:16]}-*.json"
    found = []
    for p in sorted(Path(cache_dir).glob(pattern)):
        e = json.loads(p.read_text())
        if e.get("input_sha") == wsha and (not model or e.get("model") == model) and match(e):
            found.append((e.get("created", ""), p.name, p, e))
    if not found:
        return None, None
    _, _, p, e = max(found, key=lambda x: (x[0], x[1]))
    return p, e


def store(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(entry, created=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    path.write_text(json.dumps(entry, indent=1, sort_keys=True) + "\n")


def write_out(out, obj):
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, sort_keys=True))


def default_model():
    return os.environ.get("BATON_MODEL", "claude-haiku-4-5")


# ---- prompt ------------------------------------------------------------------------------------------------------
def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC (%a)")


def _record_line(r):
    if r["type"] == "OWNER":
        return f"{r['id']} | OWNER | duty {r['duty']} is owned by {r['person']}"
    if r["type"] == "ROUTES_TO":
        return f"{r['id']} | ROUTES_TO | duty {r['duty']} pages rota {r['rota']}"
    if r["type"] == "SHIFT":
        return f"{r['id']} | SHIFT | {r['person']} is on {r['rota']} from {_iso(r['from'])} to {_iso(r['to'])}"
    return f"{r['id']} | ESCALATES_TO | {r['from_person']} escalates to {r['to_person']}"


def prompt(w):
    w = extract_input(w)
    people = "\n".join(f"{p['id']} | {p['name']} | {p.get('team') or '-'} | {p.get('role') or '-'} | "
                       + (f"left {_iso(p['left_at'])}" if p.get("left_at") else "active") for p in w["people"])
    duties = "\n".join(f"{d['id']} | {d['name']} | {d['kind']}" for d in w["duties"]) or "(none)"
    records = "\n".join(_record_line(r) for r in w["records"]) or "(none)"
    msgs = "\n".join(f"{m['id']} | {_iso(m['at'])} | {m.get('channel', '-')} | {m['author']} | {m['text']}"
                     for m in w.get("messages", [])) or "(none)"
    logs = "\n".join(f"{j['id']} | {_iso(j['at'])} | {j['job']} | {j['actor']} | {j['status']}"
                     for j in w.get("joblogs", [])) or "(none)"
    tkts = "\n".join(f"{t['id']} | {_iso(t['at'])} | {t['author']} | {t['text']}"
                     for t in w.get("tickets", [])) or "(none)"
    return (
        "You read a company's chat, job logs and tickets and report who actually does or owes what, with sources. "
        "The company's records (owners, rotas, escalations) are listed too; your job is what the records do NOT "
        "show: jobs someone keeps alive by hand, promises made to customers, duties people say were handed over.\n\n"
        "Rules:\n"
        "- One belief per (person, duty). person must be a person id from PEOPLE.\n"
        "- duty: reuse a duty id from DUTIES when the belief is about one; otherwise invent a short, stable, "
        "lowercase id that describes the duty. duty_name: a short human name. kind: job, promise, vendor, "
        "oncall, report or other.\n"
        "- claim: one plain sentence saying what the person does or owes and why you think so.\n"
        "- events: deadlines or scheduled moments this duty needs that are NOT already a scheduled duty, as "
        "{at: epoch milliseconds UTC, label}. Use the time stated in the text; if the text gives a day but no "
        "time, use the start of that day (00:00 UTC). Use [] when there are none.\n"
        "- sources: the ids (msg-, log-, tkt-, rec-) of every item that supports the belief, copied exactly. "
        "Never invent an id.\n"
        "- Report weak or second-hand claims too (one chat line, hearsay, guesses), citing only what exists. A "
        "separate gate decides what is trusted; do not filter for it.\n\n"
        f"Now: {_iso(w['now'])} = {w['now']} ms. One day = {w['day_ms']} ms.\n\n"
        f"PEOPLE (id | name | team | role | status)\n{people}\n\n"
        f"DUTIES (id | name | kind)\n{duties}\n\n"
        f"RECORDS (id | type | meaning)\n{records}\n\n"
        f"MESSAGES (id | time | channel | author | text)\n{msgs}\n\n"
        f"JOB LOGS (id | time | job | actor | status)\n{logs}\n\n"
        f"TICKETS (id | time | author | text)\n{tkts}\n"
    )


def _normalise(raw):
    out = []
    for i, b in enumerate(raw, 1):
        x = {k: b.get(k) for k in KEYS}
        x["id"] = f"b-{i:02d}"
        x["events"] = [{"at": int(e["at"]), "label": str(e["label"])} for e in (x["events"] or [])]
        x["sources"] = [str(s) for s in (x["sources"] or [])]
        for k in ("person", "duty", "duty_name", "kind", "claim"):
            x[k] = "" if x[k] is None else str(x[k])
        out.append(x)
    return out


# ---- command -----------------------------------------------------------------------------------------------------
def run(world_dir, out, model=None, offline=False, cache_dir=None):
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE
    w = extract_input(read_world(world_dir))
    wbytes = input_bytes(w)
    path, entry = lookup(cache_dir, wbytes, model, PROMPT_VERSION, exact_only=not offline and bool(model))
    if entry is None and offline:
        raise CacheMiss(f"no cached extraction for this world (model {model or 'any'}); "
                        f"run without --offline with a model key")
    cached = entry is not None
    if not cached:
        model = model or default_model()
        path = cache_file(cache_dir, wbytes, model, PROMPT_VERSION)
        if model == llm.FAKE:
            print(f"baton extract: model 'fake' is {llm.FAKE_LABEL}", file=sys.stderr)
            beliefs, usage = llm.fake_beliefs(w), None
        else:
            obj, usage = llm.call_json(model, prompt(w), SCHEMA, name="beliefs")
            beliefs = _normalise(obj.get("beliefs", []))
        entry = {"model": model, "prompt_version": PROMPT_VERSION, "input_sha": hashlib.sha256(wbytes).hexdigest(),
                 "beliefs": beliefs, "usage": usage}
        store(path, entry)
    write_out(out, entry["beliefs"])
    return {"out": str(out), "model": entry["model"], "prompt_version": entry["prompt_version"], "cached": cached,
            "cache_file": str(path), "beliefs": len(entry["beliefs"]), "usage": entry.get("usage")}
