"""Tradeable-market yield by volume band.

The old universe was gamma's single-query ceiling: 2,100 markets, all above
$2.97M. Slicing the same window by month reaches 18,832, with a median of
$769k -- so the old view was roughly the top tenth of resolved markets by
volume, and the question is how many tradeable news markets sit below it.

Yield cannot be assumed constant across bands. The screen that matters is
"at least $200 fillable at a 5c cap in the 30 minutes after the onset", and
that is exactly what thin markets fail -- blind test 2 found markets with
$3.5k-$11k of lifetime volume where nothing was fillable at all. So this
samples each band and measures the yield rather than extrapolating the
high-volume rate downward.
"""

from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import JumpConfig
from polybuyer.jumps import detect
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk.discover import (KNOWN_INSTANT_PAT, OFF_PLATFORM_PAT,
                                         SCHEDULED_PAT, SPORTS_PAT)
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

CFG = JumpConfig(min_market_trades=60)
CAP, WIN, MIN_FILL = 0.05, 1800, 200.0
BANDS = [(250_000, 500_000), (500_000, 1_000_000),
         (1_000_000, 3_000_000), (3_000_000, 10**12)]
SAMPLE = 55
SEED = 20260902


def screened(m: dict) -> bool:
    q = m["q"]
    if m.get("gst"):
        return False
    return not (SPORTS_PAT.search(q) or SCHEDULED_PAT.search(q)
                or OFF_PLATFORM_PAT.search(q) or KNOWN_INSTANT_PAT.search(q))


def tradeable(f, m) -> tuple[bool, float]:
    try:
        trs = normalise_many(market_tape(f, m["cid"]).trades)
    except Exception:
        return False, 0.0
    if len(trs) < 60:
        return False, 0.0
    tape = Tape(m["cid"], trs)
    last = tape.median_price(tape.end - 3600, tape.end + 1)
    if last is None:
        return False, 0.0
    terminal = 1.0 if last >= 0.5 else 0.0
    js = detect(tape, CFG, terminal=terminal)
    res = [j for j in js if (j.direction > 0) == (terminal >= 0.5)]
    if not res:
        return False, 0.0
    j = res[-1]
    payoff = terminal if j.direction > 0 else 1.0 - terminal
    fill = tape.simulate_fill(j.onset_ts, j.before, j.direction,
                              want_shares=1e9, cap=CAP, window_s=WIN)
    cost = fill.shares * fill.vwap
    if cost < MIN_FILL:
        return False, 0.0
    return True, fill.shares * (payoff - fill.vwap)


def main() -> None:
    random.seed(SEED)
    f = Fetcher(cache_dir=".polycache")
    uni = json.load(open("experiments/universe_full.json"))
    print(f"  {len(uni)} resolved markets in the window\n")

    rows = []
    print(f"  {'band':<22}{'total':>8}{'screened':>10}{'sampled':>9}"
          f"{'tradeable':>11}{'yield':>8}{'med PnL':>10}")
    for lo, hi in BANDS:
        pool = [m for m in uni if lo <= m["vol"] < hi]
        scr = [m for m in pool if screened(m)]
        if not scr:
            continue
        samp = random.sample(scr, min(SAMPLE, len(scr)))
        ok, pnls = 0, []
        for m in samp:
            t, p = tradeable(f, m)
            if t:
                ok += 1; pnls.append(p)
        y = ok / len(samp)
        med = sorted(pnls)[len(pnls) // 2] if pnls else 0.0
        label = f"${lo//1000}k-${hi//1000}k" if hi < 10**12 else f"${lo//1000}k+"
        rows.append({"lo": lo, "hi": hi, "total": len(pool),
                     "screened": len(scr), "sampled": len(samp),
                     "tradeable": ok, "yield": y,
                     "screen_rate": len(scr) / len(pool),
                     "median_pnl": med})
        print(f"  {label:<22}{len(pool):>8}{len(scr):>10}{len(samp):>9}"
              f"{ok:>11}{y:>7.0%}{med:>10,.0f}", flush=True)

    print(f"\n  extrapolated tradeable news markets in 9 months:")
    tot = 0.0
    for r in rows:
        est = r["screened"] * r["yield"]
        tot += est
        label = f"${r['lo']//1000}k-${r['hi']//1000}k" if r["hi"] < 10**12 else f"${r['lo']//1000}k+"
        print(f"    {label:<22}{est:>8.0f}")
    print(f"    {'TOTAL':<22}{tot:>8.0f}")
    json.dump(rows, open("experiments/band_yield.json", "w"), indent=1)


if __name__ == "__main__":
    main()
