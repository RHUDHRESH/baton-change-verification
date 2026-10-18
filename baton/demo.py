"""`python -m baton demo`: the whole story in one command, offline.

generate Halden (seed N) -> load into FalkorDB -> rehearse the departure in lanes W, R, G -> hand every G failure to
an active colleague (round-robin) -> show that nothing is left uncovered. Beliefs come from the cached AI extraction
for this exact world (fixtures/extract_cache, keyed by the hash of what the extractor reads; see extract.py); the demo never calls a model
and never sees the generator's planted truth.
"""
import json
import sys
import tempfile
from pathlib import Path

from . import extract, generate, handover, rehearse
from . import graph as G

Q_STAYERS = "MATCH (p:Person) WHERE p.left_at IS NULL AND p.id <> $leaver RETURN p.id ORDER BY p.id"


def beliefs_path(seed, tmp, override=None):
    """The --beliefs file if given, else the newest cached extraction of this exact world written to tmp."""
    if override:
        p = Path(override)
        if not p.is_file():
            print(f"baton demo: beliefs file {p} not found", file=sys.stderr)
            sys.exit(4)
        return p
    p = Path(tmp) / "beliefs.json"
    try:
        extract.run(tmp, p, offline=True)
    except extract.CacheMiss as err:
        print(f"baton demo: seed {seed}: {err}", file=sys.stderr)
        sys.exit(4)
    return p


def run(seed, port, offline=True, beliefs=None):
    # offline is the only mode today: extraction is read from its cache, nothing goes over the network.
    world, _ = generate.build(seed)
    with tempfile.TemporaryDirectory(prefix=f"baton-demo-{seed}-") as tmp:
        (Path(tmp) / "world.json").write_text(json.dumps(world, sort_keys=True, indent=1) + "\n")
        bp = beliefs_path(seed, tmp, beliefs)
        leaver = world["leaver"]
        s = rehearse.open_session(tmp, bp, leaver, port, cmd="demo")
        live = s["live"]
        hash_before = G.fingerprint(live)
        lanes, g_rows, unpromoted = {}, [], []
        for lane in "WRG":
            r = rehearse.on_fork(s, lane, "all")
            rows = rehearse.failures(s, r["present"], r["gone"])
            lanes[lane] = {"failures": len(rows)}
            if lane == "G":
                g_rows, unpromoted = rows, r["unpromoted"]
        stayers = [x[0] for x in live.ro_query(Q_STAYERS, {"leaver": leaver}).result_set]
        duties = sorted({r["duty"] for r in g_rows})
        assigns = [f"{du}={stayers[i % len(stayers)]}" for i, du in enumerate(duties)] if stayers else []
        h = handover.run(tmp, bp, leaver, assigns, port, session=s)
        hash_after = G.fingerprint(live)
    return {"seed": seed, "offline": bool(offline), "graph": live.name, "leaver": leaver, "lanes": lanes,
            "live_hash_before": hash_before, "live_hash_after": hash_after,
            "after_handover": {"failures": len(h["failures_after"]), "accepted": len(h["accepted"]),
                               "refused": len(h["refused"])},
            "unpromoted": len(unpromoted)}
