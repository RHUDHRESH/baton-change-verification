"""`python -m baton handover`: successors accept the leaver's duties on a fork, then the rehearsal runs again.

The database enforces the rules, not Python:
  - authority: each acceptance is ONE guarded write. Its MATCH/WHERE re-checks at commit time that the duty exists and
    that the successor exists, is still active (left_at IS NULL) and is not the leaver. No row matched = no edge.
  - one accepted successor per duty: a FalkorDB UNIQUE constraint on OWNER.active_key (set to the duty id on
    accepted edges only; record OWNER edges have no active_key, so the constraint ignores them). A second
    acceptance for the same duty is rejected by the engine as a constraint violation.
  - make-before-break: successor edges are created while the leaver is still present; the departure is applied
    after them, then the cover pass decides what is still uncovered.
The live graph is only fingerprinted; the fork is dropped.
"""
import time

from redis.exceptions import ResponseError

from . import graph as G
from . import rehearse

Q_ACCEPT = """
MATCH (d:Duty {id: $duty}), (p:Person {id: $person})
WHERE p.left_at IS NULL AND p.id <> $leaver
CREATE (d)-[r:OWNER {vf: $leave_at, vt: $open, basis: 'accepted', active_key: d.id, accepted_by: p.id,
                     rec: 'handover:' + d.id + '=' + p.id}]->(p)
RETURN count(r)"""

Q_WHY_NOT = """
OPTIONAL MATCH (d:Duty {id: $duty})
OPTIONAL MATCH (p:Person {id: $person})
RETURN d IS NOT NULL, p IS NOT NULL, p.left_at, p.id = $leaver"""


def _constraint_status(g):
    rows = g.ro_query("CALL db.constraints()").result_set
    return [r[-1] for r in rows if r[0] == "UNIQUE" and r[1] == "OWNER" and list(r[2]) == ["active_key"]]


def _one_successor_per_duty(fork, db, wait_s=5.0):
    """Index OWNER.active_key, add the UNIQUE constraint, and wait until FalkorDB reports it OPERATIONAL.
    Idempotent: a graph that already has them (a committed live graph, or a GRAPH.COPY of one) keeps them."""
    if not _constraint_status(fork):
        try:
            fork.query("CREATE INDEX FOR ()-[r:OWNER]-() ON (r.active_key)")
        except ResponseError as err:
            if "already indexed" not in str(err).lower():
                raise
        db.connection.execute_command("GRAPH.CONSTRAINT", "CREATE", fork.name, "UNIQUE", "RELATIONSHIP", "OWNER",
                                      "PROPERTIES", 1, "active_key")
    deadline = time.monotonic() + wait_s
    while True:
        status = _constraint_status(fork)
        if status == ["OPERATIONAL"]:
            return
        if status == ["FAILED"] or time.monotonic() > deadline:
            raise RuntimeError(f"FalkorDB unique constraint on OWNER.active_key is {status or 'missing'}")
        time.sleep(0.02)


def _why_not(fork, duty, person, leaver):
    has_duty, has_person, left_at, is_leaver = fork.ro_query(
        Q_WHY_NOT, {"duty": duty, "person": person, "leaver": leaver}).result_set[0]
    if not has_duty:
        return f"no duty '{duty}' in the graph"
    if not has_person:
        return "person has left or does not exist (no such person)"
    if is_leaver:
        return "person is the one leaving"
    return f"person has left or does not exist (left_at {left_at})"


def _accept_all(fork, db, s, assigns):
    _one_successor_per_duty(fork, db)
    accepted, refused = [], []
    for raw in assigns:
        duty, sep, person = raw.partition("=")
        duty, person = duty.strip(), person.strip()
        if not sep or not duty or not person:
            refused.append({"duty": duty, "person": person, "reason": f"expected DUTY=PERSON, got '{raw}'"})
            continue
        params = {"duty": duty, "person": person, "leaver": s["leaver"], "leave_at": s["leave_at"], "open": G.OPEN}
        try:
            made = fork.query(Q_ACCEPT, params).result_set[0][0]
        except ResponseError as err:
            if "unique constraint" not in str(err).lower():
                raise
            refused.append({"duty": duty, "person": person, "reason": "duty already has an accepted successor"})
            continue
        if made:
            accepted.append({"duty": duty, "person": person})
        else:
            refused.append({"duty": duty, "person": person, "reason": _why_not(fork, duty, person, s["leaver"])})
    return accepted, refused


def run(world_dir, beliefs_file, leaver, assigns, port, session=None):
    s = session or rehearse.open_session(world_dir, beliefs_file, leaver, port, cmd="handover")
    r = rehearse.on_fork(s, "G", "all", before_departure=lambda fork: _accept_all(fork, s["db"], s, assigns))
    accepted, refused = r["extra"]
    return {"leaver": leaver, "graph": s["live"].name, "accepted": accepted, "refused": refused,
            "failures_after": rehearse.failures(s, r["present"], r["gone"]),
            "live_hash_before": r["live_hash_before"], "live_hash_after": r["live_hash_after"]}
