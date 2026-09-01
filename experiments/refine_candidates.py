"""Stage 1b: the resolving jump, the head fakes, and whether the guards help.

Two corrections to `candidates50.py`, both material.

**Jump selection.** It picked "the last jump ending on the winning side",
which lets through a move that went the *wrong way* and merely stayed
below 0.5 in a market resolving NO. Six of thirty-five candidates had
negative PnL for that reason. The resolving jump is the one whose
*direction* agrees with the payoff.

**Head fakes.** Those six are not noise to be filtered away -- they are the
thing the strategy actually risks. A live desk fires on news as it lands,
without knowing which repricing holds. So this measures both:

    resolving jumps   the upper bound: every trade we would want
    head fakes        moves that passed the same liquidity and guard tests
                      and went the other way

The bracket between them is the honest range, and neither number alone
means anything.

**The guards.** Only five markets were blocked by the don't-chase
thresholds in the first pass, which is a suspiciously light touch for a
filter meant to keep us out of trades that have already run. This sweeps
them to see what tightening costs and buys, on both populations.
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
from polybuyer.sources import market_tape
from polybuyer.tape import Tape
from polybuyer.newsdesk.guards import WINDOWS, evaluate

CFG = JumpConfig(min_market_trades=60)
TEST_CAP = 0.05
TEST_WINDOW_S = 1800
MIN_FILLABLE_USD = 200.0

#: Guard settings to sweep: (5m, 1h, 2h, 1d). The first is what ships.
GUARD_SETS = {
    "shipped (.20/.20/.20/.30)": (0.20, 0.20, 0.20, 0.30),
    "tight   (.10/.10/.15/.20)": (0.10, 0.10, 0.15, 0.20),
    "tighter (.05/.08/.10/.15)": (0.05, 0.08, 0.10, 0.15),
    "off": (9.9, 9.9, 9.9, 9.9),
}


def _iso(ts): return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def guard_moves(tape, ts, entry, direction):
    hist = {lab: tape.median_price(ts - s - 900, ts - s) for lab, s in WINDOWS}
    return evaluate(entry, hist, direction, {"5m": 9.9, "1h": 9.9,
                                             "2h": 9.9, "1d": 9.9}).moves


def blocked_by(moves, thr):
    keys = ("5m", "1h", "2h", "1d")
    return any(moves.get(k) is not None and moves[k] > t
               for k, t in zip(keys, thr))


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    cands = json.load(open("experiments/candidates50.json"))
    trades = []

    for m in cands:
        trs = normalise_many(market_tape(f, m["cid"]).trades)
        tape = Tape(m["cid"], trs)
        terminal = m["terminal"]
        for j in detect(tape, CFG, terminal=terminal):
            direction = j.direction
            payoff = terminal if direction > 0 else 1.0 - terminal
            fill = tape.simulate_fill(j.onset_ts, j.before, direction,
                                      want_shares=1e9, cap=TEST_CAP,
                                      window_s=TEST_WINDOW_S)
            fillable = fill.shares * fill.vwap
            if fillable < MIN_FILLABLE_USD:
                continue
            wins = (direction > 0) == (terminal >= 0.5)
            trades.append({
                "cid": m["cid"], "q": m["q"], "vol": m["vol"],
                "onset": _iso(j.onset_ts), "onset_ts": j.onset_ts,
                "before": round(j.before, 4), "after": round(j.after, 4),
                "direction": direction, "terminal": terminal,
                "kind": "resolving" if wins else "head fake",
                "fillable_usd": round(fillable, 2), "vwap": round(fill.vwap, 4),
                "pnl_usd": round(fill.shares * (payoff - fill.vwap), 2),
                "moves": {k: (round(v, 4) if v is not None else None)
                          for k, v in guard_moves(tape, j.onset_ts,
                                                  j.before, direction).items()},
            })

    res = [t for t in trades if t["kind"] == "resolving"]
    fake = [t for t in trades if t["kind"] == "head fake"]
    print(f"  {len(cands)} markets -> {len(trades)} fillable repricings")
    print(f"    {len(res)} resolving, {len(fake)} head fakes")

    print(f"\n  guard sweep (a fire is allowed only if no window is breached)")
    print(f"  {'setting':<28} {'res kept':>9} {'res PnL':>11} "
          f"{'fake kept':>10} {'fake PnL':>11} {'net':>11}")
    rows = []
    for name, thr in GUARD_SETS.items():
        rk = [t for t in res if not blocked_by(t["moves"], thr)]
        fk = [t for t in fake if not blocked_by(t["moves"], thr)]
        rp = sum(t["pnl_usd"] for t in rk)
        fp = sum(t["pnl_usd"] for t in fk)
        rows.append({"setting": name, "thresholds": thr,
                     "resolving_kept": len(rk), "resolving_pnl": round(rp, 2),
                     "fake_kept": len(fk), "fake_pnl": round(fp, 2),
                     "net_pnl": round(rp + fp, 2)})
        print(f"  {name:<28} {len(rk):>5}/{len(res):<3} ${rp:>10,.0f} "
              f"{len(fk):>4}/{len(fake):<3} ${fp:>10,.0f} ${rp+fp:>10,.0f}")

    json.dump({"trades": trades, "guard_sweep": rows},
              open("experiments/refined.json", "w"), indent=1)
    print(f"\n  -> experiments/refined.json")

    top = sorted(res, key=lambda t: -t["pnl_usd"])[:12]
    print(f"\n  largest resolving repricings (the X-search shortlist):")
    for t in top:
        print(f"    ${t['pnl_usd']:>9,.0f}  {t['before']:.2f}->{t['after']:.2f}"
              f"  fill ${t['fillable_usd']:>8,.0f}  {t['onset'][:16]}  "
              f"{t['q'][:44]}")


if __name__ == "__main__":
    main()
