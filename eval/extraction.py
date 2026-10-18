"""Score the committed real-model extraction caches (predictions 8 and 9 in eval/PREDICTIONS.md).

For each seed with a cached extraction: regenerate the world (and, for scoring only, its answer key), replay the cached
beliefs offline, run Baton's gate via `rehearse`, and compare what the gate promoted with the planted truth.
A promoted belief counts as matching a planted true duty when it names the same person and cites at least one of the
same sources. Usage: python -m eval.extraction --seeds 7,101,202,303 --port P --out eval/results/extraction.json"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def baton(*a):
    r = subprocess.run([sys.executable, "-m", "baton", *map(str, a)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr)
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True); ap.add_argument("--port", type=int, default=6379)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for s in [int(x) for x in a.seeds.split(",")]:
        d = Path(tempfile.mkdtemp())
        baton("generate", "--seed", s, "--out", d)
        key = json.loads((d / "answer_key.json").read_text()); (d / "answer_key.json").unlink()
        w = json.loads((d / "world.json").read_text())
        baton("extract", "--world", d, "--out", d / "b.json", "--offline")
        beliefs = json.loads((d / "b.json").read_text())
        out = json.loads(baton("rehearse", "--world", d, "--beliefs", d / "b.json", "--leaver", w["leaver"],
                               "--lane", "G", "--confirm", "all", "--port", a.port))
        refused = {u["belief"] for u in out["unpromoted"]}
        promoted = [b for b in beliefs if b["id"] not in refused]
        def match(b, t):
            return b["person"] == t["person"] and set(b["sources"]) & set(t["sources"])
        truth = key["true_beliefs"]
        found = [t for t in truth if any(match(b, t) for b in beliefs)]
        found_promoted = [t for t in found if any(match(b, t) for b in promoted)]
        false_promoted = [b["id"] for b in promoted if not any(match(b, t) for t in truth)]
        rows.append({"seed": s, "beliefs": len(beliefs), "promoted": len(promoted), "refused": len(refused),
                     "true_duties": len(truth), "true_found_by_model": len(found),
                     "true_found_and_promoted": len(found_promoted), "false_promoted": false_promoted})
    tot_found = sum(r["true_found_by_model"] for r in rows)
    res = {"rows": rows, "summary": {
        "promoted_share_of_found": (sum(r["true_found_and_promoted"] for r in rows) / tot_found) if tot_found else None,
        "false_promotions": sum(len(r["false_promoted"]) for r in rows),
        "found_share_of_true": tot_found / sum(r["true_duties"] for r in rows)},
        "model_note": "cached extractions labelled claude-haiku-via-harness (Claude Haiku subagent in Claude Code)"}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps(res["summary"]))


if __name__ == "__main__":
    main()
