"""TEST PHASE -- run once, no tuning.

Executes the strategy frozen in STRATEGY.md against the test half. Every
parameter comes from that file or from PREREGISTRATION.md; nothing is chosen
here.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from categorise import categorise
from split import load

from polybuyer.config import DEFAULT
from polybuyer.jumps import detect
from polybuyer.model import dedupe, normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import market_resolutions, market_tape
from polybuyer.stats import bootstrap_ratio
from polybuyer.tape import Tape

TARGETS = ("geopolitics", "politics", "corporate")   # frozen in STRATEGY.md
LATENCIES = [(0, "oracle"), (2, "powerstream"), (15, "good API"),
             (45, "NO powerstream"), (120, "slow poll"), (300, "human")]
ACCURACIES = [1.00, 0.90, 0.80, 0.70]
STAKE = 500.0
CAP = 0.02
WINDOW_S = 600
SEED = 20260901


def run_signals(tapes, res, meta, persistent: bool):
    """Collect (cid, onset, direction) for every signal the bot would fire on."""
    sigs = []
    for cid, tape in tapes.items():
        r = res.get(cid)
        if r is None or not r.is_terminal:
            continue
        for j in detect(tape, DEFAULT.jump,
                        terminal=r.ref_terminal,
                        require_persistence=persistent):
            sigs.append((cid, j.onset_ts, j.direction))
    return sigs


def simulate(sigs, tapes, res, latency: int, accuracy: float):
    """Enter at onset+latency; return per-market (pnl, capital)."""
    rng = random.Random(SEED)
    by_market: dict[str, list[float]] = {}
    filled = 0
    fills: list[float] = []

    for cid, onset, direction in sigs:
        tape = tapes[cid]
        r = res[cid]
        t0 = onset + latency
        px = tape.price_at(t0)
        if px is None:
            continue
        # The bot reads the story wrong some of the time.
        d = direction if rng.random() < accuracy else -direction
        unit = px if d > 0 else 1.0 - px
        if not (0.0 < unit < 1.0):
            continue
        want = STAKE / unit
        fill = tape.simulate_fill(t0, px, d, want, CAP, WINDOW_S)
        fills.append(fill.fill_frac)
        if fill.shares <= 0:
            by_market.setdefault(cid, [0.0, 0.0])
            continue
        filled += 1
        payoff = r.ref_terminal if d > 0 else 1.0 - r.ref_terminal
        pnl = fill.shares * (payoff - fill.vwap)
        cap = fill.notional
        m = by_market.setdefault(cid, [0.0, 0.0])
        m[0] += pnl
        m[1] += cap

    return by_market, filled, (sum(fills) / len(fills) if fills else 0.0)


def main() -> None:
    s = load()
    test = [m for m in s["test"]
            if categorise(m["question"], m["slug"]) in TARGETS]
    assert all(m["endDate"] >= s["boundary"] for m in test), "split violated"
    print(f"TEST half: {len(s['test'])} markets, "
          f"{len(test)} in target categories {TARGETS}", file=sys.stderr)

    f = Fetcher(cache_dir=".polycache")
    meta = {m["conditionId"]: m for m in test}
    cids = list(meta)
    raw, trunc = [], set()
    for i, cid in enumerate(cids, 1):
        t = market_tape(f, cid)
        raw.extend(t.trades)
        if t.truncated:
            trunc.add(cid)
        if i % 50 == 0:
            print(f"  {i}/{len(cids)}, {len(raw)} prints", file=sys.stderr)

    payloads = market_resolutions(f, cids, workers=12)
    res = {c: resolution_from_clob(c, p) for c, p in payloads.items()}
    trades = dedupe(normalise_many(raw))
    grouped: dict[str, list] = {}
    for t in trades:
        grouped.setdefault(t.condition_id, []).append(t)
    tapes = {c: Tape(c, ts) for c, ts in grouped.items()}

    print(f"\n{len(tapes)} tapes, {len(trunc)} truncated\n")

    for persistent, label in ((True, "persistent (news that was real)"),
                              (False, "all alarms (incl. moves that reverted)")):
        sigs = run_signals(tapes, res, meta, persistent)
        print("=" * 78)
        print(f"SIGNAL SET: {label} -- {len(sigs)} signals")
        print("=" * 78)
        print(f"{'latency':<16}{'acc':>6}{'filled':>8}{'fill%':>7}"
              f"{'capital':>11}{'PnL':>10}{'ROI':>9}{'p':>8}")
        for lat, name in LATENCIES:
            for acc in ACCURACIES:
                bm, filled, mf = simulate(sigs, tapes, res, lat, acc)
                if not bm:
                    continue
                cids_ = list(bm)
                ci = bootstrap_ratio([bm[c][0] for c in cids_],
                                     [bm[c][1] for c in cids_], DEFAULT.stats)
                cap = sum(bm[c][1] for c in cids_)
                pnl = sum(bm[c][0] for c in cids_)
                tag = f"{name} {lat}s"
                print(f"{tag:<16}{acc:>6.0%}{filled:>8}{mf:>7.0%}"
                      f"{cap:>11,.0f}{pnl:>10,.0f}{ci.point:>9.1%}"
                      f"{ci.p_le_zero:>8.3f}")
            print()


if __name__ == "__main__":
    main()
