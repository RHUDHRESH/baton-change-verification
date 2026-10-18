"""`python -m baton commit`: write accepted successors to the LIVE graph, then to a git repository, and read both back.

Order is the whole point (graph first, file second, read-back third):
  1. preview  - a GRAPH.COPY fork runs the gate so we know which duties exist: record duties, plus duties known only
                from beliefs that passed the gate (those get a Duty node on live when, and only when, assigned).
  2. graph    - each assignment is ONE guarded write on the live graph. The MATCH/WHERE re-checks that the successor
                exists, is active (left_at IS NULL) and is not the leaver; FalkorDB's UNIQUE constraint on
                OWNER.active_key refuses a second accepted successor for a duty (the violating query is rolled back
                whole, so no stray Duty/Source). Each accepted edge cites a new (:Source {type:'record'}).
                The leaver's left_at is NOT set on live: they have not left yet.
  3. external - only if at least one write was accepted: OWNERS.d/<graph>.yaml in the --repo working tree is merged
                with the accepted `duty: person` lines, committed, then read back with `git show HEAD:<file>`.
  4. verify   - the G-lane rehearsal runs again on a fresh fork of the live graph; every duty still failing is
                `still_uncovered`, and the leaver is `ready_to_leave` only when that list is empty.
"""
import re
import hashlib
import json
import subprocess
import time
import os
import stat
import secrets
from contextlib import contextmanager
from pathlib import Path

from redis.exceptions import ResponseError

from . import graph as G
from . import handover
from . import rehearse

Q_DUTY_INFO = "MATCH (d:Duty) WHERE d.id IN $ids RETURN d.id, d.name, d.kind, d.from_belief"

_ACCEPT_TAIL = """
CREATE (d)-[r:OWNER {vf: $leave_at, vt: $open, basis: 'accepted', active_key: d.id, accepted_by: p.id,
                     accepted_at: $at, rec: $src}]->(p)
CREATE (:Source {id: $src, type: 'record', author: p.id, at: $at, duty: d.id, people: [p.id],
                 text: 'accepted handover: ' + d.id + ' is owned by ' + p.id + ' from the departure of ' + $leaver})
RETURN count(r)"""

# duty already in the live graph, or not known at all (then nothing matches and nothing is written)
Q_ACCEPT_EXISTING = """
MATCH (d:Duty {id: $duty}), (p:Person {id: $person})
WHERE p.left_at IS NULL AND p.id <> $leaver""" + _ACCEPT_TAIL

# duty known only from a gate-passed belief: its Duty node is created in the same guarded write
Q_ACCEPT_BELIEF = """
MATCH (p:Person {id: $person})
WHERE p.left_at IS NULL AND p.id <> $leaver
MERGE (d:Duty {id: $duty})
  ON CREATE SET d.name = $name, d.kind = $kind, d.from_belief = true""" + _ACCEPT_TAIL

Q_PERSON = "OPTIONAL MATCH (p:Person {id: $person}) RETURN p IS NOT NULL, p.left_at"

FILE_DIR = "OWNERS.d"


@contextmanager
def _safe_parent(root, relative):
    """RT-05: anchor all file operations to directory handles, never links.

    The deployed Linux service supports openat/no-follow. Other platforms fail
    closed rather than silently using a race-prone path-based fallback.
    """
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(p in ("..", ".") for p in parts):
        raise ValueError("unsafe repository destination")
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("Safe repository writes require Linux directory-handle support; use the Docker service")
    handle = os.open(Path(root).resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=handle)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handle)
            os.close(handle)
            handle = child
        yield handle, parts[-1]
    finally:
        os.close(handle)


def _safe_read(root, relative):
    with _safe_parent(root, relative) as (parent, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("repository destination must be a regular file with no extra links")
            return stream.read()


def _safe_write(root, relative, text):
    # Validate existing links, then atomically replace the directory entry. Even
    # a link swapped in afterward is replaced, never opened for writing.
    _safe_read(root, relative)
    with _safe_parent(root, relative) as (parent, name):
        temporary = f".baton-{secrets.token_hex(16)}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


def _owners_rel(graph):
    return f"{FILE_DIR}/{re.sub(r'[^A-Za-z0-9_.-]', '_', graph)}.yaml"


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def _repo_root(repo):
    r = _git(repo, "rev-parse", "--show-toplevel", check=False) if Path(repo).is_dir() else None
    if r is None or r.returncode != 0:
        raise SystemExit(f"baton commit: --repo {repo} is not a git repository")
    return Path(r.stdout.strip())


def _parse_assign(raw):
    duty, sep, person = raw.partition("=")
    return duty.strip(), person.strip(), bool(sep and duty.strip() and person.strip())


def _preview(s, duties):
    """Fork the live graph, run the gate, and return {duty id: (name, kind, from_belief)} for the assigned duties."""
    r = rehearse.on_fork(s, "G", "all", before_departure=lambda fork: {
        row[0]: row[1:] for row in fork.ro_query(Q_DUTY_INFO, {"ids": sorted(duties)}).result_set})
    return r["extra"], r["live_hash_before"]


def _why_not(live, duty, person, leaver, known):
    if person == leaver:
        return "person is the one leaving"
    has_person, left_at = live.ro_query(Q_PERSON, {"person": person}).result_set[0]
    if not has_person:
        return "person has left or does not exist (no such person)"
    if left_at is not None:
        return f"person has left or does not exist (left_at {left_at})"
    if not known:
        return f"no duty '{duty}' in the graph (no record and no belief that passed the gate)"
    return "the graph refused the write"


def _write_live(s, assigns, info):
    live = s["live"]
    handover._one_successor_per_duty(live, s["db"])
    committed, refused = [], []
    for raw in assigns:
        duty, person, ok = _parse_assign(raw)
        if not ok:
            refused.append({"duty": duty, "person": person, "reason": f"expected DUTY=PERSON, got '{raw}'"})
            continue
        known = duty in info
        name, kind, from_belief = info.get(duty, (None, None, None))
        q = Q_ACCEPT_BELIEF if known and from_belief else Q_ACCEPT_EXISTING
        params = {"duty": duty, "person": person, "leaver": s["leaver"], "leave_at": s["leave_at"], "open": G.OPEN,
                  "at": int(time.time() * 1000), "src": f"accept:{duty}={person}@{s['leave_at']}",
                  "name": name, "kind": kind}
        try:
            made = live.query(q, params).result_set[0][0]
        except ResponseError as err:
            if "unique constraint" not in str(err).lower():
                raise
            refused.append({"duty": duty, "person": person, "reason": "duty already has an accepted successor"})
            continue
        if made:
            committed.append({"duty": duty, "person": person})
        else:
            refused.append({"duty": duty, "person": person,
                            "reason": _why_not(live, duty, person, s["leaver"], known)})
    return committed, refused


def _parse_owners(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        duty, _, person = line.partition(":")
        out[duty.strip()] = person.strip()
    return out


def _write_external(repo, graph, leaver, committed):
    root = _repo_root(repo)
    rel = _owners_rel(graph)
    owners = _parse_owners(_safe_read(root, rel) or "")
    owners.update({c["duty"]: c["person"] for c in committed})
    _safe_write(root, rel, f"# Accepted successors for graph {graph}, written by baton commit after FalkorDB accepted them.\n"
                    "# duty: person\n" + "".join(f"{d}: {p}\n" for d, p in sorted(owners.items())))
    msg = (f"baton: hand over {len(committed)} dut{'y' if len(committed) == 1 else 'ies'} from {leaver}\n\n"
           + "".join(f"{c['duty']} -> {c['person']}\n" for c in committed))
    _git(root, "add", "--", rel)
    changed = _git(root, "diff", "--cached", "--quiet", "--", rel, check=False)
    if changed.returncode:
        _git(root, "-c", "user.name=Baton", "-c", "user.email=baton@localhost", "commit", "-q", "-m", msg, "--", rel)
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    shown = _parse_owners(_git(root, "show", f"HEAD:{rel}").stdout)
    read_back = [{"duty": c["duty"], "person": shown.get(c["duty"])} for c in committed]
    return {"repo": str(root), "file": rel, "commit": head, "read_back": read_back, "verified": read_back == committed}


def run(world_dir, beliefs_file, leaver, assigns, repo, port):
    s = rehearse.open_session(world_dir, beliefs_file, leaver, port, cmd="commit")  # FalkorDB down -> exit 3 here
    root = _repo_root(repo)  # a bad --repo is refused before anything is written
    identity = json.dumps([s["live"].name, leaver, s["leave_at"], sorted(assigns)])
    operation_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    journal = f".baton/receipts/{operation_id}.json"
    # Refuse unsafe destinations before changing the live graph.
    _safe_read(root, _owners_rel(s["live"].name))
    with s["db"].connection.lock(f"baton:commit:{s['live'].name}", timeout=300, blocking_timeout=30):
        existing = _safe_read(root, journal)
        if existing is not None:
            saved = json.loads(existing)
            committed, refused, hash_before = saved["committed"], saved["refused"], saved["live_hash_before"]
        else:
            info, hash_before = _preview(s, {_parse_assign(a)[0] for a in assigns})
            committed, refused = _write_live(s, assigns, info)
            saved = {"committed": committed, "refused": refused, "live_hash_before": hash_before,
                     "operation_id": operation_id, "state": "graph_committed", "graph": s["live"].name,
                     "created_at": int(time.time() * 1000)}
            _safe_write(root, journal, json.dumps(saved, indent=2))
        external = None
        if committed:
            try:
                external = _write_external(repo, s["live"].name, leaver, committed)
            except Exception as err:
                external = {"verified": False, "error": str(err), "retryable": True}
        r = rehearse.on_fork(s, "G", "all")
        still = sorted({f["duty"] for f in rehearse.failures(s, r["present"], r["gone"])})
        result = {"leaver": leaver, "graph": s["live"].name, "committed": committed, "refused": refused,
                  "still_uncovered": still, "ready_to_leave": not still, "external": external,
                  "live_hash_before": hash_before, "live_hash_after": r["live_hash_after"],
                  "operation_id": operation_id,
                  "created_at": saved.get("created_at", int(time.time() * 1000)),
                  "state": "external_pending" if external and not external["verified"] else "verified"}
        _safe_write(root, journal, json.dumps(result, indent=2))
        return result
