"""Feature: commit_write. Baton gets the work done: accepted successors are written to the LIVE graph (the database
enforces one successor per duty and refuses people who have left), then to a real external system (a git repository
file, committed), and both are read back into a receipt. Nothing reaches the external system if the graph write fails."""
import json
import socket
import subprocess
import pytest
from conftest import baton, baton_json, write_beliefs
import oracle


def _repo(tmp_path):
    r = tmp_path / "ops-repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
                    "-m", "init"], check=True)
    return r


def _head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def _setup(worlds, seed, tmp_path, port):
    d, w, k = worlds(seed)
    # fresh copy so live-graph writes from one check never leak into another
    dd = tmp_path / "w"; dd.mkdir()
    w = dict(w, seed=f"{w['seed']}-{tmp_path.name}")
    (dd / "world.json").write_text(json.dumps(w))
    beliefs = k["true_beliefs"] + k["noise_beliefs"]
    bp = write_beliefs(dd, beliefs, "beliefs_commit.json")
    duties = sorted({du for du, _ in oracle.expected_failures(w, beliefs, "G")})
    stayers = sorted(p["id"] for p in w["people"] if p["id"] != w["leaver"] and p["left_at"] is None)
    gone = [p["id"] for p in w["people"] if p["left_at"] is not None and p["id"] != w["leaver"]]
    return dd, w, beliefs, bp, duties, stayers, gone


def _commit(port, d, bp, leaver, repo, assigns, check=True):
    args = []
    for du, p in assigns:
        args += ["--assign", f"{du}={p}"]
    r = baton("commit", "--world", d, "--beliefs", bp, "--leaver", leaver, "--repo", repo, "--port", port, *args,
              check=check)
    return r if not check else json.loads(r.stdout)


def test_full_handover_is_written_to_the_live_graph_and_rehearsal_goes_green(worlds, port, tmp_path):
    d, w, beliefs, bp, duties, stayers, gone = _setup(worlds, 7, tmp_path, port)
    repo = _repo(tmp_path)
    out = _commit(port, d, bp, w["leaver"], repo, [(du, stayers[i % len(stayers)]) for i, du in enumerate(duties)])
    assert {c["duty"] for c in out["committed"]} == set(duties)
    assert out["ready_to_leave"] is True and out["still_uncovered"] == []
    assert out["live_hash_before"] != out["live_hash_after"]
    after = baton_json("rehearse", "--world", d, "--beliefs", bp, "--leaver", w["leaver"], "--lane", "G",
                       "--confirm", "all", "--port", port)
    assert after["failures"] == []


def test_external_file_is_committed_and_read_back_into_the_receipt(worlds, port, tmp_path):
    d, w, beliefs, bp, duties, stayers, gone = _setup(worlds, 101, tmp_path, port)
    repo = _repo(tmp_path)
    before = _head(repo)
    assigns = [(duties[0], stayers[0])]
    out = _commit(port, d, bp, w["leaver"], repo, assigns)
    ext = out["external"]
    assert ext["verified"] is True
    assert ext["commit"] == _head(repo) != before
    shown = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{ext['file']}"], capture_output=True,
                           text=True).stdout
    assert duties[0] in shown and stayers[0] in shown
    assert ext["read_back"] == [{"duty": duties[0], "person": stayers[0]}]


def test_partial_handover_is_written_but_not_ready_to_leave(worlds, port, tmp_path):
    d, w, beliefs, bp, duties, stayers, gone = _setup(worlds, 202, tmp_path, port)
    repo = _repo(tmp_path)
    out = _commit(port, d, bp, w["leaver"], repo, [(duties[0], stayers[0])])
    assert out["ready_to_leave"] is False
    assert set(out["still_uncovered"]) == set(duties) - {duties[0]}


def test_database_refuses_a_second_successor_and_a_departed_person(worlds, port, tmp_path):
    d, w, beliefs, bp, duties, stayers, gone = _setup(worlds, 303, tmp_path, port)
    repo = _repo(tmp_path)
    first = _commit(port, d, bp, w["leaver"], repo, [(duties[0], stayers[0])])
    assert [c["duty"] for c in first["committed"]] == [duties[0]]
    head = _head(repo)
    second = _commit(port, d, bp, w["leaver"], repo, [(duties[0], stayers[1]), (duties[-1], gone[0])])
    reasons = {(r["duty"], r["person"]): r["reason"] for r in second["refused"]}
    assert (duties[0], stayers[1]) in reasons and (duties[-1], gone[0]) in reasons
    assert second["committed"] == []
    assert _head(repo) == head, "nothing refused may reach the external system"


def test_nothing_reaches_the_repo_when_falkordb_is_down(worlds, port, tmp_path):
    d, w, beliefs, bp, duties, stayers, gone = _setup(worlds, 7, tmp_path, port)
    repo = _repo(tmp_path)
    head = _head(repo)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
    r = _commit(dead, d, bp, w["leaver"], repo, [(duties[0], stayers[0])], check=False)
    assert r.returncode != 0 and "falkordb" in (r.stderr + r.stdout).lower()
    assert _head(repo) == head
