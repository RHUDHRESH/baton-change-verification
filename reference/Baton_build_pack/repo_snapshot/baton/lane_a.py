"""`python -m baton lane-a`: the "AI alone" lane. The same model reads the same raw world, with no graph, and answers
the rehearsal's question directly. Its answer is what Baton is compared against.

Output schema: {model, question, failures: [{duty, at, why}], owners: [{duty, person, basis}]}.
Cached exactly like `extract` (see extract.py), under fixtures/lane_a_cache by default, with the leaver in the key:
<input_sha16>-<model>-<key>.json, key = sha256(input bytes + model + PROMPT_VERSION + leaver)[:16], holding
{model, prompt_version, input_sha, leaver, created, answer, usage}. The input is the world the model is shown
(`lane_a_input`: everything except capability data - CAN records and people[].capacity - which is not part of this
question), serialised the way the generator writes world.json. --offline replays or exits 4.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import llm
from .extract import CacheMiss, cache_file, default_model, lookup, read_world, store, write_out

PROMPT_VERSION = "v1"
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "fixtures" / "lane_a_cache"

SCHEMA = {
    "type": "object",
    "properties": {
        "failures": {"type": "array", "items": {
            "type": "object",
            "properties": {"duty": {"type": "string"}, "at": {"type": "integer"}, "why": {"type": "string"}},
            "required": ["duty", "at", "why"], "additionalProperties": False}},
        "owners": {"type": "array", "items": {
            "type": "object",
            "properties": {"duty": {"type": "string"}, "person": {"type": "string"}, "basis": {"type": "string"}},
            "required": ["duty", "person", "basis"], "additionalProperties": False}},
    },
    "required": ["failures", "owners"], "additionalProperties": False,
}


def lane_a_input(w):
    """The world as the AI-alone lane sees it: capability data (CAN records, people[].capacity) left out."""
    return dict(w, records=[r for r in w["records"] if r.get("type") != "CAN"],
                people=[{k: v for k, v in p.items() if k != "capacity"} for p in w["people"]])


def input_bytes(w):
    return (json.dumps(w, sort_keys=True, indent=1) + "\n").encode()


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def question(w, leaver, leave_at):
    end = w["now"] + w["window_days"] * w["day_ms"]
    return (f"{leaver} leaves at {leave_at} ({_iso(leave_at)}). Which scheduled events in the window "
            f"[{w['now']}, {end}) ({_iso(w['now'])} to {_iso(end)}) will have nobody able to act if {leaver} leaves "
            f"at {leave_at}, and who owns each duty now?")


def prompt(w, leaver, leave_at):
    return (
        "Below is everything a company's systems hold, as raw JSON: people (left_at = when they left, null = still "
        "here), duties, records (OWNER, ROUTES_TO rota, SHIFT on a rota with from/to, ESCALATES_TO), scheduled "
        "events (duty, at), chat messages, job logs and tickets. Times are epoch milliseconds UTC.\n\n"
        f"QUESTION: {question(w, leaver, leave_at)}\n\n"
        "Answer with: failures = one entry per scheduled event (or deadline you found in the text) that nobody "
        "will be able to act on, as {duty, at (epoch ms), why}; owners = who owns each duty right now according to "
        "everything you read, as {duty, person (person id), basis (cite ids)}. Include duties that appear only in "
        "chat, job logs or tickets.\n\n"
        f"WORLD:\n{json.dumps(w, sort_keys=True)}\n"
    )


def run(world_dir, leaver, out, model=None, offline=False, cache_dir=None):
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE
    w = lane_a_input(read_world(world_dir))
    wbytes = input_bytes(w)
    extra = leaver.encode()
    same_leaver = lambda e: e.get("leaver") == leaver  # noqa: E731
    path, entry = lookup(cache_dir, wbytes, model, PROMPT_VERSION, extra, match=same_leaver,
                         exact_only=not offline and bool(model))
    if entry is None and offline:
        raise CacheMiss(f"no cached AI-alone answer for this world and leaver {leaver} (model {model or 'any'}); "
                        f"run without --offline with a model key")
    cached = entry is not None
    if not cached:
        leave_at = w["leave_at"] if leaver == w["leaver"] else w["now"]
        model = model or default_model()
        path = cache_file(cache_dir, wbytes, model, PROMPT_VERSION, extra)
        if model == llm.FAKE:
            print(f"baton lane-a: model 'fake' is {llm.FAKE_LABEL}", file=sys.stderr)
            obj, usage = llm.fake_lane_a(w, leaver, leave_at), None
        else:
            obj, usage = llm.call_json(model, prompt(w, leaver, leave_at), SCHEMA, name="ai_alone")
        answer = {"model": model, "question": question(w, leaver, leave_at),
                  "failures": obj.get("failures", []), "owners": obj.get("owners", [])}
        entry = {"model": model, "prompt_version": PROMPT_VERSION, "input_sha": hashlib.sha256(wbytes).hexdigest(),
                 "leaver": leaver, "answer": answer, "usage": usage}
        store(path, entry)
    write_out(out, entry["answer"])
    return {"out": str(out), "model": entry["model"], "prompt_version": entry["prompt_version"], "cached": cached,
            "cache_file": str(path), "failures": len(entry["answer"]["failures"]),
            "owners": len(entry["answer"]["owners"])}
