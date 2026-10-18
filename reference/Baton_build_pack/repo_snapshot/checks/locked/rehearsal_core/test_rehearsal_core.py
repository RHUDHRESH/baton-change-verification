"""Feature: rehearsal-core. Checks written before any product code. Behaviour only, through `python -m baton`."""
import json
import socket

import pytest
from conftest import baton, baton_json, write_beliefs
import oracle

DEV, UNSEEN = 7, (101, 202, 303)


def _pairs(rows):
    return {(r["duty"], r["at"]) for r in rows}


def _rehearse(port, d, beliefs_path, leaver, lane, confirm="all"):
    return baton_json("rehearse", "--world", d, "--beliefs", beliefs_path, "--leaver", leaver, "--lane", lane,
                      "--confirm", confirm, "--port", port)


def _setup(worlds, seed, noise=True):
    d, w, k = worlds(seed)
    beliefs = k["true_beliefs"] + (k["noise_beliefs"] if noise else [])
    return d, w, k, beliefs, write_beliefs(d, beliefs, "beliefs_noise.json" if noise else "beliefs_clean.json")


# 1 ---------------------------------------------------------------------------------------------------------------
def test_generate_is_deterministic_and_seed_sensitive(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for d, s in ((a, 11), (b, 11), (c, 12)):
        baton("generate", "--seed", s, "--out", d)
    assert (a / "world.json").read_bytes() == (b / "world.json").read_bytes()
    assert (a / "answer_key.json").read_bytes() == (b / "answer_key.json").read_bytes()
    assert (a / "world.json").read_bytes() != (c / "world.json").read_bytes()


# 2 ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", (DEV,) + UNSEEN)
def test_world_holds_schedules_not_failures_and_has_every_planted_shape(worlds, seed):
    d, w, k, beliefs, _ = _setup(worlds, seed)
    text = json.dumps(w).lower()
    for banned in ("expected_failures", "answer_key", "true_beliefs", "noise_beliefs"):
        assert banned not in text, f"world.json leaks '{banned}'"
    people = {p["id"]: p for p in w["people"]}
    assert w["leaver"] in people and people[w["leaver"]]["left_at"] is None
    assert sum(1 for p in w["people"] if p["left_at"] is None) >= 4
    # an escalation chain whose primary already left before now, ending at the leaver
    esc = [r for r in w["records"] if r["type"] == "ESCALATES_TO" and r["to_person"] == w["leaver"]]
    assert any(people[r["from_person"]]["left_at"] is not None and people[r["from_person"]]["left_at"] <= w["now"]
               for r in esc)
    # at least one event outside the 30-day window, and messages/joblogs/tickets present
    end = w["now"] + w["window_days"] * w["day_ms"]
    assert any(e["at"] >= end for e in w["events"])
    assert w["messages"] and w["joblogs"] and w["tickets"]
    # every planted true belief is about the leaver and cites existing sources; noise exists in 3 kinds
    assert k["true_beliefs"] and all(oracle.promoted(w, b) for b in k["true_beliefs"])
    assert len(k["noise_beliefs"]) >= 3 and not any(oracle.promoted(w, b) for b in k["noise_beliefs"])


# 3 ---------------------------------------------------------------------------------------------------------------
def test_baton_G_matches_oracle_on_dev_seed(worlds, port):
    d, w, k, beliefs, bp = _setup(worlds, DEV)
    got = _rehearse(port, d, bp, w["leaver"], "G")
    assert _pairs(got["failures"]) == oracle.expected_failures(w, beliefs, "G")


# 4 ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", UNSEEN)
def test_baton_G_matches_oracle_on_unseen_seeds(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    got = _rehearse(port, d, bp, w["leaver"], "G")
    assert _pairs(got["failures"]) == oracle.expected_failures(w, beliefs, "G")


# 5 ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", (DEV,) + UNSEEN)
def test_records_only_lane_R_matches_oracle(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    got = _rehearse(port, d, bp, w["leaver"], "R")
    assert _pairs(got["failures"]) == oracle.expected_failures(w, beliefs, "R")


# 6 ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", (DEV,) + UNSEEN)
def test_workflow_lane_W_matches_oracle(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    got = _rehearse(port, d, bp, w["leaver"], "W")
    assert _pairs(got["failures"]) == oracle.expected_failures(w, beliefs, "W")


# 7 ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", (DEV,) + UNSEEN)
def test_each_lane_sees_strictly_more_W_then_R_then_G(worlds, seed):
    d, w, k, beliefs, _ = _setup(worlds, seed)
    W, R, G = (oracle.expected_failures(w, beliefs, x) for x in "WRG")
    assert len(W) < len(R) < len(G) and R <= G, (len(W), len(R), len(G))


# 8 ---------------------------------------------------------------------------------------------------------------
def test_gate_refuses_every_noise_belief_and_noise_changes_nothing(worlds, port):
    d, w, k, _, bp_noise = _setup(worlds, DEV, noise=True)
    _, _, _, _, bp_clean = _setup(worlds, DEV, noise=False)
    noisy = _rehearse(port, d, bp_noise, w["leaver"], "G")
    clean = _rehearse(port, d, bp_clean, w["leaver"], "G")
    refused = {u["belief"] for u in noisy["unpromoted"]}
    assert {b["id"] for b in k["noise_beliefs"]} <= refused
    assert all(u.get("reason") for u in noisy["unpromoted"])
    assert not ({b["id"] for b in k["true_beliefs"]} & refused)
    assert _pairs(noisy["failures"]) == _pairs(clean["failures"])


# 9 ---------------------------------------------------------------------------------------------------------------
def test_unconfirmed_beliefs_are_labelled_believed_not_confirmed(worlds, port):
    d, w, k, beliefs, bp = _setup(worlds, DEV)
    record_held = {r["duty"] for r in w["records"] if r["type"] in ("OWNER", "ROUTES_TO")}
    none = _rehearse(port, d, bp, w["leaver"], "G", confirm="none")
    allc = _rehearse(port, d, bp, w["leaver"], "G", confirm="all")
    only_belief = [r for r in none["failures"] if r["duty"] not in record_held]
    assert only_belief, "expected some failures that exist only because of beliefs"
    assert all(r["status"] == "believed" for r in only_belief)
    for r in allc["failures"]:
        assert r["status"] in ("record", "confirmed")
    assert _pairs(none["failures"]) == _pairs(allc["failures"])


# 10 --------------------------------------------------------------------------------------------------------------
def test_every_failure_cites_sources_that_exist(worlds, port):
    d, w, k, beliefs, bp = _setup(worlds, DEV)
    idx = oracle.source_index(w)
    got = _rehearse(port, d, bp, w["leaver"], "G")
    assert got["failures"]
    for r in got["failures"]:
        assert r["sources"], r
        assert all(s in idx for s in r["sources"]), r
        assert isinstance(r["day"], int) and r["day"] == (r["at"] - w["now"]) // w["day_ms"]


# 11 --------------------------------------------------------------------------------------------------------------
def test_live_graph_untouched_and_fork_dropped(worlds, port):
    from falkordb import FalkorDB
    d, w, k, beliefs, bp = _setup(worlds, DEV)
    baton("load", "--world", d, "--port", port)
    db = FalkorDB(port=port)
    name = f"halden_{w['seed']}"
    assert name in db.list_graphs()

    def snap():
        g = db.select_graph(name)
        people = g.ro_query("MATCH (p:Person) RETURN p.id, p.left_at ORDER BY p.id").result_set
        n = g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
        e = g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
        return people, n, e
    before = snap()
    got = _rehearse(port, d, bp, w["leaver"], "G")
    assert snap() == before
    assert got["live_hash_before"] == got["live_hash_after"]
    assert not [x for x in db.list_graphs() if "fork" in x.lower()]


# 12 --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", (DEV, UNSEEN[0]))
def test_handover_to_active_successors_clears_every_failure(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    got = _rehearse(port, d, bp, w["leaver"], "G")
    end = w["now"] + w["window_days"] * w["day_ms"]
    stayers = sorted(p["id"] for p in w["people"] if p["id"] != w["leaver"] and p["left_at"] is None)
    duties = sorted({r["duty"] for r in got["failures"]})
    assigns = []
    for i, du in enumerate(duties):
        assigns += ["--assign", f"{du}={stayers[i % len(stayers)]}"]
    out = baton_json("handover", "--world", d, "--beliefs", bp, "--leaver", w["leaver"], *assigns, "--port", port)
    assert not out["refused"], out["refused"]
    assert {a["duty"] for a in out["accepted"]} == set(duties)
    assert out["failures_after"] == []


# 13 --------------------------------------------------------------------------------------------------------------
def test_handover_refuses_departed_successor_and_second_owner(worlds, port):
    d, w, k, beliefs, bp = _setup(worlds, DEV)
    got = _rehearse(port, d, bp, w["leaver"], "G")
    du = sorted({r["duty"] for r in got["failures"]})[0]
    gone = next(p["id"] for p in w["people"] if p["left_at"] is not None and p["id"] != w["leaver"])
    stayers = sorted(p["id"] for p in w["people"] if p["id"] != w["leaver"] and p["left_at"] is None)
    out = baton_json("handover", "--world", d, "--beliefs", bp, "--leaver", w["leaver"],
                     "--assign", f"{du}={gone}", "--port", port)
    assert any(r["duty"] == du and r["person"] == gone for r in out["refused"])
    assert du in {r["duty"] for r in out["failures_after"]}
    out2 = baton_json("handover", "--world", d, "--beliefs", bp, "--leaver", w["leaver"],
                      "--assign", f"{du}={stayers[0]}", "--assign", f"{du}={stayers[1]}", "--port", port)
    assert len([a for a in out2["accepted"] if a["duty"] == du]) == 1
    assert len([r for r in out2["refused"] if r["duty"] == du]) == 1


# 14 --------------------------------------------------------------------------------------------------------------
def test_fails_loudly_when_falkordb_is_down(worlds):
    d, w, k, beliefs, bp = _setup(worlds, DEV)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
    r = baton("rehearse", "--world", d, "--beliefs", bp, "--leaver", w["leaver"], "--lane", "G",
              "--confirm", "all", "--port", dead, check=False)
    assert r.returncode != 0
    assert "falkordb" in (r.stderr + r.stdout).lower()
    assert '"failures"' not in r.stdout


# 15 --------------------------------------------------------------------------------------------------------------
def test_wiring_demo_runs_end_to_end_offline(port, worlds):
    d, w, k, beliefs, _ = _setup(worlds, DEV)
    out = baton_json("demo", "--seed", DEV, "--port", port, "--offline")
    assert out["leaver"] == w["leaver"]
    for lane in ("W", "R", "G"):
        assert isinstance(out["lanes"][lane]["failures"], int)
    for x in "WR":
        assert out["lanes"][x]["failures"] == len(oracle.expected_failures(w, beliefs, x))
    assert out["lanes"]["G"]["failures"] > out["lanes"]["R"]["failures"]
    assert out["live_hash_before"] == out["live_hash_after"]
    assert out["after_handover"]["failures"] == 0


# 16 --------------------------------------------------------------------------------------------------------------
def test_product_never_reads_the_answer_key_or_oracle(worlds, port, tmp_path):
    import shutil
    from conftest import ROOT
    for f in (ROOT / "baton").rglob("*.py"):
        src = f.read_text()
        assert "oracle" not in src, f"{f} mentions the oracle"
        if f.name != "generate.py":
            assert "answer_key" not in src, f"{f} reads the answer key"
    d, w, k, beliefs, bp = _setup(worlds, UNSEEN[1])
    iso = tmp_path / "iso"; iso.mkdir()
    shutil.copy(d / "world.json", iso / "world.json")
    got = _rehearse(port, iso, bp, w["leaver"], "G")
    assert _pairs(got["failures"]) == oracle.expected_failures(w, beliefs, "G")


# 17 --------------------------------------------------------------------------------------------------------------
def test_the_graph_is_the_source_of_truth_not_the_json(worlds, port):
    from falkordb import FalkorDB
    d, w, k, beliefs, bp = _setup(worlds, UNSEEN[2])
    baton("load", "--world", d, "--port", port)
    g = FalkorDB(port=port).select_graph(f"halden_{w['seed']}")
    g.query("MATCH (:Person)-[r:ESCALATES_TO]->(:Person {id:$l}) DELETE r", {"l": w["leaver"]})
    got = _rehearse(port, d, bp, w["leaver"], "R")
    w2 = dict(w, records=[r for r in w["records"]
                          if not (r["type"] == "ESCALATES_TO" and r["to_person"] == w["leaver"])])
    assert _pairs(got["failures"]) == oracle.expected_failures(w2, beliefs, "R")
    assert _pairs(got["failures"]) != oracle.expected_failures(w, beliefs, "R")
