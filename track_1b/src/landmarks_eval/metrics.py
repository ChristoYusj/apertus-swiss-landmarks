"""Scores: SimpleQA metrics, confidence intervals and agreement statistics (pure Python, deterministic)."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict

LABELS = ("correct", "incorrect", "not_attempted")


def rates(labels: list[str]) -> dict:
    c = Counter(labels)
    n = sum(c[l] for l in LABELS)
    attempted = c["correct"] + c["incorrect"]
    out = {"n": n, **{l: c[l] for l in LABELS}}
    out["pct_correct"] = c["correct"] / n if n else None
    out["pct_incorrect"] = c["incorrect"] / n if n else None
    out["pct_not_attempted"] = c["not_attempted"] / n if n else None
    out["correct_given_attempted"] = c["correct"] / attempted if attempted else None
    out["hallucination_rate"] = c["incorrect"] / attempted if attempted else None  # incorrect / attempted
    p, cga = out["pct_correct"], out["correct_given_attempted"]
    out["f_score"] = 2 * p * cga / (p + cga) if p and cga else (0.0 if n else None)
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def bootstrap_values(rows: list[dict], stat, cluster_key: str = "landmark_qid", b: int = 2000,
                     seed: int = 20261015) -> list[float] | None:
    """stat() on b resamples of whole landmarks (items of one landmark are correlated), sorted."""
    clusters = defaultdict(list)
    for r in rows:
        clusters[r[cluster_key]].append(r)
    keys = sorted(clusters)
    if len(keys) < 2:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(b):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in clusters[k]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    return sorted(vals) or None


def percentile_ci(vals: list[float] | None):
    if not vals:
        return None
    return (vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))])


def bootstrap_p(vals: list[float] | None) -> float | None:
    """Two-sided bootstrap p-value for H0: statistic = 0 (share of resamples on the other side of 0, doubled)."""
    if not vals:
        return None
    lo = sum(v <= 0 for v in vals) / len(vals)
    hi = sum(v >= 0 for v in vals) / len(vals)
    return min(1.0, 2 * min(lo, hi))


def cluster_bootstrap(rows: list[dict], stat, cluster_key: str = "landmark_qid", b: int = 2000, seed: int = 20261015):
    """95 % percentile CI of stat(rows), resampling whole landmarks (items of one landmark are correlated)."""
    return percentile_ci(bootstrap_values(rows, stat, cluster_key, b, seed))


def holm(pvalues: dict[str, float | None], alpha: float = 0.05) -> dict[str, dict]:
    """Holm step-down adjustment over the tests that have a p-value."""
    items = sorted(((k, p) for k, p in pvalues.items() if p is not None), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = {"p": p, "p_holm": running, "reject_at_0.05": running < alpha}
    return out


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    assert len(a) == len(b)
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def fleiss_kappa(table: list[list[str]]) -> float | None:
    """table: one list of labels per item (same number of raters per item)."""
    if not table:
        return None
    m = len(table[0])
    cats = sorted({l for row in table for l in row})
    n = len(table)
    p_j = [sum(row.count(c) for row in table) / (n * m) for c in cats]
    p_i = [(sum(row.count(c) ** 2 for c in cats) - m) / (m * (m - 1)) for row in table]
    p_bar, p_e = sum(p_i) / n, sum(p * p for p in p_j)
    return 1.0 if p_e == 1 else (p_bar - p_e) / (1 - p_e)


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value for discordant counts b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def rnd(x, nd: int = 6):
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, (list, tuple)):
        return [rnd(v, nd) for v in x]
    if isinstance(x, dict):
        return {k: rnd(v, nd) for k, v in x.items()}
    return x
