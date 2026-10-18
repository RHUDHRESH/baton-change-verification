# Adapted from agent-memory-bench by Liz Zhang (MIT), https://github.com/zhang-liz/agent-memory-bench
# Copyright (c) 2026 Liz Zhang — MIT License (see third_party/amb/LICENSE)
# (amb/llm.py: provider routing, rate-limit retry and usage accounting; amb/extract.py: the two structured-output
# calls; amb/fake.py: the idea of a scripted offline stand-in). Changes for Baton: one call_json() entry point, SDKs
# imported lazily, missing keys reported as ModelUnavailable, and a Baton-specific scripted "fake" model.
"""One structured-output call to a language model, plus the scripted stand-in used for offline plumbing tests.

`call_json(model, prompt, schema)` returns (parsed_json, usage). Models whose name starts with gpt- go through the
OpenAI Responses API with a strict json_schema; claude-* models go through Anthropic Messages with an output schema.
The SDKs are imported only when a real call is made, so offline replay needs neither SDK nor key.

Model "fake" is NOT a language model: it is a few lines of deterministic Python (see fake_beliefs / fake_lane_a)
that let the cache, CLI and rehearsal plumbing run with no network. Its output must never be reported as a result.
"""
import os

FAKE = "fake"
FAKE_LABEL = "fake (scripted stand-in, not a real model; plumbing tests only)"

# USD per million tokens (from amb/llm.py, checked there 2026-09-25 / 2026-10-02). Unknown models get usd None.
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50, "cache_read": 0.075},
    "gpt-6-luna": {"input": 0.10, "output": 0.50, "cache_read": 0.01},
    "gpt-6.1-sol": {"input": 2.00, "output": 10.00, "cache_read": 0.10},
}
KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class ModelUnavailable(Exception):
    """No key or no SDK for a real model; the CLI turns this into exit code 5."""


def provider(model):
    if model == FAKE:
        return FAKE
    return "openai" if model.startswith(("gpt-", "o1", "o3", "o4")) else "anthropic"


def with_rate_limit_retry(fn, *args, **kwargs):
    """Call fn, waiting out rate limits. SDK retries are too short when several runs share one org quota."""
    import random
    import time

    for attempt in range(12):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # match both SDKs' RateLimitError without importing either here
            if type(e).__name__ != "RateLimitError" or attempt == 11:
                raise
            time.sleep(min(60, 2 ** attempt) + random.random())


def require_key(model):
    """Raise ModelUnavailable unless a real model's API key is in the environment."""
    prov = provider(model)
    if prov == FAKE:
        return
    env = KEY_ENV[prov]
    if not os.environ.get(env):
        raise ModelUnavailable(f"model {model} needs {env} in the environment (no key found); "
                               f"use --offline to replay a cached run, or --model fake for a plumbing test")


def _usage(model, inp, out, cached):
    rec = {"input": inp, "output": out, "cache_read": cached}
    p = PRICES.get(model)
    rec["usd"] = None if p is None else round(((inp - cached) * p["input"] + cached * p["cache_read"]
                                               + out * p["output"]) / 1e6, 6)
    return rec


def call_json(model, prompt, schema, name="answer", max_tokens=16000):
    """One structured call. Returns (obj, usage). Raises ModelUnavailable if the key or SDK is missing."""
    import json

    require_key(model)
    if provider(model) == "openai":
        try:
            from openai import OpenAI
        except ImportError as err:
            raise ModelUnavailable("the openai package is not installed (pip install openai)") from err
        resp = with_rate_limit_retry(
            OpenAI().responses.create, model=model, input=prompt,
            text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
            store=False, max_output_tokens=max_tokens)
        raw, u = resp.output_text, resp.usage
        det = getattr(u, "input_tokens_details", None)
        usage = _usage(model, getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0,
                       getattr(det, "cached_tokens", 0) or 0)
    else:
        try:
            from anthropic import Anthropic
        except ImportError as err:
            raise ModelUnavailable("the anthropic package is not installed (pip install anthropic)") from err
        resp = with_rate_limit_retry(
            Anthropic().messages.create, model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}})
        raw = next((b.text for b in resp.content if b.type == "text"), "")
        u = resp.usage
        cached = getattr(u, "cache_read_input_tokens", 0) or 0
        usage = _usage(model, (getattr(u, "input_tokens", 0) or 0) + cached, getattr(u, "output_tokens", 0) or 0,
                       cached)
    try:
        return json.loads(raw), usage
    except json.JSONDecodeError as err:
        raise ValueError(f"model {model} returned unparseable output: {raw[:200]!r}") from err


# ---- the scripted stand-in ---------------------------------------------------------------------------------------
def _norm(s):
    return " " + "".join(c if c.isalnum() else " " for c in s.lower()) + " "


def fake_beliefs(world):
    """Scripted, deterministic 'extraction' from the raw world (never a model, never the generator's key).

    One belief per message whose author is a known person and which names a job (by id or name) or a customer
    (a name seen in a ticket author's brackets): it cites the message plus the job logs that author wrote for that
    job, or the tickets from that customer. Weak claims are kept; the gate decides.
    """
    people = {p["id"]: p for p in world["people"]}
    jobs = [d for d in world["duties"] if d["id"].startswith("d-job-")]
    customers = sorted({t["author"].rsplit("(", 1)[1].rstrip(")").strip() for t in world.get("tickets", [])
                        if t.get("author", "").endswith(")") and "(" in t["author"]})
    out = []
    for m in world.get("messages", []):
        who = m.get("author")
        if who not in people:
            continue
        text = _norm(m["text"])
        hit = None
        for d in jobs:
            slug = d["id"][len("d-job-"):]
            if _norm(slug) in text or _norm(d["name"]) in text:
                logs = [j["id"] for j in world.get("joblogs", []) if j["job"] == d["id"] and j["actor"] == who]
                hit = (d["id"], d["name"], "job", logs)
                break
        if hit is None:
            for c in customers:
                if _norm(c) in text:
                    tkts = [t["id"] for t in world.get("tickets", []) if t["author"].endswith(f"({c})")]
                    slug = "-".join(_norm(c).split())
                    hit = (f"promise-{slug}", f"Commitment to {c}", "promise", tkts)
                    break
        if hit is None:
            continue
        duty, duty_name, kind, extra = hit
        out.append({"id": f"b-{len(out) + 1:02d}", "person": who, "duty": duty, "duty_name": duty_name, "kind": kind,
                    "claim": f"[fake model, scripted] {people[who]['name']} mentioned {duty_name} in {m['id']}",
                    "events": [], "sources": [m["id"]] + extra})
    return out


def fake_lane_a(world, leaver, leave_at):
    """Scripted 'AI alone' answer: events in the window whose only OWNER record is the leaver. Plumbing only."""
    end = world["now"] + world["window_days"] * world["day_ms"]
    owners = {}
    for r in world["records"]:
        if r["type"] == "OWNER":
            owners.setdefault(r["duty"], set()).add(r["person"])
    failures = [{"duty": e["duty"], "at": e["at"], "why": f"[fake model, scripted] only owner record is {leaver}"}
                for e in world["events"] if leave_at <= e["at"] < end and owners.get(e["duty"]) == {leaver}]
    own = [{"duty": d, "person": p, "basis": "[fake model, scripted] OWNER record"}
           for d in sorted(owners) for p in sorted(owners[d])]
    return {"failures": failures, "owners": own}
