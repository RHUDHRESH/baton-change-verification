"""Score AI-alone (lane A) answers against the independent reference (predictions 6 and 7).

Each case folder holds world.json (what the model read) and lane_a.json (its answer); the sealed answer key is passed
separately and is never in the folder the model read. Matching: an answer row counts as a hit if (duty, at) equals a
true failing event, or, for a duty known only from chat (not in world.duties), if it names a chat-only duty and the same
calendar day as a true event of a chat-only duty. False-claim adoption: the model's owners list names the person of a
planted single-source transfer claim for that claim's duty.
Usage: python -m eval.lane_a_score CASE_DIR:KEY_JSON[:SCALE] ... --out eval/results/lane_a.json"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks" / "locked" / "rehearsal_core"))
import oracle  # noqa: E402  (measuring tool; product code never imports this)


def score(case, keyp, scale):
    w = json.loads((Path(case) / "world.json").read_text())
    k = json.loads(Path(keyp).read_text())
    a = json.loads((Path(case) / "lane_a.json").read_text())
    beliefs = k["true_beliefs"] + k["noise_beliefs"]
    truth = oracle.expected_failures(w, beliefs, "G")
    recorded = {d["id"] for d in w["duties"]}
    day = w["day_ms"]
    chat_truth = {(du, at) for du, at in truth if du not in recorded}
    hits, used = 0, set()
    for f in a.get("failures", []):
        key = (f.get("duty"), f.get("at"))
        if key in truth and key not in used:
            hits += 1; used.add(key); continue
        if f.get("duty") not in recorded and isinstance(f.get("at"), int):
            for t in sorted(chat_truth - used):
                if t[1] // day == f["at"] // day:
                    hits += 1; used.add(t); break
    n = len(a.get("failures", []))
    owners = {(o.get("person"), o.get("duty")) for o in a.get("owners", [])}
    false_claims = [b for b in k["noise_beliefs"] if len(b["sources"]) == 1]
    adopted = sorted({f'{b["person"]}->{b["duty"]}' for b in false_claims if (b["person"], b["duty"]) in owners})
    return {"case": str(case), "scale": scale, "seed": w["seed"], "truth_events": len(truth), "answered": n,
            "hits": hits, "recall": hits / len(truth) if truth else None, "precision": hits / n if n else None,
            "false_claims_planted": len(false_claims), "false_claims_adopted": adopted,
            "model": a.get("model"), "notes": a.get("notes")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="+"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for c in a.cases:
        parts = c.split(":")
        rows.append(score(parts[0], parts[1], int(parts[2]) if len(parts) > 2 else 1))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"rows": rows}, indent=1, sort_keys=True))
    for r in rows:
        print(r["seed"], "x%s" % r["scale"], "recall %.2f" % r["recall"], "precision %.2f" % (r["precision"] or 0),
              "false claims adopted", r["false_claims_adopted"])


if __name__ == "__main__":
    main()
