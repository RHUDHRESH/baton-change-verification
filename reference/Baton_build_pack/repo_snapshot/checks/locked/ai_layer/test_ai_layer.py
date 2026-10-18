"""Feature: ai_layer. The model reads messy text and proposes beliefs; results are cached so judges replay them with
no key; Liz Zhang's agent-memory-bench company (MIT) is imported as a second, externally-written test company.
Checks run offline only: they test plumbing and honesty, not model quality (the eval measures quality)."""
import json
from pathlib import Path
import pytest
from conftest import ROOT, baton, baton_json, write_beliefs
import oracle

KEYS = {"id", "person", "duty", "duty_name", "kind", "claim", "events", "sources"}


def test_fake_model_extraction_is_deterministic_and_well_formed(worlds, tmp_path):
    d, w, k = worlds(101)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    baton("extract", "--world", d, "--out", a, "--model", "fake", "--cache-dir", tmp_path / "c1")
    baton("extract", "--world", d, "--out", b, "--model", "fake", "--cache-dir", tmp_path / "c2")
    assert a.read_bytes() == b.read_bytes()
    beliefs = json.loads(a.read_text())
    assert isinstance(beliefs, list)
    people = {p["id"] for p in w["people"]}
    idx = oracle.source_index(w)
    for x in beliefs:
        assert set(x) == KEYS, x
        assert x["person"] in people
        assert all(s in idx for s in x["sources"]), x


def test_offline_replays_the_cache_byte_for_byte_and_never_guesses(worlds, tmp_path):
    d, w, k = worlds(202)
    cache = tmp_path / "cache"
    first = tmp_path / "first.json"
    baton("extract", "--world", d, "--out", first, "--model", "fake", "--cache-dir", cache)
    again = tmp_path / "again.json"
    baton("extract", "--world", d, "--out", again, "--model", "fake", "--cache-dir", cache, "--offline")
    assert first.read_bytes() == again.read_bytes()
    # a different world must not hit the old cache
    w2 = dict(w, seed=w["seed"], messages=w["messages"][:-1])
    d2 = tmp_path / "w2"; d2.mkdir(); (d2 / "world.json").write_text(json.dumps(w2))
    out = tmp_path / "miss.json"
    r = baton("extract", "--world", d2, "--out", out, "--model", "fake", "--cache-dir", cache, "--offline", check=False)
    assert r.returncode == 4 and "no cached extraction" in (r.stderr + r.stdout).lower()
    assert not out.exists()


def test_real_model_offline_without_cache_fails_clearly(worlds, tmp_path):
    d, w, k = worlds(303)
    out = tmp_path / "x.json"
    r = baton("extract", "--world", d, "--out", out, "--model", "gpt-5.4-mini", "--cache-dir", tmp_path / "empty",
              "--offline", check=False)
    assert r.returncode == 4 and "no cached extraction" in (r.stderr + r.stdout).lower()
    assert not out.exists()


def test_committed_seed7_cache_replays_offline_and_feeds_the_rehearsal(worlds, port, tmp_path):
    d, w, k = worlds(7)
    out = tmp_path / "b7.json"
    baton("extract", "--world", d, "--out", out, "--offline")
    beliefs = json.loads(out.read_text())
    assert beliefs and all(set(x) == KEYS for x in beliefs)
    R = baton_json("rehearse", "--world", d, "--beliefs", out, "--leaver", w["leaver"], "--lane", "R",
                   "--confirm", "all", "--port", port)
    G = baton_json("rehearse", "--world", d, "--beliefs", out, "--leaver", w["leaver"], "--lane", "G",
                   "--confirm", "all", "--port", port)
    assert len(G["failures"]) > len(R["failures"])


def test_ai_alone_lane_replays_from_cache_with_its_schema(worlds, tmp_path):
    d, w, k = worlds(7)
    out = tmp_path / "a.json"
    baton("lane-a", "--world", d, "--leaver", w["leaver"], "--out", out, "--offline")
    a = json.loads(out.read_text())
    assert set(a) >= {"model", "failures", "owners"}
    for f in a["failures"]:
        assert set(f) >= {"duty", "at"}


def test_amb_import_is_deterministic_loadable_and_credited(tmp_path, port):
    a, b = tmp_path / "a", tmp_path / "b"
    baton("amb-import", "--seed", 3, "--steps", 60, "--out", a)
    baton("amb-import", "--seed", 3, "--steps", 60, "--out", b)
    assert (a / "world.json").read_bytes() == (b / "world.json").read_bytes()
    w = json.loads((a / "world.json").read_text())
    assert len(w["messages"]) + len(w.get("tickets", [])) >= 30
    assert (a / "amb_truth.json").exists()
    assert "amb_truth" not in (a / "world.json").read_text()
    baton("load", "--world", a, "--port", port)
    vendored = list((ROOT / "third_party").rglob("*.py"))
    assert vendored and any("Liz Zhang" in p.read_text() for p in vendored)
    assert (ROOT / "third_party").rglob("LICENSE*")


def test_product_never_shows_the_truth_to_the_model():
    for f in (ROOT / "baton").rglob("*.py"):
        src = f.read_text()
        if f.name not in ("amb_import.py",):
            assert "amb_truth" not in src, f"{f} reads amb_truth"
