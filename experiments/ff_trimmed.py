"""PnL and bounds with the top markets removed, and with them capped.

"Drop the best 5" is a stress test, not an estimator. It removes the five
largest contributors *by construction*, so it is biased low by exactly as
much as the full sample is biased high by including whatever luck is in
them. Neither number is the answer; the gap between them is the honest
statement of what 396 markets can support.

So this reports four cuts:

    full            everything (optimistic: includes the luck)
    drop best 5     the project's concentration screen (pessimistic)
    winsorised      top 5 capped at the 6th-largest PnL, not deleted --
                    keeps the markets and their capital, removes only the
                    extremity of their outcomes
    symmetric trim  best 5 AND worst 5 removed, which is what a trimmed
                    estimator normally means and is not biased in either
                    direction

Dollar PnL is reported alongside every return, because a percentage on
recycled capital is easy to misread.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.stats import bootstrap_ratio

CFG = DEFAULT.stats
N_DROP = DEFAULT.screen.concentration_drop_n


def per_market(rows):
    num, den, q = defaultdict(float), defaultdict(float), {}
    for p in rows:
        num[p["cid"]] += p["pnl"]
        den[p["cid"]] += p["capital"]
        q.setdefault(p["cid"], p.get("question", p["cid"][:10]))
    cids = sorted(den)
    return cids, np.array([num[c] for c in cids]), np.array([den[c] for c in cids])


def row(label, num, den):
    iv = bootstrap_ratio(list(num), list(den), CFG)
    pnl, cap = float(num.sum()), float(den.sum())
    print(f"  {label:<20}{pnl:>+11,.0f}{cap:>12,.0f}{iv.point:>+9.1%}"
          f"  [{iv.lo:+6.1%},{iv.hi:+6.1%}]{iv.p_le_zero:>8.3f}{iv.n:>7}")
    return {"label": label, "pnl_usd": pnl, "deployed_usd": cap,
            "point": iv.point, "lo": iv.lo, "hi": iv.hi,
            "p_le_zero": iv.p_le_zero, "n": iv.n,
            "significant": bool(iv.significant)}


def main() -> None:
    d = json.load(open("experiments/ff_timeline.json"))
    out = {}
    for name, ps in d["positions"].items():
        cids, num, den = per_market(ps)
        order = np.argsort(-num)
        top, bot = set(order[:N_DROP].tolist()), set(order[-N_DROP:].tolist())
        keep_top = np.array([i for i in range(len(cids)) if i not in top])
        keep_both = np.array([i for i in range(len(cids))
                              if i not in top and i not in bot])
        wins = num.copy()
        wins[list(top)] = num[order[N_DROP]]      # cap at the 6th largest

        print(f"\n  {name}")
        print(f"  {'cut':<20}{'PnL $':>11}{'deployed $':>12}{'return':>9}"
              f"{'95% interval':>17}{'p':>8}{'mkts':>7}")
        r = {}
        r["full"] = row("full sample", num, den)
        r["drop_best_5"] = row(f"drop best {N_DROP}", num[keep_top], den[keep_top])
        r["winsorised"] = row(f"winsorise top {N_DROP}", wins, den)
        r["symmetric_trim"] = row(f"trim best+worst {N_DROP}",
                                  num[keep_both], den[keep_both])
        out[name] = r

        if name == "$250 → $5,000":
            print(f"\n    the {N_DROP} markets removed:")
            for i in order[:N_DROP]:
                print(f"      {num[i]:>+10,.0f} on {den[i]:>9,.0f} deployed "
                      f"({num[i]/den[i]:>+7.0%})  {cids[i][:22]}")
            print(f"    they are {den[list(top)].sum()/den.sum():.1%} of capital "
                  f"and {num[list(top)].sum()/num.sum():.1%} of PnL")

    json.dump(out, open("experiments/ff_trimmed.json", "w"), indent=1)
    print("\n  -> experiments/ff_trimmed.json")


if __name__ == "__main__":
    main()
