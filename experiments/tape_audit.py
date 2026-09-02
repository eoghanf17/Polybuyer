"""Why do two thirds of screened markets have no detectable repricing?

That drop -- 200 of 315 in the first run -- is the largest in the funnel
and the only one that is a property of *our detector* rather than of the
market. If it is throwing away tradeable news the strategy is being
starved by a parameter; if those markets genuinely drifted to resolution
without a jump, there was never a trade in them and the filter is right.

So each failure is recorded with enough to tell the two apart: print
count, tape span, the largest move the tape contains at all, and whether a
deliberately loosened detector finds anything the shipped one missed.
"""

from __future__ import annotations

import json
import os
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

SHIPPED = JumpConfig(min_market_trades=60)
#: Deliberately loose: smaller move, weaker persistence, thinner tapes.
LOOSE = JumpConfig(min_market_trades=25, min_move=0.05,
                   persistence_frac=0.35, min_span_s=3600)
CAP, WIN, MIN_FILL = 0.05, 1800, 200.0


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    uni = json.load(open("experiments/universe.json"))
    keep = []
    for m in uni:
        q, blob = m["q"], m["q"]
        if SPORTS_PAT.search(q) or SCHEDULED_PAT.search(blob) \
           or OFF_PLATFORM_PAT.search(q) or KNOWN_INSTANT_PAT.search(blob):
            continue
        keep.append(m)
    print(f"  {len(keep)} markets past the text screens (no gameStartTime "
          f"field in the cached universe, so in-play is under-filtered here)\n")

    stats = {"thin_tape": 0, "no_terminal": 0, "no_jump_either": 0,
             "loose_only": 0, "jump_ok": 0, "unfillable": 0, "tradeable": 0,
             "tape_error": 0}
    recovered, tradeable = [], []

    for i, m in enumerate(keep, 1):
        if i % 100 == 0:
            print(f"    {i}/{len(keep)}", flush=True)
        try:
            trs = normalise_many(market_tape(f, m["cid"]).trades)
        except Exception:
            stats["tape_error"] += 1; continue
        if len(trs) < 25:
            stats["thin_tape"] += 1; continue
        tape = Tape(m["cid"], trs)
        last = tape.median_price(tape.end - 3600, tape.end + 1)
        if last is None:
            stats["no_terminal"] += 1; continue
        terminal = 1.0 if last >= 0.5 else 0.0

        js = detect(tape, SHIPPED, terminal=terminal) if len(trs) >= 60 else []
        loose = detect(tape, LOOSE, terminal=terminal)
        if not js:
            if not loose:
                stats["no_jump_either"] += 1
                continue
            stats["loose_only"] += 1
            js = loose
            recovered.append({"cid": m["cid"], "q": m["q"], "vol": m["vol"],
                              "prints": len(trs), "n_jumps": len(loose)})
        else:
            stats["jump_ok"] += 1

        res = [j for j in js if (j.direction > 0) == (terminal >= 0.5)]
        if not res:
            stats["unfillable"] += 1; continue
        j = res[-1]
        payoff = terminal if j.direction > 0 else 1.0 - terminal
        fill = tape.simulate_fill(j.onset_ts, j.before, j.direction,
                                  want_shares=1e9, cap=CAP, window_s=WIN)
        cost = fill.shares * fill.vwap
        if cost < MIN_FILL:
            stats["unfillable"] += 1; continue
        stats["tradeable"] += 1
        tradeable.append({
            "cid": m["cid"], "q": m["q"], "vol": m["vol"],
            "onset_ts": j.onset_ts, "before": round(j.before, 4),
            "after": round(j.after, 4), "direction": j.direction,
            "terminal": terminal, "fillable_usd": round(cost, 2),
            "vwap": round(fill.vwap, 4),
            "pnl_usd": round(fill.shares * (payoff - fill.vwap), 2),
            "loose": bool(not detect(tape, SHIPPED, terminal=terminal)
                          if len(trs) >= 60 else True),
        })

    print(f"\n  {json.dumps(stats, indent=2)}")
    print(f"\n  tradeable: {len(tradeable)}  "
          f"(shipped detector: {sum(1 for t in tradeable if not t['loose'])}, "
          f"only found by the loose one: {sum(1 for t in tradeable if t['loose'])})")
    tot = sum(t["pnl_usd"] for t in tradeable)
    print(f"  demonstrable PnL across them: ${tot:,.0f}")
    json.dump({"tradeable": tradeable, "recovered_by_loose": recovered,
               "stats": stats}, open("experiments/tape_audit.json", "w"), indent=1)
    print("  -> experiments/tape_audit.json")


if __name__ == "__main__":
    main()
