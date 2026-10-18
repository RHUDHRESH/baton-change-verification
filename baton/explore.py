"""Read a time-valid company view from a rehearsal fork for visualization."""
from . import rehearse

NODE_QUERY = "MATCH (n) RETURN id(n), labels(n), properties(n)"
EDGE_QUERY = "MATCH (a)-[r]->(b) RETURN id(r), id(a), id(b), type(r), properties(r)"
KINDS = {"Person", "Duty", "Rota"}
RELATIONS = {"OWNER", "ROUTES_TO", "SHIFT", "ESCALATES_TO", "HOLDS", "CAN"}


def run(world_dir, beliefs_file, leaver, port):
    session = rehearse.open_session(world_dir, beliefs_file, leaver, port, cmd="explore")

    def snapshot(fork, present, gone):
        nodes = []
        for identity, labels, props in fork.ro_query(NODE_QUERY).result_set:
            kind = next((label for label in labels if label in KINDS), None)
            if kind:
                nodes.append({"data": {"id": f"n{identity}", "entity_id": props["id"], "kind": kind,
                                       "label": props.get("name", props["id"]), "properties": props,
                                       "departed": kind == "Person" and props.get("left_at") is not None
                                       and props["left_at"] <= session["leave_at"]}})
        identities = {node["data"]["id"] for node in nodes}
        edges = []
        for identity, source, target, kind, props in fork.ro_query(EDGE_QUERY).result_set:
            if kind not in RELATIONS or f"n{source}" not in identities or f"n{target}" not in identities:
                continue
            if not props.get("vf", 0) <= session["leave_at"] < props.get("vt", 253402300799000):
                continue
            sources = props.get("srcs", [props["rec"]] if props.get("rec") else [])
            edges.append({"data": {"id": f"e{identity}", "source": f"n{source}", "target": f"n{target}",
                                   "kind": kind, "label": kind, "source_ids": sources, "properties": props}})
        return {"nodes": nodes, "edges": edges}

    result = rehearse.on_fork(session, "G", "none", after_departure=snapshot)
    return {**result["after"], "at": session["leave_at"], "graph": session["live"].name, "fixture": True,
            "live_hash_before": result["live_hash_before"], "live_hash_after": result["live_hash_after"]}
