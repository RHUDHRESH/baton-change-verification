"""Independent reference oracle (locked). Pure Python BFS over world.json, written before the product code.
The product must reach the same answers through FalkorDB. Nothing here imports the product."""

MAX_HOPS = 4


def _active(person, t):
    return person.get("left_at") is None or person["left_at"] > t


def _edges(world, beliefs, lane):
    """Return adjacency builders for a lane: W (owner fields only), R (all records), G (records + promoted beliefs)."""
    recs = world["records"]
    owner = [r for r in recs if r["type"] == "OWNER"]
    if lane == "W":
        return owner, [], [], [], []
    routes = [r for r in recs if r["type"] == "ROUTES_TO"]
    shifts = [r for r in recs if r["type"] == "SHIFT"]
    esc = [r for r in recs if r["type"] == "ESCALATES_TO"]
    holds = [] if lane != "G" else [b for b in beliefs if promoted(world, b)]
    return owner, routes, shifts, esc, holds


def source_index(world):
    idx = {}
    for kind, key in (("message", "messages"), ("joblog", "joblogs"), ("ticket", "tickets")):
        for x in world.get(key, []):
            idx[x["id"]] = kind
    for r in world["records"]:
        idx[r["id"]] = "record"
    return idx


def promoted(world, belief):
    """Gate: every cited source exists, at least 2 sources, from at least 2 different source types."""
    idx = source_index(world)
    refs = belief.get("sources", [])
    if len(refs) < 2 or any(r not in idx for r in refs):
        return False
    return len({idx[r] for r in refs}) >= 2


def all_events(world, beliefs, lane):
    evs = [(e["duty"], e["at"]) for e in world["events"]]
    if lane == "G":
        for b in beliefs:
            if promoted(world, b):
                evs += [(b["duty"], e["at"]) for e in b.get("events", [])]
    return sorted(set(evs))


def covered(world, beliefs, lane, duty, t, people):
    owner, routes, shifts, esc, holds = _edges(world, beliefs, lane)
    if lane == "W":
        return any(o["duty"] == duty and o.get("since", 0) <= t and _active(people[o["person"]], t) for o in owner)
    frontier = [("duty", duty)]
    seen = set(frontier)
    for _ in range(MAX_HOPS):
        nxt = []
        for kind, node in frontier:
            out = []
            if kind == "duty":
                out += [("person", o["person"]) for o in owner if o["duty"] == node and o.get("since", 0) <= t]
                out += [("person", b["person"]) for b in holds if b["duty"] == node]
                out += [("rota", r["rota"]) for r in routes if r["duty"] == node]
            elif kind == "rota":
                out += [("person", s["person"]) for s in shifts if s["rota"] == node and s["from"] <= t < s["to"]]
            elif kind == "person":
                out += [("person", e["to_person"]) for e in esc if e["from_person"] == node]
            for o in out:
                if o[0] == "person" and _active(people[o[1]], t):
                    return True
                if o not in seen:
                    seen.add(o)
                    nxt.append(o)
        frontier = nxt
    return False


def expected_failures(world, beliefs, lane):
    """Events in the window that are covered while the leaver is present but not covered once they leave."""
    now, day, win = world["now"], world["day_ms"], world["window_days"]
    live = {p["id"]: dict(p) for p in world["people"]}
    fork = {k: dict(v) for k, v in live.items()}
    fork[world["leaver"]]["left_at"] = world["leave_at"]
    out = set()
    for duty, at in all_events(world, beliefs, lane):
        if not (now <= at < now + win * day):
            continue
        if lane == "W":
            # depth-1 template: only duties whose owner field names the leaver
            if not any(o["duty"] == duty and o["person"] == world["leaver"]
                       for o in world["records"] if o["type"] == "OWNER"):
                continue
        if covered(world, beliefs, lane, duty, at, live) and not covered(world, beliefs, lane, duty, at, fork):
            out.add((duty, at))
    return out
