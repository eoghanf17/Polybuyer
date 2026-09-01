"""Significance, resampled at the right level.

Every trade in a market shares a single resolution.  Two hundred prints in
one football match are one observation, not two hundred, and resampling
trades instead of markets overstates significance by roughly three orders of
magnitude -- enough to make pure noise look certain.

So the bootstrap unit is always the market.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .config import StatsConfig


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    lo: float
    hi: float
    #: Bootstrap probability the true value is <= 0.
    p_le_zero: float
    n: int
    #: Too few independent clusters for the interval to mean anything.
    underpowered: bool = False

    @property
    def significant(self) -> bool:
        """Positive at the 5% level, one-sided, and actually powered."""
        return (not self.underpowered) and self.p_le_zero < 0.05

    def __str__(self) -> str:
        if self.underpowered:
            return f"{self.point:+.1%} (n={self.n}, underpowered)"
        return (f"{self.point:+.1%} [{self.lo:+.1%}, {self.hi:+.1%}] "
                f"p={self.p_le_zero:.3f} n={self.n}")


def bootstrap_ratio(
    num: Sequence[float],
    den: Sequence[float],
    cfg: StatsConfig,
) -> Interval:
    """Cluster-bootstrap a ratio estimator (e.g. PnL / capital).

    ``num`` and ``den`` are per-market totals, paired.  Markets are resampled
    with replacement; the ratio is recomputed from the resampled totals, so
    markets with more capital carry proportionally more weight exactly as
    they do in the point estimate.
    """
    a = np.asarray(num, dtype=float)
    b = np.asarray(den, dtype=float)
    n = len(a)
    if n == 0 or b.sum() <= 0:
        return Interval(0.0, 0.0, 0.0, 1.0, n, underpowered=True)

    point = float(a.sum() / b.sum())

    # A bootstrap over one or two clusters resamples the same market over
    # and over: the interval collapses onto the point estimate and reports
    # p=0.000 from a single lucky trade.  That is not a small inaccuracy,
    # it is the single easiest way for this pipeline to manufacture a
    # superstar out of noise, so it is refused outright.
    if n < cfg.min_clusters:
        return Interval(point, point, point, 1.0, n, underpowered=True)
    rng = np.random.default_rng(cfg.seed)
    idx = rng.integers(0, n, size=(cfg.n_boot, n))
    num_s = a[idx].sum(axis=1)
    den_s = b[idx].sum(axis=1)
    ok = den_s > 0
    if not ok.any():
        return Interval(point, point, point, 1.0, n)
    draws = num_s[ok] / den_s[ok]

    return Interval(
        point=point,
        lo=float(np.percentile(draws, cfg.ci_lo)),
        hi=float(np.percentile(draws, cfg.ci_hi)),
        p_le_zero=float((draws <= 0).mean()),
        n=n,
    )


def bootstrap_mean(xs: Sequence[float], cfg: StatsConfig) -> Interval:
    """Cluster-bootstrap a mean over markets."""
    a = np.asarray(xs, dtype=float)
    n = len(a)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, 1.0, 0)
    rng = np.random.default_rng(cfg.seed)
    draws = a[rng.integers(0, n, size=(cfg.n_boot, n))].mean(axis=1)
    return Interval(
        point=float(a.mean()),
        lo=float(np.percentile(draws, cfg.ci_lo)),
        hi=float(np.percentile(draws, cfg.ci_hi)),
        p_le_zero=float((draws <= 0).mean()),
        n=n,
    )


def fdr_qvalues(pvalues: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg q-values.

    Screening hundreds of wallets and reporting the ones with p < 0.05 finds
    roughly 5% of them no matter what the data says.  With a few hundred
    candidates that is dozens of "significant" traders made entirely of
    luck, which is precisely the failure mode this whole exercise exists to
    avoid.  The q-value is the expected false-discovery rate incurred by
    accepting a candidate and everything ranked above it.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [1.0] * m
    running = 1.0
    for rank_from_end, i in enumerate(reversed(order)):
        k = m - rank_from_end            # 1-based rank of this p-value
        running = min(running, m * pvalues[i] / k)
        q[i] = min(1.0, max(0.0, running))
    return q


def effective_n(group_ids: Sequence[str]) -> float:
    """Independent-observation count, discounting correlated groups.

    Forty markets on the same World Cup are not forty independent tests of
    anything.  Uses the inverse Herfindahl of the group-size distribution,
    which returns the true count when groups are singletons and collapses
    toward the number of *groups* when they are not.
    """
    if not group_ids:
        return 0.0
    counts: dict[str, int] = {}
    for g in group_ids:
        counts[g] = counts.get(g, 0) + 1
    total = sum(counts.values())
    shares = np.array([c / total for c in counts.values()])
    return float(1.0 / np.square(shares).sum())
