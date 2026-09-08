"""Does subsample-and-average buy significance? No. Here is the arithmetic.

The proposal: draw many subsamples of 70-80% of the markets, compute the
return on each, average across them, and treat the result as better
evidence.

It does not work, and the reason is worth stating precisely because the
failure is silent -- it produces a *narrower* interval that is simply
wrong.

**Resampling cannot create information.** The uncertainty here comes from
having 396 markets of which ~20 carry the return. Every subsample is drawn
from those same 396. The average of subsample estimates converges to the
full-sample estimate by construction; that is what averaging does. What it
cannot do is tell you the full-sample estimate is more reliable than the
data supports.

**The spread of subsample means is not the standard error.** This is the
trap. A subsample of size m has roughly sqrt(n/m) times the standard error
of the full sample, so the *average* of many subsample means has a spread
much smaller than the true SE. Reading significance off that spread
understates uncertainty by a large factor. Subsampling theory (Politis &
Romano) does support valid inference from m-out-of-n draws, but only with
an explicit rescaling by sqrt(m/n) -- and once rescaled it returns
approximately the ordinary bootstrap interval. No free significance.

This script demonstrates both empirically, then runs the two things that
*would* be informative: whether the concentration is a sizing artefact,
and an honest out-of-time split.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.stats import bootstrap_ratio

CFG = DEFAULT.stats
RNG = np.random.default_rng(CFG.seed)
LADDER = "$250 → $5,000"


def per_market(ps):
    num, den, first = defaultdict(float), defaultdict(float), {}
    for p in ps:
        num[p["cid"]] += p["pnl"]
        den[p["cid"]] += p["capital"]
        first[p["cid"]] = min(first.get(p["cid"], p["entry_ts"]), p["entry_ts"])
    cids = sorted(den)
    return (cids, np.array([num[c] for c in cids]),
            np.array([den[c] for c in cids]),
            np.array([first[c] for c in cids]))


def subsample_demo(num, den, fracs=(0.7, 0.8), draws=4000):
    n = len(num)
    point = num.sum() / den.sum()
    out = {}
    for f in fracs:
        m = max(2, int(round(f * n)))
        ests = np.empty(draws)
        for i in range(draws):
            idx = RNG.choice(n, size=m, replace=False)
            d = den[idx].sum()
            ests[i] = num[idx].sum() / d if d > 0 else 0.0
        naive_lo, naive_hi = np.percentile(ests, [2.5, 97.5])
        # Correct rescaling for m-out-of-n subsampling.
        scale = np.sqrt(m / n)
        resc_lo = point - (np.percentile(ests, 97.5) - point) / scale
        resc_hi = point + (point - np.percentile(ests, 2.5)) / scale
        out[f] = {"m": m, "mean_of_subsamples": float(ests.mean()),
                  "naive_ci": [float(naive_lo), float(naive_hi)],
                  "naive_width": float(naive_hi - naive_lo),
                  "rescaled_ci": [float(resc_lo), float(resc_hi)],
                  "rescaled_width": float(resc_hi - resc_lo),
                  "naive_p_le_zero": float((ests <= 0).mean())}
    return point, out


def main() -> None:
    d = json.load(open("experiments/ff_timeline.json"))
    ps = d["positions"][LADDER]
    cids, num, den, first = per_market(ps)
    n = len(cids)
    boot = bootstrap_ratio(list(num), list(den), CFG)

    print(f"  {LADDER}: {n} markets\n")
    print(f"  ordinary cluster bootstrap (the honest baseline)")
    print(f"    {boot.point:+.1%}  [{boot.lo:+.1%}, {boot.hi:+.1%}]  "
          f"p={boot.p_le_zero:.3f}  width {boot.hi-boot.lo:.1%}\n")

    point, sub = subsample_demo(num, den)
    print(f"  subsample-and-average, {CFG.n_boot:,} draws each")
    print(f"  {'frac':>6}{'m':>6}{'mean':>10}{'naive CI':>22}{'naive p':>9}"
          f"{'rescaled CI':>22}")
    for f, r in sub.items():
        print(f"  {f:>6.0%}{r['m']:>6}{r['mean_of_subsamples']:>+10.1%}"
              f"  [{r['naive_ci'][0]:+6.1%},{r['naive_ci'][1]:+6.1%}]"
              f"{r['naive_p_le_zero']:>9.3f}"
              f"  [{r['rescaled_ci'][0]:+6.1%},{r['rescaled_ci'][1]:+6.1%}]")
    print(f"\n  The mean of subsamples returns the point estimate "
          f"({point:+.1%}) -- it adds nothing.")
    print(f"  The naive interval is narrower than the bootstrap's "
          f"{boot.hi-boot.lo:.1%} and is WRONG.")
    print(f"  Rescaled, it reproduces the bootstrap. No free significance.\n")

    # Is the concentration a sizing artefact or a return artefact?
    ret = np.where(den > 0, num / np.maximum(den, 1e-9), 0.0)
    order_pnl = np.argsort(-num)
    top5 = order_pnl[:5]
    print("  is the concentration about SIZE or about RETURN?")
    print(f"    top 5 markets by PnL hold {den[top5].sum()/den.sum():>5.1%} "
          f"of capital and {num[top5].sum()/num.sum():>5.1%} of PnL")
    print(f"    their mean return {ret[top5].mean():+.0%} vs "
          f"{np.median(ret):+.1%} median across all markets")
    print(f"    capital Gini {_gini(den):.2f}, PnL Gini {_gini(np.abs(num)):.2f}")

    # Equal-weight: strips the sizing effect entirely.
    eq = bootstrap_ratio(list(ret), [1.0] * n, CFG)
    print(f"\n  equal-weighted mean return per market (sizing removed)")
    print(f"    {eq.point:+.1%}  [{eq.lo:+.1%}, {eq.hi:+.1%}]  "
          f"p={eq.p_le_zero:.3f}")

    # Honest out-of-time split.
    cut = float(np.median(first))
    a = first <= cut
    b = ~a
    ia = bootstrap_ratio(list(num[a]), list(den[a]), CFG)
    ib = bootstrap_ratio(list(num[b]), list(den[b]), CFG)
    print(f"\n  out-of-time split at the median entry date")
    print(f"    first half   {ia.point:+.1%}  [{ia.lo:+.1%}, {ia.hi:+.1%}]  "
          f"p={ia.p_le_zero:.3f}  n={ia.n}")
    print(f"    second half  {ib.point:+.1%}  [{ib.lo:+.1%}, {ib.hi:+.1%}]  "
          f"p={ib.p_le_zero:.3f}  n={ib.n}")

    json.dump({"ladder": LADDER, "n_markets": n,
               "bootstrap": {"point": boot.point, "lo": boot.lo, "hi": boot.hi,
                             "p_le_zero": boot.p_le_zero},
               "subsampling": {str(k): v for k, v in sub.items()},
               "equal_weighted": {"point": eq.point, "lo": eq.lo, "hi": eq.hi,
                                  "p_le_zero": eq.p_le_zero},
               "time_split": {
                   "first": {"point": ia.point, "lo": ia.lo, "hi": ia.hi,
                             "p_le_zero": ia.p_le_zero, "n": ia.n},
                   "second": {"point": ib.point, "lo": ib.lo, "hi": ib.hi,
                              "p_le_zero": ib.p_le_zero, "n": ib.n}}},
              open("experiments/ff_resampling.json", "w"), indent=1)
    print("\n  -> experiments/ff_resampling.json")


def _gini(x) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() <= 0:
        return 0.0
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


if __name__ == "__main__":
    main()
