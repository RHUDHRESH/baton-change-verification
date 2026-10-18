"""CLI entrypoint: python -m baton generate|load|rehearse|handover|commit|cut|ask|extract|lane-a|amb-import|demo (JSON on stdout)."""
import argparse
import json
import sys


def _parser():
    p = argparse.ArgumentParser(prog="baton", description="Rehearse a departure before it happens.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write a synthetic Halden world (world.json + its key) to a folder")
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--scale", type=int, default=1, help="grow the company ~N x by adding business units (default 1)")

    lo = sub.add_parser("load", help="load world.json into FalkorDB as graph halden_<seed>")
    lo.add_argument("--world", required=True)
    lo.add_argument("--port", type=int, default=6379)

    r = sub.add_parser("rehearse", help="fork the graph, remove the leaver, list what breaks")
    r.add_argument("--world", required=True)
    r.add_argument("--beliefs", required=True)
    r.add_argument("--leaver", required=True)
    r.add_argument("--lane", choices=["W", "R", "G"], default="G")
    r.add_argument("--confirm", choices=["all", "none"], default="none")
    r.add_argument("--port", type=int, default=6379)

    h = sub.add_parser("handover", help="assign successors and re-run the rehearsal")
    h.add_argument("--world", required=True)
    h.add_argument("--beliefs", required=True)
    h.add_argument("--leaver", required=True)
    h.add_argument("--assign", action="append", default=[], metavar="DUTY=PERSON")
    h.add_argument("--port", type=int, default=6379)

    cm = sub.add_parser("commit", help="write accepted successors to the live graph, then to a git repo; read both back")
    cm.add_argument("--world", required=True)
    cm.add_argument("--beliefs", required=True)
    cm.add_argument("--leaver", required=True)
    cm.add_argument("--assign", action="append", default=[], metavar="DUTY=PERSON")
    cm.add_argument("--repo", required=True, help="git repository that receives OWNERS.d/<graph>.yaml")
    cm.add_argument("--port", type=int, default=6379)

    c = sub.add_parser("cut", help="maxFlow on a fork: can the stayers absorb what the leaver held? (min cut, N-1)")
    c.add_argument("--world", required=True)
    c.add_argument("--beliefs", required=True)
    c.add_argument("--leaver", required=True)
    c.add_argument("--port", type=int, default=6379)

    a = sub.add_parser("ask", help="ask the company graph a question; answer with rows, sources and the Cypher run")
    a.add_argument("--catalogue", action="store_true", help="print the fixed {tool: cypher} catalogue and exit")
    a.add_argument("--world")
    a.add_argument("--beliefs")
    a.add_argument("--question")
    a.add_argument("--port", type=int, default=6379)
    a.add_argument("--offline", action="store_true", help="deterministic router only; never call a model")

    x = sub.add_parser("extract", help="a model reads chat, job logs and tickets and proposes beliefs (cached)")
    x.add_argument("--world", required=True)
    x.add_argument("--out", required=True)
    x.add_argument("--model", help="gpt-*, claude-*, or 'fake' (scripted stand-in for plumbing tests)")
    x.add_argument("--offline", action="store_true", help="only replay the cache for this exact world; never call")
    x.add_argument("--cache-dir", help="default fixtures/extract_cache")

    la = sub.add_parser("lane-a", help="the 'AI alone' lane: the same model answers from the raw world (cached)")
    la.add_argument("--world", required=True)
    la.add_argument("--leaver", required=True)
    la.add_argument("--out", required=True)
    la.add_argument("--model")
    la.add_argument("--offline", action="store_true")
    la.add_argument("--cache-dir", help="default fixtures/lane_a_cache")

    am = sub.add_parser("amb-import", help="import an agent-memory-bench company (Liz Zhang, MIT) as a Baton world")
    am.add_argument("--seed", type=int, required=True)
    am.add_argument("--steps", type=int, default=200)
    am.add_argument("--out", required=True)

    d = sub.add_parser("demo", help="generate, load, rehearse all lanes, hand over")
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--port", type=int, default=6379)
    d.add_argument("--offline", action="store_true", help="never touch the network (extraction comes from its cache)")
    d.add_argument("--beliefs", help="beliefs file to use instead of the cached extraction for this world")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    from .graph import Unreachable, die_unreachable
    try:
        if args.cmd == "generate":
            from . import generate
            out = generate.run(args.seed, args.out, args.scale)
        elif args.cmd == "load":
            from . import load
            out = load.run(args.world, args.port)
        elif args.cmd == "rehearse":
            from . import rehearse
            out = rehearse.run(args.world, args.beliefs, args.leaver, args.lane, args.confirm, args.port)
        elif args.cmd == "handover":
            from . import handover
            out = handover.run(args.world, args.beliefs, args.leaver, args.assign, args.port)
        elif args.cmd == "commit":
            from . import commit
            out = commit.run(args.world, args.beliefs, args.leaver, args.assign, args.repo, args.port)
        elif args.cmd == "cut":
            from . import cut
            out = cut.run(args.world, args.beliefs, args.leaver, args.port)
        elif args.cmd == "ask":
            from . import ask
            if args.catalogue:
                out = ask.catalogue()
            else:
                missing = [f"--{k}" for k in ("world", "beliefs", "question") if not getattr(args, k)]
                if missing:
                    _parser().error(f"ask needs {', '.join(missing)} (or --catalogue)")
                out = ask.run(args.world, args.beliefs, args.question, args.port, args.offline)
        elif args.cmd == "extract":
            from . import extract
            out = extract.run(args.world, args.out, args.model, args.offline, args.cache_dir)
        elif args.cmd == "lane-a":
            from . import lane_a
            out = lane_a.run(args.world, args.leaver, args.out, args.model, args.offline, args.cache_dir)
        elif args.cmd == "amb-import":
            from . import amb_import
            out = amb_import.run(args.seed, args.steps, args.out)
        else:
            from . import demo
            out = demo.run(args.seed, args.port, args.offline, args.beliefs)
    except Unreachable as err:
        die_unreachable(err)
    except Exception as err:
        from .extract import CacheMiss
        from .llm import ModelUnavailable
        if isinstance(err, CacheMiss):
            print(f"baton {args.cmd}: {err}", file=sys.stderr)
            return 4
        if isinstance(err, ModelUnavailable):
            print(f"baton {args.cmd}: {err}", file=sys.stderr)
            return 5
        raise
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
