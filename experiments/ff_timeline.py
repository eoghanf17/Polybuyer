"""FootballFan98 ladder: capital deployed over time, and PnL over time.

`follow.evaluate()` reports totals -- "$15k deployed, +16.7%" -- which
answers "how much capital did this strategy consume in a year", not "how
much did I have at risk on a given Tuesday". Those are very different
numbers when positions are held to resolution: cumulative deployment
counts a dollar again every time it is redeployed, while concurrent
exposure is what a bankroll actually has to cover.

So this re-runs the same simulation emitting one record per filled
position -- entry time, capital, exit time, PnL -- and integrates them
into two series:

    deployed(t)   sum of capital in positions open at t
    pnl(t)        cumulative PnL from positions closed by t

Exit is the market's resolution. There is no resolution timestamp in the
CLOB payload, so the tape's last print is used as the proxy: these markets
stop trading when they settle, which is exactly the moment the position
pays out.

Everything is recorded liquidity -- fills come only from prints that
actually executed after the signal, inside the cap and window, with the
whole cluster excluded.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.clusters import fetch_and_build
from polybuyer.config import DEFAULT
from polybuyer.follow import Ladder, STRATEGIES
from polybuyer.model import dedupe, normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import (market_resolution, market_tape,
                               wallet_trade_history)
from polybuyer.tape import Tape

TARGET = "0xc31d0a0d63d760d72a1236d16beaa6a71c854ebe"   # FootballFan98
LADDERS = {
    "$50 -> $1,000": Ladder(lo_usd=50.0, hi_usd=1_000.0),
    "$500 -> $5,000": Ladder(lo_usd=500.0, hi_usd=5_000.0),
}
STRATEGY = "first-10k"
DAYS = 365
OUT = "experiments/ff_timeline.json"


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    cfg = DEFAULT
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start = now - DAYS * 86_400

    print(f"  fetching {DAYS}d of history for {TARGET[:10]}...")
    rows = wallet_trade_history(f, TARGET, start, now)
    trades = dedupe(normalise_many(rows))
    print(f"    {len(trades)} prints, "
          f"${sum(t.notional for t in trades):,.0f} notional")

    print("  building the operator cluster...")
    try:
        rep = fetch_and_build(f, [TARGET])
        cluster = sorted(set(rep.siblings(TARGET)) | {TARGET})
    except Exception as e:
        print(f"    cluster lookup failed ({e}); using the target alone")
        cluster = [TARGET]
    print(f"    {len(cluster)} wallet(s) in the cluster")

    by_market: dict[str, list] = {}
    for t in trades:
        by_market.setdefault(t.condition_id, []).append(t)
    # Rank by the cluster's own notional: taking markets in insertion order
    # biases to whatever the fetch happened to page first.
    ranked = sorted(by_market, key=lambda c: -sum(x.notional for x in by_market[c]))
    print(f"  {len(ranked)} markets touched; fetching tapes...")

    build = STRATEGIES[STRATEGY]
    clusterset = frozenset(w.lower() for w in cluster)
    positions = {k: [] for k in LADDERS}
    skipped = {"unresolved": 0, "thin": 0, "no_signal": 0, "no_fill": 0,
           "uncovered": 0}

    for i, cid in enumerate(ranked, 1):
        if i % 25 == 0:
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

        # Signals come from the wallet's OWN history, not from the tape.
        # market_tape caps at MARKET_TAPE_CAP and returns newest-first, so
        # on a busy market the tape holds only recent prints -- building
        # signals from it would mistake their fifth trade for their first.
        sigs = build(by_market[cid])
        if not sigs:
            skipped["no_signal"] += 1; continue

        for sig in sigs:
            if sig.ts < start:
                continue
            # A truncated tape that begins after the signal cannot say what
            # liquidity followed it. evaluate() calls these unusable rather
            # than scoring them on the wrong window; so does this.
            if mt.truncated and sig.ts < tape.start:
                skipped["uncovered"] += 1
                continue
            d = sig.direction
            unit = sig.entry_ref if d > 0 else 1.0 - sig.entry_ref
            if unit <= 0:
                continue
            payoff = terminal if d > 0 else 1.0 - terminal
            for name, lad in LADDERS.items():
                want = lad.usd(sig.notional) / unit
                fill = tape.simulate_fill(sig.ts, sig.entry_ref, d, want,
                                          cfg.follow.cap, cfg.follow.window_s,
                                          clusterset)
                if fill.shares <= 0:
                    if name == "$50 -> $1,000":
                        skipped["no_fill"] += 1
                    continue
                positions[name].append({
                    "cid": cid, "in_play": bool(res.in_play),
                    "entry_ts": sig.ts,
                    "exit_ts": max(exit_ts, sig.ts + 1),
                    "capital": round(fill.notional, 2),
                    "pnl": round(fill.shares * (payoff - fill.vwap), 2),
                    "target_notional": round(sig.notional, 2),
                })

    out = {"target": TARGET, "cluster": cluster, "strategy": STRATEGY,
           "days": DAYS, "skipped": skipped, "positions": positions}
    json.dump(out, open(OUT, "w"), indent=1)

    print(f"\n  skipped: {skipped}")
    for name, ps in positions.items():
        if not ps:
            print(f"  {name}: no filled positions"); continue
        cap = sum(p["capital"] for p in ps)
        pnl = sum(p["pnl"] for p in ps)
        peak = _peak_deployed(ps)
        hold = sum(p["exit_ts"] - p["entry_ts"] for p in ps) / len(ps) / 86_400
        print(f"\n  {name}")
        print(f"    {len(ps)} positions, cumulative deployed ${cap:,.0f}, "
              f"PnL ${pnl:,.0f} ({pnl/cap:+.1%})")
        print(f"    peak concurrent exposure ${peak:,.0f}")
        print(f"    mean hold {hold:.1f} days, "
          f"median {_median_hold(ps):.1f} days")
    print(f"\n  -> {OUT}")


def _median_hold(ps) -> float:
    h = sorted((p["exit_ts"] - p["entry_ts"]) / 86_400 for p in ps)
    return h[len(h) // 2] if h else 0.0


def _peak_deployed(ps) -> float:
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
