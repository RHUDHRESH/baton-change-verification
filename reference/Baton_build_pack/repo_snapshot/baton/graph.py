"""FalkorDB connection and the graph-level helpers every command shares (name, existence, fingerprint, fork)."""
import hashlib
import json
import os
import sys

OPEN = 253_402_300_799_000  # 9999-12-31T23:59:59Z in epoch ms: "still valid"


class Unreachable(Exception):
    """FalkorDB could not be reached; the CLI turns this into exit code 3."""


def graph_name(seed, scale=1):
    """halden_<seed> for the default company; a scaled world (generate --scale N) is halden_<seed>_x<N>."""
    return f"halden_{seed}" if scale == 1 else f"halden_{seed}_x{scale}"


def connect(port):
    """Return a live FalkorDB client for FALKORDB_HOST (default localhost) and `port`, or raise Unreachable."""
    from falkordb import FalkorDB
    host = os.environ.get("FALKORDB_HOST", "localhost")
    try:
        db = FalkorDB(host=host, port=port, socket_connect_timeout=3)
        db.connection.ping()
    except Exception as err:  # redis raises several connection error types; all mean the same thing here
        raise Unreachable(f"FalkorDB is not reachable at {host}:{port}: {err}") from err
    return db


def die_unreachable(err):
    print(str(err), file=sys.stderr)
    sys.exit(3)


def exists(db, name):
    return name in db.list_graphs()


def fingerprint(g):
    """Deterministic digest of every node and edge with all properties, computed by read-only queries."""
    nodes = g.ro_query("MATCH (n) RETURN labels(n), properties(n)").result_set
    edges = g.ro_query("MATCH (a)-[r]->(b) RETURN a.id, type(r), properties(r), b.id").result_set
    rows = sorted(json.dumps(x, sort_keys=True, default=str) for x in nodes + edges)
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def fork(db, name, suffix):
    """GRAPH.COPY the live graph to `<name>:fork:<suffix>` (replacing a stale one) and return the fork."""
    fname = f"{name}:fork:{suffix}"
    if exists(db, fname):
        db.select_graph(fname).delete()
    db.select_graph(name).copy(fname)
    return db.select_graph(fname)
