"""FootballFan98 cluster: capital deployed over time, and PnL over time.

Follows the **cluster**, which is the only thing that makes sense here.
FootballFan98 alone is the loss-making leg -- -$1.07M against the cluster's
+$4.76M -- so a simulation of that wallet measures the worst member rather
than the strategy, and an earlier version of this file did exactly that and
returned -11.9%.

Three corrections carried from `newsdesk.learnings`:

**Signals are the cluster's combined position.** The four wallets are
merged into one trade sequence per market before the first-above-$10k
signal is taken, so a position built across two wallets reads as one entry
rather than two small ones.

**All four are excluded from follower liquidity.** You cannot fill against
the order you are copying, nor against the same operator's other wallet
firing the same idea.

**Signals come from wallet history, not the tape.** `market_tape` is capped
and newest-first, so on a busy market it holds only recent prints and the
cluster's fifth trade reads as its first. Signals whose tape does not reach
back are dropped as unmeasurable.

`follow.evaluate()` reports totals, which cannot answer "how much did I
have at risk on a given Tuesday" -- cumulative deployment counts a dollar
again every time it recycles. So this emits one record per filled position
and integrates them into deployed(t) and pnl(t).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.follow import Ladder, STRATEGIES
from polybuyer.model import dedupe, normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import (market_resolution, market_tape,
                               wallet_trade_history)
from polybuyer.tape import Tape
from polybuyer.targets import FOOTBALLFAN_CLUSTER, FOOTBALLFAN_WALLETS

LADDERS = {
    "$50 → $1,000": Ladder(lo_usd=50.0, hi_usd=1_000.0),
    "$250 → $5,000": Ladder(lo_usd=250.0, hi_usd=5_000.0),
    "$500 → $10,000": Ladder(lo_usd=500.0, hi_usd=10_000.0),
}
STRATEGY = "first-10k"
DAYS = 365
OUT = "experiments/ff_timeline.json"


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    cfg = DEFAULT
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start = now - DAYS * 86_400

    trades = []
    for m in FOOTBALLFAN_CLUSTER:
        rows = wallet_trade_history(f, m.address, start, now)
        t = normalise_many(rows)
        print(f"  {m.handle:<15} {len(t):>6} prints  "
              f"${sum(x.notional for x in t):>14,.0f}", flush=True)
        trades.extend(t)
    trades = dedupe(trades)
    print(f"  {'CLUSTER':<15} {len(trades):>6} prints  "
          f"${sum(t.notional for t in trades):>14,.0f}\n")

    by_market: dict[str, list] = {}
    for t in trades:
        by_market.setdefault(t.condition_id, []).append(t)
    ranked = sorted(by_market, key=lambda c: -sum(x.notional for x in by_market[c]))
    print(f"  {len(ranked)} markets touched by the cluster; fetching tapes...")

    build = STRATEGIES[STRATEGY]
    clusterset = frozenset(FOOTBALLFAN_WALLETS)
    positions = {k: [] for k in LADDERS}
    skipped = {"unresolved": 0, "thin": 0, "no_signal": 0, "uncovered": 0,
               "no_fill": 0}

    for i, cid in enumerate(ranked, 1):
        if i % 40 == 0:
            print(f"    {i}/{len(ranked)}", flush=True)
        payload = market_resolution(f, cid)
        if not payload:
            skipped["unresolved"] += 1; continue
        res = resolution_from_clob(cid, payload)
        if not res.is_terminal or res.ref_terminal is None:
            skipped["unresolved"] += 1; continue
        mt = market_tape(f, cid)
        trs = normalise_many(mt.trades)
        if len(trs) < 20:
            skipped["thin"] += 1; continue
        tape = Tape(cid, trs)
        terminal = res.ref_terminal
        exit_ts = tape.end

        # The cluster's combined sequence -- one entry, not four.
        sigs = build(sorted(by_market[cid], key=lambda t: t.ts))
        if not sigs:
            skipped["no_signal"] += 1; continue

        for sig in sigs:
            if sig.ts < start:
                continue
            if mt.truncated and sig.ts < tape.start:
                skipped["uncovered"] += 1; continue
            d = sig.direction
            unit = sig.entry_ref if d > 0 else 1.0 - sig.entry_ref
            if unit <= 0:
                continue
            payoff = terminal if d > 0 else 1.0 - terminal
            filled_any = False
            for name, lad in LADDERS.items():
                want = lad.usd(sig.notional) / unit
                fill = tape.simulate_fill(sig.ts, sig.entry_ref, d, want,
                                          cfg.follow.cap, cfg.follow.window_s,
                                          clusterset)
                if fill.shares <= 0:
                    continue
                filled_any = True
                positions[name].append({
                    "cid": cid, "in_play": bool(res.in_play),
                    "entry_ts": sig.ts,
                    "exit_ts": max(exit_ts, sig.ts + 1),
                    "capital": round(fill.notional, 2),
                    "pnl": round(fill.shares * (payoff - fill.vwap), 2),
                    "target_notional": round(sig.notional, 2)})
            if not filled_any:
                skipped["no_fill"] += 1

    json.dump({"cluster": [m.handle for m in FOOTBALLFAN_CLUSTER],
               "wallets": list(FOOTBALLFAN_WALLETS), "strategy": STRATEGY,
               "days": DAYS, "skipped": skipped, "positions": positions},
              open(OUT, "w"), indent=1)

    print(f"\n  skipped: {skipped}\n")
    for name, ps in positions.items():
        if not ps:
            print(f"  {name}: no filled positions"); continue
        news = [p for p in ps if not p["in_play"]]
        cap = sum(p["capital"] for p in ps)
        pnl = sum(p["pnl"] for p in ps)
        print(f"  {name}")
        print(f"    {len(ps)} positions ({len(news)} news, "
              f"{len(ps)-len(news)} in-play)")
        print(f"    cumulative deployed ${cap:,.0f}   PnL ${pnl:,.0f} "
              f"({pnl/cap:+.1%})")
        print(f"    peak concurrent exposure ${_peak(ps):,.0f}")
        if news:
            nc = sum(p["capital"] for p in news); np_ = sum(p["pnl"] for p in news)
            print(f"    news only: ${nc:,.0f} deployed, ${np_:,.0f} "
                  f"({np_/nc:+.1%})" if nc else "")
    print(f"\n  -> {OUT}")


def _peak(ps) -> float:
    ev = []
    for p in ps:
        ev.append((p["entry_ts"], p["capital"]))
        ev.append((p["exit_ts"], -p["capital"]))
    ev.sort()
    cur = peak = 0.0
    for _, d in ev:
        cur += d
        peak = max(peak, cur)
    return peak


if __name__ == "__main__":
    main()
