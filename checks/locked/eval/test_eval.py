"""Feature: eval. Measured, pre-registered evidence: Baton stays exact as the company grows, and costs ~no model
tokens per question after one extraction, while the AI-alone lane must re-read everything. The eval harness lives in
eval/ (a measuring tool, allowed to use the locked reference); product code stays in baton/."""
import json
import subprocess
import sys
import time
import pytest
from conftest import ROOT, baton, baton_json, write_beliefs
import oracle


def test_scale_1_is_byte_identical_to_the_default_generator(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    baton("generate", "--seed", 7, "--out", a)
    baton("generate", "--seed", 7, "--scale", 1, "--out", b)
    assert (a / "world.json").read_bytes() == (b / "world.json").read_bytes()


@pytest.mark.parametrize("seed", (11, 12))
def test_scale_grows_the_company_and_keeps_every_planted_shape(tmp_path, seed):
    small, big = tmp_path / "s", tmp_path / "b"
    baton("generate", "--seed", seed, "--out", small)
    baton("generate", "--seed", seed, "--scale", 8, "--out", big)
    ws, wb = (json.loads((x / "world.json").read_text()) for x in (small, big))
    kb = json.loads((big / "answer_key.json").read_text())
    assert len(wb["people"]) >= 5 * len(ws["people"])
    assert len(wb["events"]) >= 5 * len(ws["events"])
    assert len(wb["messages"]) >= 5 * len(ws["messages"])
    beliefs = kb["true_beliefs"] + kb["noise_beliefs"]
    W, R, G = (oracle.expected_failures(wb, beliefs, x) for x in "WRG")
    assert len(W) < len(R) < len(G) and R <= G
    assert all(oracle.promoted(wb, b) for b in kb["true_beliefs"])
    assert not any(oracle.promoted(wb, b) for b in kb["noise_beliefs"])


def test_baton_is_exact_on_a_large_company_and_fast(worlds, port, tmp_path):
    d = tmp_path / "big"
    baton("generate", "--seed", 21, "--scale", 8, "--out", d)
    w = json.loads((d / "world.json").read_text())
    k = json.loads((d / "answer_key.json").read_text())
    beliefs = k["true_beliefs"] + k["noise_beliefs"]
    bp = write_beliefs(d, beliefs, "b.json")
    t = time.time()
    got = baton_json("rehearse", "--world", d, "--beliefs", bp, "--leaver", w["leaver"], "--lane", "G",
                     "--confirm", "all", "--port", port)
    assert time.time() - t < 60
    assert {(r["duty"], r["at"]) for r in got["failures"]} == oracle.expected_failures(w, beliefs, "G")


def test_eval_harness_reports_exactness_with_confidence_intervals(tmp_path, port):
    out = tmp_path / "res"
    r = subprocess.run([sys.executable, "-m", "eval.run", "--seeds", "1000-1005", "--scales", "1,4",
                        "--lanes", "W,R,G", "--port", str(port), "--out", str(out)], cwd=ROOT, capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-1500:]
    res = json.loads((out / "results.json").read_text())
    assert len(res["runs"]) == 6 * 2 * 3
    for run in res["runs"]:
        assert set(run) >= {"seed", "scale", "lane", "exact", "precision", "recall", "model_tokens_per_question"}
    g = [x for x in res["runs"] if x["lane"] == "G"]
    assert all(x["exact"] for x in g)
    s = res["summary"]
    for lane in ("W", "R", "G"):
        assert set(s[lane]) >= {"recall_mean", "recall_ci95"}
    assert (out / "report.md").exists()


def test_predictions_were_committed_before_any_results():
    def first_commit(path):
        out = subprocess.run(["git", "-C", str(ROOT), "log", "--reverse", "--format=%H", "--", path],
                             capture_output=True, text=True).stdout.split()
        return out[0] if out else None
    pred = first_commit("eval/PREDICTIONS.md")
    assert pred, "eval/PREDICTIONS.md must be committed"
    text = (ROOT / "eval" / "PREDICTIONS.md").read_text()
    assert "%" in text or "0." in text
    res = first_commit("eval/results")
    if res:
        anc = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", pred, res])
        assert anc.returncode == 0 and pred != res
