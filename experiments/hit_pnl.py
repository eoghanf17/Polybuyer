"""What the three blind-test-2 hits would actually have paid.

Short answer: nothing that can be demonstrated. This script exists to show
the arithmetic rather than assert it.

## Why the question needed re-asking

`blind2.py` located each market's "repricing" as the first print at
ref >= 0.90 that held for six hours. That is not a news jump -- for a
market that opens high it is simply the market's first print. Running
`jumps.detect` over the same tapes puts the three hits in a different
light: the Squid post predates the market's entire tape, the Burnham post
falls between two detected jumps in a market already at 0.89, and the OBJ
post lands exactly on its jump onset.

So blind test 2's 3/8 is a measure of **whether the rule caught a post
about the story**, which is real. It is not a measure of whether the story
could have been traded, and this file is the second question.

## Method

Entry price is the median over the hour before the post, falling back to
the last print before it -- with the staleness of that fallback reported,
because a "price" from four days ago is not a price you could have traded
against.

Fills come from :meth:`Tape.simulate_fill`, which consumes only prints
that actually executed on our side inside the cap. No historical order
books exist, so this counts liquidity somebody else demonstrably took and
ignores every resting offer nobody hit. It is a **lower bound**.

Windows run out to the market's close rather than stopping at ten minutes.
In a market with a hundred prints across four months, a limit order rests
for hours; capping the window at the 600s used for liquid follow-trading
would understate the answer for the wrong reason.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import JumpConfig
from polybuyer.jumps import detect
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk import corpus as C
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

AGGRESSIONS = [0.01, 0.02, 0.05, 0.10]
WINDOWS = [("10m", 600), ("1h", 3600), ("6h", 21_600), ("24h", 86_400),
           ("to close", 10**9)]
#: Thin tapes: relax the print-count floor, leave the move logic alone.
CFG = JumpConfig(min_market_trades=40)


def entry_price(tape: Tape, ts: int) -> tuple[float | None, float]:
    """Reference price at the post, and how stale it is in hours."""
    p = tape.median_price(ts - 3600, ts)
    if p is not None:
        return p, 0.0
    prior = tape.slice(tape.start, ts)
    if not prior:
        return None, float("inf")
    return prior[-1].ref_price, (ts - prior[-1].ts) / 3600.0


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    posts = [p for p in C.load()
             if p.source == "blind2/keyword_rules" and p.label == C.BREAKER]
    best: dict[str, C.Post] = {}
    for p in posts:
        cur = best.get(p.market)
        if cur is None or p.created_at < cur.created_at:
            best[p.market] = p

    out = []
    for market, p in sorted(best.items()):
        trs = normalise_many(market_tape(f, p.condition_id).trades)
        tape = Tape(p.condition_id, trs)
        ts = int(dt.datetime.fromisoformat(
            p.created_at.replace("Z", "+00:00")).timestamp())
        term = tape.median_price(tape.end - 3600, tape.end + 1)
        term = 1.0 if (term or 0) >= 0.5 else 0.0

        print(f"\n{'='*78}\n{market}")
        print(f"  breaker @{p.handle} ({p.followers:,}f) at "
              f"{dt.datetime.utcfromtimestamp(ts):%Y-%m-%d %H:%M} UTC")
        print(f"  tape: {len(trs)} prints, ${sum(x.notional for x in trs):,.0f} "
              f"lifetime notional, {dt.datetime.utcfromtimestamp(tape.start):%b %d} "
              f"-> {dt.datetime.utcfromtimestamp(tape.end):%b %d}")

        if ts < tape.start:
            print(f"  UNTRADEABLE: post lands "
                  f"{(tape.start - ts)/3600:.1f}h before the market's first print.")
            out.append({"market": market, "verdict": "no market yet",
                        "handle": p.handle}); continue

        jumps = detect(tape, CFG, terminal=term)
        nearest = min(jumps, key=lambda j: abs(j.onset_ts - ts), default=None)
        if nearest is not None:
            print(f"  nearest real jump: {nearest.before:.2f}->{nearest.after:.2f} "
                  f"at {(nearest.onset_ts - ts)/3600:+.1f}h relative to the post "
                  f"({len(jumps)} jumps in this tape)")

        entry, stale = entry_price(tape, ts)
        if entry is None:
            print("  UNTRADEABLE: no price before the post.")
            out.append({"market": market, "verdict": "no price"}); continue
        direction = 1 if term > entry else -1
        print(f"  price at post {entry:.3f}"
              + (f"  (STALE: last print {stale:.1f}h earlier)" if stale > 1 else "")
              + f"   terminal {term:.0f}   headroom "
                f"{abs(term - entry):.3f}/share")
        n_after = len(tape.slice(ts, ts + 601))
        print(f"  prints in the 10 min after the post: {n_after}")

        rows = []
        print(f"\n  {'window':>9} {'aggr':>6} {'fillable':>10} {'vwap':>7}"
              f" {'PnL':>9} {'ROI':>7}")
        any_fill = False
        for label, wsec in WINDOWS:
            for a in AGGRESSIONS:
                fill = tape.simulate_fill(ts, entry, direction,
                                          want_shares=1e9, cap=a, window_s=wsec)
                if fill.shares <= 0:
                    continue
                any_fill = True
                cost = fill.shares * fill.vwap
                pnl = fill.shares * (1.0 - fill.vwap)
                rows.append({"window": label, "aggression": a,
                             "fillable_usd": cost, "vwap": fill.vwap,
                             "pnl_usd": pnl,
                             "roi": pnl / cost if cost else 0.0})
                print(f"  {label:>9} {a:>6.2f} ${cost:>9,.0f} {fill.vwap:>7.3f}"
                      f" ${pnl:>8,.0f} {pnl/cost if cost else 0:>6.0%}")
        if not any_fill:
            print("   -- no fillable liquidity on our side at any cap or window --")
        out.append({"market": market, "handle": p.handle,
                    "followers": p.followers, "entry": entry,
                    "stale_h": stale, "terminal": term,
                    "prints_10m": n_after, "ladder": rows,
                    "verdict": "fillable" if any_fill else "no liquidity"})

    json.dump(out, open("experiments/hit_pnl.json", "w"), indent=1)
    print(f"\n{'='*78}\n  written to experiments/hit_pnl.json")


if __name__ == "__main__":
    main()
