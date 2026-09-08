"""Is the cluster trading lineup announcements?

Entries cluster around 30 minutes before kickoff, and official lineups drop
at a known time -- 60 minutes before kickoff in the Premier League, 60-75
in most major leagues. That makes the hypothesis testable rather than
merely plausible: if lineup news is the edge, entries should **pile up just
after** the announcement, and trades in that window should carry the
return.

## Guarding against choosing the answer

This is a subset selected after seeing the data, which is how spurious
results get made. Three precautions:

1. The candidate window is fixed from **football**, not from returns:
   lineups at T-60 to T-75, so the reaction window is T-75 to T-30.
2. The timing histogram is examined **before** any PnL is computed, so the
   mechanism claim stands or falls on shape alone.
3. The window is **swept** afterwards. A real effect degrades smoothly as
   the window moves; an artefact appears at one setting and vanishes beside
   it.

Even so, this is exploratory. It cannot be confirmatory on the same data
that suggested it.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.model import resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import market_resolution
from polybuyer.stats import bootstrap_ratio

CFG = DEFAULT.stats
#: Declared from football, before looking at any return.
LINEUP_LO_MIN, LINEUP_HI_MIN = 30, 75


def per_market(rows):
    num, den = defaultdict(float), defaultdict(float)
    for p in rows:
        num[p["cid"]] += p["pnl"]
        den[p["cid"]] += p["capital"]
    cids = sorted(den)
    return [num[c] for c in cids], [den[c] for c in cids]


def show(label, rows):
    if not rows:
        print(f"  {label:<28} no positions")
        return None
    num, den = per_market(rows)
    iv = bootstrap_ratio(num, den, CFG)
    flag = " UNDERPOWERED" if iv.underpowered else ""
    print(f"  {label:<28}{iv.point:>+8.1%}  [{iv.lo:+6.1%},{iv.hi:+6.1%}]  "
          f"p={iv.p_le_zero:.3f}  n={iv.n:<4} ${sum(den):>9,.0f}{flag}")
    return {"point": iv.point, "lo": iv.lo, "hi": iv.hi,
            "p_le_zero": iv.p_le_zero, "n": iv.n,
            "deployed": sum(den), "pnl": sum(num),
            "underpowered": bool(iv.underpowered)}


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    d = json.load(open("experiments/ff_timeline.json"))

    kicks = {}
    for cid in sorted({p["cid"] for ps in d["positions"].values() for p in ps}):
        pay = market_resolution(f, cid)
        if pay:
            r = resolution_from_clob(cid, pay)
            if r.game_start_ts:
                kicks[cid] = r.game_start_ts

    # ---- Step 1: shape only. No PnL yet. -----------------------------
    ref = d["positions"]["$250 → $5,000"]
    for p in ref:
        g = kicks.get(p["cid"])
        p["lead_min"] = (g - p["entry_ts"]) / 60.0 if g else None
    leads = [p["lead_min"] for p in ref if p["lead_min"] is not None]

    print("  entries by minutes before kickoff (shape examined before PnL)\n")
    bins = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90),
            (90, 120), (120, 180), (180, 360), (360, 10**9)]
    hist = Counter()
    for x in leads:
        if x <= 0:
            hist["in-play"] += 1
            continue
        for lo, hi in bins:
            if lo < x <= hi:
                hist[f"{lo}-{hi}m"] += 1
                break
    peak = max(hist.values())
    for lo, hi in bins:
        k = f"{lo}-{hi}m"
        n = hist.get(k, 0)
        bar = "█" * max(0, round(28 * n / peak))
        print(f"    {k:>10} {n:>4}  {bar}")
    print(f"    {'in-play':>10} {hist.get('in-play',0):>4}")
    inw = sum(1 for x in leads if LINEUP_LO_MIN <= x <= LINEUP_HI_MIN)
    print(f"\n    {inw}/{len(leads)} ({inw/len(leads):.0%}) fall in the declared "
          f"lineup window T-{LINEUP_HI_MIN} to T-{LINEUP_LO_MIN}")

    # ---- Step 2: returns -------------------------------------------
    out = {"histogram": dict(hist), "window": [LINEUP_LO_MIN, LINEUP_HI_MIN],
           "ladders": {}}
    for name, ps in d["positions"].items():
        for p in ps:
            g = kicks.get(p["cid"])
            p["lead_min"] = (g - p["entry_ts"]) / 60.0 if g else None
        inl = [p for p in ps if p["lead_min"] is not None
               and LINEUP_LO_MIN <= p["lead_min"] <= LINEUP_HI_MIN]
        out_l = [p for p in ps if p["lead_min"] is not None
                 and not (LINEUP_LO_MIN <= p["lead_min"] <= LINEUP_HI_MIN)]
        print(f"\n  {name}")
        r = {}
        r["all"] = show("all positions", ps)
        r["lineup_window"] = show(f"lineup T-{LINEUP_HI_MIN}..T-{LINEUP_LO_MIN}", inl)
        r["outside"] = show("everything else", out_l)
        out["ladders"][name] = r

    # ---- Step 3: sweep ---------------------------------------------
    print("\n  window sweep (a real effect degrades smoothly)")
    print(f"  {'window':<18}{'return':>9}{'p':>8}{'markets':>9}{'deployed':>12}")
    ps = d["positions"]["$250 → $5,000"]
    sweep = []
    for lo, hi in [(0, 30), (15, 45), (30, 60), (30, 75), (45, 90),
                   (60, 120), (75, 150), (0, 1e9)]:
        sel = [p for p in ps if p["lead_min"] is not None and lo <= p["lead_min"] <= hi]
        if len(sel) < 5:
            continue
        num, den = per_market(sel)
        iv = bootstrap_ratio(num, den, CFG)
        lab = f"T-{hi:g}..T-{lo:g}" if hi < 1e8 else "all pre-kickoff"
        print(f"  {lab:<18}{iv.point:>+9.1%}{iv.p_le_zero:>8.3f}"
              f"{iv.n:>9}{sum(den):>12,.0f}")
        sweep.append({"lo": lo, "hi": hi, "point": iv.point,
                      "p_le_zero": iv.p_le_zero, "n": iv.n,
                      "deployed": sum(den)})
    out["sweep"] = sweep
    json.dump(out, open("experiments/ff_lineup.json", "w"), indent=1)
    print("\n  -> experiments/ff_lineup.json")


if __name__ == "__main__":
    main()
