# Cluster bootstrap adapted from agent-memory-bench by Liz Zhang (MIT),
# Copyright (c) 2026 Liz Zhang — MIT License (see third_party/amb/LICENSE)
# https://github.com/zhang-liz/agent-memory-bench (amb/analyze.py: boot_ci, "95% cluster bootstrap over worlds:
# resampling whole worlds keeps correlated questions together"). Ported to the standard library (no numpy) with a
# fixed RNG seed so the same results always give the same interval.
"""95% confidence intervals by resampling whole clusters (here: seeds, i.e. whole companies)."""
import random

N_BOOT = 2000
RNG_SEED = 0


def _percentile(xs, q):
    """Linear-interpolated percentile (numpy's default method), q in [0, 100]."""
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def boot_ci(groups, n=N_BOOT, seed=RNG_SEED):
    """Mean of all values, with a 95% CI from resampling whole groups. Returns (mean, lo, hi); lo/hi are None when
    there are fewer than two groups (one company cannot tell you how much companies vary)."""
    groups = [list(g) for g in groups if g]
    if not groups:
        return None, None, None
    flat = [x for g in groups for x in g]
    mean = sum(flat) / len(flat)
    if len(groups) == 1:
        return mean, None, None
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        pick = [groups[rng.randrange(len(groups))] for _ in groups]
        vals = [x for g in pick for x in g]
        stats.append(sum(vals) / len(vals))
    return mean, _percentile(stats, 2.5), _percentile(stats, 97.5)
