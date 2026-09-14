"""Per-account PnL for the cluster, and each account's best and worst markets.

Mark-to-terminal, the project's standard: ``pnl = ref_signed * (terminal -
ref_price)`` summed over a wallet's prints in a market. That sidesteps
SPLIT/MERGE accounting entirely -- it prices every share acquired against
where the market actually settled, regardless of how the position was
assembled or unwound.

Covers the same 365-day window as the follow simulation, so the totals are
**not** the lifetime figures Polymarket displays. They are a cross-check on
those: the signs and the relative magnitudes should agree, and if they do
not, the addresses are wrong.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.model import dedupe, normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import market_resolution, market_tape, wallet_trade_history
from polybuyer.targets import FOOTBALLFAN_CLUSTER

DAYS = 365
TOP = 5


def main() -> None:
    import datetime as dt
    f = Fetcher(cache_dir=".polycache")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start = now - DAYS * 86_400

    by_wallet = {}
    for m in FOOTBALLFAN_CLUSTER:
        t = normalise_many(wallet_trade_history(f, m.address, start, now))
        by_wallet[m.handle] = dedupe(t)
        print(f"  {m.handle:<15} {len(by_wallet[m.handle]):>6} prints", flush=True)

    cids = sorted({t.condition_id for ts in by_wallet.values() for t in ts})
    print(f"\n  resolving {len(cids)} markets...")
    terminal, title = {}, {}
    for i, cid in enumerate(cids, 1):
        if i % 200 == 0:
            print(f"    {i}/{len(cids)}", flush=True)
        pay = market_resolution(f, cid)
        if not pay:
            continue
        r = resolution_from_clob(cid, pay)
        if r.is_terminal and r.ref_terminal is not None:
            terminal[cid] = r.ref_terminal
            title[cid] = str(pay.get("question") or cid[:24])

    out = {}
    for handle, trades in by_wallet.items():
        per = defaultdict(float)
        vol = defaultdict(float)
        for t in trades:
            if t.condition_id not in terminal:
                continue
            per[t.condition_id] += t.ref_signed * (terminal[t.condition_id] - t.ref_price)
            vol[t.condition_id] += t.notional
        ranked = sorted(per.items(), key=lambda kv: -kv[1])
        out[handle] = {
            "markets_scored": len(per),
            "total_pnl_365d": sum(per.values()),
            "volume_365d": sum(vol.values()),
            "wins": [{"cid": c, "q": title.get(c, ""), "pnl": v,
                      "volume": vol[c]} for c, v in ranked[:TOP]],
            "losses": [{"cid": c, "q": title.get(c, ""), "pnl": v,
                        "volume": vol[c]} for c, v in ranked[-TOP:][::-1]],
        }

    json.dump(out, open("experiments/ff_account_pnl.json", "w"), indent=1)

    print(f"\n{'='*78}")
    print(f"  {'account':<15}{'markets':>9}{'volume 365d':>16}{'PnL 365d':>15}"
          f"{'stated lifetime':>17}")
    for m in FOOTBALLFAN_CLUSTER:
        o = out[m.handle]
        print(f"  {m.handle:<15}{o['markets_scored']:>9}"
              f"{o['volume_365d']:>16,.0f}{o['total_pnl_365d']:>+15,.0f}"
              f"{m.pnl_usd:>+17,.0f}")
    tot = sum(o["total_pnl_365d"] for o in out.values())
    print(f"  {'CLUSTER':<15}{'':>9}"
          f"{sum(o['volume_365d'] for o in out.values()):>16,.0f}{tot:>+15,.0f}"
          f"{sum(m.pnl_usd for m in FOOTBALLFAN_CLUSTER):>+17,.0f}")

    for m in FOOTBALLFAN_CLUSTER:
        o = out[m.handle]
        print(f"\n  {m.handle} — top {TOP} wins")
        for w in o["wins"]:
            print(f"    {w['pnl']:>+12,.0f}  on {w['volume']:>11,.0f}  {w['q'][:46]}")
        print(f"  {m.handle} — top {TOP} losses")
        for w in o["losses"]:
            print(f"    {w['pnl']:>+12,.0f}  on {w['volume']:>11,.0f}  {w['q'][:46]}")
    print(f"\n  -> experiments/ff_account_pnl.json")


if __name__ == "__main__":
    main()
