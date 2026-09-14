"""Cluster-level PnL per market: the four wallets treated as one book.

Different from the per-account view. Here a market where FootballFan98
loses and the unnamed wallet wins nets to a single figure, which is what
"follow the cluster" actually means -- you would have copied the combined
position, not four separate ones.

Mark-to-terminal per print, summed across all four wallets:
``pnl = ref_signed * (terminal - ref_price)``. 365-day window, matching the
follow simulation.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.model import dedupe, normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import market_resolution, wallet_trade_history
from polybuyer.targets import FOOTBALLFAN_CLUSTER

DAYS = 365
TOP = 15


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start = now - DAYS * 86_400

    trades = []
    for m in FOOTBALLFAN_CLUSTER:
        trades.extend(normalise_many(wallet_trade_history(f, m.address, start, now)))
    trades = dedupe(trades)
    print(f"  {len(trades):,} prints across the cluster")

    cids = sorted({t.condition_id for t in trades})
    terminal, title = {}, {}
    for i, cid in enumerate(cids, 1):
        if i % 300 == 0:
            print(f"    resolving {i}/{len(cids)}", flush=True)
        pay = market_resolution(f, cid)
        if not pay:
            continue
        r = resolution_from_clob(cid, pay)
        if r.is_terminal and r.ref_terminal is not None:
            terminal[cid] = r.ref_terminal
            title[cid] = str(pay.get("question") or cid[:24])

    pnl, vol, wallets = defaultdict(float), defaultdict(float), defaultdict(set)
    for t in trades:
        if t.condition_id not in terminal:
            continue
        pnl[t.condition_id] += t.ref_signed * (terminal[t.condition_id] - t.ref_price)
        vol[t.condition_id] += t.notional
        wallets[t.condition_id].add(t.wallet)

    rows = sorted(pnl.items(), key=lambda kv: -kv[1])
    total = sum(pnl.values())
    wins = [v for _, v in rows if v > 0]
    losses = [v for _, v in rows if v < 0]

    print(f"\n  {len(rows)} settled markets, ${sum(vol.values()):,.0f} traded")
    print(f"  cluster PnL {total:+,.0f}")
    print(f"  {len(wins)} winners (+{sum(wins):,.0f}), "
          f"{len(losses)} losers ({sum(losses):,.0f}), "
          f"hit rate {len(wins)/len(rows):.0%}")

    print(f"\n  TOP {TOP} WINS")
    print(f"  {'PnL':>12}{'volume':>13}{'w':>3}  market")
    for c, v in rows[:TOP]:
        print(f"  {v:>+12,.0f}{vol[c]:>13,.0f}{len(wallets[c]):>3}  {title[c][:52]}")

    print(f"\n  TOP {TOP} LOSSES")
    print(f"  {'PnL':>12}{'volume':>13}{'w':>3}  market")
    for c, v in rows[-TOP:][::-1]:
        print(f"  {v:>+12,.0f}{vol[c]:>13,.0f}{len(wallets[c]):>3}  {title[c][:52]}")

    t5 = sum(v for _, v in rows[:5])
    b5 = sum(v for _, v in rows[-5:])
    print(f"\n  top 5 = {t5:+,.0f} ({t5/total:+.0%} of net)   "
          f"bottom 5 = {b5:+,.0f} ({b5/total:+.0%})   "
          f"net of tails {t5+b5:+,.0f} ({(t5+b5)/total:+.0%})")

    json.dump({"total_pnl": total, "markets": len(rows),
               "volume": sum(vol.values()),
               "winners": len(wins), "losers": len(losses),
               "rows": [{"cid": c, "q": title[c], "pnl": v, "volume": vol[c],
                         "wallets": len(wallets[c])} for c, v in rows]},
              open("experiments/ff_cluster_markets.json", "w"), indent=1)
    print("\n  -> experiments/ff_cluster_markets.json")


if __name__ == "__main__":
    main()
