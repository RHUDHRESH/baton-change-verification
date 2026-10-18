"""Ratchet for feature ask (approved 2026-10-18): who-owns questions, and human-readable answers."""
import re
import pytest
from conftest import baton_json, write_beliefs
import oracle


def _setup(worlds, seed):
    d, w, k = worlds(seed)
    beliefs = k["true_beliefs"] + k["noise_beliefs"]
    return d, w, k, beliefs, write_beliefs(d, beliefs, "beliefs_ratchet.json")


def _ask(port, d, bp, q):
    return baton_json("ask", "--world", d, "--beliefs", bp, "--question", q, "--port", port, "--offline")


@pytest.mark.parametrize("seed", (7, 202))
def test_who_owns_a_recorded_duty_names_its_record_owners(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    owners = {}
    for r in w["records"]:
        if r["type"] == "OWNER":
            owners.setdefault(r["duty"], set()).add(r["person"])
    duty = sorted(owners)[0]
    name = next(x["name"] for x in w["duties"] if x["id"] == duty)
    out = _ask(port, d, bp, f"Who owns {name}?")
    assert out["tool"] == "who_owns" and out["args"]["duty"] == duty
    assert {r["person"] for r in out["rows"]} == owners[duty]
    assert out["sources"] and all(s in oracle.source_index(w) for s in out["sources"])


@pytest.mark.parametrize("seed", (7, 202))
def test_who_owns_a_duty_known_only_from_chat_names_the_gated_holder(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    b = next(x for x in k["true_beliefs"] if x["duty"] not in {y["id"] for y in w["duties"]})
    out = _ask(port, d, bp, f"Who owns {b['duty_name']}?")
    assert out["tool"] == "who_owns"
    assert {r["person"] for r in out["rows"]} == {b["person"]}
    assert set(out["sources"]) == set(b["sources"])


@pytest.mark.parametrize("seed", (7, 202))
def test_answers_use_human_names_not_raw_ids(worlds, port, seed):
    d, w, k, beliefs, bp = _setup(worlds, seed)
    name = next(p["name"] for p in w["people"] if p["id"] == w["leaver"])
    ids = {x["id"] for x in w["duties"]} | {b["duty"] for b in beliefs}
    for q in (f"What does {name} owe?", f"What breaks if {name} leaves?"):
        out = _ask(port, d, bp, q)
        assert all(r.get("duty_name") for r in out["rows"]), out["rows"][:2]
        leaked = [i for i in ids if re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w-])", out["answer"])]
        assert not leaked, leaked
