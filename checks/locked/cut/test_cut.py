"""Feature: cut. Can the people who stay absorb everything the leaver held? Proven with FalkorDB algo.maxFlow on a
fork, with a min-cut certificate and an N-1 sweep (what if one more person is also unavailable)."""
import socket
import pytest
from conftest import baton, baton_json, write_beliefs
import oracle
import flow_oracle as fo

SEEDS = (7, 101, 202, 303)


def _setup(worlds, seed):
    d, w, k = worlds(seed)
    beliefs = k["true_beliefs"] + k["noise_beliefs"]
    return d, w, k, beliefs, write_beliefs(d, beliefs, "beliefs_cut.json")


def _cut(port, d, bp, leaver):
    return baton_json("cut", "--world", d, "--beliefs", bp, "--leaver", leaver, "--port", port)


@pytest.mark.parametrize("seed", SEEDS)
def test_world_has_capability_and_capacity_data(worlds, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    assert any(r["type"] == "CAN" for r in w["records"])
    assert all(isinstance(p.get("capacity"), int) and p["capacity"] >= 1 for p in w["people"])


@pytest.mark.parametrize("seed", SEEDS)
def test_flow_and_verdict_match_the_reference(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    duties, cap = fo.network(w, beliefs)
    exp = fo.maxflow(cap)
    out = _cut(port, d, bp, w["leaver"])
    assert out["demand"] == len(duties)
    assert out["flow"] == exp
    assert out["verdict"] == ("POSSIBLE" if exp == len(duties) else "IMPOSSIBLE")


def test_both_verdicts_occur_across_seeds(worlds):
    verdicts = set()
    for s in SEEDS:
        d, w, k, beliefs, _ = _setup(worlds, s)
        duties, cap = fo.network(w, beliefs)
        verdicts.add(fo.maxflow(cap) == len(duties))
    assert verdicts == {True, False}


@pytest.mark.parametrize("seed", SEEDS)
def test_min_cut_is_a_certificate(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    duties, cap = fo.network(w, beliefs)
    out = _cut(port, d, bp, w["leaver"])
    total = 0
    for e in out["min_cut"]:
        key = (e["from"], e["to"])
        assert key in cap, e
        total += cap[key]
    assert total == out["flow"]
    if out["verdict"] == "IMPOSSIBLE":
        assert out["unplaceable"], "an IMPOSSIBLE verdict must name the duties nobody can take"
        assert set(out["unplaceable"]) <= set(duties)


@pytest.mark.parametrize("seed", (7, 202))
def test_n_minus_1_sweep_matches_the_reference(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    duties, cap = fo.network(w, beliefs)
    out = _cut(port, d, bp, w["leaver"])
    stayers = sorted(p["id"] for p in w["people"] if p["left_at"] is None and p["id"] != w["leaver"])
    assert set(out["n_minus_1"]) == set(stayers)
    for pid in stayers:
        assert out["n_minus_1"][pid] == fo.maxflow(fo.without(cap, pid)), pid


def test_cut_runs_on_a_fork_and_leaves_the_live_graph_alone(worlds, port):
    from falkordb import FalkorDB
    d, w, k, beliefs, bp = _setup(worlds, 7)
    out = _cut(port, d, bp, w["leaver"])
    assert out["live_hash_before"] == out["live_hash_after"]
    assert not [x for x in FalkorDB(port=port).list_graphs() if "fork" in x.lower()]
    assert "algo.maxFlow" in out["cypher"]


def test_cut_fails_loudly_when_falkordb_is_down(worlds):
    d, w, k, beliefs, bp = _setup(worlds, 7)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
    r = baton("cut", "--world", d, "--beliefs", bp, "--leaver", w["leaver"], "--port", dead, check=False)
    assert r.returncode != 0 and "falkordb" in (r.stderr + r.stdout).lower()
