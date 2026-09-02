"""What blind test 3's hits would have paid, entering at the post.

The first test in this project where entry is the post's own timestamp
rather than the repricing onset. That matters twice: it is the honest
entry point for a live desk, and it is the only configuration in which the
don't-chase guards have a late entry to act on.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk import ledger as L
from polybuyer.newsdesk.guards import WINDOWS, evaluate
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

CAPS = [0.01, 0.02, 0.05, 0.10]
HOLD = [("30m", 1800), ("2h", 7200), ("to close", 10**9)]
DESK = [("tier2 keyword", 0.02, 3.0), ("tier1 principal", 0.05, 10.0)]


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    rows = json.load(open("experiments/blind4_result.json"))
    hits = [r for r in rows if any(v["hit"] for v in r["by_floor"].values())]
    print(f"  {len(hits)} markets hit of {len(rows)}\n")

    out = []
    for r in hits:
        # Prefer the 10k-floor hit: that is the configuration that ships.
        h = r["by_floor"].get("10000") or r["by_floor"].get(10_000)
        if not (h and h["hit"]):
            h = next(v for v in r["by_floor"].values() if v["hit"])
        post_ts = int(dt.datetime.fromisoformat(
            h["at"].replace("Z", "+00:00")).timestamp())
        onset = r["onset_ts"]
        trs = normalise_many(market_tape(f, r["cid"]).trades)
        tape = Tape(r["cid"], trs)
        direction = r["direction"]
        terminal = r["terminal"]
        payoff = terminal if direction > 0 else 1.0 - terminal

        entry = tape.median_price(post_ts - 3600, post_ts)
        stale = 0.0
        if entry is None:
            prior = tape.slice(tape.start, post_ts)
            if not prior:
                print(f"  {r['q'][:50]}: no price before the post"); continue
            entry, stale = prior[-1].ref_price, (post_ts - prior[-1].ts) / 3600

        print(f"{'='*78}\n{r['q']}")
        print(f"  @{h['handle']} ({h['followers']:,}f) at {h['at'][:19]}")
        print(f"  post leads the onset by {(onset - post_ts)/60:.0f} min")
        print(f"  entry {entry:.3f}" + (f" (STALE {stale:.1f}h)" if stale > 1 else "")
              + f"   onset {r['before']:.2f}->{r['after']:.2f}"
                f"   terminal {terminal:.0f}   payoff {payoff:.0f}")
        print(f"  post: {h['text'][:150]}")

        hist = {lab: tape.median_price(post_ts - s - 900, post_ts - s)
                for lab, s in WINDOWS}
        g = evaluate(entry, hist, direction, {"5m": 0.20, "1h": 0.20,
                                              "2h": 0.20, "1d": 0.30})
        print(f"  guards at the post: {'PASS' if g.passed else 'BLOCKED'} -- {g.reason}")

        ladder = []
        print(f"\n  {'hold':>9} {'cap':>6} {'fillable':>11} {'vwap':>7} "
              f"{'PnL':>10} {'ROI':>7}")
        for label, wsec in HOLD:
            for cap in CAPS:
                fill = tape.simulate_fill(post_ts, entry, direction,
                                          want_shares=1e9, cap=cap, window_s=wsec)
                if fill.shares <= 0:
                    continue
                cost = fill.shares * fill.vwap
                pnl = fill.shares * (payoff - fill.vwap)
                ladder.append({"window": label, "aggression": cap,
                               "fillable_usd": round(cost, 2),
                               "vwap": round(fill.vwap, 4),
                               "pnl_usd": round(pnl, 2),
                               "roi": round(pnl / cost, 4) if cost else 0.0})
                print(f"  {label:>9} {cap:>6.2f} ${cost:>10,.0f} {fill.vwap:>7.3f}"
                      f" ${pnl:>9,.0f} {pnl/cost if cost else 0:>6.0%}")
        if not ladder:
            print("   -- nothing fillable on our side --")

        rec = L.MarketRecord(
            condition_id=r["cid"], question=r["q"], volume_usd=r["vol"],
            resolved=True, terminal=terminal, entry_price=entry,
            direction=direction, ladder=ladder,
            signal_handle=h["handle"], signal_followers=h["followers"],
            signal_at=h["at"], signal_tier="keyword",
            signal_lead_s=float(onset - post_ts),
            verdict=L.FILLABLE if ladder else L.NO_LIQUIDITY,
            sources=["blind4"],
            notes=(f"blind3 hit; guards at post: "
                   f"{'pass' if g.passed else 'BLOCKED - ' + g.reason}"))
        out.append(rec)

        for name, cap, size in DESK:
            v = rec.pnl_at(cap, size)
            print(f"  desk {name:<16} ${size:>5.0f} @ {cap:.0%}: "
                  + (f"${v:,.2f}" if v is not None else "not fillable"))

    L.add(out)
    print(f"\n{'='*78}\n  {len(out)} markets merged into the ledger")


if __name__ == "__main__":
    main()
