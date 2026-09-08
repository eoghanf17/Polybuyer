"""Statistical verification of the cluster ladder result.

The headline numbers (+12.6% / +13.5% / +15.7%) were reported as point
estimates. This project's own rule is that a point estimate on clustered
data means very little: the independent unit is the **market**, since every
position in a market shares one resolution, and per-trade resampling
overstates significance by orders of magnitude.

So this runs what should have run alongside the headline:

**Cluster bootstrap.** Markets resampled with replacement, ratio recomputed
from resampled totals. `StatsConfig.min_clusters` is 20, raised from 8 after
a live false positive where a wallet scored +40.0% [+14.1%, +55.3%] off 11
markets and came back +8.9% [-12.2%, +27.3%] on its full history.

**Concentration.** Drop the best N markets and see what survives. The
original study's screen used `concentration_drop_n = 5`; an edge that
evaporates without its five best markets is a few lucky resolutions.

**Segment splits.** Pre-match, in-play and non-match bootstrapped
separately, because the in-play and non-match samples are small enough that
their point estimates should not be quoted at all without an interval.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.stats import bootstrap_ratio

CFG = DEFAULT.stats
DROP_N = DEFAULT.screen.concentration_drop_n


def per_market(ps):
    num, den = defaultdict(float), defaultdict(float)
    for p in ps:
        num[p["cid"]] += p["pnl"]
        den[p["cid"]] += p["capital"]
    cids = sorted(den)
    return cids, [num[c] for c in cids], [den[c] for c in cids]


def fmt(iv) -> str:
    flag = "  UNDERPOWERED" if getattr(iv, "underpowered", False) else ""
    return (f"{iv.point:+7.1%}  [{iv.lo:+6.1%}, {iv.hi:+6.1%}]  "
            f"p={iv.p_le_zero:.3f}  n={iv.n}{flag}")


def main() -> None:
    d = json.load(open("experiments/ff_timeline.json"))
    out = {}

    print(f"  cluster bootstrap, {CFG.n_boot:,} resamples, "
          f"min_clusters={CFG.min_clusters}\n")
    for name, ps in d["positions"].items():
        cids, num, den = per_market(ps)
        iv = bootstrap_ratio(num, den, CFG)
        print(f"  {name}")
        print(f"    all           {fmt(iv)}")

        # Concentration: drop the best markets by PnL.
        order = sorted(range(len(cids)), key=lambda i: -num[i])
        keep = [i for i in range(len(cids)) if i not in set(order[:DROP_N])]
        iv_d = bootstrap_ratio([num[i] for i in keep], [den[i] for i in keep], CFG)
        print(f"    drop best {DROP_N:<2}  {fmt(iv_d)}")

        seg_res = {}
        for seg in ("pre-match", "in-play", "non-match"):
            sel = [p for p in ps if p.get("segment") == seg]
            if not sel:
                continue
            c2, n2, d2 = per_market(sel)
            iv_s = bootstrap_ratio(n2, d2, CFG)
            seg_res[seg] = {"point": iv_s.point, "lo": iv_s.lo, "hi": iv_s.hi,
                            "p_le_zero": iv_s.p_le_zero, "significant": bool(iv_s.significant), "n": iv_s.n,
                            "underpowered": bool(getattr(iv_s, "underpowered", False))}
            print(f"    {seg:<13} {fmt(iv_s)}")
        out[name] = {
            "all": {"point": iv.point, "lo": iv.lo, "hi": iv.hi, "p_le_zero": iv.p_le_zero, "significant": bool(iv.significant),
                    "n": iv.n,
                    "underpowered": bool(getattr(iv, "underpowered", False))},
            "drop_best_n": {"n_dropped": DROP_N, "point": iv_d.point,
                            "lo": iv_d.lo, "hi": iv_d.hi, "p_le_zero": iv_d.p_le_zero, "significant": bool(iv_d.significant),
                            "n": iv_d.n},
            "segments": seg_res}
        print()

    json.dump(out, open("experiments/ff_verify.json", "w"), indent=1)
    print("  -> experiments/ff_verify.json")


if __name__ == "__main__":
    main()
