"""TRAINING PHASE -- train half only.

Characterises news repricings so the strategy can be written. Nothing here
touches the test half; the split file is the boundary and it is enforced by
only ever indexing split['train'].
"""

from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from categorise import categorise
from split import load

from polybuyer.config import DEFAULT
from polybuyer.jumps import detect
from polybuyer.model import dedupe, normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import market_resolutions, market_tape
from polybuyer.tape import Tape


def main() -> None:
    s = load()
    train = s["train"]
    assert all(m["endDate"] <= s["boundary"] for m in train), "split violated"
    print(f"TRAIN ONLY: {len(train)} markets to {s['boundary'][:10]}", file=sys.stderr)

    f = Fetcher(cache_dir=".polycache")
    meta = {m["conditionId"]: m for m in train}
    cids = list(meta)

    raw: list[dict] = []
    trunc: set[str] = set()
    for i, cid in enumerate(cids, 1):
        t = market_tape(f, cid)
        raw.extend(t.trades)
        if t.truncated:
            trunc.add(cid)
        if i % 50 == 0:
            print(f"  {i}/{len(cids)} markets, {len(raw)} prints", file=sys.stderr)

    payloads = market_resolutions(f, cids, workers=12)
    res = {c: resolution_from_clob(c, p) for c, p in payloads.items()}
    trades = dedupe(normalise_many(raw))
    by_market: dict[str, list] = {}
    for t in trades:
        by_market.setdefault(t.condition_id, []).append(t)

    rows = []
    for cid, ts in by_market.items():
        r = res.get(cid)
        tape = Tape(cid, ts)
        jumps = detect(tape, DEFAULT.jump,
                       terminal=(r.ref_terminal if r else None))
        cat = categorise(meta[cid]["question"], meta[cid]["slug"])
        for j in jumps:
            # The quantity that decides viability: how long the price stays
            # gettable after the move starts.
            win = tape.follow_window(j.onset_ts, j.before, j.direction, 0.02)
            rows.append({
                "cid": cid, "cat": cat, "mag": j.magnitude,
                "window": win, "vol": meta[cid]["volume"],
                "q": meta[cid]["question"],
            })

    print(f"\n{len(rows)} repricings across {len(by_market)} markets "
          f"({len(trunc)} tapes truncated)\n")

    agg = collections.defaultdict(list)
    for r in rows:
        agg[r["cat"]].append(r)

    def med(xs):
        xs = sorted(x for x in xs if x != float("inf"))
        return xs[len(xs) // 2] if xs else float("inf")

    print(f"{'category':<14}{'mkts':>6}{'jumps':>7}{'jumps/mkt':>11}"
          f"{'med move':>10}{'med window':>12}{'<45s':>7}{'<2s':>6}")
    print("-" * 74)
    for cat, rs in sorted(agg.items(), key=lambda kv: -len(kv[1])):
        wins = [r["window"] for r in rs]
        nm = len({r["cid"] for r in rs})
        fast45 = sum(1 for w in wins if w < 45) / len(wins)
        fast2 = sum(1 for w in wins if w < 2) / len(wins)
        m = med(wins)
        ms = "inf" if m == float("inf") else (f"{m:.0f}s" if m < 90 else f"{m/60:.0f}m")
        print(f"{cat:<14}{nm:>6}{len(rs):>7}{len(rs)/max(1,nm):>11.2f}"
              f"{med([r['mag'] for r in rs]):>10.0%}{ms:>12}{fast45:>7.0%}{fast2:>6.0%}")

    print("\nlargest repricings in TRAIN, by move size:")
    for r in sorted(rows, key=lambda r: -r["mag"])[:14]:
        w = r["window"]
        ws = "inf" if w == float("inf") else (f"{w:.0f}s" if w < 90 else f"{w/60:.0f}m")
        print(f"  {r['mag']:>4.0%} move  window {ws:>6}  [{r['cat']:<12}] {r['q'][:52]}")


if __name__ == "__main__":
    main()
