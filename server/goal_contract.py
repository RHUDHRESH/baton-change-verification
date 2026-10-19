"""Authority and evidence checks for model-authored goal plans.

This module never interprets a goal, chooses a tool, or generates a plan.
"""
import copy
import hashlib
import json
import re

CATALOG_VERSION = "company-goals-v1"
MAX_STEPS = 6
EFFECT_TOOLS = {"publish_task", "verify_release"}
EFFECTS = [
    {"name": "publish_task", "description": "Create the model-authored source-backed Jira task and Slack report in the configured operator destinations, after approval. This creates work; it never claims code is fixed.",
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string", "minLength": 12, "maxLength": 160},
         "description": {"type": "string", "minLength": 30, "maxLength": 3500},
         "source_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8}},
         "required": ["title", "description", "source_ids"], "additionalProperties": False}},
    {"name": "verify_release", "description": "Request the approved immutable FalkorDB-py #212 verification capability. Both declared redis-py environments are required; source repair is disabled. Existing verified evidence may be reused explicitly, never presented as a fresh run.",
     "inputSchema": {"type": "object", "properties": {"change_id": {"type": "string", "enum": ["FalkorDB/falkordb-py#212"]}},
                     "required": ["change_id"], "additionalProperties": False}},
]


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value):
    return hashlib.sha256((value if isinstance(value, bytes) else str(value).encode("utf-8"))).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_arguments(value, schema, path="arguments"):
    """Validate the deliberately small JSON Schema subset used by our tools."""
    kind = schema.get("type")
    types = {"string": str, "object": dict, "array": list, "integer": int, "boolean": bool, "number": (int, float)}
    require(kind in types and isinstance(value, types[kind]) and not (kind in {"integer", "number"} and isinstance(value, bool)),
            path + " has an invalid type")
    if "enum" in schema:
        require(value in schema["enum"], path + " is outside the approved values")
    if kind == "string":
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 2000), path + " length is invalid")
        require(not schema.get("pattern") or re.fullmatch(schema["pattern"], value), path + " format is invalid")
    elif kind == "object":
        props = schema.get("properties", {})
        require(set(schema.get("required", [])).issubset(value), path + " is missing required fields")
        require(schema.get("additionalProperties") is not False or set(value).issubset(props), path + " contains unknown fields")
        for key, item in value.items():
            if key in props:
                validate_arguments(item, props[key], path + "." + key)
    elif kind == "array":
        require(schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 30), path + " item count is invalid")
        for item in value:
            validate_arguments(item, schema.get("items", {}), path + "[]")
    elif kind in {"integer", "number"}:
        require(schema.get("minimum", -1000000) <= value <= schema.get("maximum", 1000000), path + " is out of bounds")
    return value


def _strings(values, name, minimum=0, maximum=8, length=1000):
    require(isinstance(values, list) and minimum <= len(values) <= maximum, name + " count is invalid")
    require(all(isinstance(v, str) and 1 <= len(v.strip()) <= len(v) <= length for v in values), name + " must contain bounded nonempty text")
    return values


def proposal_hash(proposal, goal, evidence, catalog, binding):
    material = {k: v for k, v in proposal.items() if k != "hash"}
    refs = sorted(({k: e.get(k) for k in ("id", "source_id", "sha256", "kind")} for e in evidence), key=lambda e: e["id"])
    return sha(encode({"goal": goal, "proposal": material, "catalog_version": CATALOG_VERSION,
                       "catalog_sha256": sha(encode(catalog)), "evidence": refs, "binding": binding}))


def validate_proposal(proposal, goal, evidence, catalog, binding):
    require(isinstance(goal, str) and 10 <= len(goal.strip()) <= len(goal) <= 1600, "Goal must contain 10 to 1600 characters")
    require(isinstance(binding, str) and re.fullmatch(r"[a-f0-9]{64}", binding), "A current graph evidence binding is required")
    require(isinstance(evidence, list) and 1 <= len(evidence) <= 100, "A plan requires actual inspected graph evidence")
    refs = {e.get("id"): e for e in evidence if isinstance(e, dict)}
    require(len(refs) == len(evidence) and all(isinstance(k, str) and k for k in refs), "Evidence identities are missing or duplicated")
    require(all(re.fullmatch(r"[a-f0-9]{64}", str(e.get("sha256", ""))) for e in evidence), "Evidence must contain actual content hashes")
    source_ids = {e.get("source_id") for e in evidence if e.get("kind") == "source" and e.get("source_id")}
    tools = {t["name"]: t for t in catalog}
    require(len(tools) == len(catalog), "Duplicate capability catalog names")
    require(isinstance(proposal, dict), "The model must produce a structured work proposal")
    allowed = {"hash", "summary", "success_criteria", "assumptions", "questions", "steps", "limitations"}
    require(set(proposal).issubset(allowed), "The proposal contains unsupported fields")
    value = copy.deepcopy(proposal)
    require(isinstance(value.get("summary"), str) and 15 <= len(value["summary"].strip()) <= len(value["summary"]) <= 1800, "The model must explain the proposed work")
    _strings(value.get("success_criteria"), "Success criteria", minimum=1, maximum=6, length=500)
    for field in ("assumptions", "questions", "limitations"):
        value.setdefault(field, [])
        _strings(value[field], field, maximum=8, length=700)
    steps = value.get("steps")
    require(isinstance(steps, list) and 1 <= len(steps) <= MAX_STEPS, "A work proposal needs one to six steps")
    ids = []
    for step in steps:
        require(isinstance(step, dict) and set(step) == {"id", "title", "tool_name", "args", "why", "evidence_ids", "depends_on", "expected_result"}, "Invalid model-authored step fields")
        require(isinstance(step["id"], str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", step["id"]), "Invalid step identity")
        ids.append(step["id"])
        for field, lower, upper in (("title", 5, 180), ("why", 10, 1000), ("expected_result", 5, 700)):
            require(isinstance(step[field], str) and lower <= len(step[field].strip()) <= len(step[field]) <= upper, "Step " + field + " is invalid")
        require(step["tool_name"] in tools, "The model selected an unapproved capability")
        validate_arguments(step["args"], tools[step["tool_name"]]["inputSchema"])
        _strings(step["evidence_ids"], "Step evidence", maximum=15, length=160)
        require(set(step["evidence_ids"]).issubset(refs), "Step cites evidence that was not inspected")
        _strings(step["depends_on"], "Step dependencies", maximum=MAX_STEPS, length=32)
        require(len(set(step["depends_on"])) == len(step["depends_on"]), "Duplicate step dependencies")
        if step["tool_name"] in EFFECT_TOOLS:
            require(step["evidence_ids"] and any(refs[i].get("kind") == "source" for i in step["evidence_ids"]), "An effect requires a source actually inspected by the agent")
            if step["tool_name"] == "publish_task":
                require(set(step["args"]["source_ids"]).issubset(source_ids), "Publication cites a source the agent did not inspect")
    require(len(set(ids)) == len(ids), "Duplicate step identities")
    remaining, completed = {s["id"]: set(s["depends_on"]) for s in steps}, set()
    require(all(deps.issubset(ids) and identity not in deps for identity, deps in remaining.items()), "Unknown or self-dependent plan step")
    while remaining:
        ready = {identity for identity, deps in remaining.items() if deps.issubset(completed)}
        require(ready, "The model proposed a cyclic dependency graph")
        completed.update(ready)
        remaining = {identity: deps for identity, deps in remaining.items() if identity not in ready}
    calculated = proposal_hash(value, goal, evidence, catalog, binding)
    require(not value.get("hash") or value["hash"] == calculated, "The sealed model proposal has changed")
    value["hash"] = calculated
    return value
