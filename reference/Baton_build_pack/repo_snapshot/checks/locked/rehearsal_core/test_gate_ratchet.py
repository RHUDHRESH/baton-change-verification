"""Ratchet for rehearsal_core (approved 2026-10-18 ~12:50 IST): a source only counts if it is about the belief.
A one-line claim padded with an unrelated record id (or a joblog of another job by another person) must be refused."""
import pytest
from conftest import baton_json, write_beliefs


def _unrelated(w, belief, kind):
    if kind == "record":
        for r in w["records"]:
            people = {r.get("person"), r.get("from_person"), r.get("to_person")}
            if r.get("duty") != belief["duty"] and belief["person"] not in people:
                return r["id"]
    else:
        for j in w["joblogs"]:
            if j["job"] != belief["duty"] and j["actor"] != belief["person"]:
                return j["id"]
    return None


@pytest.mark.parametrize("seed,kind", [(7, "record"), (202, "record"), (7, "joblog"), (303, "joblog")])
def test_padding_a_one_source_claim_with_an_unrelated_source_is_refused(worlds, port, seed, kind):
    d, w, k = worlds(seed)
    single = next(b for b in k["noise_beliefs"] if len(b["sources"]) == 1)
    pad = _unrelated(w, single, kind)
    assert pad, "fixture: no unrelated source found"
    padded = dict(single, id="padded-1", sources=single["sources"] + [pad])
    beliefs = k["true_beliefs"] + [padded]
    bp = write_beliefs(d, beliefs, f"beliefs_pad_{kind}.json")
    out = baton_json("rehearse", "--world", d, "--beliefs", bp, "--leaver", w["leaver"], "--lane", "G",
                     "--confirm", "all", "--port", port)
    refused = {u["belief"]: u["reason"] for u in out["unpromoted"]}
    assert "padded-1" in refused
    assert not ({b["id"] for b in k["true_beliefs"]} & set(refused))
