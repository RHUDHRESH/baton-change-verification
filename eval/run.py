"""`python -m eval.run --seeds A-B --scales 1,4 --lanes W,R,G[,A] --port P --out DIR`

Measures Baton the way a user runs it. For every seed x scale it generates a company into a temp folder
(`python -m baton generate`), then runs `python -m baton rehearse` once per lane as a subprocess, with every model key
removed from the environment (so "0 model tokens per question" is enforced, not assumed), and scores the answer.

Truth set: the locked independent reference (checks/locked/rehearsal_core/oracle.py, imported here as a measuring
tool; the product never sees it), lane G, over the generator's planted beliefs (its answer key: true claims plus
planted noise). The answer key is used ONLY here, for scoring and for the planted-beliefs file the lanes read; this
run measures the rehearsal engine on planted beliefs, and LLM-extraction results are reported separately.

Per run: exact (G: equal to the reference's G set; W/R: equal to the reference for that lane), precision and recall
against the G truth, model_tokens_per_question (W/R/G: 0; A: estimated as len(input JSON chars)/4), seconds.
Lane A (the AI alone) is never called here: it is scored only from a cached real-model run for this exact input
(fixtures/lane_a_cache) and otherwise reported as "not run".

Writes DIR/results.json {runs, summary, meta} and DIR/report.md. Confidence intervals: 95% bootstrap over seeds
(whole companies), eval/stats.py (adapted from agent-memory-bench by Liz Zhang, MIT).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .stats import boot_ci

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks" / "locked" / "rehearsal_core"))
import oracle  # noqa: E402  (the locked reference: a measuring tool)

LANE_TEXT = {
    "W": "Workflow tool: owner fields only",
    "R": "Baton, records only (AI switched off)",
    "G": "Baton: records + gated beliefs",
    "A": "AI alone: one model reads the whole raw company",
}
MODEL_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
NOT_RUN = "not run: no cached real-model answer for this exact input"


def parse_seeds(text):
    out = []
    for part in text.split(","):
        part = part.strip()
        if re.fullmatch(r"\d+-\d+", part):
            a, b = map(int, part.split("-"))
            out += list(range(a, b + 1))
        elif part:
            out.append(int(part))
    return out


def baton(args, env=None):
    r = subprocess.run([sys.executable, "-m", "baton", *map(str, args)], cwd=ROOT, capture_output=True, text=True,
                       env=env, timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"eval: baton {' '.join(map(str, args[:1]))} exited {r.returncode}: {r.stderr[-800:]}")
    return json.loads(r.stdout)


def score(got, truth):
    hit = len(got & truth)
    return {"precision": hit / len(got) if got else 1.0, "recall": hit / len(truth) if truth else 1.0,
            "found": hit, "reported": len(got), "truth": len(truth)}


def lane_a_run(w, truth, noise, cache_dir):
    from baton import extract, lane_a
    inp = lane_a.lane_a_input(w)
    tokens = len(json.dumps(inp, sort_keys=True)) / 4
    _, entry = extract.lookup(cache_dir, lane_a.input_bytes(inp), None, lane_a.PROMPT_VERSION, w["leaver"].encode(),
                              match=lambda e: e.get("leaver") == w["leaver"])
    run = {"model_tokens_per_question": round(tokens), "tokens_basis": "estimate: len(input JSON chars) / 4"}
    if entry is None:
        return dict(run, status=NOT_RUN, exact=None, precision=None, recall=None)
    ans = entry["answer"]
    got = {(f["duty"], f["at"]) for f in ans.get("failures", [])}
    adopted = sorted({(o["duty"], o["person"]) for o in ans.get("owners", [])} & noise)
    usage = entry.get("usage") or {}
    if usage.get("input_tokens"):
        run.update(model_tokens_per_question=usage["input_tokens"] + usage.get("output_tokens", 0),
                   tokens_basis="measured (cached usage)")
    return dict(run, status=f"cached real-model run ({entry.get('model')})", exact=got == truth,
                adopted_noise=[list(x) for x in adopted], **score(got, truth))


def evaluate(seed, scale, lanes, port, cache_dir, created):
    with tempfile.TemporaryDirectory(prefix=f"baton-eval-{seed}-{scale}-") as tmp:
        d = Path(tmp)
        gen = baton(["generate", "--seed", seed, "--scale", scale, "--out", d])
        w = json.loads((d / "world.json").read_text())
        key = json.loads((d / "answer_key.json").read_text())
        beliefs = key["true_beliefs"] + key["noise_beliefs"]  # planted beliefs (the answer key), scoring side only
        bfile = d / "planted_beliefs.json"
        bfile.write_text(json.dumps(beliefs))
        truth = oracle.expected_failures(w, beliefs, "G")
        noise = {(b["duty"], b["person"]) for b in key["noise_beliefs"]}
        env = {k: v for k, v in os.environ.items() if k not in MODEL_KEYS}
        if any(x != "A" for x in lanes):
            loaded = baton(["load", "--world", d, "--port", port], env=env)
            if loaded["created"]:
                created.append(loaded["graph"])
        size = {k: len(w[k]) for k in ("people", "duties", "events", "messages", "joblogs", "tickets")}
        runs = []
        for lane in lanes:
            base = {"seed": seed, "scale": scale, "lane": lane, "graph": gen["graph"], "size": size}
            if lane == "A":
                runs.append(dict(base, **lane_a_run(w, truth, noise, cache_dir)))
                continue
            t = time.time()
            out = baton(["rehearse", "--world", d, "--beliefs", bfile, "--leaver", w["leaver"], "--lane", lane,
                         "--confirm", "all", "--port", port], env=env)
            secs = time.time() - t
            got = {(f["duty"], f["at"]) for f in out["failures"]}
            ref = truth if lane == "G" else oracle.expected_failures(w, beliefs, lane)
            runs.append(dict(base, exact=got == ref, matches_lane_reference=got == ref, model_tokens_per_question=0,
                             tokens_basis="none: no model is called at question time (model keys removed)",
                             seconds=round(secs, 3), live_graph_untouched=out["live_hash_before"] ==
                             out["live_hash_after"], status="run", **score(got, truth)))
        return runs


def summarise(runs, lanes):
    summary = {}
    for lane in lanes:
        rs = [r for r in runs if r["lane"] == lane]
        scored = [r for r in rs if r.get("recall") is not None]
        seeds = sorted({r["seed"] for r in scored})

        def per_seed(field, rows):
            return [[float(r[field]) for r in rows if r["seed"] == s] for s in seeds]

        rm, rlo, rhi = boot_ci(per_seed("recall", scored))
        pm, plo, phi = boot_ci(per_seed("precision", scored))
        ex = [r["exact"] for r in scored]
        tok = [r["model_tokens_per_question"] for r in rs]
        summary[lane] = {
            "description": LANE_TEXT[lane], "runs": len(rs), "scored_runs": len(scored),
            "recall_mean": rm, "recall_ci95": [rlo, rhi], "precision_mean": pm, "precision_ci95": [plo, phi],
            "exact_rate": sum(ex) / len(ex) if ex else None,
            "tokens_per_question_mean": sum(tok) / len(tok) if tok else None,
            "by_scale": {},
        }
        for sc in sorted({r["scale"] for r in rs}):
            rows = [r for r in scored if r["scale"] == sc]
            m, lo, hi = boot_ci([[float(r["recall"]) for r in rows if r["seed"] == s] for s in seeds])
            t = [r["model_tokens_per_question"] for r in rs if r["scale"] == sc]
            summary[lane]["by_scale"][str(sc)] = {
                "recall_mean": m, "recall_ci95": [lo, hi], "scored_runs": len(rows),
                "exact_rate": sum(r["exact"] for r in rows) / len(rows) if rows else None,
                "tokens_per_question_mean": sum(t) / len(t) if t else None}
    return summary


# ---- report ------------------------------------------------------------------------------------------------------
def _pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def _ci(pair):
    lo, hi = pair
    return "CI n/a: one seed" if lo is None else f"{100 * lo:.0f}-{100 * hi:.0f}%"


def predictions():
    rows = []
    for line in (ROOT / "eval" / "PREDICTIONS.md").read_text().splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([0-9.]+)\s*\|\s*$", line)
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3)))
    return rows


def judge(n, runs, summary, scales):
    """Score one pre-registered prediction from this run: (verdict, evidence)."""
    by = lambda lane, **kw: [r for r in runs if r["lane"] == lane and all(r[k] == v for k, v in kw.items())]  # noqa
    if n == 1:
        g = [r for r in by("G") if r["scale"] in (1, 4)]
        if not (1 in scales and 4 in scales) or not g:
            return "NOT RUN", "needs lane G at scales 1 and 4"
        bad = [f"seed {r['seed']} scale {r['scale']}" for r in g if not r["exact"]]
        return ("MISS", "not exact on " + ", ".join(bad)) if bad else \
            ("HIT", f"exact on all {len(g)} seed x scale runs")
    if n in (2, 3):
        lane, cut = ("W", 0.40) if n == 2 else ("R", 0.60)
        s = summary.get(lane)
        if not s or s["recall_mean"] is None:
            return "NOT RUN", f"needs lane {lane}"
        ok = s["recall_mean"] < cut
        return ("HIT" if ok else "MISS"), f"mean recall {s['recall_mean']:.3f} (95% CI {_ci(s['recall_ci95'])})"
    if n == 4:
        a = by("A")
        s1 = {r["seed"]: r["model_tokens_per_question"] for r in a if r["scale"] == 1}
        s8 = {r["seed"]: r["model_tokens_per_question"] for r in a if r["scale"] == 8}
        both = sorted(set(s1) & set(s8))
        if not both:
            return "NOT RUN", "needs lane A at scales 1 and 8 (token estimate only, no model call needed)"
        ratios = [s8[s] / s1[s] for s in both]
        ok = min(ratios) >= 6
        return ("HIT" if ok else "MISS"), f"scale-8 / scale-1 estimated tokens: min {min(ratios):.1f}x, " \
                                          f"mean {sum(ratios) / len(ratios):.1f}x over {len(both)} seeds"
    if n == 5:
        b = [r for r in runs if r["lane"] in ("W", "R", "G")]
        if not b:
            return "NOT RUN", "needs lane W, R or G"
        ok = all(r["model_tokens_per_question"] == 0 for r in b)
        return ("HIT" if ok else "MISS"), f"{len(b)} rehearsals ran with every model key removed from the " \
                                          f"environment; tokens per question {'all 0' if ok else 'non-zero'}"
    if n == 6:
        a = [r for r in by("A", scale=8) if r.get("recall") is not None]
        if not a:
            return "NOT RUN", "needs a cached real-model AI-alone run at scale 8"
        m = sum(r["recall"] for r in a) / len(a)
        return ("HIT" if m < 0.80 else "MISS"), f"mean recall {m:.3f} over {len(a)} cached runs"
    if n == 7:
        a = [r for r in by("A", scale=1) if r.get("recall") is not None]
        if len(a) < 4:
            return "NOT RUN", f"needs cached real-model AI-alone runs on 4 seeds at scale 1 (have {len(a)})"
        hits = [r["seed"] for r in a if r.get("adopted_noise")]
        return ("HIT" if hits else "MISS"), f"planted false claims adopted on seeds {hits or 'none'} " \
                                            f"(exact duty+person match) across {len(a)} seeds"
    return "NOT RUN", "needs LLM-extracted beliefs; this run uses planted beliefs (reported separately)"


def report(res, lanes):
    s, meta, runs = res["summary"], res["meta"], res["runs"]
    out = [
        "# Baton evaluation", "",
        f"Seeds {meta['seeds'][0]}-{meta['seeds'][-1]} ({len(meta['seeds'])} companies) x scales "
        f"{', '.join(map(str, meta['scales']))}; lanes {', '.join(lanes)}. Commit `{meta['git_commit']}`, "
        f"{meta['generated_at']}, {meta['seconds']:.0f} s.", "",
        "**Beliefs: planted beliefs (the generator's answer key: true claims plus planted noise); LLM-extraction "
        "results are reported separately.** Truth = the independent reference's lane-G answer for those beliefs. "
        "Recall = share of the true failing events a lane reports; precision = share of what it reports that is "
        "true. 95% intervals: bootstrap over seeds (whole companies), method adapted from agent-memory-bench by Liz "
        "Zhang (MIT).", "",
        "| Lane | What it is | Runs | Recall (95% CI) | Precision | Exact | Model tokens per question |",
        "|---|---|---|---|---|---|---|",
    ]
    for lane in lanes:
        x = s[lane]
        if x["scored_runs"] == 0:
            rec, prec, ex = "not run", "not run", "not run"
        else:
            rec = f"{_pct(x['recall_mean'])} ({_ci(x['recall_ci95'])})"
            prec, ex = _pct(x["precision_mean"]), _pct(x["exact_rate"])
        tok = "0 (no model)" if lane != "A" else f"~{x['tokens_per_question_mean']:,.0f} (estimate)"
        out.append(f"| {lane} | {x['description']} | {x['scored_runs']}/{x['runs']} | {rec} | {prec} | {ex} | {tok} |")
    out += ["", "Exact means: lane G equals the reference's G answer; lanes W and R equal the reference's answer for "
            "that same lane (they are exact about what they can see, and still miss what only G sees).", "",
            "## By company size", "", "| Lane | Scale | Recall (95% CI) | Exact | Model tokens per question |",
            "|---|---|---|---|---|"]
    for lane in lanes:
        for sc, x in s[lane]["by_scale"].items():
            rec = "not run" if x["recall_mean"] is None else f"{_pct(x['recall_mean'])} ({_ci(x['recall_ci95'])})"
            tok = "0" if lane != "A" else f"~{x['tokens_per_question_mean']:,.0f} (estimate)"
            out.append(f"| {lane} | {sc} | {rec} | {_pct(x['exact_rate'])} | {tok} |")
    g = [r for r in runs if r["lane"] == "G"]
    if g:
        out += ["", f"Slowest Baton rehearsal (lane G, CLI subprocess, including start-up): "
                f"{max(r['seconds'] for r in g):.2f} s; largest company: "
                f"{max(r['size']['people'] for r in g)} people, {max(r['size']['events'] for r in g)} events."]
    out += ["", "## Pre-registered predictions (eval/PREDICTIONS.md)", "",
            "Scored from this run only. NOT RUN means this run did not measure it; it is never dropped.", "",
            "| # | Prediction | P | Result | Evidence |", "|---|---|---|---|---|"]
    for n, text, p in predictions():
        verdict, why = judge(n, runs, s, meta["scales"])
        out.append(f"| {n} | \"{text}\" | {p} | **{verdict}** | {why} |")
    return "\n".join(out) + "\n"


def _git_commit():
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "baton", "eval"],
                           capture_output=True, text=True).stdout.strip()
    return (r.stdout.strip() or "unknown") + ("+dirty" if dirty else "")


def _drop(port, names):
    if not names:
        return
    from falkordb import FalkorDB
    db = FalkorDB(host=os.environ.get("FALKORDB_HOST", "localhost"), port=port)
    for n in names:
        db.select_graph(n).delete()


def main(argv=None):
    p = argparse.ArgumentParser(prog="eval.run", description="Measure Baton against the independent reference.")
    p.add_argument("--seeds", required=True, help="e.g. 1000-1005 or 7,101,202")
    p.add_argument("--scales", default="1", help="comma list, e.g. 1,4,8")
    p.add_argument("--lanes", default="W,R,G", help="comma list from W,R,G,A")
    p.add_argument("--port", type=int, default=6379)
    p.add_argument("--out", required=True)
    p.add_argument("--lane-a-cache", default=str(ROOT / "fixtures" / "lane_a_cache"))
    p.add_argument("--keep-graphs", action="store_true", help="keep the graphs this run loaded (default: drop them)")
    a = p.parse_args(argv)
    seeds, scales = parse_seeds(a.seeds), [int(x) for x in a.scales.split(",") if x.strip()]
    lanes = [x.strip().upper() for x in a.lanes.split(",") if x.strip()]
    if not seeds or not scales or any(x not in LANE_TEXT for x in lanes):
        p.error("need seeds, scales and lanes from W,R,G,A")
    t0, runs, created = time.time(), [], []
    try:
        for seed in seeds:
            for scale in scales:
                runs += evaluate(seed, scale, lanes, a.port, a.lane_a_cache, created)
                print(f"eval: seed {seed} scale {scale} done ({time.time() - t0:.0f} s)", file=sys.stderr)
    finally:
        if not a.keep_graphs:
            _drop(a.port, created)
    res = {"runs": runs, "summary": summarise(runs, lanes),
           "meta": {"seeds": seeds, "scales": scales, "lanes": lanes, "git_commit": _git_commit(),
                    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "seconds": round(time.time() - t0, 1),
                    "beliefs": "planted beliefs (answer key); LLM-extraction results are reported separately",
                    "truth": "checks/locked/rehearsal_core/oracle.py expected_failures(world, beliefs, 'G')",
                    "ci": "95% bootstrap over seeds, 2000 resamples, RNG seed 0 (eval/stats.py)"}}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    (out / "report.md").write_text(report(res, lanes))
    print(json.dumps({"out": str(out), "runs": len(runs), "seconds": res["meta"]["seconds"],
                      "summary": {k: {"recall_mean": v["recall_mean"], "exact_rate": v["exact_rate"]}
                                  for k, v in res["summary"].items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
