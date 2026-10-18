"""FalkorDB connection and the graph-level helpers every command shares (name, existence, fingerprint, fork)."""
import hashlib
import json
import os
import sys
import time
import uuid

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
        db = FalkorDB(host=host, port=port, socket_connect_timeout=3,
                      username=os.environ.get("FALKORDB_USERNAME") or None,
                      password=os.environ.get("FALKORDB_PASSWORD") or None,
                      ssl=os.environ.get("FALKORDB_TLS", "0").lower() in ("1", "true", "yes"),
                      ssl_check_hostname=True, ssl_cert_reqs="required")
        db.connection.ping()
    except Exception as err:  # redis raises several connection error types; all mean the same thing here
        raise Unreachable(f"FalkorDB is not reachable at {host}:{port} ({type(err).__name__})") from None
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
    fname = f"{name}:fork:{suffix}-{uuid.uuid4().hex}"
    # This engine uses a process fork to copy graphs. Coordinate the short copy
    # operation across CLI, API and MCP processes, even for different companies.
    from redis.exceptions import ResponseError
    with db.connection.lock("baton:graph-copy-lock", timeout=30, blocking_timeout=30):
        for attempt in range(6):
            try:
                db.select_graph(name).copy(fname)
                break
            except ResponseError as err:
                if "could not fork" not in str(err).lower() or attempt == 5:
                    raise
                time.sleep(.1 * (attempt + 1))
    return db.select_graph(fname)
