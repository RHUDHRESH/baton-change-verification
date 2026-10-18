"""Feature: ask (the company brain answers questions with sources). Offline mode = deterministic router; the model,
when present, may only choose a tool and its arguments from the fixed catalogue. It never writes Cypher."""
import socket
import pytest
from conftest import baton, baton_json, write_beliefs
import oracle

SEEDS = (7, 202)


def _setup(worlds, seed):
    d, w, k = worlds(seed)
    beliefs = k["true_beliefs"] + k["noise_beliefs"]
    return d, w, k, beliefs, write_beliefs(d, beliefs, "beliefs_ask.json")


def _ask(port, d, bp, q):
    return baton_json("ask", "--world", d, "--beliefs", bp, "--question", q, "--port", port, "--offline")


def _name(w, pid):
    return next(p["name"] for p in w["people"] if p["id"] == pid)


@pytest.mark.parametrize("seed", SEEDS)
def test_what_breaks_if_someone_leaves_matches_the_rehearsal(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    out = _ask(port, d, bp, f"What breaks if {_name(w, w['leaver'])} leaves?")
    assert out["tool"] == "breaks_if_leaves" and out["args"]["person"] == w["leaver"]
    exp = {du for du, _ in oracle.expected_failures(w, beliefs, "G")}
    assert {r["duty"] for r in out["rows"]} == exp


@pytest.mark.parametrize("seed", SEEDS)
def test_what_does_someone_owe_lists_records_and_confirmed_duties(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    out = _ask(port, d, bp, f"What does {_name(w, w['leaver'])} owe?")
    assert out["tool"] == "owes"
    exp = {r["duty"] for r in w["records"] if r["type"] == "OWNER" and r["person"] == w["leaver"]}
    exp |= {b["duty"] for b in beliefs if b["person"] == w["leaver"] and oracle.promoted(w, b)}
    assert {r["duty"] for r in out["rows"]} == exp


@pytest.mark.parametrize("seed", SEEDS)
def test_why_is_a_ghost_duty_theirs_cites_exactly_its_evidence(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    b = k["true_beliefs"][0]
    out = _ask(port, d, bp, f"Why is {b['duty_name']} {_name(w, b['person'])}'s job?")
    assert out["tool"] == "why"
    assert set(out["sources"]) == set(b["sources"])


def test_who_covers_a_duty_at_a_time_matches_the_graph(worlds, port):
    d, w, k, beliefs, bp = _setup(worlds, 7)
    people = {p["id"]: p for p in w["people"]}
    routed = [r["duty"] for r in w["records"] if r["type"] == "ROUTES_TO"]
    duty = sorted(routed)[0]
    ev = sorted((e["at"], e["id"]) for e in w["events"] if e["duty"] == duty)[0]
    day = (ev[0] - w["now"]) // w["day_ms"]
    dname = next(x["name"] for x in w["duties"] if x["id"] == duty)
    out = _ask(port, d, bp, f"Who covers {dname} on day {day}?")
    assert out["tool"] == "covers"
    assert out["args"]["duty"] == duty
    covered = oracle.covered(w, beliefs, "G", duty, ev[0], people)
    assert bool(out["rows"]) == covered


def test_unanswerable_question_says_so_without_sources(worlds, port):
    d, w, k, beliefs, bp = _setup(worlds, 7)
    out = _ask(port, d, bp, "What is the CEO's favourite colour?")
    assert out["tool"] == "none" and out["sources"] == [] and out["rows"] == []
    assert "not in the graph" in out["answer"].lower()


@pytest.mark.parametrize("seed", SEEDS)
def test_cypher_comes_from_the_fixed_catalogue_and_sources_exist(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    cat = baton_json("ask", "--catalogue")
    idx = oracle.source_index(w)
    for q in (f"What does {_name(w, w['leaver'])} owe?", f"What breaks if {_name(w, w['leaver'])} leaves?"):
        out = _ask(port, d, bp, q)
        assert out["cypher"] == cat[out["tool"]]
        assert all(s in idx for s in out["sources"])
        assert out["answer"].strip()


def test_ask_fails_loudly_when_falkordb_is_down(worlds):
    d, w, k, beliefs, bp = _setup(worlds, 7)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
    r = baton("ask", "--world", d, "--beliefs", bp, "--question", "What does Priya owe?", "--port", dead,
              "--offline", check=False)
    assert r.returncode != 0 and "falkordb" in (r.stderr + r.stdout).lower()
