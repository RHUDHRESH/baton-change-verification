"""M01 assertions extracted unchanged from the supplied locked contract."""
import json
import pytest
from conftest import baton, write_beliefs
import oracle
DEV, UNSEEN = 7, (101, 202, 303)

def _setup(worlds, seed, noise=True):
    d, w, k = worlds(seed)
    beliefs = k["true_beliefs"] + (k["noise_beliefs"] if noise else [])
    return d, w, k, beliefs, write_beliefs(d, beliefs, "beliefs_noise.json" if noise else "beliefs_clean.json")


def test_generate_is_deterministic_and_seed_sensitive(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for d, s in ((a, 11), (b, 11), (c, 12)):
        baton("generate", "--seed", s, "--out", d)
    assert (a / "world.json").read_bytes() == (b / "world.json").read_bytes()
    assert (a / "answer_key.json").read_bytes() == (b / "answer_key.json").read_bytes()
    assert (a / "world.json").read_bytes() != (c / "world.json").read_bytes()


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


@pytest.mark.parametrize("seed", (DEV,) + UNSEEN)
def test_each_lane_sees_strictly_more_W_then_R_then_G(worlds, seed):
    d, w, k, beliefs, _ = _setup(worlds, seed)
    W, R, G = (oracle.expected_failures(w, beliefs, x) for x in "WRG")
    assert len(W) < len(R) < len(G) and R <= G, (len(W), len(R), len(G))


